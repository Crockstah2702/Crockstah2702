"""
Copy-Trading-Bot Orchestrator.
Startet Monitor, Executor, Position-Manager und Telegram für alle Chains.
"""

import asyncio
import logging
import time
import uuid

from config import cfg
from filters import TradeInfo, should_copy, apply_max_trade_filter
from position_manager import Position, PositionManager
from price_fetcher import get_token_price, get_token_symbol
from ai_analyzer import get_dynamic_tp_sl
from telegram_interface import TelegramInterface

log = logging.getLogger("bot")

SOL_LAMPORTS = 1_000_000_000
ETH_WEI = 10**18


class CopyTradingBot:
    def __init__(self):
        self.tg = TelegramInterface()
        self.pm = PositionManager(on_close=self._on_position_close)
        self.tg.pm = self.pm

        self.sol_executor = None
        self.eth_executor = None

    # ─── Trade-Handler ─────────────────────────────────────────

    async def _on_sol_trade(self, trade: TradeInfo):
        if self.tg.is_paused():
            log.info("[BOT] SOL-Trade ignoriert — Bot pausiert.")
            return
        if not should_copy(trade):
            return
        await self._process_trade(trade)

    async def _on_eth_trade(self, trade: TradeInfo):
        if self.tg.is_paused():
            log.info("[BOT] ETH-Trade ignoriert — Bot pausiert.")
            return
        if not should_copy(trade):
            return
        await self._process_trade(trade)

    async def _process_trade(self, trade: TradeInfo):
        # Kaufpreis ermitteln
        entry_price = await get_token_price(trade.chain, trade.output_mint)
        symbol = await get_token_symbol(trade.chain, trade.output_mint)

        # Betrag in USD schätzen
        if trade.chain == "SOL":
            sol_price = await get_token_price("SOL", "So11111111111111111111111111111111111111112") or 150.0
            in_usd = (trade.in_amount / SOL_LAMPORTS) * sol_price
        else:
            eth_price = await get_token_price("ETH", "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE") or 3000.0
            in_usd = (trade.in_amount / ETH_WEI) * eth_price

        # KI: dynamisches TP/SL
        tp_sl = await get_dynamic_tp_sl(
            chain=trade.chain,
            input_mint=trade.input_mint,
            output_mint=trade.output_mint,
            in_amount_usd=in_usd,
            current_price=entry_price,
            dex=trade.dex,
        )
        tp_pct = tp_sl["tp_pct"]
        sl_pct = tp_sl["sl_pct"]
        reasoning = tp_sl["reasoning"]

        # Trade ausführen
        if trade.chain == "SOL" and self.sol_executor:
            await self.sol_executor.execute(trade)
        elif trade.chain == "ETH" and self.eth_executor:
            await self.eth_executor.execute(trade)

        # Telegram-Notification
        await self.tg.notify_new_trade(
            symbol=symbol,
            chain=trade.chain,
            amount_usd=in_usd,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            reasoning=reasoning,
            tx_sig=trade.tx_sig,
        )

        # Position tracken (nur wenn Preis bekannt)
        if entry_price:
            capped = apply_max_trade_filter(trade)
            if trade.chain == "SOL":
                amount_tokens = trade.out_amount / 10**6  # meiste SPL-Token haben 6 Dezimalstellen
            else:
                amount_tokens = trade.out_amount / ETH_WEI

            pos = Position(
                id=str(uuid.uuid4())[:8],
                chain=trade.chain,
                input_mint=trade.input_mint,
                output_mint=trade.output_mint,
                symbol=symbol,
                entry_price=entry_price,
                amount_tokens=amount_tokens,
                amount_usd=in_usd,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                reasoning=reasoning,
            )
            await self.pm.add(pos)

    # ─── Position Close ────────────────────────────────────────

    async def _on_position_close(self, pos: Position, reason: str, price: float):
        pnl_pct = pos.pnl_pct(price)
        pnl_usd = pos.pnl_usd(price)

        # Hier könnte man automatisch verkaufen — aktuell Notification
        await self.tg.notify_close(
            symbol=pos.symbol,
            chain=pos.chain,
            reason=reason,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
        )
        log.info(f"[BOT] Position {pos.symbol} geschlossen via {reason} | P&L: {pnl_pct:+.1f}%")

    # ─── Start ────────────────────────────────────────────────

    async def run(self):
        await self.tg.start()

        tasks = [
            asyncio.create_task(self.pm.run_monitor(), name="position_monitor"),
        ]

        if cfg.ENABLE_SOL:
            cfg.validate_sol()
            from executor_solana import SolanaExecutor
            from monitor_solana import SolanaMonitor
            self.sol_executor = SolanaExecutor()
            sol_monitor = SolanaMonitor(on_trade=self._on_sol_trade)
            tasks.append(asyncio.create_task(sol_monitor.run(), name="sol_monitor"))
            log.info("[BOT] Solana aktiviert")

        if cfg.ENABLE_ETH:
            cfg.validate_eth()
            from executor_eth import EthExecutor
            from monitor_eth import EthMonitor
            self.eth_executor = EthExecutor()
            eth_monitor = EthMonitor(on_trade=self._on_eth_trade)
            tasks.append(asyncio.create_task(eth_monitor.run(), name="eth_monitor"))
            log.info("[BOT] Ethereum aktiviert")

        if cfg.DRY_RUN:
            log.warning("[BOT] *** DRY_RUN=true *** Kein echter Handel — nur Simulation!")

        await asyncio.gather(*tasks)

        if self.sol_executor:
            await self.sol_executor.close()
        await self.tg.stop()
