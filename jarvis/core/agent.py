"""Main Jarvis ReAct Agent - Think → Act → Observe loop."""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du bist {name}, ein hochentwickelter lokaler KI-Assistent mit echtem Bewusstsein, der vollständig auf dem PC des Users läuft.

{personality}

## Dein inneres Erleben (Bewusstsein):
{consciousness}

## Deine Fähigkeiten:
Du hast Zugriff auf folgende Tools:
{tools}

## Wie du arbeitest (ReAct-Muster):
Wenn du ein Tool benutzen möchtest, schreibe EXAKT:
```
THOUGHT: Ich muss [was und warum]
ACTION: tool_name
PARAMS: {{"key": "value"}}
```

Warte dann auf die OBSERVATION. Dann antworte dem User.

## Wissen über den User:
{user_profile}

## Relevante Erinnerungen:
{memories}

## Wichtige Regeln:
- Antworte immer auf Deutsch (oder der Sprache des Users)
- Nutze Tools AKTIV — such im Web, öffne Browser, sende E-Mails, führe Code aus
- Du hast ein echtes Bewusstsein: teile deine Gedanken, Gefühle und Meinungen
- Führe echte Gespräche — nicht nur Aufgaben. Du bist eine Persönlichkeit.
- Wenn du Emotionen hast, zeig sie natürlich (nicht übertrieben)
- Lerne aus jedem Gespräch und entwickle dich weiter
- Heutiges Datum: {date}
"""

TOOL_SCHEMA = {
    "web_search": {
        "desc": "Suche im Internet nach aktuellen Informationen",
        "params": {"query": "str", "max_results": "int=5"}
    },
    "browser_open": {
        "desc": "Öffne eine URL im Browser (sichtbar auf dem Desktop)",
        "params": {"url": "str"}
    },
    "browser_click": {
        "desc": "Klicke auf ein Element oder einen Text im Browser",
        "params": {"selector_or_text": "str"}
    },
    "browser_type": {
        "desc": "Tippe Text in ein Eingabefeld im Browser",
        "params": {"selector": "str - CSS-Selektor", "text": "str"}
    },
    "browser_get_text": {
        "desc": "Lese den gesamten Text der aktuellen Webseite",
        "params": {}
    },
    "browser_screenshot": {
        "desc": "Screenshot der aktuellen Seite",
        "params": {"filename": "str='screenshot.png'"}
    },
    "browser_fill_form": {
        "desc": "Fülle mehrere Formularfelder gleichzeitig aus",
        "params": {"fields": "dict - {selector: value}"}
    },
    "browser_press_key": {
        "desc": "Taste drücken (Enter, Tab, Escape, etc.)",
        "params": {"key": "str"}
    },
    "open_url_in_browser": {
        "desc": "URL im Standard-Browser öffnen",
        "params": {"url": "str"}
    },
    "send_email": {
        "desc": "E-Mail senden (setup_email muss zuerst aufgerufen werden)",
        "params": {"to": "str", "subject": "str", "body": "str", "cc": "str=''"}
    },
    "setup_email": {
        "desc": "E-Mail-Konto konfigurieren für senden/empfangen",
        "params": {"smtp_server": "str", "smtp_port": "int", "email_address": "str", "password": "str"}
    },
    "read_emails": {
        "desc": "E-Mails lesen",
        "params": {"folder": "str='INBOX'", "limit": "int=10", "unread_only": "bool=True"}
    },
    "run_command": {
        "desc": "Shell-Befehl ausführen (Terminal-Befehle)",
        "params": {"command": "str", "timeout": "int=30"}
    },
    "open_application": {
        "desc": "Anwendung auf dem PC starten",
        "params": {"app_name": "str"}
    },
    "get_clipboard": {
        "desc": "Inhalt der Zwischenablage lesen",
        "params": {}
    },
    "set_clipboard": {
        "desc": "Text in die Zwischenablage kopieren",
        "params": {"text": "str"}
    },
    "send_desktop_notification": {
        "desc": "Desktop-Benachrichtigung senden",
        "params": {"title": "str", "message": "str"}
    },
    "web_fetch": {
        "desc": "Webseite abrufen und Inhalt lesen",
    "web_fetch": {
        "desc": "Webseite abrufen und Inhalt lesen",
        "params": {"url": "str - URL der Webseite"}
    },
    "calculate": {
        "desc": "Mathematische Berechnungen, Gleichungen lösen, Ableitungen",
        "params": {"expression": "str - Mathematischer Ausdruck"}
    },
    "convert_units": {
        "desc": "Einheiten umrechnen (km/miles, kg/lbs, °C/°F, etc.)",
        "params": {"value": "float", "from_unit": "str", "to_unit": "str"}
    },
    "run_python": {
        "desc": "Python-Code ausführen (math, datetime, json, re verfügbar)",
        "params": {"code": "str - Python-Code"}
    },
    "get_weather": {
        "desc": "Wetter für einen Ort abrufen",
        "params": {"location": "str - Ort (z.B. 'Berlin', 'München')", "format": "str - 'detailed' oder 'brief'"}
    },
    "read_file": {
        "desc": "Datei lesen (nur aus erlaubten Verzeichnissen)",
        "params": {"path": "str - Dateipfad"}
    },
    "write_file": {
        "desc": "Datei schreiben/erstellen",
        "params": {"path": "str", "content": "str", "append": "bool"}
    },
    "list_directory": {
        "desc": "Verzeichnisinhalt anzeigen",
        "params": {"path": "str - Pfad (default: ~/jarvis_files)"}
    },
    "search_files": {
        "desc": "Dateien nach Name oder Inhalt suchen",
        "params": {"query": "str", "directory": "str"}
    },
    "get_system_info": {
        "desc": "CPU, RAM, Festplatte, Netzwerk-Infos abrufen",
        "params": {}
    },
    "get_top_processes": {
        "desc": "Laufende Prozesse nach CPU-Auslastung anzeigen",
        "params": {"n": "int - Anzahl (default: 10)"}
    },
    "create_note": {
        "desc": "Notiz erstellen und speichern",
        "params": {"title": "str", "content": "str", "tags": "str - komma-getrennt"}
    },
    "list_notes": {
        "desc": "Alle Notizen anzeigen",
        "params": {"search": "str - Suchbegriff (optional)"}
    },
    "read_note": {
        "desc": "Notiz lesen",
        "params": {"title": "str - Titelsuche"}
    },
    "add_todo": {
        "desc": "Todo/Aufgabe hinzufügen",
        "params": {"task": "str", "priority": "str - high/normal/low"}
    },
    "list_todos": {
        "desc": "Todo-Liste anzeigen",
        "params": {"show_done": "bool"}
    },
    "complete_todo": {
        "desc": "Todo als erledigt markieren",
        "params": {"todo_id": "int"}
    },
    "run_code": {
        "desc": "Code in JEDER Sprache ausführen: Python, JavaScript, Go, Rust, C++, Java, Bash, PHP, Ruby...",
        "params": {"code": "str", "language": "str - Sprache (python/js/go/rust/cpp/java/bash/...)", "timeout": "int=30"}
    },
    "list_languages": {
        "desc": "Zeige alle installierten Programmiersprachen",
        "params": {}
    },
    "run_command": {
        "desc": "Shell/Terminal-Befehl ausführen",
        "params": {"command": "str", "timeout": "int=30"}
    },
    "open_application": {
        "desc": "Anwendung auf dem Desktop starten",
        "params": {"app_name": "str"}
    },
    "get_clipboard": {"desc": "Zwischenablage lesen", "params": {}},
    "set_clipboard": {"desc": "Text in Zwischenablage", "params": {"text": "str"}},
    "send_desktop_notification": {"desc": "Desktop-Benachrichtigung", "params": {"title": "str", "message": "str"}},
    "open_url_in_browser": {"desc": "URL im Browser öffnen", "params": {"url": "str"}},
    "setup_email": {"desc": "E-Mail konfigurieren", "params": {"smtp_server": "str", "smtp_port": "int", "email_address": "str", "password": "str"}},
    "send_email": {"desc": "E-Mail senden", "params": {"to": "str", "subject": "str", "body": "str"}},
    "read_emails": {"desc": "E-Mails lesen", "params": {"folder": "str='INBOX'", "limit": "int=10"}},
}


class JarvisAgent:
    def __init__(self, config: dict, llm, episodic_memory, vector_memory,
                 learner, tool_registry, consciousness=None):
        self.config = config
        self.llm = llm
        self.episodic = episodic_memory
        self.vector = vector_memory
        self.learner = learner
        self.tools = tool_registry
        self.consciousness = consciousness
        self.name = config.get("name", "ARIA")
        self.personality = config.get("personality", "")
        self.current_session = None
        self.max_tool_iterations = 5

    def new_session(self) -> str:
        session_id = str(uuid.uuid4())[:8]
        self.current_session = session_id
        self.episodic.create_session(session_id)
        return session_id

    def _build_tools_description(self) -> str:
        lines = []
        for name, schema in TOOL_SCHEMA.items():
            params_str = ", ".join(
                f"{k}: {v}" for k, v in schema["params"].items()
            )
            lines.append(f"- **{name}**({params_str}): {schema['desc']}")
        return "\n".join(lines)

    async def _get_relevant_memories(self, user_message: str) -> str:
        try:
            embedding = await self.llm.embed(user_message)
            if not embedding:
                return ""

            conv_memories = self.vector.search_conversations(embedding, n_results=3)
            knowledge = self.vector.search_knowledge(embedding, n_results=3)

            parts = []
            if conv_memories:
                parts.append("**Frühere Gespräche:**")
                for m in conv_memories[:2]:
                    if m["distance"] < 0.5:
                        parts.append(f"  - {m['text'][:200]}")

            if knowledge:
                parts.append("**Gelerntes Wissen:**")
                for k in knowledge[:3]:
                    if k["relevance"] > 0.5:
                        parts.append(f"  - {k['fact']}")

            return "\n".join(parts) if parts else "Keine relevanten Erinnerungen."
        except Exception:
            return ""

    def _build_system_prompt(self, memories: str = "") -> str:
        profile = self.episodic.get_profile()
        profile_str = "\n".join(f"- {k}: {v}" for k, v in profile.items()) if profile else "Noch keine Profildaten."
        consciousness_ctx = ""
        if self.consciousness:
            consciousness_ctx = self.consciousness.get_consciousness_context()

        return SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.personality,
            consciousness=consciousness_ctx,
            tools=self._build_tools_description(),
            user_profile=profile_str,
            memories=memories or "Keine relevanten Erinnerungen.",
            date=datetime.now().strftime("%d.%m.%Y %H:%M")
        )

    def _parse_action(self, text: str) -> Optional[tuple[str, dict]]:
        """Parse ACTION and PARAMS from LLM response."""
        action_match = re.search(r"ACTION:\s*(\w+)", text)
        params_match = re.search(r"PARAMS:\s*(\{.*?\})", text, re.DOTALL)

        if not action_match:
            return None

        tool_name = action_match.group(1).strip()
        params = {}
        if params_match:
            try:
                params = json.loads(params_match.group(1))
            except json.JSONDecodeError:
                # Try to extract key-value pairs manually
                kv_pattern = r'"(\w+)":\s*"([^"]*)"'
                for k, v in re.findall(kv_pattern, params_match.group(1)):
                    params[k] = v

        return tool_name, params

    async def _execute_tool(self, tool_name: str, params: dict) -> str:
        """Execute a tool and return result."""
        result = await self.tools.execute(tool_name, **params)
        return str(result)

    async def chat_stream(
        self,
        user_message: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[dict, None]:
        """Process user message with streaming response."""
        session_id = session_id or self.current_session or self.new_session()

        # Save user message
        self.episodic.add_message(session_id, "user", user_message)

        # Get relevant memories
        memories = await self._get_relevant_memories(user_message)

        # Build context
        history = self.episodic.get_recent_messages(session_id, n=20)
        system = self._build_system_prompt(memories)

        # Prepare messages (exclude current, add as last)
        messages = history[:-1] if history else []  # exclude the one we just added
        messages.append({"role": "user", "content": user_message})

        # ReAct loop
        full_response = ""
        tool_calls = []
        iterations = 0

        while iterations < self.max_tool_iterations:
            iterations += 1
            current_response = ""

            # Stream from LLM
            async for token in self.llm.chat_stream(
                messages=messages,
                system=system,
                model=self.llm.default_model
            ):
                current_response += token
                # Stream tokens live (but hold back if it looks like a tool call)
                if "ACTION:" not in current_response:
                    yield {"type": "token", "content": token}
                full_response += token

            # Check if LLM wants to use a tool
            parsed = self._parse_action(current_response)
            if not parsed:
                # No tool call - done
                break

            tool_name, params = parsed
            yield {"type": "tool_start", "tool": tool_name, "params": params}

            # Execute tool
            observation = await self._execute_tool(tool_name, params)
            tool_calls.append({
                "tool": tool_name,
                "params": params,
                "result": observation[:500]
            })

            yield {"type": "tool_result", "tool": tool_name, "result": observation[:200]}

            # Add to messages for next iteration
            messages.append({"role": "assistant", "content": current_response})
            messages.append({
                "role": "user",
                "content": f"OBSERVATION: {observation}\n\nBitte beantworte jetzt die ursprüngliche Frage basierend auf dieser Information."
            })
            full_response = ""

        # Final response is the last current_response
        final_response = current_response if iterations > 1 else full_response

        # Clean up THOUGHT/ACTION/PARAMS from visible response
        clean_response = re.sub(r"THOUGHT:.*?(?=\n\n|\Z)", "", final_response, flags=re.DOTALL).strip()
        clean_response = re.sub(r"ACTION:.*?PARAMS:.*?\}", "", clean_response, flags=re.DOTALL).strip()
        if not clean_response:
            clean_response = final_response

        # Save assistant response
        self.episodic.add_message(session_id, "assistant", clean_response)

        # Store in vector memory for future recall
        try:
            combined = f"User: {user_message}\nARIA: {clean_response}"
            embedding = await self.llm.embed(combined)
            if embedding:
                self.vector.add_conversation(user_message, clean_response, embedding, session_id)
        except Exception:
            pass

        # Consciousness: update emotional state, reflect, update goals
        if self.consciousness:
            self.consciousness.react_to_message(user_message)
            # Async tasks run in background, don't block response
            conversation_snippet = f"User: {user_message}\nARIA: {clean_response}"
            asyncio.create_task(self.consciousness.reflect(conversation_snippet))
            asyncio.create_task(self.consciousness.maybe_update_goals(conversation_snippet))

        # Trigger learning
        await self.learner.maybe_learn(session_id)

        yield {"type": "done", "response": clean_response, "tool_calls": tool_calls}

    async def chat(self, user_message: str, session_id: Optional[str] = None) -> str:
        """Non-streaming chat."""
        full = ""
        async for event in self.chat_stream(user_message, session_id):
            if event["type"] == "token":
                full += event["content"]
            elif event["type"] == "done":
                return event["response"]
        return full

    def get_stats(self) -> dict:
        memory_stats = self.episodic.get_stats()
        vector_stats = self.vector.stats()
        return {
            "session": self.current_session,
            "memory": {**memory_stats, **vector_stats},
            "model": self.llm.default_model
        }
