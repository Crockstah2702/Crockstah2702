"""
Ethereum Wallet Monitor.
Überwacht bestätigte Transaktionen einer Wallet und erkennt DEX-Swaps.
"""

import asyncio
import logging
from web3 import AsyncWeb3
from web3.types import TxData

from config import cfg
from filters import TradeInfo

log = logging.getLogger("monitor_eth")

# Bekannte Router-Adressen (Ethereum Mainnet)
DEX_ROUTERS: dict[str, str] = {
    "0x1111111254EEB25477B68fb85Ed929f73A960582": "1inch v5",
    "0x111111125421cA6dc452d289314280a0f8842A65": "1inch v6",
    "0xE592427A0AEce92De3Edee1F18E0157C05861564": "Uniswap v3",
    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45": "Uniswap v3 (Universal)",
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D": "Uniswap v2",
    "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F": "SushiSwap",
    "0xDef1C0ded9bec7F1a1670819833240f027b25EfF": "0x Exchange",
}

ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

# ERC-20 Transfer event topic
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class EthMonitor:
    def __init__(self, on_trade):
        self.on_trade = on_trade
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(cfg.ETH_RPC_URL))
        self._last_block: int = 0

    async def run(self):
        log.info(f"[ETH] Starte Monitor für Wallet: {cfg.TARGET_WALLET_ETH}")
        self._last_block = await self.w3.eth.block_number
        log.info(f"[ETH] Startblock: {self._last_block}")

        while True:
            try:
                await self._poll()
            except Exception as e:
                log.error(f"[ETH] Poll-Fehler: {e}")
            await asyncio.sleep(3)

    async def _poll(self):
        current = await self.w3.eth.block_number
        if current <= self._last_block:
            return

        for block_num in range(self._last_block + 1, current + 1):
            await self._scan_block(block_num)

        self._last_block = current

    async def _scan_block(self, block_num: int):
        try:
            block = await self.w3.eth.get_block(block_num, full_transactions=True)
        except Exception as e:
            log.debug(f"[ETH] Block {block_num} Fehler: {e}")
            return

        target = cfg.TARGET_WALLET_ETH.lower()
        for tx in block.get("transactions", []):
            if not isinstance(tx, dict):
                continue
            sender = (tx.get("from") or "").lower()
            if sender != target:
                continue
            await self._handle_tx(tx, block_num)

    async def _handle_tx(self, tx: dict, block_num: int):
        to = (tx.get("to") or "").lower()
        router = None
        for addr, name in DEX_ROUTERS.items():
            if to == addr.lower():
                router = name
                break

        if not router:
            return

        sig = tx.get("hash", b"").hex() if isinstance(tx.get("hash"), bytes) else str(tx.get("hash", ""))
        log.info(f"[ETH] {router}-Swap erkannt in Block {block_num}: {sig[:16]}…")

        receipt = await self.w3.eth.get_transaction_receipt(sig)
        trade = self._parse_swap(tx, receipt, sig, router)
        if trade:
            await self.on_trade(trade)

    def _parse_swap(self, tx: dict, receipt, sig: str, dex: str) -> TradeInfo | None:
        target = cfg.TARGET_WALLET_ETH.lower()
        value_wei = int(tx.get("value", 0))

        input_token = ETH_ADDRESS
        output_token = None
        in_amount = value_wei
        out_amount = 0

        if not receipt:
            return None

        logs = receipt.get("logs", [])
        for log_entry in logs:
            topics = log_entry.get("topics", [])
            if not topics:
                continue
            topic0 = topics[0].hex() if isinstance(topics[0], bytes) else str(topics[0])
            if topic0.lower() != TRANSFER_TOPIC.lower():
                continue

            if len(topics) < 3:
                continue

            from_addr = "0x" + (topics[1].hex() if isinstance(topics[1], bytes) else str(topics[1]))[-40:]
            to_addr = "0x" + (topics[2].hex() if isinstance(topics[2], bytes) else str(topics[2]))[-40:]
            data = log_entry.get("data", "0x")
            amount = int(data, 16) if isinstance(data, str) and data != "0x" else 0
            token = (log_entry.get("address") or "").lower()

            if to_addr.lower() == target:
                output_token = log_entry.get("address")
                out_amount = amount
            elif from_addr.lower() == target and value_wei == 0:
                input_token = log_entry.get("address")
                in_amount = amount

        if not output_token or in_amount == 0:
            log.debug(f"[ETH] Swap-Details unvollständig für {sig[:16]}…, wird übersprungen")
            return None

        return TradeInfo(
            chain="ETH",
            input_mint=input_token,
            output_mint=output_token,
            in_amount=in_amount,
            out_amount=out_amount,
            dex=dex,
            tx_sig=sig,
            raw={"tx": tx},
        )
