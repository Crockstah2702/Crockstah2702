"""
Solana Trade Executor via Jupiter API v6.
Holt ein Quote, baut die Swap-Transaktion und schickt sie ab.
"""

import base64
import logging
import aiohttp
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore
from solana.rpc.async_api import AsyncClient  # type: ignore
from solana.rpc.types import TxOpts  # type: ignore
from solana.rpc.commitment import Confirmed  # type: ignore

from config import cfg
from filters import TradeInfo, apply_max_trade_filter

log = logging.getLogger("executor_sol")

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"

# Native SOL mint-Adresse
SOL_MINT = "So11111111111111111111111111111111111111112"


class SolanaExecutor:
    def __init__(self):
        self.keypair = Keypair.from_base58_string(cfg.SOLANA_PRIVATE_KEY)
        self.client = AsyncClient(cfg.SOLANA_RPC_URL)
        log.info(f"Solana-Wallet: {self.keypair.pubkey()}")

    async def execute(self, trade: TradeInfo):
        capped_amount = apply_max_trade_filter(trade)

        log.info(
            f"[SOL] Kopiere Trade: {trade.input_mint[:8]}… → {trade.output_mint[:8]}… "
            f"| {capped_amount / 1e9:.4f} SOL | DEX: {trade.dex}"
        )

        if cfg.DRY_RUN:
            log.info("[SOL] DRY_RUN aktiv — Trade wird NICHT ausgeführt.")
            return

        quote = await self._get_quote(trade.input_mint, trade.output_mint, capped_amount)
        if not quote:
            log.error("[SOL] Kein Quote erhalten, Trade abgebrochen.")
            return

        tx_sig = await self._swap(quote)
        if tx_sig:
            log.info(f"[SOL] Trade ausgeführt: https://solscan.io/tx/{tx_sig}")
        else:
            log.error("[SOL] Trade fehlgeschlagen.")

    async def _get_quote(self, input_mint: str, output_mint: str, amount: int) -> dict | None:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(cfg.SLIPPAGE_BPS),
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_QUOTE_URL, params=params) as resp:
                if resp.status != 200:
                    log.error(f"[SOL] Quote-Fehler {resp.status}: {await resp.text()}")
                    return None
                return await resp.json()

    async def _swap(self, quote: dict) -> str | None:
        payload = {
            "quoteResponse": quote,
            "userPublicKey": str(self.keypair.pubkey()),
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(JUPITER_SWAP_URL, json=payload) as resp:
                if resp.status != 200:
                    log.error(f"[SOL] Swap-Anfrage-Fehler {resp.status}: {await resp.text()}")
                    return None
                data = await resp.json()

        raw_tx = base64.b64decode(data["swapTransaction"])
        tx = VersionedTransaction.from_bytes(raw_tx)
        signed = self.keypair.sign_message(bytes(tx.message))
        tx.signatures[0] = signed

        result = await self.client.send_raw_transaction(
            bytes(tx),
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
        )
        return str(result.value) if result.value else None

    async def close(self):
        await self.client.close()
