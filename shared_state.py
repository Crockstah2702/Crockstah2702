"""
Gemeinsamer Zustand zwischen Bot-Tasks, Scanner und Web-Terminal.
Wird im selben Asyncio-Event-Loop genutzt; Lock schützt zusätzlich vor
gleichzeitigem Zugriff aus dem uvicorn-Threadpool.
"""

import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class LogEntry:
    time: str
    level: str  # INFO / WARN / ERROR / TRADE / TP / SL
    message: str


@dataclass
class LivePosition:
    id: str
    symbol: str
    chain: str
    entry_price: float
    current_price: float
    amount_usd: float
    tp_pct: float
    sl_pct: float
    pnl_pct: float
    pnl_usd: float
    reasoning: str


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()

        self.bot_active: bool = False
        self.paused: bool = False
        self.dry_run: bool = True
        self.enable_sol: bool = True
        self.enable_eth: bool = True
        self.enable_scanner: bool = True

        self.total_trades: int = 0
        self.total_pnl_usd: float = 0.0
        self.total_tp_hits: int = 0
        self.total_sl_hits: int = 0

        self.positions: dict[str, LivePosition] = {}
        self.logs: deque = deque(maxlen=200)
        self.price_history: dict[str, list[float]] = {}

        self.scanner: dict[str, list[dict]] = {
            "pre_bonding": [],
            "new_pairs": [],
            "trending": [],
        }
        self.scanner_updated: str = "—"

    def add_log(self, level: str, message: str):
        entry = LogEntry(time=datetime.now().strftime("%H:%M:%S"), level=level, message=message)
        with self._lock:
            self.logs.append(entry)

    def upsert_position(self, p: LivePosition):
        with self._lock:
            self.positions[p.id] = p

    def remove_position(self, pos_id: str):
        with self._lock:
            self.positions.pop(pos_id, None)

    def add_price_point(self, symbol: str, price: float):
        with self._lock:
            hist = self.price_history.setdefault(symbol, [])
            hist.append(price)
            if len(hist) > 80:
                hist.pop(0)

    def update_scanner(self, results: dict):
        with self._lock:
            self.scanner = results
            self.scanner_updated = datetime.now().strftime("%H:%M:%S")

    def record_close(self, reason: str, pnl_usd: float):
        with self._lock:
            self.total_pnl_usd += pnl_usd
            if reason == "TP":
                self.total_tp_hits += 1
            elif reason == "SL":
                self.total_sl_hits += 1

    def snapshot(self) -> dict:
        """Vollständiger JSON-Snapshot für das Web-Terminal."""
        with self._lock:
            return {
                "status": {
                    "active": self.bot_active,
                    "paused": self.paused,
                    "dry_run": self.dry_run,
                    "enable_sol": self.enable_sol,
                    "enable_eth": self.enable_eth,
                    "enable_scanner": self.enable_scanner,
                    "total_trades": self.total_trades,
                    "total_pnl_usd": round(self.total_pnl_usd, 2),
                    "tp_hits": self.total_tp_hits,
                    "sl_hits": self.total_sl_hits,
                },
                "positions": [asdict(p) for p in self.positions.values()],
                "logs": [asdict(l) for l in list(self.logs)[-40:]],
                "price_history": dict(self.price_history),
                "scanner": self.scanner,
                "scanner_updated": self.scanner_updated,
            }


# Globale Instanz — von Bot, Scanner und Web-Terminal geteilt
state = SharedState()
