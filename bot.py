"""
Copy-Trading-Bot Orchestrator.
Wird vom Web-Terminal gesteuert: start() erzeugt alle Async-Tasks,
stop() bricht sie ab. Live-Daten landen in shared_state.state.
"""

import asyncio
import logging
import uuid

from config import cfg
from filters import TradeInfo, should_copy, apply_max_trade_filter
from position_manager import Position, PositionManager
from price_fetcher import get_token_price, get_token_symbol
from ai_analyzer import get_dynamic_tp_sl
from scanner import Scanner
from shared_state import state

log = logging.getLogger("bot")

SOL_LAMPORTS = 1_000_000_000
ETH_WEI = 10**18
SOL_MINT = "So11111111111111111111111111111111111111112"
ETH_NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


class CopyTradingBot:
    def __init__(self):
        self.pm = PositionManager(on_close=self._on_position_close)
        self.scanner = Scanner(on_update=self._on_scanner_update)
        self.tg = None
        self.sol_executor = None
        self.eth_executor = None
        self._tasks: list[asyncio.Task] = []
        self._running = False

    # ─── Steuerung (vom Web) ───────────────────────────────────

    async def start(self):
        if self._running:
            return
        cfg.reload()
        self._running = True

        state.bot_active = True
        state.paused = False
        state.dry_run = cfg.DRY_RUN
        state.enable_sol = cfg.ENABLE_SOL
        state.enable_eth = cfg.ENABLE_ETH
        state.enable_scanner = cfg.ENABLE_SCANNER

        state.add_log("INFO", "Bot wird gestartet…")
        if cfg.DRY_RUN:
            state.add_log("WARN", "DRY_RUN aktiv — es wird NICHT echt gehandelt.")

        await self._start_telegram()

        self._tasks.append(asyncio.create_task(self.pm.run_monitor(), name="positions"))

        if cfg.ENABLE_SCANNER:
            self._tasks.append(asyncio.create_task(self.scanner.run(), name="scanner"))
            state.add_log("INFO", "Call-Bot / Scanner aktiviert.")

        if cfg.ENABLE_SOL:
            try:
                cfg.validate_sol()
                from executor_solana import SolanaExecutor
                from monitor_solana import SolanaMonitor
                self.sol_executor = SolanaExecutor()
                mon = SolanaMonitor(on_trade=self._on_sol_trade)
                self._tasks.append(asyncio.create_task(mon.run(), name="sol_monitor"))
                state.add_log("INFO", f"Solana-Copy-Trading aktiv → {cfg.TARGET_WALLET_SOL[:8]}…")
            except Exception as e:
                state.add_log("ERROR", f"Solana-Start fehlgeschlagen: {e}")

        if cfg.ENABLE_ETH:
            try:
                cfg.validate_eth()
                from executor_eth import EthExecutor
                from monitor_eth import EthMonitor
                self.eth_executor = EthExecutor()
                mon = EthMonitor(on_trade=self._on_eth_trade)
                self._tasks.append(asyncio.create_task(mon.run(), name="eth_monitor"))
                state.add_log("INFO", f"ETH-Copy-Trading aktiv → {cfg.TARGET_WALLET_ETH[:10]}…")
            except Exception as e:
                state.add_log("ERROR", f"ETH-Start fehlgeschlagen: {e}")

        state.add_log("INFO", "Bot läuft ✓")

    async def stop(self):
        self._running = False
        state.bot_active = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self.sol_executor:
            try:
                await self.sol_executor.close()
            except Exception:
                pass
        if self.tg:
            try:
                await self.tg.stop()
            except Exception:
                pass
        state.add_log("INFO", "Bot gestoppt.")

    def pause(self):
        state.paused = True
        state.add_log("WARN", "Trading pausiert.")

    def resume(self):
        state.paused = False
        state.add_log("INFO", "Trading fortgesetzt.")

    async def _start_telegram(self):
        if not cfg.TELEGRAM_BOT_TOKEN:
            return
        try:
            from telegram_interface import TelegramInterface
            self.tg = TelegramInterface(position_manager=self.pm)
            await self.tg.start()
        except Exception as e:
            log.warning(f"Telegram nicht gestartet: {e}")
            self.tg = None

    # ─── Trade-Handler ─────────────────────────────────────────

    async def _on_sol_trade(self, trade: TradeInfo):
        if state.paused:
            return
        if should_copy(trade):
            await self._process_trade(trade)

    async def _on_eth_trade(self, trade: TradeInfo):
        if state.paused:
            return
        if should_copy(trade):
            await self._process_trade(trade)

    async def _process_trade(self, trade: TradeInfo):
        entry_price = await get_token_price(trade.chain, trade.output_mint)
        symbol = await get_token_symbol(trade.chain, trade.output_mint)

        if trade.chain == "SOL":
            sol_usd = await get_token_price("SOL", SOL_MINT) or 150.0
            in_usd = (trade.in_amount / SOL_LAMPORTS) * sol_usd
        else:
            eth_usd = await get_token_price("ETH", ETH_NATIVE) or 3000.0
            in_usd = (trade.in_amount / ETH_WEI) * eth_usd

        tp_sl = await get_dynamic_tp_sl(
            chain=trade.chain, input_mint=trade.input_mint,
            output_mint=trade.output_mint, in_amount_usd=in_usd,
            current_price=entry_price, dex=trade.dex,
        )
        tp_pct, sl_pct, reasoning = tp_sl["tp_pct"], tp_sl["sl_pct"], tp_sl["reasoning"]

        state.total_trades += 1
        state.add_log("TRADE", f"{symbol} ({trade.chain}) ${in_usd:.0f} | TP +{tp_pct:.0f}% SL -{sl_pct:.0f}%")

        if trade.chain == "SOL" and self.sol_executor:
            await self.sol_executor.execute(trade)
        elif trade.chain == "ETH" and self.eth_executor:
            await self.eth_executor.execute(trade)

        if self.tg:
            await self.tg.notify_new_trade(symbol, trade.chain, in_usd, tp_pct, sl_pct, reasoning, trade.tx_sig)

        if entry_price:
            decimals = 10**6 if trade.chain == "SOL" else ETH_WEI
            pos = Position(
                id=str(uuid.uuid4())[:8], chain=trade.chain,
                input_mint=trade.input_mint, output_mint=trade.output_mint,
                symbol=symbol, entry_price=entry_price,
                amount_tokens=trade.out_amount / decimals, amount_usd=in_usd,
                tp_pct=tp_pct, sl_pct=sl_pct, reasoning=reasoning,
            )
            await self.pm.add(pos)

    async def _on_position_close(self, pos: Position, reason: str, price: float):
        if self.tg:
            await self.tg.notify_close(pos.symbol, pos.chain, reason,
                                       pos.pnl_pct(price), pos.pnl_usd(price))

    async def _on_scanner_update(self, results: dict):
        state.update_scanner(results)
