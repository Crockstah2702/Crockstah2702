"""Maus, Tastatur und Bildschirmsteuerung via PyAutoGUI."""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _get_pyautogui():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True   # Maus in obere linke Ecke = Notfall-Stop
        pyautogui.PAUSE = 0.1
        return pyautogui
    except ImportError:
        return None


def mouse_click(x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> str:
    """Klicke mit der Maus an einer Position (oder aktuelle Position)."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert: pip install pyautogui"
    try:
        if x is not None and y is not None:
            pg.click(x, y, button=button, clicks=clicks)
            return f"✅ Klick ({button}) an Position ({x}, {y})"
        else:
            pos = pg.position()
            pg.click(button=button, clicks=clicks)
            return f"✅ Klick ({button}) an aktueller Position ({pos.x}, {pos.y})"
    except Exception as e:
        return f"❌ Klick-Fehler: {e}"


def mouse_double_click(x: int, y: int) -> str:
    """Doppelklick an einer Position."""
    return mouse_click(x, y, clicks=2)


def mouse_right_click(x: int, y: int) -> str:
    """Rechtsklick an einer Position."""
    return mouse_click(x, y, button="right")


def mouse_move(x: int, y: int, duration: float = 0.3) -> str:
    """Bewege die Maus zu einer Position."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        pg.moveTo(x, y, duration=duration)
        return f"✅ Maus bewegt zu ({x}, {y})"
    except Exception as e:
        return f"❌ Fehler: {e}"


def mouse_drag(from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5) -> str:
    """Drag & Drop von einer Position zur anderen."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        pg.dragTo(to_x, to_y, duration=duration)
        return f"✅ Drag von ({from_x},{from_y}) nach ({to_x},{to_y})"
    except Exception as e:
        return f"❌ Fehler: {e}"


def mouse_scroll(amount: int = 3, direction: str = "down") -> str:
    """Scrolle mit der Maus."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        clicks = -amount if direction == "down" else amount
        pg.scroll(clicks)
        return f"✅ Gescrollt ({direction}, {amount})"
    except Exception as e:
        return f"❌ Fehler: {e}"


def type_text(text: str, interval: float = 0.03) -> str:
    """Schreibe Text via Tastatur (an aktueller Cursor-Position)."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        pg.typewrite(text, interval=interval)
        return f"✅ Text getippt: '{text[:50]}{'...' if len(text)>50 else ''}'"
    except Exception as e:
        # Fallback für Sonderzeichen
        try:
            import subprocess
            subprocess.run(["xdotool", "type", "--", text])
            return f"✅ Text via xdotool getippt"
        except Exception:
            return f"❌ Fehler: {e}"


def key_press(keys: str) -> str:
    """Drücke eine Taste oder Tastenkombination (z.B. 'ctrl+c', 'alt+tab', 'enter', 'win')."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        # Kombinationen wie 'ctrl+c' aufteilen
        if '+' in keys:
            parts = [k.strip().lower() for k in keys.split('+')]
            pg.hotkey(*parts)
        else:
            pg.press(keys.lower())
        return f"✅ Taste gedrückt: {keys}"
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_mouse_position() -> str:
    """Gibt die aktuelle Mausposition zurück."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        pos = pg.position()
        return f"Aktuelle Mausposition: X={pos.x}, Y={pos.y}"
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_screen_size() -> str:
    """Gibt die Bildschirmauflösung zurück."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        size = pg.size()
        return f"Bildschirmauflösung: {size.width} x {size.height} Pixel"
    except Exception as e:
        return f"❌ Fehler: {e}"


def find_on_screen(image_path: str, confidence: float = 0.8) -> str:
    """Suche ein Bild auf dem Bildschirm und gib seine Position zurück."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        location = pg.locateOnScreen(image_path, confidence=confidence)
        if location:
            center = pg.center(location)
            return f"✅ Gefunden an: X={center.x}, Y={center.y} (Bereich: {location})"
        return f"❌ Bild nicht auf dem Bildschirm gefunden: {image_path}"
    except Exception as e:
        return f"❌ Fehler: {e}"


def click_on_image(image_path: str, confidence: float = 0.8) -> str:
    """Suche ein Bild auf dem Bildschirm und klicke darauf."""
    pg = _get_pyautogui()
    if not pg:
        return "❌ pyautogui nicht installiert"
    try:
        location = pg.locateOnScreen(image_path, confidence=confidence)
        if location:
            center = pg.center(location)
            pg.click(center.x, center.y)
            return f"✅ Auf Bild geklickt an ({center.x}, {center.y})"
        return f"❌ Bild nicht gefunden: {image_path}"
    except Exception as e:
        return f"❌ Fehler: {e}"
