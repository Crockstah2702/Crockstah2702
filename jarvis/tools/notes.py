"""Notes and todo management tool."""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NOTES_DIR = Path("./data/notes")
TODOS_FILE = Path("./data/todos.json")


def _ensure_dirs():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    TODOS_FILE.parent.mkdir(parents=True, exist_ok=True)


def create_note(title: str, content: str, tags: str = "") -> str:
    """Create a new note."""
    _ensure_dirs()
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title[:30].replace(' ', '_')}.md"
    filepath = NOTES_DIR / filename
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    note_content = f"# {title}\n\n"
    if tag_list:
        note_content += f"**Tags:** {', '.join(tag_list)}\n"
    note_content += f"**Erstellt:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    note_content += content
    filepath.write_text(note_content, encoding="utf-8")
    return f"Notiz erstellt: {filename}"


def list_notes(search: str = "") -> str:
    """List all notes, optionally filtered by search term."""
    _ensure_dirs()
    notes = []
    for f in sorted(NOTES_DIR.glob("*.md"), reverse=True):
        if search.lower() in f.read_text(errors="replace").lower() if search else True:
            size = f.stat().st_size
            notes.append(f"📝 {f.stem} ({size} B)")
    if not notes:
        return "Keine Notizen vorhanden."
    return f"Notizen ({len(notes)}):\n" + "\n".join(notes[:20])


def read_note(title: str) -> str:
    """Read a note by title (partial match)."""
    _ensure_dirs()
    title_lower = title.lower()
    for f in NOTES_DIR.glob("*.md"):
        if title_lower in f.stem.lower():
            return f.read_text(encoding="utf-8")
    return f"Keine Notiz gefunden für: '{title}'"


def add_todo(task: str, priority: str = "normal") -> str:
    """Add a todo item."""
    _ensure_dirs()
    todos = _load_todos()
    todo = {
        "id": len(todos) + 1,
        "task": task,
        "priority": priority,
        "done": False,
        "created": datetime.now().isoformat()
    }
    todos.append(todo)
    _save_todos(todos)
    return f"Todo hinzugefügt #{todo['id']}: {task}"


def list_todos(show_done: bool = False) -> str:
    """List all todos."""
    todos = _load_todos()
    if not todos:
        return "Keine Todos vorhanden. 🎉"
    filtered = todos if show_done else [t for t in todos if not t["done"]]
    if not filtered:
        return "Alle Todos erledigt! 🎉"
    lines = []
    for t in filtered:
        status = "✅" if t["done"] else "⬜"
        prio = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(t["priority"], "🟡")
        lines.append(f"{status} {prio} #{t['id']}: {t['task']}")
    return f"Todos ({len(filtered)}):\n" + "\n".join(lines)


def complete_todo(todo_id: int) -> str:
    """Mark a todo as done."""
    todos = _load_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = True
            t["completed_at"] = datetime.now().isoformat()
            _save_todos(todos)
            return f"Todo #{todo_id} als erledigt markiert: {t['task']}"
    return f"Todo #{todo_id} nicht gefunden."


def _load_todos() -> list:
    if TODOS_FILE.exists():
        try:
            return json.loads(TODOS_FILE.read_text())
        except Exception:
            return []
    return []


def _save_todos(todos: list):
    TODOS_FILE.write_text(json.dumps(todos, ensure_ascii=False, indent=2))
