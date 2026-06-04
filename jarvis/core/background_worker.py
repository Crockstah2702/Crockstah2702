"""
Jarvis Hintergrundarbeiter — läuft autonom, überwacht, plant und handelt
eigenständig wie ein Mensch der im Hintergrund arbeitet.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

TASKS_FILE = Path("./data/background_tasks.json")


@dataclass
class BackgroundTask:
    id: str
    name: str
    description: str
    schedule: str          # "once", "every_5m", "every_1h", "daily", "on_startup"
    command: str           # Was Jarvis ausführen soll
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    result_log: list[str] = field(default_factory=list)


class BackgroundWorker:
    """Jarvis läuft ständig im Hintergrund und führt Aufgaben selbstständig aus."""

    def __init__(self, agent):
        self.agent = agent
        self._tasks: dict[str, BackgroundTask] = {}
        self._running = False
        self._session_id = "background"
        self._load_tasks()

    def _load_tasks(self):
        try:
            if TASKS_FILE.exists():
                data = json.loads(TASKS_FILE.read_text())
                for t in data:
                    task = BackgroundTask(**t)
                    self._tasks[task.id] = task
        except Exception:
            pass

    def _save_tasks(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        import dataclasses
        data = [dataclasses.asdict(t) for t in self._tasks.values()]
        TASKS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def add_task(self, name: str, description: str, schedule: str,
                  command: str) -> str:
        """Hintergrundaufgabe hinzufügen."""
        task_id = f"task_{datetime.now().timestamp():.0f}"
        task = BackgroundTask(
            id=task_id,
            name=name,
            description=description,
            schedule=schedule,
            command=command,
            next_run=datetime.now().isoformat()
        )
        self._tasks[task_id] = task
        self._save_tasks()
        return f"✅ Hintergrundaufgabe '{name}' hinzugefügt (ID: {task_id})"

    def remove_task(self, task_id: str) -> str:
        if task_id in self._tasks:
            name = self._tasks[task_id].name
            del self._tasks[task_id]
            self._save_tasks()
            return f"✅ Aufgabe '{name}' entfernt"
        return f"❌ Aufgabe '{task_id}' nicht gefunden"

    def list_tasks(self) -> str:
        if not self._tasks:
            return "Keine Hintergrundaufgaben."
        lines = []
        for t in self._tasks.values():
            status = "✅" if t.enabled else "⏸️"
            lines.append(f"{status} [{t.id}] {t.name} — {t.schedule}\n   {t.description}")
        return "\n".join(lines)

    def _should_run(self, task: BackgroundTask) -> bool:
        if not task.enabled:
            return False
        if not task.next_run:
            return True
        try:
            next_run = datetime.fromisoformat(task.next_run)
            return datetime.now() >= next_run
        except Exception:
            return True

    def _compute_next_run(self, schedule: str) -> str:
        now = datetime.now()
        intervals = {
            "every_1m": timedelta(minutes=1),
            "every_5m": timedelta(minutes=5),
            "every_15m": timedelta(minutes=15),
            "every_30m": timedelta(minutes=30),
            "every_1h": timedelta(hours=1),
            "every_6h": timedelta(hours=6),
            "every_12h": timedelta(hours=12),
            "daily": timedelta(days=1),
        }
        delta = intervals.get(schedule)
        if delta:
            return (now + delta).isoformat()
        return ""  # "once" → no next run

    async def _run_task(self, task: BackgroundTask):
        logger.info(f"Hintergrundaufgabe: {task.name}")
        try:
            # Stelle sicher, dass der Agent eine Session hat
            if not self.agent.current_session:
                self.agent.new_session()
            session = self.agent.current_session

            # Führe die Aufgabe über den Agenten aus
            prompt = (f"[HINTERGRUNDAUFGABE: {task.name}]\n"
                      f"Führe folgendes selbstständig aus: {task.command}\n"
                      f"Berichte kurz was du getan hast.")
            result = await self.agent.chat(prompt, session)
            task.result_log.append(f"{datetime.now().strftime('%H:%M:%S')}: {result[:200]}")
            task.result_log = task.result_log[-20:]  # Letzte 20 Logs behalten
            task.run_count += 1
            task.last_run = datetime.now().isoformat()
            task.next_run = self._compute_next_run(task.schedule)
            if not task.next_run:
                task.enabled = False  # "once" → deaktivieren nach Ausführung
            self._save_tasks()
        except Exception as e:
            logger.error(f"Hintergrundaufgabe Fehler ({task.name}): {e}")

    async def run_forever(self):
        """Läuft dauerhaft im Hintergrund und führt Aufgaben aus."""
        self._running = True
        logger.info("Hintergrundarbeiter gestartet")

        # Startup-Aufgaben sofort ausführen
        for task in list(self._tasks.values()):
            if task.schedule == "on_startup" and task.enabled:
                await self._run_task(task)

        while self._running:
            for task in list(self._tasks.values()):
                if self._should_run(task):
                    asyncio.create_task(self._run_task(task))
            await asyncio.sleep(30)  # Alle 30s prüfen

    def stop(self):
        self._running = False

    # Vordefinierte nützliche Hintergrundaufgaben
    def setup_default_tasks(self):
        defaults = [
            {
                "name": "PC-Kennenlernen",
                "description": "Beim Start: PC-Infos sammeln und im Gedächtnis speichern",
                "schedule": "on_startup",
                "command": (
                    "Führe folgende Befehle aus um den PC kennenzulernen, "
                    "und speichere die wichtigsten Infos als Fakten:\n"
                    "1. get_system_info() — OS, CPU, RAM, Festplatte\n"
                    "2. list_directory('~') — Was liegt im Home-Verzeichnis?\n"
                    "3. list_running_apps() — Welche Apps laufen?\n"
                    "Merke dir diese Infos für zukünftige Gespräche."
                )
            },
            {
                "name": "Systemüberwachung",
                "description": "Prüfe CPU/RAM alle 30min, warn bei hoher Auslastung",
                "schedule": "every_30m",
                "command": "Prüfe Systemressourcen. Wenn CPU > 90% oder RAM > 90%, erstelle eine Desktop-Benachrichtigung."
            },
        ]
        for d in defaults:
            if not any(t.name == d["name"] for t in self._tasks.values()):
                self.add_task(**d)
