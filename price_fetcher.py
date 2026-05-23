"""
Preis-Abruf für Solana- und Ethereum-Token.
Solana: Jupiter Price API
Ethereum: DexScreener API
"""

import logging
import aiohttp

log = logging.getLogger("price")

SOL_MINT = "So11111111111111111111111111111111111111112"
ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

JUPITER_PRICE_URL = "https://price.jup.ag/v4/price"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"


async def get_sol_token_price(mint: str) -> float | None:
    """Gibt den aktuellen USD-Preis eines Solana-Tokens zurück."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_PRICE_URL, params={"ids": mint}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", {}).get(mint, {}).get("price", 0)) or None
    except Exception as e:
        log.debug(f"[PRICE] SOL-Preis-Fehler für {mint[:8]}…: {e}")
        return None


async def get_eth_token_price(address: str) -> float | None:
    """Gibt den aktuellen USD-Preis eines ETH-Tokens zurück."""
    if address.lower() == ETH_ADDRESS.lower():
        return await _get_eth_price()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{DEXSCREENER_URL}/{address}") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs", [])
                if not pairs:
                    return None
                return float(pairs[0].get("priceUsd", 0)) or None
    except Exception as e:
        log.debug(f"[PRICE] ETH-Preis-Fehler für {address[:10]}…: {e}")
        return None


async def _get_eth_price() -> float | None:
    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs", [])
                return float(pairs[0].get("priceUsd", 0)) if pairs else None
    except Exception:
        return None


async def get_token_price(chain: str, mint: str) -> float | None:
    if chain == "SOL":
        return await get_sol_token_price(mint)
    elif chain == "ETH":
        return await get_eth_token_price(mint)
    return None


async def get_token_symbol(chain: str, mint: str) -> str:
    """Versucht das Token-Symbol abzurufen."""
    try:
        if chain == "SOL":
            async with aiohttp.ClientSession() as session:
                async with session.get(JUPITER_PRICE_URL, params={"ids": mint}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        info = data.get("data", {}).get(mint, {})
                        return info.get("mintSymbol", mint[:8])
        elif chain == "ETH":
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{DEXSCREENER_URL}/{mint}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pairs = data.get("pairs", [])
                        if pairs:
                            return pairs[0].get("baseToken", {}).get("symbol", mint[:10])
    except Exception:
        pass
    return mint[:10]
