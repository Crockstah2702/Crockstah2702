"""
Position-Manager.
Verfolgt offene Positionen, überwacht Preise und schließt Trades bei TP/SL.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from price_fetcher import get_token_price, get_token_symbol
from filters import TradeInfo

log = logging.getLogger("positions")

PRICE_CHECK_INTERVAL = 15  # Sekunden


@dataclass
class Position:
    id: str
    chain: str
    input_mint: str
    output_mint: str
    symbol: str
    entry_price: float
    amount_tokens: float
    amount_usd: float
    tp_pct: float
    sl_pct: float
    reasoning: str
    opened_at: float = field(default_factory=time.time)
    closed: bool = False

    @property
    def tp_price(self) -> float:
        return self.entry_price * (1 + self.tp_pct / 100)

    @property
    def sl_price(self) -> float:
        return self.entry_price * (1 - self.sl_pct / 100)

    def pnl_pct(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        return ((current_price - self.entry_price) / self.entry_price) * 100

    def pnl_usd(self, current_price: float) -> float:
        return self.amount_tokens * (current_price - self.entry_price)


class PositionManager:
    def __init__(self, on_close: Callable[[Position, str, float], Awaitable[None]]):
        """on_close(position, reason, current_price) wird aufgerufen wenn TP/SL ausgelöst."""
        self.positions: dict[str, Position] = {}
        self.on_close = on_close
        self._lock = asyncio.Lock()

    async def add(self, position: Position):
        async with self._lock:
            self.positions[position.id] = position
        log.info(
            f"[POS] NEU {position.symbol} ({position.chain}) | "
            f"Entry: ${position.entry_price:.6f} | "
            f"TP: +{position.tp_pct:.0f}% (${position.tp_price:.6f}) | "
            f"SL: -{position.sl_pct:.0f}% (${position.sl_price:.6f})"
        )

    async def get_all(self) -> list[Position]:
        async with self._lock:
            return [p for p in self.positions.values() if not p.closed]

    async def run_monitor(self):
        """Läuft dauerhaft und prüft alle Positionen auf TP/SL."""
        log.info("[POS] Preis-Monitor gestartet")
        while True:
            await self._check_all()
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

    async def _check_all(self):
        async with self._lock:
            open_positions = [p for p in self.positions.values() if not p.closed]

        for pos in open_positions:
            try:
                current_price = await get_token_price(pos.chain, pos.output_mint)
                if not current_price:
                    continue

                pnl = pos.pnl_pct(current_price)
                log.debug(f"[POS] {pos.symbol}: ${current_price:.6f} | P&L: {pnl:+.1f}%")

                if current_price >= pos.tp_price:
                    await self._close(pos, "TP", current_price)
                elif current_price <= pos.sl_price:
                    await self._close(pos, "SL", current_price)

            except Exception as e:
                log.error(f"[POS] Fehler bei {pos.symbol}: {e}")

    async def _close(self, pos: Position, reason: str, price: float):
        async with self._lock:
            if pos.closed:
                return
            pos.closed = True

        pnl = pos.pnl_pct(price)
        pnl_usd = pos.pnl_usd(price)
        emoji = "🟢" if reason == "TP" else "🔴"
        log.info(
            f"[POS] {emoji} {reason} ausgelöst für {pos.symbol} | "
            f"P&L: {pnl:+.1f}% (${pnl_usd:+.2f})"
        )
        await self.on_close(pos, reason, price)
