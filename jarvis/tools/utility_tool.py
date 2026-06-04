"""Hilfsmittel: Timer, Übersetzung, QR-Codes, Passwörter, Base64, Git, Prozesse."""
import asyncio
import base64
import logging
import os
import platform
import secrets
import string
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Laufende Timer
_timers: dict[str, asyncio.Task] = {}


async def set_timer(minutes: float, message: str = "Timer abgelaufen!") -> str:
    """Setze einen Timer. ARIA benachrichtigt nach X Minuten."""
    timer_id = f"timer_{len(_timers)+1}"
    seconds = float(minutes) * 60

    async def _run():
        await asyncio.sleep(seconds)
        # Desktop-Benachrichtigung
        sys_os = platform.system()
        try:
            if sys_os == "Linux":
                await asyncio.create_subprocess_exec(
                    "notify-send", "⏰ ARIA Timer", message
                )
            elif sys_os == "Darwin":
                await asyncio.create_subprocess_exec(
                    "osascript", "-e",
                    f'display notification "{message}" with title "⏰ ARIA Timer"'
                )
        except Exception:
            pass
        logger.info(f"Timer '{timer_id}' abgelaufen: {message}")
        _timers.pop(timer_id, None)

    task = asyncio.create_task(_run())
    _timers[timer_id] = task
    return f"✅ Timer gesetzt: {minutes} Minute(n) — '{message}' [{timer_id}]"


def cancel_timer(timer_id: str = "") -> str:
    """Storniere einen laufenden Timer."""
    if not timer_id and _timers:
        # Stoppe den letzten Timer
        tid, task = list(_timers.items())[-1]
        task.cancel()
        _timers.pop(tid)
        return f"✅ Timer '{tid}' gestoppt"
    if timer_id in _timers:
        _timers[timer_id].cancel()
        _timers.pop(timer_id)
        return f"✅ Timer '{timer_id}' gestoppt"
    return f"Timer '{timer_id}' nicht gefunden. Aktive Timer: {list(_timers.keys())}"


def list_timers() -> str:
    """Zeige alle aktiven Timer."""
    if not _timers:
        return "Keine aktiven Timer."
    return "Aktive Timer:\n" + "\n".join(f"  - {tid}" for tid in _timers.keys())


def translate_text(text: str, target_language: str = "de",
                   source_language: str = "auto") -> str:
    """Übersetze Text in eine Zielsprache (ohne API-Key)."""
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source=source_language, target=target_language)
        result = translator.translate(text)
        return f"Übersetzung ({source_language} → {target_language}):\n{result}"
    except ImportError:
        return "❌ deep-translator nicht installiert: pip install deep-translator"
    except Exception as e:
        return f"❌ Übersetzungsfehler: {e}"


def generate_password(length: int = 16, special_chars: bool = True,
                       numbers: bool = True, uppercase: bool = True) -> str:
    """Generiere ein sicheres Passwort."""
    chars = string.ascii_lowercase
    if uppercase:
        chars += string.ascii_uppercase
    if numbers:
        chars += string.digits
    if special_chars:
        chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
    pwd = "".join(secrets.choice(chars) for _ in range(int(length)))
    strength = "Schwach"
    if length >= 12 and special_chars and numbers:
        strength = "Sehr stark"
    elif length >= 10:
        strength = "Stark"
    elif length >= 8:
        strength = "Mittel"
    return f"Passwort ({length} Zeichen, {strength}):\n  {pwd}"


def encode_base64(text: str) -> str:
    """Kodiere Text als Base64."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"Base64-kodiert:\n{encoded}"


def decode_base64(text: str) -> str:
    """Dekodiere Base64-Text."""
    try:
        decoded = base64.b64decode(text).decode("utf-8")
        return f"Dekodiert:\n{decoded}"
    except Exception as e:
        return f"❌ Base64-Fehler: {e}"


def generate_qr(text: str, output_path: str = "~/jarvis_files/qrcode.png") -> str:
    """Erstelle einen QR-Code aus Text oder URL."""
    try:
        import qrcode
        from PIL import Image
        p = Path(os.path.expanduser(output_path))
        p.parent.mkdir(parents=True, exist_ok=True)
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(p))
        return f"✅ QR-Code erstellt: {p}\n   Inhalt: {text[:60]}"
    except ImportError:
        return "❌ qrcode nicht installiert: pip install qrcode[pil]"
    except Exception as e:
        return f"❌ QR-Fehler: {e}"


def kill_process(name_or_pid: str) -> str:
    """Beende einen laufenden Prozess nach Name oder PID."""
    try:
        import psutil
        killed = []
        # Versuche als PID
        try:
            pid = int(name_or_pid)
            proc = psutil.Process(pid)
            pname = proc.name()
            proc.terminate()
            killed.append(f"{pname} (PID {pid})")
        except ValueError:
            # Nach Name suchen
            for proc in psutil.process_iter(["pid", "name"]):
                if name_or_pid.lower() in proc.info["name"].lower():
                    proc.terminate()
                    killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
        if killed:
            return f"✅ Prozesse beendet: {', '.join(killed)}"
        return f"❌ Kein Prozess '{name_or_pid}' gefunden"
    except ImportError:
        return "❌ psutil nicht installiert: pip install psutil"
    except Exception as e:
        return f"❌ Fehler: {e}"


def git_status(repo_path: str = ".") -> str:
    """Zeige den Git-Status eines Repositories."""
    try:
        p = Path(os.path.expanduser(repo_path))
        result = subprocess.run(
            ["git", "-C", str(p), "status"],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"❌ Git-Fehler: {e}"


def git_log(repo_path: str = ".", n: int = 10) -> str:
    """Zeige die letzten Git-Commits."""
    try:
        p = Path(os.path.expanduser(repo_path))
        result = subprocess.run(
            ["git", "-C", str(p), "log", f"--max-count={n}",
             "--pretty=format:%h %ad %s (%an)", "--date=short"],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr or "Keine Commits gefunden"
    except Exception as e:
        return f"❌ Git-Fehler: {e}"


def git_commit(repo_path: str, message: str, files: list = None) -> str:
    """Erstelle einen Git-Commit."""
    try:
        p = Path(os.path.expanduser(repo_path))
        # Stage files
        if files:
            for f in files:
                subprocess.run(["git", "-C", str(p), "add", f], capture_output=True)
        else:
            subprocess.run(["git", "-C", str(p), "add", "-A"], capture_output=True)
        # Commit
        result = subprocess.run(
            ["git", "-C", str(p), "commit", "-m", message],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"❌ Git-Fehler: {e}"


def git_clone(url: str, destination: str = "") -> str:
    """Klone ein Git-Repository."""
    try:
        args = ["git", "clone", url]
        if destination:
            args.append(os.path.expanduser(destination))
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "❌ Timeout beim Klonen"
    except Exception as e:
        return f"❌ Fehler: {e}"


def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Berechne den Hash eines Textes."""
    import hashlib
    try:
        h = hashlib.new(algorithm)
        h.update(text.encode("utf-8"))
        return f"{algorithm.upper()}-Hash:\n{h.hexdigest()}"
    except ValueError:
        algos = ", ".join(sorted(hashlib.algorithms_available)[:10])
        return f"❌ Algorithmus '{algorithm}' nicht verfügbar. Verfügbar: {algos}"


def get_date_time(timezone: str = "local") -> str:
    """Zeige das aktuelle Datum und die Uhrzeit."""
    from datetime import datetime
    import time
    now = datetime.now()
    utc = datetime.utcnow()
    return (f"Aktuelle Zeit:\n"
            f"  Lokal:  {now.strftime('%A, %d. %B %Y %H:%M:%S')}\n"
            f"  UTC:    {utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"  Unix:   {int(time.time())}")


def count_words(text: str) -> str:
    """Zähle Wörter, Zeichen und Sätze in einem Text."""
    words = len(text.split())
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", ""))
    sentences = text.count(".") + text.count("!") + text.count("?")
    return (f"Text-Statistik:\n"
            f"  Wörter: {words}\n"
            f"  Zeichen: {chars} (ohne Leerzeichen: {chars_no_spaces})\n"
            f"  Sätze (ca.): {sentences}\n"
            f"  Lesezeit (ca.): {words//200 + 1} Minute(n)")
