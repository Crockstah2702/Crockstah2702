"""Erweiterte System-Tools: Apps starten, Befehle, Zwischenablage, Benachrichtigungen."""
import asyncio
import logging
import os
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)


async def run_command(command: str, timeout: int = 30) -> str:
    """Führe einen Shell-Befehl aus und gib das Ergebnis zurück."""
    # Sicherheits-Blockliste
    blocked = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:", "format c:"]
    for b in blocked:
        if b in command.lower():
            return f"❌ Blockierter Befehl: '{b}' ist nicht erlaubt."
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if result and err:
            return f"Output:\n{result}\n\nFehler:\n{err}"
        return result or err or "(kein Output)"
    except asyncio.TimeoutError:
        return f"❌ Zeitüberschreitung nach {timeout}s"
    except Exception as e:
        return f"❌ Fehler: {e}"


async def open_application(app_name: str) -> str:
    """Starte eine Anwendung."""
    sys_os = platform.system()
    try:
        if sys_os == "Windows":
            os.startfile(app_name)
        elif sys_os == "Darwin":
            await asyncio.create_subprocess_exec("open", "-a", app_name)
        else:  # Linux
            proc = await asyncio.create_subprocess_exec(
                app_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
        return f"✅ Anwendung gestartet: {app_name}"
    except Exception as e:
        return f"❌ Fehler beim Starten von {app_name}: {e}"


async def open_url_in_browser(url: str) -> str:
    """Öffne eine URL im Standard-Browser."""
    import webbrowser
    webbrowser.open(url)
    return f"✅ URL im Browser geöffnet: {url}"


def get_clipboard() -> str:
    """Lese den Inhalt der Zwischenablage."""
    try:
        import subprocess
        sys_os = platform.system()
        if sys_os == "Windows":
            import win32clipboard
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            return data
        elif sys_os == "Darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return result.stdout
        else:
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout
            result = subprocess.run(["xsel", "--clipboard", "--output"],
                                    capture_output=True, text=True)
            return result.stdout
    except Exception as e:
        return f"Zwischenablage nicht verfügbar: {e}"


def set_clipboard(text: str) -> str:
    """Schreibe Text in die Zwischenablage."""
    try:
        sys_os = platform.system()
        if sys_os == "Windows":
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text)
            win32clipboard.CloseClipboard()
        elif sys_os == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        else:
            proc = subprocess.run(["xclip", "-selection", "clipboard"],
                                  input=text.encode(), capture_output=True)
            if proc.returncode != 0:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode())
        return f"✅ In Zwischenablage kopiert: '{text[:50]}...'" if len(text) > 50 else f"✅ In Zwischenablage: '{text}'"
    except Exception as e:
        return f"❌ Zwischenablage-Fehler: {e}"


async def send_desktop_notification(title: str, message: str,
                                     urgency: str = "normal") -> str:
    """Sende eine Desktop-Benachrichtigung."""
    sys_os = platform.system()
    try:
        if sys_os == "Windows":
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5)
        elif sys_os == "Darwin":
            await asyncio.create_subprocess_exec(
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"'
            )
        else:
            await asyncio.create_subprocess_exec(
                "notify-send", f"--urgency={urgency}", title, message
            )
        return f"✅ Benachrichtigung gesendet: {title}"
    except Exception as e:
        return f"❌ Benachrichtigungsfehler: {e}"


def list_running_apps() -> str:
    """Liste laufende Anwendungen auf."""
    try:
        import psutil
        apps = set()
        for p in psutil.process_iter(["name"]):
            name = p.info.get("name", "")
            if name and not name.startswith("["):
                apps.add(name)
        return "Laufende Anwendungen:\n" + "\n".join(sorted(apps)[:30])
    except Exception as e:
        return f"Fehler: {e}"


async def take_screenshot(filename: str = "desktop_screenshot.png") -> str:
    """Screenshot vom Desktop machen."""
    from pathlib import Path
    SCREENSHOT_DIR = Path("./data/screenshots")
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / filename
    try:
        import pyautogui
        pyautogui.screenshot(str(path))
        return f"✅ Desktop-Screenshot: {path}"
    except ImportError:
        # Fallback
        sys_os = platform.system()
        try:
            if sys_os == "Darwin":
                await asyncio.create_subprocess_exec("screencapture", str(path))
            elif sys_os == "Linux":
                await asyncio.create_subprocess_exec("scrot", str(path))
            else:
                return "❌ pyautogui nicht installiert: pip install pyautogui"
            return f"✅ Screenshot gespeichert: {path}"
        except Exception as e:
            return f"❌ Screenshot-Fehler: {e}"
