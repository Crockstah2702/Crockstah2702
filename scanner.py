"""
Call-Bot / Token-Scanner.
Findet vielversprechende Tokens aus mehreren Quellen:

  1. PRE-BONDING — Pump.fun-Token kurz vor der Migration zu Raydium
     (Moralis-API wenn Key vorhanden, sonst Pump.fun-Frontend-API)
  2. NEW PAIRS    — Frisch gelistete Pools (GeckoTerminal)
  3. TRENDING     — Tokens mit Momentum / Volumen-Anstieg (GeckoTerminal)

Jeder Token bekommt einen Potenzial-Score (0-100) aus Liquidität,
Volumen, Preisänderung und Transaktionszahl.

HINWEIS: Keine dieser Quellen garantiert steigende Kurse. Der Score ist
eine Heuristik, keine Anlageberatung. Memecoins sind hochriskant.
"""

import asyncio
import logging
import time
import aiohttp

from config import cfg

log = logging.getLogger("scanner")

GECKO = "https://api.geckoterminal.com/api/v2"
PUMP_FRONTEND = "https://frontend-api-v3.pump.fun"
MORALIS = "https://solana-gateway.moralis.io"

# Pump.fun: Bonding-Curve gilt bei ca. $69k Market-Cap als abgeschlossen
BONDING_TARGET_USD = 69_000


def _score(liquidity: float, volume: float, price_change: float, txns: int) -> int:
    """Einfacher Potenzial-Score 0-100 aus mehreren Signalen."""
    s = 0.0
    # Liquidität (max 25)
    s += min(25, (liquidity / 50_000) * 25)
    # Volumen (max 30)
    s += min(30, (volume / 100_000) * 30)
    # Positive Preisänderung (max 25)
    if price_change > 0:
        s += min(25, (price_change / 100) * 25)
    # Aktivität / Transaktionen (max 20)
    s += min(20, (txns / 500) * 20)
    return int(max(0, min(100, s)))


class Scanner:
    def __init__(self, on_update=None):
        """on_update(dict) Callback mit den Kategorien pre_bonding / new_pairs / trending."""
        self.on_update = on_update
        self.results: dict[str, list[dict]] = {
            "pre_bonding": [],
            "new_pairs": [],
            "trending": [],
        }

    async def run(self, interval: int = 45):
        log.info("[SCAN] Call-Bot gestartet — sucht Pre-Bonding, neue Pairs & Trending")
        while True:
            try:
                await self.scan_once()
            except Exception as e:
                log.error(f"[SCAN] Fehler: {e}")
            await asyncio.sleep(interval)

    async def scan_once(self):
        pre_bonding, new_pairs, trending = await asyncio.gather(
            self._scan_pre_bonding(),
            self._scan_new_pairs(),
            self._scan_trending(),
            return_exceptions=True,
        )
        self.results = {
            "pre_bonding": pre_bonding if isinstance(pre_bonding, list) else [],
            "new_pairs": new_pairs if isinstance(new_pairs, list) else [],
            "trending": trending if isinstance(trending, list) else [],
        }
        log.info(
            f"[SCAN] {len(self.results['pre_bonding'])} Pre-Bonding | "
            f"{len(self.results['new_pairs'])} New | "
            f"{len(self.results['trending'])} Trending"
        )
        if self.on_update:
            await self.on_update(self.results)

    # ─── 1. PRE-BONDING (Pump.fun) ─────────────────────────────

    async def _scan_pre_bonding(self) -> list[dict]:
        if cfg.MORALIS_API_KEY:
            tokens = await self._pre_bonding_moralis()
            if tokens:
                return tokens
        return await self._pre_bonding_pumpfun()

    async def _pre_bonding_moralis(self) -> list[dict]:
        url = f"{MORALIS}/token/mainnet/exchange/pumpfun/bonding?limit=50"
        headers = {"X-API-Key": cfg.MORALIS_API_KEY, "accept": "application/json"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers, timeout=15) as r:
                    if r.status != 200:
                        log.debug(f"[SCAN] Moralis {r.status}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.debug(f"[SCAN] Moralis-Fehler: {e}")
            return []

        out = []
        for t in data.get("result", []):
            progress = float(t.get("bondingCurveProgress", 0) or 0)
            out.append({
                "symbol": t.get("symbol", "?"),
                "name": t.get("name", ""),
                "address": t.get("tokenAddress", ""),
                "progress": round(progress, 1),
                "mcap": float(t.get("fullyDilutedValuation", 0) or 0),
                "price": float(t.get("priceUsd", 0) or 0),
                "source": "Pump.fun (Moralis)",
                "link": f"https://pump.fun/{t.get('tokenAddress', '')}",
            })
        # Die mit höchstem Fortschritt zuerst (kurz vor Migration)
        out.sort(key=lambda x: x["progress"], reverse=True)
        return [t for t in out if t["progress"] >= 75][:20]

    async def _pre_bonding_pumpfun(self) -> list[dict]:
        url = f"{PUMP_FRONTEND}/coins?offset=0&limit=50&sort=market_cap&order=DESC&includeNsfw=false"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status != 200:
                        log.debug(f"[SCAN] Pump.fun {r.status}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.debug(f"[SCAN] Pump.fun-Fehler: {e}")
            return []

        coins = data if isinstance(data, list) else data.get("coins", [])
        out = []
        for c in coins:
            if c.get("complete"):  # schon migriert
                continue
            mcap = float(c.get("usd_market_cap", 0) or 0)
            progress = round(min(100, (mcap / BONDING_TARGET_USD) * 100), 1)
            if progress < 75:
                continue
            out.append({
                "symbol": c.get("symbol", "?"),
                "name": c.get("name", ""),
                "address": c.get("mint", ""),
                "progress": progress,
                "mcap": mcap,
                "price": 0.0,
                "source": "Pump.fun",
                "link": f"https://pump.fun/{c.get('mint', '')}",
            })
        out.sort(key=lambda x: x["progress"], reverse=True)
        return out[:20]

    # ─── 2. NEW PAIRS (GeckoTerminal) ──────────────────────────

    async def _scan_new_pairs(self) -> list[dict]:
        url = f"{GECKO}/networks/solana/new_pools?page=1"
        data = await self._get_json(url)
        if not data:
            return []
        return self._parse_gecko_pools(data, label="new")

    # ─── 3. TRENDING (GeckoTerminal) ───────────────────────────

    async def _scan_trending(self) -> list[dict]:
        url = f"{GECKO}/networks/solana/trending_pools?page=1&duration=1h"
        data = await self._get_json(url)
        if not data:
            return []
        return self._parse_gecko_pools(data, label="trending")

    def _parse_gecko_pools(self, data: dict, label: str) -> list[dict]:
        out = []
        for pool in data.get("data", []):
            attr = pool.get("attributes", {})
            liquidity = float(attr.get("reserve_in_usd", 0) or 0)
            volume = float(attr.get("volume_usd", {}).get("h24", 0) or 0)
            change = float(attr.get("price_change_percentage", {}).get("h1", 0) or 0)
            tx = attr.get("transactions", {}).get("h1", {})
            txns = int(tx.get("buys", 0) or 0) + int(tx.get("sells", 0) or 0)

            if liquidity < cfg.MIN_LIQUIDITY_USD:
                continue
            if label == "trending" and volume < cfg.MIN_VOLUME_USD:
                continue

            name = attr.get("name", "?")
            base_addr = ""
            rel = pool.get("relationships", {}).get("base_token", {}).get("data", {})
            if rel:
                base_addr = rel.get("id", "").replace("solana_", "")

            out.append({
                "symbol": name.split(" / ")[0] if " / " in name else name,
                "name": name,
                "address": base_addr,
                "liquidity": round(liquidity),
                "volume": round(volume),
                "change_1h": round(change, 1),
                "txns": txns,
                "score": _score(liquidity, volume, change, txns),
                "source": "GeckoTerminal",
                "link": f"https://dexscreener.com/solana/{base_addr}" if base_addr else "",
            })
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:20]

    async def _get_json(self, url: str) -> dict | None:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=15, headers={"accept": "application/json"}) as r:
                    if r.status != 200:
                        log.debug(f"[SCAN] {url} → {r.status}")
                        return None
                    return await r.json()
        except Exception as e:
            log.debug(f"[SCAN] GET-Fehler {url}: {e}")
            return None
