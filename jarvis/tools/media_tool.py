"""Medien abspielen, Lautstärke steuern, Audio-Tools."""
import asyncio
import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)

_current_process = None


async def play_media(path_or_url: str) -> str:
    """Spiele eine Audio- oder Videodatei ab (lokal oder URL)."""
    global _current_process
    sys_os = platform.system()

    # Stoppe vorherigen Player
    await stop_media()

    try:
        if sys_os == "Windows":
            os.startfile(path_or_url)
            return f"✅ Medien geöffnet: {path_or_url}"
        elif sys_os == "Darwin":
            _current_process = await asyncio.create_subprocess_exec(
                "open", path_or_url)
        else:  # Linux
            for player in ["vlc", "mpv", "cvlc", "xdg-open"]:
                if _which(player):
                    _current_process = await asyncio.create_subprocess_exec(
                        player, path_or_url,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    return f"✅ Medien werden abgespielt mit {player}: {path_or_url}"
        return f"✅ Medien geöffnet: {path_or_url}"
    except Exception as e:
        return f"❌ Fehler beim Abspielen: {e}"


async def stop_media() -> str:
    """Stoppe die aktuelle Medienwiedergabe."""
    global _current_process
    if _current_process:
        try:
            _current_process.terminate()
            _current_process = None
            return "✅ Wiedergabe gestoppt"
        except Exception as e:
            return f"❌ Fehler: {e}"
    return "ℹ️ Nichts läuft gerade"


def get_volume() -> str:
    """Lese die aktuelle Systemlautstärke aus."""
    sys_os = platform.system()
    try:
        if sys_os == "Linux":
            result = subprocess.run(
                ["amixer", "sget", "Master"],
                capture_output=True, text=True
            )
            import re
            match = re.search(r'\[(\d+)%\]', result.stdout)
            vol = match.group(1) if match else "unbekannt"
            muted = "[off]" in result.stdout
            return f"Lautstärke: {vol}% {'(stumm)' if muted else ''}"
        elif sys_os == "Darwin":
            result = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True, text=True
            )
            return f"Lautstärke: {result.stdout.strip()}%"
        elif sys_os == "Windows":
            return "Lautstärke-Abfrage auf Windows erfordert pywin32"
    except Exception as e:
        return f"❌ Fehler: {e}"
    return "Lautstärke: unbekannt"


def set_volume(level: int) -> str:
    """Setze die Systemlautstärke (0-100)."""
    level = max(0, min(100, int(level)))
    sys_os = platform.system()
    try:
        if sys_os == "Linux":
            subprocess.run(
                ["amixer", "sset", "Master", f"{level}%"],
                capture_output=True
            )
            return f"✅ Lautstärke auf {level}% gesetzt"
        elif sys_os == "Darwin":
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {level}"]
            )
            return f"✅ Lautstärke auf {level}% gesetzt"
        elif sys_os == "Windows":
            # Über Tastenkombination annähern
            return "❌ Windows Lautstärke: bitte manuell über Systemeinstellungen"
    except Exception as e:
        return f"❌ Fehler: {e}"
    return f"✅ Lautstärke gesetzt: {level}%"


def mute_volume() -> str:
    """Schalte den Ton stumm."""
    sys_os = platform.system()
    try:
        if sys_os == "Linux":
            subprocess.run(["amixer", "sset", "Master", "mute"], capture_output=True)
            return "✅ Stumm geschaltet"
        elif sys_os == "Darwin":
            subprocess.run(["osascript", "-e", "set volume output muted true"])
            return "✅ Stumm geschaltet"
    except Exception as e:
        return f"❌ Fehler: {e}"
    return "✅ Stumm geschaltet"


def unmute_volume() -> str:
    """Hebe die Stummschaltung auf."""
    sys_os = platform.system()
    try:
        if sys_os == "Linux":
            subprocess.run(["amixer", "sset", "Master", "unmute"], capture_output=True)
            return "✅ Stummschaltung aufgehoben"
        elif sys_os == "Darwin":
            subprocess.run(["osascript", "-e", "set volume output muted false"])
            return "✅ Stummschaltung aufgehoben"
    except Exception as e:
        return f"❌ Fehler: {e}"
    return "✅ Stummschaltung aufgehoben"


def list_media_files(directory: str = "~") -> str:
    """Liste alle Mediendateien in einem Verzeichnis auf."""
    import os
    from pathlib import Path
    base = Path(os.path.expanduser(directory))
    media_ext = {".mp3", ".mp4", ".wav", ".flac", ".ogg", ".avi", ".mkv",
                 ".mov", ".m4a", ".aac", ".wma", ".webm", ".m4v"}
    try:
        files = []
        for f in base.rglob("*"):
            if f.suffix.lower() in media_ext:
                size_mb = f.stat().st_size / (1024*1024)
                files.append(f"  {f.name} ({size_mb:.1f} MB) — {f}")
        if not files:
            return f"Keine Mediendateien in {base}"
        return f"Mediendateien in {base} ({len(files)}):\n" + "\n".join(files[:30])
    except Exception as e:
        return f"❌ Fehler: {e}"


def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None
