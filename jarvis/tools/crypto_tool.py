"""Crypto-Preise, Marktdaten und technische Analyse — ohne API-Key."""
import json
import logging
import math
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

COINGECKO = "https://api.coingecko.com/api/v3"
HEADERS = {"Accept": "application/json", "User-Agent": "ARIA-Trading/1.0"}
TIMEOUT = 10

# Häufige Symbol → CoinGecko-ID Mappings
SYMBOL_MAP = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
    "bnb": "binancecoin", "xrp": "ripple", "ada": "cardano",
    "doge": "dogecoin", "avax": "avalanche-2", "dot": "polkadot",
    "matic": "matic-network", "link": "chainlink", "uni": "uniswap",
    "ltc": "litecoin", "atom": "cosmos", "near": "near",
    "apt": "aptos", "sui": "sui", "arb": "arbitrum",
    "op": "optimism", "inj": "injective-protocol",
    "wif": "dogwifcoin", "bonk": "bonk", "pepe": "pepe",
    "shib": "shiba-inu", "floki": "floki", "popcat": "popcat",
}


def _resolve_id(symbol_or_id: str) -> str:
    s = symbol_or_id.lower().strip()
    return SYMBOL_MAP.get(s, s)


def get_crypto_price(symbol: str, currency: str = "usd") -> str:
    """Aktuellen Preis einer Kryptowährung abrufen."""
    coin_id = _resolve_id(symbol)
    try:
        r = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": coin_id, "vs_currencies": currency,
                    "include_24hr_change": "true", "include_market_cap": "true"},
            headers=HEADERS, timeout=TIMEOUT
        )
        data = r.json()
        if coin_id not in data:
            return f"❌ Coin '{symbol}' nicht gefunden. Versuche den vollen Namen (z.B. 'bitcoin')."
        d = data[coin_id]
        price = d.get(currency, 0)
        change = d.get(f"{currency}_24h_change", 0)
        mcap = d.get(f"{currency}_market_cap", 0)
        arrow = "📈" if change > 0 else "📉"
        return (f"{symbol.upper()} Preis:\n"
                f"  Preis:      ${price:,.4f}\n"
                f"  24h:        {arrow} {change:+.2f}%\n"
                f"  Market Cap: ${mcap:,.0f}")
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_multiple_prices(symbols: str) -> str:
    """Preise mehrerer Coins auf einmal abrufen (komma-getrennt)."""
    coins = [s.strip() for s in symbols.split(",")]
    ids = ",".join(_resolve_id(c) for c in coins)
    try:
        r = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
            headers=HEADERS, timeout=TIMEOUT
        )
        data = r.json()
        lines = [f"{'Coin':<12} {'Preis':>12} {'24h':>10}"]
        lines.append("-" * 38)
        for coin, sym in zip(coins, ids.split(",")):
            if sym in data:
                p = data[sym].get("usd", 0)
                c = data[sym].get("usd_24h_change", 0)
                arrow = "▲" if c > 0 else "▼"
                lines.append(f"{coin.upper():<12} ${p:>11,.4f} {arrow}{abs(c):>8.2f}%")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_top_cryptos(n: int = 20, currency: str = "usd") -> str:
    """Top Kryptowährungen nach Market Cap."""
    try:
        r = requests.get(
            f"{COINGECKO}/coins/markets",
            params={"vs_currency": currency, "order": "market_cap_desc",
                    "per_page": min(int(n), 50), "page": 1,
                    "price_change_percentage": "24h"},
            headers=HEADERS, timeout=TIMEOUT
        )
        coins = r.json()
        lines = [f"{'#':<4} {'Name':<14} {'Preis':>12} {'24h':>9} {'Market Cap':>16}"]
        lines.append("-" * 60)
        for i, c in enumerate(coins, 1):
            chg = c.get("price_change_percentage_24h", 0) or 0
            arrow = "▲" if chg > 0 else "▼"
            lines.append(
                f"{i:<4} {c['symbol'].upper():<14} ${c['current_price']:>11,.4f} "
                f"{arrow}{abs(chg):>7.2f}% ${c['market_cap']:>14,.0f}"
            )
        return f"Top {n} Kryptowährungen:\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_price_history(symbol: str, days: int = 7, currency: str = "usd") -> str:
    """Preisverlauf der letzten N Tage abrufen."""
    coin_id = _resolve_id(symbol)
    try:
        r = requests.get(
            f"{COINGECKO}/coins/{coin_id}/market_chart",
            params={"vs_currency": currency, "days": days},
            headers=HEADERS, timeout=TIMEOUT
        )
        data = r.json()
        prices = [p[1] for p in data.get("prices", [])]
        if not prices:
            return f"Keine Preisdaten für {symbol}"

        # Kompakte Analyse
        current = prices[-1]
        start = prices[0]
        high = max(prices)
        low = min(prices)
        change = ((current - start) / start) * 100
        vol = _calculate_volatility(prices)

        # ASCII-Minigraph
        graph = _mini_chart(prices, width=30)

        return (f"{symbol.upper()} — letzten {days} Tage:\n"
                f"  Jetzt:       ${current:,.4f}\n"
                f"  Start:       ${start:,.4f}\n"
                f"  Änderung:    {change:+.2f}%\n"
                f"  Hoch:        ${high:,.4f}\n"
                f"  Tief:        ${low:,.4f}\n"
                f"  Volatilität: {vol:.2f}%\n\n"
                f"  {graph}")
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_trending_coins() -> str:
    """Trending Coins auf CoinGecko (letzte 24h)."""
    try:
        r = requests.get(f"{COINGECKO}/search/trending",
                         headers=HEADERS, timeout=TIMEOUT)
        data = r.json()
        coins = data.get("coins", [])
        lines = ["🔥 Trending Coins (24h):"]
        for i, item in enumerate(coins[:10], 1):
            c = item.get("item", {})
            lines.append(f"  {i}. {c.get('symbol','?').upper()} — {c.get('name','?')} "
                         f"(Rank #{c.get('market_cap_rank','?')})")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def calculate_technical_analysis(symbol: str, days: int = 14) -> str:
    """RSI, MACD, Moving Averages für eine Kryptowährung berechnen."""
    coin_id = _resolve_id(symbol)
    try:
        r = requests.get(
            f"{COINGECKO}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": max(days, 30)},
            headers=HEADERS, timeout=TIMEOUT
        )
        prices = [p[1] for p in r.json().get("prices", [])]
        if len(prices) < 30:
            return f"Nicht genug Daten für {symbol}"

        current = prices[-1]
        rsi = _rsi(prices, 14)
        ma7 = sum(prices[-7:]) / 7
        ma20 = sum(prices[-20:]) / 20
        ma50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else None
        macd_val, signal = _macd(prices)
        vol = _calculate_volatility(prices[-30:])

        # Interpretation
        rsi_signal = "Überverkauft (Kaufsignal?)" if rsi < 30 else "Überkauft (Verkaufsignal?)" if rsi > 70 else "Neutral"
        ma_trend = "Bullish (MA7 > MA20)" if ma7 > ma20 else "Bearish (MA7 < MA20)"
        macd_signal = "Bullish" if macd_val > signal else "Bearish"

        result = (f"Technische Analyse: {symbol.upper()}\n"
                  f"  Aktueller Preis: ${current:,.4f}\n\n"
                  f"  RSI (14):    {rsi:.1f} — {rsi_signal}\n"
                  f"  MA 7:        ${ma7:,.4f}\n"
                  f"  MA 20:       ${ma20:,.4f}\n")
        if ma50:
            result += f"  MA 50:       ${ma50:,.4f}\n"
        result += (f"  MACD:        {macd_val:+.4f} — {macd_signal}\n"
                   f"  Volatilität: {vol:.2f}%\n\n"
                   f"  Trend:       {ma_trend}\n"
                   f"  Gesamtbild:  {'🟢 Bullish' if ma7 > ma20 and rsi < 65 else '🔴 Bearish' if ma7 < ma20 and rsi > 50 else '🟡 Neutral'}")
        return result
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_fear_greed_index() -> str:
    """Crypto Fear & Greed Index abrufen."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=TIMEOUT)
        data = r.json()["data"][0]
        value = int(data["value"])
        classification = data["value_classification"]
        emoji = "😱" if value < 25 else "😨" if value < 45 else "😐" if value < 55 else "😄" if value < 75 else "🤑"
        bar = "█" * (value // 10) + "░" * (10 - value // 10)
        return (f"Fear & Greed Index:\n"
                f"  {emoji} {value}/100 — {classification}\n"
                f"  [{bar}]")
    except Exception as e:
        return f"❌ Fehler: {e}"


# ── Technische Hilfsfunktionen ──────────────────────────────────────

def _rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(prices: list, period: int) -> list:
    k = 2 / (period + 1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(p * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _macd(prices: list) -> tuple:
    if len(prices) < 26:
        return 0.0, 0.0
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal = _ema(macd_line, 9)
    return macd_line[-1], signal[-1]


def _calculate_volatility(prices: list) -> float:
    if len(prices) < 2:
        return 0.0
    returns = [(prices[i] - prices[i-1]) / prices[i-1] * 100
               for i in range(1, len(prices))]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def _mini_chart(prices: list, width: int = 30) -> str:
    if not prices:
        return ""
    step = max(1, len(prices) // width)
    sampled = prices[::step][-width:]
    mn, mx = min(sampled), max(sampled)
    if mx == mn:
        return "─" * len(sampled)
    chars = "▁▂▃▄▅▆▇█"
    bars = [chars[int((p - mn) / (mx - mn) * 7)] for p in sampled]
    return "".join(bars)
