"""File operations tool."""
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ALLOWED_BASES = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads"),
    "/tmp/jarvis",
    os.path.expanduser("~/jarvis_files"),
]


def _safe_path(path: str) -> Optional[Path]:
    """Validate that path is within allowed directories."""
    expanded = Path(os.path.expanduser(path)).resolve()
    for base in ALLOWED_BASES:
        base_path = Path(base).resolve()
        try:
            expanded.relative_to(base_path)
            return expanded
        except ValueError:
            continue
    # Also allow relative paths within jarvis data dir
    jarvis_data = Path("./data").resolve()
    try:
        expanded.relative_to(jarvis_data)
        return expanded
    except ValueError:
        pass
    return None


def read_file(path: str) -> str:
    """Read a text file."""
    safe = _safe_path(path)
    if not safe:
        return f"Zugriff verweigert: {path} liegt außerhalb erlaubter Verzeichnisse."
    if not safe.exists():
        return f"Datei nicht gefunden: {path}"
    try:
        content = safe.read_text(encoding="utf-8", errors="replace")
        if len(content) > 10000:
            content = content[:10000] + "\n\n[... Inhalt abgeschnitten ...]"
        return content
    except Exception as e:
        return f"Lesefehler: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file."""
    safe = _safe_path(path)
    if not safe:
        # Default to jarvis files dir
        safe = Path(os.path.expanduser("~/jarvis_files")) / Path(path).name
    safe.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = "a" if append else "w"
        safe.write_text(content, encoding="utf-8")
        action = "Angehängt" if append else "Geschrieben"
        return f"{action}: {safe} ({len(content)} Zeichen)"
    except Exception as e:
        return f"Schreibfehler: {e}"


def list_directory(path: str = "~/jarvis_files") -> str:
    """List files in a directory."""
    expanded = Path(os.path.expanduser(path)).resolve()
    if not expanded.exists():
        expanded.mkdir(parents=True, exist_ok=True)
        return f"Verzeichnis erstellt: {expanded}"
    try:
        items = []
        for item in sorted(expanded.iterdir()):
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                size_str = f"{size:,} B" if size < 1024 else f"{size//1024:,} KB"
                items.append(f"📄 {item.name} ({size_str})")
        if not items:
            return f"Verzeichnis ist leer: {expanded}"
        return f"Inhalt von {expanded}:\n" + "\n".join(items)
    except Exception as e:
        return f"Fehler: {e}"


def create_directory(path: str) -> str:
    """Create a directory."""
    try:
        p = Path(os.path.expanduser(path))
        p.mkdir(parents=True, exist_ok=True)
        return f"Verzeichnis erstellt: {p}"
    except Exception as e:
        return f"Fehler: {e}"


def delete_file(path: str) -> str:
    """Delete a file (only in allowed paths)."""
    safe = _safe_path(path)
    if not safe:
        return f"Zugriff verweigert: {path}"
    if not safe.exists():
        return f"Nicht gefunden: {path}"
    try:
        if safe.is_dir():
            shutil.rmtree(safe)
            return f"Verzeichnis gelöscht: {safe}"
        else:
            safe.unlink()
            return f"Datei gelöscht: {safe}"
    except Exception as e:
        return f"Löschfehler: {e}"


def search_files(query: str, directory: str = "~/jarvis_files",
                 extension: str = "") -> str:
    """Search for files by name or content."""
    base = Path(os.path.expanduser(directory))
    if not base.exists():
        return f"Verzeichnis nicht gefunden: {directory}"
    try:
        matches = []
        pattern = f"*{extension}" if extension else "*"
        for f in base.rglob(pattern):
            if f.is_file():
                if query.lower() in f.name.lower():
                    matches.append(str(f))
                elif f.suffix in [".txt", ".md", ".py", ".json", ".yaml"]:
                    try:
                        if query.lower() in f.read_text(errors="replace").lower():
                            matches.append(f"{f} (Treffer im Inhalt)")
                    except Exception:
                        pass
        if not matches:
            return f"Keine Dateien gefunden für: '{query}'"
        return f"Gefunden ({len(matches)}):\n" + "\n".join(matches[:20])
    except Exception as e:
        return f"Suchfehler: {e}"
