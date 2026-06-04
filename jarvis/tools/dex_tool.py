"""DEX-Daten: DexScreener API, Solana Token-Infos, Axiom.trade Automation."""
import json
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

DEXSCREENER = "https://api.dexscreener.com"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
HEADERS = {"Accept": "application/json", "User-Agent": "ARIA-Trading/1.0"}
TIMEOUT = 10


def get_token_info(address_or_symbol: str) -> str:
    """Token-Info von DexScreener abrufen (Preis, Liquidity, Volume, Chart-Link)."""
    try:
        # Suche nach Symbol oder Adresse
        if len(address_or_symbol) > 20:
            # Wahrscheinlich eine Adresse
            url = f"{DEXSCREENER}/latest/dex/tokens/{address_or_symbol}"
        else:
            url = f"{DEXSCREENER}/latest/dex/search?q={address_or_symbol}"

        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        data = r.json()
        pairs = data.get("pairs", [])

        if not pairs:
            return f"❌ Keine Daten für '{address_or_symbol}' auf DexScreener"

        # Nehme das Pair mit der höchsten Liquidität
        pair = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]

        base = pair.get("baseToken", {})
        price_usd = float(pair.get("priceUsd", 0) or 0)
        price_native = float(pair.get("priceNative", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol24 = float((pair.get("volume") or {}).get("h24", 0) or 0)
        chg1h = float((pair.get("priceChange") or {}).get("h1", 0) or 0)
        chg24h = float((pair.get("priceChange") or {}).get("h24", 0) or 0)
        txns24 = pair.get("txns", {}).get("h24", {})
        buys = txns24.get("buys", 0)
        sells = txns24.get("sells", 0)
        chain = pair.get("chainId", "?")
        dex = pair.get("dexId", "?")
        pair_url = pair.get("url", "")
        fdv = float(pair.get("fdv", 0) or 0)

        # Risiko-Einschätzung
        risk = _assess_risk(liq, vol24, buys + sells)

        arrow1h = "▲" if chg1h > 0 else "▼"
        arrow24h = "▲" if chg24h > 0 else "▼"

        return (f"🔍 {base.get('name','?')} ({base.get('symbol','?').upper()})\n"
                f"  Chain:       {chain.upper()} | DEX: {dex}\n"
                f"  Preis USD:   ${price_usd:.8f}\n"
                f"  1h:          {arrow1h} {chg1h:+.2f}%\n"
                f"  24h:         {arrow24h} {chg24h:+.2f}%\n"
                f"  Liquidität:  ${liq:,.0f}\n"
                f"  Vol. 24h:    ${vol24:,.0f}\n"
                f"  FDV:         ${fdv:,.0f}\n"
                f"  Txns 24h:    {buys} Käufe / {sells} Verkäufe\n"
                f"  Risiko:      {risk}\n"
                f"  Chart:       {pair_url}\n"
                f"  Adresse:     {base.get('address','?')}")
    except Exception as e:
        return f"❌ Fehler: {e}"


def search_dex_pairs(query: str, limit: int = 5) -> str:
    """Suche nach Trading-Pairs auf DexScreener."""
    try:
        r = requests.get(f"{DEXSCREENER}/latest/dex/search?q={query}",
                         headers=HEADERS, timeout=TIMEOUT)
        pairs = r.json().get("pairs", [])[:limit]
        if not pairs:
            return f"Keine Pairs gefunden für '{query}'"

        lines = [f"DexScreener Suche: '{query}' ({len(pairs)} Ergebnisse)\n"]
        for p in pairs:
            base = p.get("baseToken", {})
            price = float(p.get("priceUsd", 0) or 0)
            liq = float((p.get("liquidity") or {}).get("usd", 0) or 0)
            chg = float((p.get("priceChange") or {}).get("h24", 0) or 0)
            chain = p.get("chainId", "?").upper()
            lines.append(f"  {base.get('symbol','?').upper()} ({chain}) "
                         f"${price:.6f} | 24h: {chg:+.1f}% | Liq: ${liq:,.0f}")
            lines.append(f"    → {p.get('url','')}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_new_solana_tokens(limit: int = 10) -> str:
    """Neue Solana Token auf DexScreener — frisch gelistet."""
    try:
        r = requests.get(f"{DEXSCREENER}/token-profiles/latest/v1",
                         headers=HEADERS, timeout=TIMEOUT)
        tokens = r.json()
        sol_tokens = [t for t in tokens if t.get("chainId", "") == "solana"][:limit]
        if not sol_tokens:
            return "Keine neuen Solana Tokens gefunden"

        lines = [f"🆕 Neue Solana Tokens ({len(sol_tokens)}):"]
        for t in sol_tokens:
            lines.append(f"  {t.get('symbol','?').upper()} — {t.get('description','')[:60]}")
            lines.append(f"    Adresse: {t.get('tokenAddress','?')}")
            links = t.get("links", [])
            for l in links:
                if l.get("type") in ["twitter", "website"]:
                    lines.append(f"    {l['type'].capitalize()}: {l.get('url','')}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_solana_wallet_balance(wallet_address: str) -> str:
    """Solana Wallet-Balance abrufen (SOL + Token)."""
    try:
        # SOL Balance
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getBalance",
            "params": [wallet_address]
        }
        r = requests.post(SOLANA_RPC, json=payload, timeout=TIMEOUT)
        lamports = r.json().get("result", {}).get("value", 0)
        sol = lamports / 1e9

        # SOL Preis
        sol_price_r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=5
        )
        sol_price = sol_price_r.json().get("solana", {}).get("usd", 0)
        sol_value = sol * sol_price

        # Token Accounts
        token_payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }
        tr = requests.post(SOLANA_RPC, json=token_payload, timeout=TIMEOUT)
        token_accounts = tr.json().get("result", {}).get("value", [])

        lines = [f"💼 Wallet: {wallet_address[:8]}...{wallet_address[-6:]}\n"
                 f"  SOL: {sol:.4f} (≈ ${sol_value:,.2f})\n"]

        token_lines = []
        for acc in token_accounts[:20]:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = float(info.get("tokenAmount", {}).get("uiAmount", 0) or 0)
            mint = info.get("mint", "")
            if amount > 0:
                token_lines.append(f"  Token: {mint[:8]}... — {amount:.4f}")

        if token_lines:
            lines.append("Token-Holdings:")
            lines.extend(token_lines[:10])
        else:
            lines.append("  Keine Token-Holdings")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def analyze_token_risk(address: str) -> str:
    """Einfache Risiko-Analyse eines Tokens (Liquidität, Volume, Käufer/Verkäufer-Ratio)."""
    try:
        r = requests.get(f"{DEXSCREENER}/latest/dex/tokens/{address}",
                         headers=HEADERS, timeout=TIMEOUT)
        pairs = r.json().get("pairs", [])
        if not pairs:
            return f"❌ Keine Daten für {address}"

        pair = sorted(pairs, key=lambda x: float((x.get("liquidity") or {}).get("usd", 0) or 0), reverse=True)[0]
        base = pair.get("baseToken", {})
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol24 = float((pair.get("volume") or {}).get("h24", 0) or 0)
        txns = pair.get("txns", {})
        buys_1h = txns.get("h1", {}).get("buys", 0)
        sells_1h = txns.get("h1", {}).get("sells", 0)
        buys_24h = txns.get("h24", {}).get("buys", 0)
        sells_24h = txns.get("h24", {}).get("sells", 0)
        chg1h = float((pair.get("priceChange") or {}).get("h1", 0) or 0)
        chg24h = float((pair.get("priceChange") or {}).get("h24", 0) or 0)
        fdv = float(pair.get("fdv", 0) or 0)

        warnings = []
        score = 100

        if liq < 10000:
            warnings.append("⚠️ SEHR GERINGE Liquidität (<$10k) — Hohe Slippage, Rug-Gefahr!")
            score -= 40
        elif liq < 50000:
            warnings.append("⚠️ Niedrige Liquidität (<$50k)")
            score -= 20

        if vol24 == 0:
            warnings.append("⚠️ Kein Volumen in 24h — möglicherweise inaktiv")
            score -= 20

        if buys_24h + sells_24h < 10:
            warnings.append("⚠️ Sehr wenige Transaktionen — geringes Interesse")
            score -= 15

        if sells_24h > buys_24h * 2:
            warnings.append("⚠️ Viel mehr Verkäufe als Käufe — Aussteigen möglicherweise schwer")
            score -= 20

        if chg1h < -20:
            warnings.append(f"⚠️ Starker Preisabfall in 1h ({chg1h:.1f}%)")
            score -= 15

        if liq > 0 and fdv > 0 and fdv / liq > 1000:
            warnings.append("⚠️ FDV/Liquidität-Ratio sehr hoch — mögliche Inflation")
            score -= 10

        risk_level = "🟢 NIEDRIG" if score >= 70 else "🟡 MITTEL" if score >= 40 else "🔴 HOCH"

        result = (f"🔍 Risiko-Analyse: {base.get('name','?')} ({base.get('symbol','?').upper()})\n"
                  f"  Risiko-Score:  {score}/100 — {risk_level}\n"
                  f"  Liquidität:    ${liq:,.0f}\n"
                  f"  Vol. 24h:      ${vol24:,.0f}\n"
                  f"  Käufe/Verkäufe (24h): {buys_24h}/{sells_24h}\n"
                  f"  Preis 1h/24h:  {chg1h:+.1f}% / {chg24h:+.1f}%\n")
        if warnings:
            result += "\nWarnungen:\n" + "\n".join(f"  {w}" for w in warnings)
        else:
            result += "\n✅ Keine offensichtlichen Warnsignale"

        result += f"\n\n⚠️ ACHTUNG: Dies ist KEINE Finanzberatung. Immer selbst recherchieren!"
        return result
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_trending_solana_tokens() -> str:
    """Trending Solana Tokens von DexScreener."""
    try:
        r = requests.get(f"{DEXSCREENER}/latest/dex/search?q=sol",
                         headers=HEADERS, timeout=TIMEOUT)
        pairs = r.json().get("pairs", [])
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        # Sort by 24h volume
        sol_pairs = sorted(sol_pairs,
                           key=lambda x: float((x.get("volume") or {}).get("h24", 0) or 0),
                           reverse=True)[:10]

        lines = ["🔥 Trending Solana Tokens (nach Volumen):"]
        for p in sol_pairs:
            base = p.get("baseToken", {})
            vol = float((p.get("volume") or {}).get("h24", 0) or 0)
            chg = float((p.get("priceChange") or {}).get("h24", 0) or 0)
            price = float(p.get("priceUsd", 0) or 0)
            arrow = "▲" if chg > 0 else "▼"
            lines.append(f"  {base.get('symbol','?').upper():<12} "
                         f"${price:.6f} {arrow}{abs(chg):.1f}% | Vol: ${vol:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def _assess_risk(liquidity: float, volume: float, txns: int) -> str:
    if liquidity < 5000:
        return "🔴 SEHR HOCH (Rug-Gefahr!)"
    elif liquidity < 50000:
        return "🟠 HOCH"
    elif liquidity < 200000:
        return "🟡 MITTEL"
    else:
        return "🟢 NIEDRIG"
