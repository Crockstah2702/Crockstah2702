"""
Dynamisches TP/SL via Claude KI.
Analysiert Token-Eigenschaften und schlägt optimale TP/SL-Prozentsätze vor.
"""

import asyncio
import json
import logging
from config import cfg
from price_fetcher import get_token_symbol

log = logging.getLogger("ai")

_client = None


def _get_client():
    global _client
    if _client is None:
        if not cfg.ANTHROPIC_API_KEY:
            return None
        try:
            import anthropic
        except ModuleNotFoundError:
            log.warning("[AI] 'anthropic' nicht installiert — TP/SL nutzt Standardwerte")
            return None
        _client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    return _client


async def get_dynamic_tp_sl(
    chain: str,
    input_mint: str,
    output_mint: str,
    in_amount_usd: float,
    current_price: float | None,
    dex: str,
) -> dict:
    """
    Gibt {'tp_pct': float, 'sl_pct': float, 'reasoning': str} zurück.
    TP und SL sind positive Prozentwerte (z.B. tp_pct=40.0 = +40%).
    """
    symbol = await get_token_symbol(chain, output_mint)

    prompt = f"""Du bist ein erfahrener Krypto-Trader-Assistent. Analysiere diesen Trade und schlage dynamische Take-Profit (TP) und Stop-Loss (SL) Levels vor.

Trade-Daten:
- Chain: {chain}
- Token gekauft: {symbol} ({output_mint[:12]}…)
- Eingezahlt: {in_amount_usd:.2f} USD
- Aktueller Preis: {f"${current_price:.6f}" if current_price else "unbekannt"}
- DEX: {dex}
- Input Token: {input_mint[:12]}…

Kriterien für deine Entscheidung:
- Solana Meme-Coins/neue Token: aggressiver TP (50-200%), engerer SL (15-25%)
- Etablierte Token (>$10M Market Cap): konservativer TP (20-40%), TP (10-15%)
- ETH DeFi Token: mittel TP (30-60%), SL (12-18%)
- Kleine Trade-Größe (<$100): kann aggressiver sein
- Große Trade-Größe (>$1000): konservativer

Antworte NUR mit diesem JSON-Format (kein anderer Text):
{{
  "tp_pct": <Zahl zwischen 20 und 300>,
  "sl_pct": <Zahl zwischen 5 und 50>,
  "reasoning": "<1-2 Sätze Begründung auf Deutsch>"
}}"""

    client = _get_client()
    if client is None:
        return {"tp_pct": 50.0, "sl_pct": 20.0,
                "reasoning": "Standardwerte (kein ANTHROPIC_API_KEY gesetzt)"}

    try:
        message = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        result = json.loads(raw)
        tp = float(result.get("tp_pct", 50.0))
        sl = float(result.get("sl_pct", 20.0))
        reasoning = result.get("reasoning", "")

        # Sicherheitsgrenzen
        tp = max(10.0, min(500.0, tp))
        sl = max(3.0, min(60.0, sl))

        log.info(f"[AI] {symbol}: TP={tp:.0f}% | SL={sl:.0f}% | {reasoning}")
        return {"tp_pct": tp, "sl_pct": sl, "reasoning": reasoning}

    except Exception as e:
        log.warning(f"[AI] Analyse fehlgeschlagen ({e}), verwende Standardwerte")
        return {
            "tp_pct": 50.0,
            "sl_pct": 20.0,
            "reasoning": "Standardwerte (KI nicht verfügbar)",
        }
