"""
Solana Wallet Monitor.
Dual-Mode: WebSocket (Echtzeit) + direktes On-Chain-Polling (Backup).
Erkennt Jupiter- und Raydium-Swaps.
"""

import asyncio
import json
import logging
import aiohttp
import websockets

from config import cfg
from filters import TradeInfo

log = logging.getLogger("monitor_sol")

JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
RAYDIUM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SOL_MINT = "So11111111111111111111111111111111111111112"

POLL_INTERVAL = 10  # Sekunden für On-Chain-Backup-Polling


class SolanaMonitor:
    def __init__(self, on_trade):
        self.on_trade = on_trade
        self._seen: set[str] = set()

    async def run(self):
        log.info(f"[SOL] Überwache Wallet direkt auf der Blockchain: {cfg.TARGET_WALLET_SOL}")
        # Starte WebSocket + Polling-Backup parallel
        await asyncio.gather(
            self._run_websocket(),
            self._run_onchain_polling(),
        )

    # ─── WebSocket (Echtzeit) ──────────────────────────────────

    async def _run_websocket(self):
        while True:
            try:
                await self._connect_ws()
            except Exception as e:
                log.error(f"[SOL] WebSocket-Fehler: {e} — Neuverbindung in 5s")
                await asyncio.sleep(5)

    async def _connect_ws(self):
        async with websockets.connect(cfg.SOLANA_WS_URL) as ws:
            sub = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [cfg.TARGET_WALLET_SOL]},
                    {"commitment": "confirmed"},
                ],
            }
            await ws.send(json.dumps(sub))
            log.info("[SOL] WebSocket verbunden ✓")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._handle_ws_message(msg)
                except Exception as e:
                    log.debug(f"[SOL] Parse-Fehler: {e}")

    async def _handle_ws_message(self, msg: dict):
        if msg.get("method") != "logsNotification":
            return
        result = msg.get("params", {}).get("result", {})
        value = result.get("value", {})
        sig = value.get("signature", "")
        if value.get("err") or not sig:
            return

        logs = value.get("logs", [])
        dex = self._detect_dex(logs)
        if dex:
            await self._process_signature(sig, dex)

    # ─── On-Chain Polling (direkte Blockchain-Prüfung) ──────────

    async def _run_onchain_polling(self):
        """
        Pollt getSignaturesForAddress direkt an der Blockchain —
        damit werden auch Transaktionen gefunden die der WebSocket verpasst.
        """
        last_sig: str | None = None
        await asyncio.sleep(5)  # WebSocket zuerst starten lassen

        while True:
            try:
                sigs = await self._fetch_recent_signatures(last_sig)
                if sigs:
                    last_sig = sigs[0]  # neueste Signatur merken
                    for sig in reversed(sigs):  # älteste zuerst verarbeiten
                        await self._process_signature_from_chain(sig)
            except Exception as e:
                log.debug(f"[SOL] Polling-Fehler: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_recent_signatures(self, before: str | None) -> list[str]:
        """Holt die neuesten Transaktionssignaturen der Ziel-Wallet direkt von der Blockchain."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                cfg.TARGET_WALLET_SOL,
                {
                    "limit": 20,
                    "commitment": "confirmed",
                },
            ],
        }
        if before:
            payload["params"][1]["until"] = before

        async with aiohttp.ClientSession() as session:
            async with session.post(cfg.SOLANA_RPC_URL, json=payload) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = data.get("result", [])
        # Nur erfolgreiche Transaktionen
        return [r["signature"] for r in results if not r.get("err")]

    async def _process_signature_from_chain(self, sig: str):
        """Prüft direkt on-chain ob eine Transaktion ein Swap war."""
        if sig in self._seen:
            return
        tx = await self._fetch_tx(sig)
        if not tx:
            return
        # Prüfe ob es ein DEX-Swap ist
        logs = tx.get("meta", {}).get("logMessages", [])
        dex = self._detect_dex(logs)
        if dex:
            await self._process_signature(sig, dex, tx=tx)

    # ─── Gemeinsame Verarbeitung ───────────────────────────────

    async def _process_signature(self, sig: str, dex: str, tx: dict | None = None):
        if sig in self._seen:
            return
        self._seen.add(sig)

        log.info(f"[SOL] {dex}-Swap on-chain bestätigt: {sig[:16]}…")

        if tx is None:
            tx = await self._fetch_tx(sig)
        if not tx:
            return

        trade = self._parse_swap(tx, sig, dex)
        if trade:
            await self.on_trade(trade)

    def _detect_dex(self, logs: list[str]) -> str | None:
        combined = " ".join(logs)
        if JUPITER_V6 in combined:
            return "Jupiter"
        if RAYDIUM_V4 in combined:
            return "Raydium"
        return None

    async def _fetch_tx(self, sig: str) -> dict | None:
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
        return data.get("result")

    def _parse_swap(self, tx: dict, sig: str, dex: str) -> TradeInfo | None:
        meta = tx.get("meta", {})
        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])
        my_accounts = self._get_my_token_accounts(tx)

        input_mint = None
        output_mint = None
        in_amount = 0
        out_amount = 0

        pre_map = {b["accountIndex"]: b for b in pre_balances}
        post_map = {b["accountIndex"]: b for b in post_balances}

        for idx in set(pre_map.keys()) | set(post_map.keys()):
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

        # SOL-Balance als Fallback
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
        meta = tx.get("meta", {})
        for b in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
            if b.get("owner") == cfg.TARGET_WALLET_SOL:
                my_indices.add(b["accountIndex"])
        return my_indices
