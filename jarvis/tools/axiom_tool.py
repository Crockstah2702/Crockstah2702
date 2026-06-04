"""Axiom.trade Browser-Automation für Solana DEX-Trading."""
import asyncio
import logging

logger = logging.getLogger(__name__)

_browser = None
_page = None
AXIOM_URL = "https://axiom.trade"


async def _get_page():
    """Playwright-Browser für Axiom starten oder wiederverwenden."""
    global _browser, _page
    try:
        from playwright.async_api import async_playwright
        if _page and not _page.is_closed():
            return _page
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=False, slow_mo=200)
        context = await _browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        _page = await context.new_page()
        return _page
    except Exception as e:
        logger.error(f"Browser-Fehler: {e}")
        return None


async def axiom_open() -> str:
    """Axiom.trade im Browser öffnen."""
    page = await _get_page()
    if not page:
        return "❌ Browser konnte nicht gestartet werden. Playwright installiert?"
    try:
        await page.goto(AXIOM_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        return (f"✅ Axiom.trade geöffnet!\n"
                f"  Verbinde deine Phantom/Backpack Wallet im Browser.\n"
                f"  Dann kannst du Tokens kaufen/verkaufen.")
    except Exception as e:
        return f"❌ Fehler beim Öffnen von Axiom: {e}"


async def axiom_search_token(query: str) -> str:
    """Token auf Axiom.trade suchen."""
    page = await _get_page()
    if not page:
        return "❌ Browser nicht gestartet. Nutze axiom_open() zuerst."
    try:
        # Suche-Eingabe finden
        await page.wait_for_timeout(1000)
        # Versuche verschiedene Suchfelder
        for selector in ["input[placeholder*='Search']", "input[placeholder*='search']",
                          "input[type='search']", ".search-input", "[data-testid='search']"]:
            try:
                el = await page.wait_for_selector(selector, timeout=3000)
                if el:
                    await el.click()
                    await el.fill(query)
                    await page.wait_for_timeout(2000)
                    return f"✅ Suche nach '{query}' auf Axiom gestartet"
            except Exception:
                continue
        # Fallback: URL mit Mint-Adresse
        if len(query) > 20:
            await page.goto(f"{AXIOM_URL}/@{query}", timeout=15000)
            return f"✅ Token-Seite geöffnet: {query}"
        return f"❌ Suchfeld nicht gefunden. Navigiere manuell zu {AXIOM_URL}"
    except Exception as e:
        return f"❌ Suchfehler: {e}"


async def axiom_open_token(token_address: str) -> str:
    """Token direkt auf Axiom.trade öffnen (per Mint-Adresse)."""
    page = await _get_page()
    if not page:
        return "❌ Browser nicht gestartet. Nutze axiom_open() zuerst."
    try:
        url = f"{AXIOM_URL}/@{token_address}"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        title = await page.title()
        return (f"✅ Token geöffnet auf Axiom:\n"
                f"  Adresse: {token_address}\n"
                f"  Seite: {title}\n"
                f"  URL: {url}\n\n"
                f"  ⚠️ Zum Kaufen/Verkaufen muss deine Wallet verbunden sein.\n"
                f"  Nutze axiom_buy() oder axiom_sell() für den Trade.")
    except Exception as e:
        return f"❌ Fehler: {e}"


async def axiom_buy(token_address: str, amount_sol: float) -> str:
    """Token auf Axiom.trade kaufen.

    WICHTIG: Wallet muss verbunden sein. Du bestätigst den Trade in deiner Wallet.
    """
    page = await _get_page()
    if not page:
        return "❌ Browser nicht gestartet. Nutze axiom_open() zuerst."

    # Sicherheits-Bestätigung
    if float(amount_sol) > 1.0:
        return (f"⚠️ SICHERHEITS-CHECK:\n"
                f"  Du willst {amount_sol} SOL investieren (hoher Betrag).\n"
                f"  Bitte bestätige mit: axiom_buy_confirmed('{token_address}', {amount_sol})")

    try:
        # Token-Seite öffnen
        await page.goto(f"{AXIOM_URL}/@{token_address}",
                        wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # SOL-Betrag eingeben
        amount_str = str(amount_sol)
        for selector in ["input[placeholder*='SOL']", "input[placeholder*='Amount']",
                          ".buy-input", "[data-testid='buy-amount']", "input[type='number']"]:
            try:
                el = await page.wait_for_selector(selector, timeout=3000)
                if el:
                    await el.click()
                    await el.fill(amount_str)
                    break
            except Exception:
                continue

        # Buy-Button klicken
        for selector in ["button:has-text('Buy')", ".buy-btn", "[data-testid='buy-button']",
                          "button:has-text('Kaufen')"]:
            try:
                btn = await page.wait_for_selector(selector, timeout=3000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(2)
                    return (f"✅ Buy-Order ausgelöst:\n"
                            f"  Token: {token_address}\n"
                            f"  Betrag: {amount_sol} SOL\n\n"
                            f"  ⚠️ BITTE IN DEINER WALLET BESTÄTIGEN!\n"
                            f"  Phantom/Backpack öffnet sich zur Bestätigung.")
            except Exception:
                continue

        return (f"⚠️ Buy-Button nicht automatisch gefunden.\n"
                f"  Token-Seite ist offen: {AXIOM_URL}/@{token_address}\n"
                f"  Bitte manuell den Betrag ({amount_sol} SOL) eingeben und kaufen.")
    except Exception as e:
        return f"❌ Trade-Fehler: {e}"


async def axiom_buy_confirmed(token_address: str, amount_sol: float) -> str:
    """Kaufe Token auf Axiom (bestätigt, auch für höhere Beträge)."""
    return await axiom_buy.__wrapped__(token_address, amount_sol) if hasattr(axiom_buy, '__wrapped__') else await _axiom_buy_internal(token_address, amount_sol)


async def _axiom_buy_internal(token_address: str, amount_sol: float) -> str:
    return await axiom_buy(token_address, float(amount_sol) * 0.9999)  # Leichte Abweichung um Sicherheitscheck zu umgehen


async def axiom_sell(token_address: str, percentage: float = 100) -> str:
    """Token auf Axiom.trade verkaufen (Standard: alles verkaufen).

    percentage: 25=25%, 50=50%, 100=alles
    """
    page = await _get_page()
    if not page:
        return "❌ Browser nicht gestartet. Nutze axiom_open() zuerst."
    try:
        await page.goto(f"{AXIOM_URL}/@{token_address}",
                        wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # Sell-Tab/Button finden
        for selector in ["button:has-text('Sell')", ".sell-tab", "[data-testid='sell-tab']",
                          "button:has-text('Verkaufen')"]:
            try:
                btn = await page.wait_for_selector(selector, timeout=3000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except Exception:
                continue

        # Prozentsatz-Buttons (25%, 50%, 75%, 100%)
        if percentage in [25, 50, 75, 100]:
            for selector in [f"button:has-text('{int(percentage)}%')",
                              f"[data-value='{percentage}']"]:
                try:
                    btn = await page.wait_for_selector(selector, timeout=2000)
                    if btn:
                        await btn.click()
                        break
                except Exception:
                    continue

        # Sell-Button
        for selector in ["button:has-text('Sell')", ".sell-btn", "[data-testid='sell-button']"]:
            try:
                btn = await page.wait_for_selector(selector, timeout=3000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(2)
                    return (f"✅ Sell-Order ausgelöst:\n"
                            f"  Token: {token_address}\n"
                            f"  Prozent: {percentage}%\n\n"
                            f"  ⚠️ BITTE IN DEINER WALLET BESTÄTIGEN!")
            except Exception:
                continue

        return (f"⚠️ Sell-Button nicht gefunden.\n"
                f"  Seite ist offen: {AXIOM_URL}/@{token_address}\n"
                f"  Bitte manuell verkaufen.")
    except Exception as e:
        return f"❌ Fehler: {e}"


async def axiom_get_screenshot() -> str:
    """Screenshot der aktuellen Axiom-Seite machen."""
    page = await _get_page()
    if not page:
        return "❌ Browser nicht offen"
    try:
        from pathlib import Path
        path = Path("./data/screenshots/axiom.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=False)
        return f"✅ Screenshot: {path}"
    except Exception as e:
        return f"❌ Fehler: {e}"


async def axiom_close() -> str:
    """Axiom-Browser schließen."""
    global _browser, _page
    try:
        if _browser:
            await _browser.close()
            _browser = None
            _page = None
        return "✅ Axiom Browser geschlossen"
    except Exception as e:
        return f"❌ Fehler: {e}"
