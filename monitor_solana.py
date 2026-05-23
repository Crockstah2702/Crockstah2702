"""
Solana Wallet Monitor.
Überwacht eine Wallet via WebSocket (logsSubscribe) und erkennt Jupiter-Swaps.
"""

import asyncio
import json
import logging
import aiohttp
import websockets

from config import cfg
from filters import TradeInfo

log = logging.getLogger("monitor_sol")

# Bekannte Programm-IDs
JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
RAYDIUM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SOL_MINT = "So11111111111111111111111111111111111111112"


class SolanaMonitor:
    def __init__(self, on_trade):
        self.on_trade = on_trade  # async callback(TradeInfo)
        self._seen: set[str] = set()

    async def run(self):
        log.info(f"[SOL] Starte Monitor für Wallet: {cfg.TARGET_WALLET_SOL}")
        while True:
            try:
                await self._connect()
            except Exception as e:
                log.error(f"[SOL] WebSocket-Fehler: {e} — Neuverbindung in 5s")
                await asyncio.sleep(5)

    async def _connect(self):
        async with websockets.connect(cfg.SOLANA_WS_URL) as ws:
            sub_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [cfg.TARGET_WALLET_SOL]},
                    {"commitment": "confirmed"},
                ],
            }
            await ws.send(json.dumps(sub_msg))
            log.info("[SOL] WebSocket verbunden, warte auf Transaktionen...")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._handle_message(msg)
                except Exception as e:
                    log.debug(f"[SOL] Parse-Fehler: {e}")

    async def _handle_message(self, msg: dict):
        method = msg.get("method")
        if method != "logsNotification":
            return

        result = msg.get("params", {}).get("result", {})
        value = result.get("value", {})
        sig = value.get("signature", "")
        err = value.get("err")

        if err:
            return
        if sig in self._seen:
            return
        self._seen.add(sig)

        logs = value.get("logs", [])
        dex = self._detect_dex(logs)
        if not dex:
            return

        log.info(f"[SOL] {dex}-Transaktion erkannt: {sig[:16]}…")
        trade = await self._fetch_trade_details(sig, dex)
        if trade:
            await self.on_trade(trade)

    def _detect_dex(self, logs: list[str]) -> str | None:
        combined = " ".join(logs)
        if JUPITER_V6 in combined:
            return "Jupiter"
        if RAYDIUM_V4 in combined:
            return "Raydium"
        return None

    async def _fetch_trade_details(self, sig: str, dex: str) -> TradeInfo | None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(cfg.SOLANA_RPC_URL, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        tx = data.get("result")
        if not tx:
            return None

        return self._parse_swap(tx, sig, dex)

    def _parse_swap(self, tx: dict, sig: str, dex: str) -> TradeInfo | None:
        meta = tx.get("meta", {})
        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])

        # Finde welche Token-Accounts zur Ziel-Wallet gehören
        my_accounts = self._get_my_token_accounts(tx)

        input_mint = None
        output_mint = None
        in_amount = 0
        out_amount = 0

        pre_map = {b["accountIndex"]: b for b in pre_balances}
        post_map = {b["accountIndex"]: b for b in post_balances}

        all_indices = set(pre_map.keys()) | set(post_map.keys())
        for idx in all_indices:
            if idx not in my_accounts:
                continue

            pre_ui = int(pre_map.get(idx, {}).get("uiTokenAmount", {}).get("amount", "0") or "0")
            post_ui = int(post_map.get(idx, {}).get("uiTokenAmount", {}).get("amount", "0") or "0")
            diff = post_ui - pre_ui
            mint = (post_map.get(idx) or pre_map.get(idx, {})).get("mint", "")

            if diff < 0 and input_mint is None:
                input_mint = mint
                in_amount = abs(diff)
            elif diff > 0 and output_mint is None:
                output_mint = mint
                out_amount = diff

        # SOL-Balance-Änderung als Fallback für Input/Output
        if not input_mint:
            pre_sol = meta.get("preBalances", [])
            post_sol = meta.get("postBalances", [])
            accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
            for i, acc in enumerate(accounts):
                key = acc if isinstance(acc, str) else acc.get("pubkey", "")
                if key == cfg.TARGET_WALLET_SOL and i < len(pre_sol) and i < len(post_sol):
                    sol_diff = post_sol[i] - pre_sol[i]
                    if sol_diff < 0:
                        input_mint = SOL_MINT
                        in_amount = abs(sol_diff)
                    elif sol_diff > 0 and not output_mint:
                        output_mint = SOL_MINT
                        out_amount = sol_diff

        if not input_mint or not output_mint or in_amount == 0:
            log.debug(f"[SOL] Swap-Details unvollständig für {sig[:16]}…, wird übersprungen")
            return None

        return TradeInfo(
            chain="SOL",
            input_mint=input_mint,
            output_mint=output_mint,
            in_amount=in_amount,
            out_amount=out_amount,
            dex=dex,
            tx_sig=sig,
            raw=tx,
        )

    def _get_my_token_accounts(self, tx: dict) -> set[int]:
        accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        my_indices: set[int] = set()
        for i, acc in enumerate(accounts):
            key = acc if isinstance(acc, str) else acc.get("pubkey", "")
            if key == cfg.TARGET_WALLET_SOL:
                my_indices.add(i)
        # Token-Accounts die der Wallet gehören via preTokenBalances owner-Feld
        meta = tx.get("meta", {})
        for b in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
            if b.get("owner") == cfg.TARGET_WALLET_SOL:
                my_indices.add(b["accountIndex"])
        return my_indices
