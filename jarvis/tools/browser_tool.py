"""
Browser-Automatisierung — Jarvis kann den Browser steuern:
Webseiten öffnen, Formulare ausfüllen, Klicken, Screenshots machen.
Nutzt Playwright (muss installiert sein: playwright install chromium).
"""
import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_browser = None
_page = None
SCREENSHOT_DIR = Path("./data/screenshots")


async def _get_page():
    global _browser, _page
    try:
        from playwright.async_api import async_playwright
        if _page is None or _browser is None:
            p = await async_playwright().start()
            _browser = await p.chromium.launch(headless=False)  # headless=False = sichtbar
            _page = await _browser.new_page()
            await _page.set_viewport_size({"width": 1280, "height": 800})
        return _page
    except ImportError:
        return None


async def browser_open(url: str) -> str:
    """Öffne eine URL im Browser."""
    page = await _get_page()
    if not page:
        return ("Playwright nicht installiert.\n"
                "Installieren mit:\n"
                "  pip install playwright\n"
                "  playwright install chromium")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        return f"✅ Geöffnet: {url}\nTitel: {title}"
    except Exception as e:
        return f"❌ Browser-Fehler: {e}"


async def browser_click(selector_or_text: str) -> str:
    """Klicke auf ein Element (CSS-Selektor oder sichtbaren Text)."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    try:
        # Erst Text versuchen
        try:
            await page.get_by_text(selector_or_text, exact=False).first.click(timeout=5000)
            return f"✅ Geklickt auf: '{selector_or_text}'"
        except Exception:
            await page.click(selector_or_text, timeout=5000)
            return f"✅ Element geklickt: {selector_or_text}"
    except Exception as e:
        return f"❌ Klick-Fehler: {e}"


async def browser_type(selector: str, text: str) -> str:
    """Tippe Text in ein Eingabefeld."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    try:
        await page.fill(selector, text)
        return f"✅ Text eingegeben in {selector}: '{text}'"
    except Exception:
        try:
            await page.type(selector, text)
            return f"✅ Text getippt: '{text}'"
        except Exception as e:
            return f"❌ Tipp-Fehler: {e}"


async def browser_get_text() -> str:
    """Lese den sichtbaren Text der aktuellen Seite."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    try:
        # Entferne Script/Style
        text = await page.evaluate("""() => {
            const el = document.body.cloneNode(true);
            el.querySelectorAll('script,style,nav,footer').forEach(e => e.remove());
            return el.innerText;
        }""")
        lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 15]
        return "\n".join(lines[:100])
    except Exception as e:
        return f"❌ Text-Fehler: {e}"


async def browser_screenshot(filename: str = "screenshot.png") -> str:
    """Mache einen Screenshot der aktuellen Seite."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / filename
        await page.screenshot(path=str(path), full_page=False)
        return f"✅ Screenshot gespeichert: {path}"
    except Exception as e:
        return f"❌ Screenshot-Fehler: {e}"


async def browser_fill_form(fields: dict) -> str:
    """Fülle mehrere Formularfelder aus. fields = {selector: value}"""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    results = []
    for selector, value in fields.items():
        try:
            await page.fill(selector, str(value))
            results.append(f"✅ {selector}: '{value}'")
        except Exception as e:
            results.append(f"❌ {selector}: {e}")
    return "\n".join(results)


async def browser_scroll(direction: str = "down", amount: int = 500) -> str:
    """Scrolle die Seite."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    y = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy(0, {y})")
    return f"Gescrollt {direction} um {amount}px"


async def browser_wait(ms: int = 1000) -> str:
    """Warte eine bestimmte Zeit."""
    await asyncio.sleep(ms / 1000)
    return f"Gewartet {ms}ms"


async def browser_get_url() -> str:
    """Gib die aktuelle URL zurück."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    return page.url


async def browser_press_key(key: str) -> str:
    """Drücke eine Taste (Enter, Tab, Escape, etc.)."""
    page = await _get_page()
    if not page:
        return "Browser nicht verfügbar."
    try:
        await page.keyboard.press(key)
        return f"✅ Taste gedrückt: {key}"
    except Exception as e:
        return f"❌ Tastenfehler: {e}"


async def browser_close() -> str:
    """Schließe den Browser."""
    global _browser, _page
    try:
        if _browser:
            await _browser.close()
            _browser = None
            _page = None
        return "✅ Browser geschlossen"
    except Exception as e:
        return f"❌ Fehler: {e}"
