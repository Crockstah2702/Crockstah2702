"""
Ethereum Trade Executor via 1inch API v5.
Holt ein Quote und führt den Swap über den 1inch-Router aus.
"""

import logging
import aiohttp
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware  # type: ignore
from eth_account import Account

from config import cfg
from filters import TradeInfo, apply_max_trade_filter

log = logging.getLogger("executor_eth")

ONEINCH_BASE = "https://api.1inch.dev/swap/v6.0/1"  # Chain ID 1 = Ethereum
ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


class EthExecutor:
    def __init__(self):
        from key_utils import get_eth_account
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(cfg.ETH_RPC_URL))
        self.account = get_eth_account()
        log.info(f"ETH-Wallet: {self.account.address}")

    async def execute(self, trade: TradeInfo):
        capped_amount = apply_max_trade_filter(trade)

        log.info(
            f"[ETH] Kopiere Trade: {trade.input_mint[:10]}… → {trade.output_mint[:10]}… "
            f"| {capped_amount / 1e18:.6f} ETH | DEX: {trade.dex}"
        )

        if cfg.DRY_RUN:
            log.info("[ETH] DRY_RUN aktiv — Trade wird NICHT ausgeführt.")
            return

        swap_data = await self._get_swap(trade.input_mint, trade.output_mint, capped_amount)
        if not swap_data:
            log.error("[ETH] Kein Swap-Data erhalten, Trade abgebrochen.")
            return

        tx_hash = await self._send_tx(swap_data, capped_amount, trade.input_mint)
        if tx_hash:
            log.info(f"[ETH] Trade ausgeführt: https://etherscan.io/tx/{tx_hash}")
        else:
            log.error("[ETH] Trade fehlgeschlagen.")

    async def _get_swap(self, src: str, dst: str, amount: int) -> dict | None:
        params = {
            "src": src,
            "dst": dst,
            "amount": str(amount),
            "from": self.account.address,
            "slippage": cfg.SLIPPAGE_BPS / 100,  # 1inch erwartet Prozent
            "disableEstimate": "false",
            "allowPartialFill": "false",
        }
        headers = {"Authorization": f"Bearer {cfg.ETH_RPC_URL}"}  # 1inch braucht API-Key
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ONEINCH_BASE}/swap", params=params) as resp:
                if resp.status != 200:
                    log.error(f"[ETH] 1inch Fehler {resp.status}: {await resp.text()}")
                    return None
                return await resp.json()

    async def _send_tx(self, swap_data: dict, amount: int, src_token: str) -> str | None:
        tx = swap_data.get("tx", {})
        is_eth = src_token.lower() == ETH_ADDRESS.lower()

        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        gas_price = await self.w3.eth.gas_price

        raw_tx = {
            "from": self.account.address,
            "to": self.w3.to_checksum_address(tx["to"]),
            "data": tx["data"],
            "value": amount if is_eth else 0,
            "gas": int(tx.get("gas", 300_000)),
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": 1,
        }

        signed = self.account.sign_transaction(raw_tx)
        result = await self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return result.hex() if result else None
