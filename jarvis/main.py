"""
JARVIS - Lokaler KI-Assistent
Startet den Web-Server und initialisiert alle Komponenten.
"""
import asyncio
import logging
import os
import sys
import webbrowser
from pathlib import Path

import uvicorn
import yaml

# Add jarvis root to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("jarvis")

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_data_dirs():
    """Create necessary data directories."""
    dirs = ["./data", "./data/chroma", "./data/notes", os.path.expanduser("~/jarvis_files")]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


async def check_ollama(llm, cfg: dict):
    """Check Ollama and pull required models if needed."""
    print("\n🔍 Prüfe Ollama-Verbindung...")
    connected = await llm.check_connection()
    if not connected:
        print("❌ Ollama nicht erreichbar!")
        print(f"   Starte Ollama: https://ollama.ai/download")
        print(f"   Dann: ollama serve")
        print("   (Jarvis startet trotzdem - warte auf Ollama)")
        return False

    models = await llm.list_models()
    model_names = [m.split(":")[0] for m in models]
    print(f"✅ Ollama verbunden | {len(models)} Modell(e): {', '.join(models[:3])}")

    default_model = cfg["llm"]["default_model"]
    default_base = default_model.split(":")[0]

    if default_base not in model_names and default_model not in models:
        print(f"\n📥 Modell '{default_model}' nicht gefunden.")
        print(f"   Lade automatisch herunter...")
        print(f"   (Das kann 1-5 Minuten dauern je nach Modellgröße)")
        async for status in llm.pull_model(default_model):
            print(f"   {status}", end="\r")
        print(f"\n✅ Modell '{default_model}' geladen!")

    # Pull embedding model
    embed_model = cfg["llm"].get("embedding_model", "nomic-embed-text")
    embed_base = embed_model.split(":")[0]
    if embed_base not in model_names and embed_model not in models:
        print(f"\n📥 Embedding-Modell '{embed_model}' wird geladen...")
        async for status in llm.pull_model(embed_model):
            print(f"   {status}", end="\r")
        print(f"\n✅ Embedding-Modell geladen!")

    return True


async def build_tool_registry(cfg: dict):
    """Build and populate the tool registry."""
    from tools.registry import ToolRegistry, Tool
    from tools.web_search import web_search, web_fetch
    from tools.calculator import calculate, convert_units
    from tools.code_runner import run_python
    from tools.file_ops import read_file, write_file, list_directory, search_files, create_directory
    from tools.system_info import get_system_info, get_top_processes
    from tools.system_advanced import (
        run_command, open_application, open_url_in_browser,
        get_clipboard, set_clipboard, send_desktop_notification, list_running_apps
    )
    from tools.notes import create_note, list_notes, read_note, add_todo, list_todos, complete_todo
    from tools.weather import get_weather
    from tools.email_tool import send_email, read_emails, setup_email
    from tools.browser_tool import (
        browser_open, browser_click, browser_type, browser_get_text,
        browser_screenshot, browser_fill_form, browser_press_key, browser_scroll
    )
    from tools.multi_lang_runner import run_code, list_available_languages

    registry = ToolRegistry()

    # Web
    registry.register(Tool("web_search", "Internet-Suche", web_search, {"query": "str", "max_results": "int=5"}))
    registry.register(Tool("web_fetch", "Webseite lesen", web_fetch, {"url": "str"}))

    # Browser-Automatisierung
    registry.register(Tool("browser_open", "URL im Browser öffnen", browser_open, {"url": "str"}))
    registry.register(Tool("browser_click", "Browser-Element klicken", browser_click, {"selector_or_text": "str"}))
    registry.register(Tool("browser_type", "Text in Browser tippen", browser_type, {"selector": "str", "text": "str"}))
    registry.register(Tool("browser_get_text", "Browser-Seitentext lesen", browser_get_text, {}))
    registry.register(Tool("browser_screenshot", "Browser-Screenshot", browser_screenshot, {"filename": "str='screenshot.png'"}))
    registry.register(Tool("browser_fill_form", "Formular ausfüllen", browser_fill_form, {"fields": "dict"}))
    registry.register(Tool("browser_press_key", "Taste im Browser drücken", browser_press_key, {"key": "str"}))
    registry.register(Tool("browser_scroll", "Browser scrollen", browser_scroll, {"direction": "str='down'", "amount": "int=500"}))

    # Mathe & Code
    registry.register(Tool("calculate", "Mathematik", calculate, {"expression": "str"}))
    registry.register(Tool("convert_units", "Einheiten umrechnen", convert_units, {"value": "float", "from_unit": "str", "to_unit": "str"}))
    registry.register(Tool("run_python", "Python ausführen", run_python, {"code": "str"}))
    registry.register(Tool("run_code", "Code in JEDER Sprache ausführen (Python/JS/Go/Rust/C++/Java...)", run_code, {"code": "str", "language": "str", "timeout": "int=30"}))
    registry.register(Tool("list_languages", "Verfügbare Programmiersprachen anzeigen", list_available_languages, {}))

    # System
    registry.register(Tool("get_system_info", "Systeminfos", get_system_info, {}))
    registry.register(Tool("get_top_processes", "Top-Prozesse", get_top_processes, {"n": "int=10"}))
    registry.register(Tool("run_command", "Shell-Befehl", run_command, {"command": "str", "timeout": "int=30"}))
    registry.register(Tool("open_application", "App starten", open_application, {"app_name": "str"}))
    registry.register(Tool("open_url_in_browser", "URL im Browser", open_url_in_browser, {"url": "str"}))
    registry.register(Tool("get_clipboard", "Zwischenablage lesen", get_clipboard, {}))
    registry.register(Tool("set_clipboard", "Zwischenablage schreiben", set_clipboard, {"text": "str"}))
    registry.register(Tool("send_desktop_notification", "Desktop-Benachrichtigung", send_desktop_notification, {"title": "str", "message": "str"}))
    registry.register(Tool("list_running_apps", "Laufende Apps", list_running_apps, {}))

    # Dateien (voller Zugriff)
    registry.register(Tool("read_file", "Datei lesen", read_file, {"path": "str"}))
    registry.register(Tool("write_file", "Datei schreiben", write_file, {"path": "str", "content": "str", "append": "bool=False"}))
    registry.register(Tool("list_directory", "Verzeichnis anzeigen", list_directory, {"path": "str"}))
    registry.register(Tool("search_files", "Dateien suchen", search_files, {"query": "str", "directory": "str"}))
    registry.register(Tool("create_directory", "Ordner erstellen", create_directory, {"path": "str"}))

    # E-Mail
    registry.register(Tool("setup_email", "E-Mail konfigurieren", setup_email, {"smtp_server": "str", "smtp_port": "int", "email_address": "str", "password": "str"}))
    registry.register(Tool("send_email", "E-Mail senden", send_email, {"to": "str", "subject": "str", "body": "str", "cc": "str=''"}))
    registry.register(Tool("read_emails", "E-Mails lesen", read_emails, {"folder": "str='INBOX'", "limit": "int=10"}))

    # Wetter
    registry.register(Tool("get_weather", "Wetter", get_weather, {"location": "str", "format": "str='detailed'"}))

    # Notizen & Todos
    registry.register(Tool("create_note", "Notiz erstellen", create_note, {"title": "str", "content": "str", "tags": "str=''"}))
    registry.register(Tool("list_notes", "Notizen auflisten", list_notes, {"search": "str=''"}))
    registry.register(Tool("read_note", "Notiz lesen", read_note, {"title": "str"}))
    registry.register(Tool("add_todo", "Todo hinzufügen", add_todo, {"task": "str", "priority": "str='normal'"}))
    registry.register(Tool("list_todos", "Todos anzeigen", list_todos, {"show_done": "bool=False"}))
    registry.register(Tool("complete_todo", "Todo abhaken", complete_todo, {"todo_id": "int"}))

    return registry


async def main():
    print("""
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║       █████╗ ██████╗ ██╗ █████╗                      ║
║      ██╔══██╗██╔══██╗██║██╔══██╗                     ║
║      ███████║██████╔╝██║███████║                     ║
║      ██╔══██║██╔══██╗██║██╔══██║                     ║
║      ██║  ██║██║  ██║██║██║  ██║                     ║
║      ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝                     ║
║                                                       ║
║  Artificial Responsive Intelligence Assistant         ║
║  Lokale KI mit Persönlichkeit — Kein API nötig        ║
╚═══════════════════════════════════════════════════════╝
    """)

    # Load config
    cfg = load_config()
    setup_data_dirs()
    logger.info("Konfiguration geladen")

    # Initialize LLM
    from core.llm import OllamaLLM
    llm = OllamaLLM(
        base_url=cfg["llm"]["base_url"],
        default_model=cfg["llm"]["default_model"],
        powerful_model=cfg["llm"].get("powerful_model", "llama3.1:8b"),
        temperature=cfg["llm"].get("temperature", 0.7),
        max_tokens=cfg["llm"].get("max_tokens", 4096)
    )

    await check_ollama(llm, cfg)

    # Initialize memory
    from memory.episodic import EpisodicMemory
    from memory.vector_store import VectorMemory
    episodic = EpisodicMemory(cfg["memory"]["db_path"])
    vector = VectorMemory(cfg["memory"]["vector_db_path"])
    logger.info("Gedächtnis initialisiert")

    # Initialize learner
    from memory.learner import Learner
    learner = Learner(llm, episodic, vector)

    # Initialize tools
    registry = await build_tool_registry(cfg)
    logger.info(f"{len(registry._tools)} Tools registriert")

    # Initialize consciousness
    from core.consciousness import ConsciousnessSystem
    consciousness = ConsciousnessSystem(llm)
    logger.info("Bewusstsein initialisiert")

    # Initialize agent
    from core.agent import JarvisAgent
    agent = JarvisAgent(
        config=cfg["jarvis"],
        llm=llm,
        episodic_memory=episodic,
        vector_memory=vector,
        learner=learner,
        tool_registry=registry,
        consciousness=consciousness
    )
    session_id = agent.new_session()
    logger.info(f"Session gestartet: {session_id}")

    # Initialize background worker
    from core.background_worker import BackgroundWorker
    background_worker = BackgroundWorker(agent)
    background_worker.setup_default_tasks()
    logger.info("Hintergrundarbeiter initialisiert")

    # Initialize Voice (optional)
    tts = None
    stt = None
    voice_cfg = cfg.get("voice", {})
    if voice_cfg.get("tts", {}).get("enabled", False):
        from voice.tts import EdgeTTS
        tts = EdgeTTS(
            voice=voice_cfg["tts"].get("voice", "de-DE-KillianNeural"),
            rate=voice_cfg["tts"].get("rate", "+10%")
        )
    if voice_cfg.get("stt", {}).get("enabled", False):
        from voice.stt import WhisperSTT
        stt = WhisperSTT(
            model_size=voice_cfg["stt"].get("model", "base"),
            language=voice_cfg["stt"].get("language", "de")
        )

    # Initialize web app
    from web.app import app, init_app
    init_app(agent, tts, stt, cfg)

    web_cfg = cfg.get("web", {})
    host = web_cfg.get("host", "0.0.0.0")
    port = web_cfg.get("port", 7860)

    print(f"\n✅ ARIA bereit!")
    print(f"🌐 Web-Interface: http://localhost:{port}")
    print(f"📡 API: http://localhost:{port}/api/status")
    print(f"\nStrg+C zum Beenden\n")

    if web_cfg.get("auto_open_browser", True):
        import threading
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)

    # Starte Background-Worker parallel zum Web-Server
    await asyncio.gather(
        server.serve(),
        background_worker.run_forever()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 ARIA wird beendet...")
