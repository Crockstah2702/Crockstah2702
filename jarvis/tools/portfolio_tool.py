"""Portfolio-Tracker: Positionen verwalten, P&L berechnen, Trade-Journal."""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/portfolio.db")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        name TEXT DEFAULT '',
        amount REAL NOT NULL,
        buy_price REAL NOT NULL,
        current_price REAL DEFAULT 0,
        buy_date TEXT NOT NULL,
        notes TEXT DEFAULT '',
        chain TEXT DEFAULT 'solana',
        token_address TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS trade_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        symbol TEXT NOT NULL,
        amount REAL NOT NULL,
        price REAL NOT NULL,
        value_usd REAL NOT NULL,
        pnl REAL DEFAULT 0,
        timestamp TEXT NOT NULL,
        notes TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS price_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        target_price REAL NOT NULL,
        direction TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def add_position(symbol: str, amount: float, buy_price: float,
                  notes: str = "", chain: str = "solana",
                  token_address: str = "") -> str:
    """Position hinzufügen (Kauf erfassen)."""
    conn = _connect()
    symbol = symbol.upper()
    value = float(amount) * float(buy_price)
    conn.execute("""INSERT INTO positions
        (symbol, amount, buy_price, buy_date, notes, chain, token_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, float(amount), float(buy_price),
         datetime.now().isoformat(), notes, chain, token_address))
    conn.execute("""INSERT INTO trade_journal
        (action, symbol, amount, price, value_usd, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("BUY", symbol, float(amount), float(buy_price), value,
         datetime.now().isoformat(), notes))
    conn.commit()
    conn.close()
    return (f"✅ Position hinzugefügt:\n"
            f"  {symbol}: {amount} @ ${buy_price:,.6f}\n"
            f"  Einsatz: ${value:,.2f}")


def close_position(position_id: int, sell_price: float, notes: str = "") -> str:
    """Position schließen (Verkauf erfassen) und P&L berechnen."""
    conn = _connect()
    row = conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
    if not row:
        conn.close()
        return f"❌ Position #{position_id} nicht gefunden"

    symbol = row[1]
    amount = row[3]
    buy_price = row[4]
    buy_value = amount * buy_price
    sell_value = amount * float(sell_price)
    pnl = sell_value - buy_value
    pnl_pct = (pnl / buy_value) * 100 if buy_value > 0 else 0

    conn.execute("DELETE FROM positions WHERE id=?", (position_id,))
    conn.execute("""INSERT INTO trade_journal
        (action, symbol, amount, price, value_usd, pnl, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("SELL", symbol, amount, float(sell_price), sell_value, pnl,
         datetime.now().isoformat(), notes))
    conn.commit()
    conn.close()

    emoji = "📈" if pnl > 0 else "📉"
    return (f"{emoji} Position geschlossen: {symbol}\n"
            f"  Einstieg:  ${buy_price:,.6f} × {amount}\n"
            f"  Ausstieg:  ${sell_price:,.6f}\n"
            f"  Einsatz:   ${buy_value:,.2f}\n"
            f"  Erlös:     ${sell_value:,.2f}\n"
            f"  P&L:       ${pnl:+,.2f} ({pnl_pct:+.2f}%)")


def get_portfolio(refresh_prices: bool = True) -> str:
    """Aktuelles Portfolio mit aktuellem P&L anzeigen."""
    conn = _connect()
    rows = conn.execute("SELECT * FROM positions ORDER BY buy_date DESC").fetchall()
    conn.close()

    if not rows:
        return "Portfolio ist leer. Nutze add_position() um Positionen hinzuzufügen."

    # Preise aktualisieren
    current_prices = {}
    if refresh_prices:
        symbols = list(set(r[1] for r in rows))
        for sym in symbols:
            try:
                from tools.crypto_tool import COINGECKO, SYMBOL_MAP, HEADERS
                coin_id = SYMBOL_MAP.get(sym.lower(), sym.lower())
                r = requests.get(
                    f"{COINGECKO}/simple/price?ids={coin_id}&vs_currencies=usd",
                    headers=HEADERS, timeout=5
                )
                p = r.json().get(coin_id, {}).get("usd", 0)
                if p:
                    current_prices[sym] = p
            except Exception:
                pass

    lines = [f"{'#':<4} {'Symbol':<10} {'Menge':>12} {'Einstieg':>12} "
             f"{'Aktuell':>12} {'P&L':>12} {'P&L%':>8}"]
    lines.append("─" * 74)

    total_invested = 0
    total_current = 0

    for row in rows:
        pos_id, sym, name, amount, buy_price, cur_price, buy_date, notes, chain, addr = row
        cur = current_prices.get(sym, cur_price or buy_price)
        invested = amount * buy_price
        current_val = amount * cur
        pnl = current_val - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0
        total_invested += invested
        total_current += current_val
        arrow = "▲" if pnl > 0 else "▼"
        lines.append(f"{pos_id:<4} {sym:<10} {amount:>12.4f} ${buy_price:>10,.4f} "
                     f"${cur:>10,.4f} ${pnl:>+10,.2f} {arrow}{abs(pnl_pct):>6.1f}%")

    lines.append("─" * 74)
    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    emoji = "📈" if total_pnl > 0 else "📉"
    lines.append(f"\n{emoji} Gesamt-Portfolio:")
    lines.append(f"  Investiert:    ${total_invested:,.2f}")
    lines.append(f"  Aktueller Wert: ${total_current:,.2f}")
    lines.append(f"  Gesamt P&L:    ${total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)")

    return "\n".join(lines)


def get_trade_journal(limit: int = 20) -> str:
    """Trade-Journal anzeigen."""
    conn = _connect()
    rows = conn.execute("""SELECT * FROM trade_journal
        ORDER BY timestamp DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()

    if not rows:
        return "Keine Trades im Journal."

    lines = ["📒 Trade-Journal:"]
    for row in rows:
        tid, action, sym, amount, price, value, pnl, ts, notes = row
        date = ts[:16].replace("T", " ")
        pnl_str = f" | P&L: ${pnl:+.2f}" if action == "SELL" else ""
        emoji = "🟢" if action == "BUY" else "🔴"
        lines.append(f"  {emoji} {date} | {action} {amount:.4f} {sym} "
                     f"@ ${price:,.6f} (${value:,.2f}){pnl_str}")
    return "\n".join(lines)


def set_price_alert(symbol: str, target_price: float, direction: str = "above") -> str:
    """Preis-Alert setzen (ARIA benachrichtigt wenn Preis erreicht wird)."""
    conn = _connect()
    conn.execute("""INSERT INTO price_alerts (symbol, target_price, direction, created)
        VALUES (?, ?, ?, ?)""",
        (symbol.upper(), float(target_price), direction, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    dir_str = "über" if direction == "above" else "unter"
    return (f"✅ Alert gesetzt: {symbol.upper()} {dir_str} ${target_price:,.6f}\n"
            f"   ARIA benachrichtigt dich wenn der Preis erreicht wird.")


def check_price_alerts() -> str:
    """Alle aktiven Preis-Alerts prüfen und ausgelöste melden."""
    conn = _connect()
    alerts = conn.execute("""SELECT * FROM price_alerts WHERE active=1""").fetchall()
    if not alerts:
        conn.close()
        return "Keine aktiven Preis-Alerts."

    triggered = []
    for alert in alerts:
        alert_id, sym, target, direction, active, created = alert
        try:
            from tools.crypto_tool import COINGECKO, SYMBOL_MAP, HEADERS
            coin_id = SYMBOL_MAP.get(sym.lower(), sym.lower())
            r = requests.get(
                f"{COINGECKO}/simple/price?ids={coin_id}&vs_currencies=usd",
                headers=HEADERS, timeout=5
            )
            cur_price = r.json().get(coin_id, {}).get("usd", 0)
            if cur_price:
                if (direction == "above" and cur_price >= target) or \
                   (direction == "below" and cur_price <= target):
                    triggered.append(f"🚨 ALERT: {sym} ist ${cur_price:,.6f} "
                                     f"({'über' if direction=='above' else 'unter'} "
                                     f"${target:,.6f})")
                    conn.execute("UPDATE price_alerts SET active=0 WHERE id=?", (alert_id,))
        except Exception:
            pass

    conn.commit()
    conn.close()

    if triggered:
        return "\n".join(triggered)
    return f"Keine Alerts ausgelöst ({len(alerts)} aktive Alerts)"


def get_portfolio_stats() -> str:
    """Portfolio-Statistiken: beste/schlechteste Trades, Gewinn-Quote."""
    conn = _connect()
    trades = conn.execute("""SELECT * FROM trade_journal WHERE action='SELL'
        ORDER BY pnl DESC""").fetchall()
    conn.close()

    if not trades:
        return "Noch keine abgeschlossenen Trades."

    total_trades = len(trades)
    winning = [t for t in trades if t[6] > 0]
    losing = [t for t in trades if t[6] <= 0]
    total_pnl = sum(t[6] for t in trades)
    best = trades[0]
    worst = trades[-1]
    win_rate = (len(winning) / total_trades * 100) if total_trades > 0 else 0

    return (f"📊 Portfolio-Statistiken:\n"
            f"  Trades gesamt:  {total_trades}\n"
            f"  Gewinner:       {len(winning)} ({win_rate:.1f}%)\n"
            f"  Verlierer:      {len(losing)}\n"
            f"  Gesamt P&L:     ${total_pnl:+,.2f}\n"
            f"  Bester Trade:   {best[2]} +${best[6]:,.2f}\n"
            f"  Schlechtester:  {worst[2]} ${worst[6]:,.2f}")
