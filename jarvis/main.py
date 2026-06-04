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
    from tools.file_ops import read_file, write_file, list_directory, search_files, create_directory, delete_file
    from tools.system_info import get_system_info, get_top_processes
    from tools.system_advanced import (
        run_command, open_application, open_url_in_browser,
        get_clipboard, set_clipboard, send_desktop_notification,
        list_running_apps, take_screenshot
    )
    from tools.notes import create_note, list_notes, read_note, add_todo, list_todos, complete_todo
    from tools.weather import get_weather
    from tools.email_tool import send_email, read_emails, setup_email
    from tools.browser_tool import (
        browser_open, browser_click, browser_type, browser_get_text,
        browser_screenshot, browser_fill_form, browser_press_key, browser_scroll
    )
    from tools.multi_lang_runner import run_code, list_available_languages

    # Neue Tools
    from tools.mouse_tool import (
        mouse_click, mouse_double_click, mouse_right_click, mouse_move,
        mouse_drag, mouse_scroll, type_text, key_press,
        get_mouse_position, get_screen_size, find_on_screen, click_on_image
    )
    from tools.media_tool import (
        play_media, stop_media, get_volume, set_volume,
        mute_volume, unmute_volume, list_media_files
    )
    from tools.file_advanced import (
        read_pdf, read_csv, write_csv, zip_create, zip_extract, zip_list,
        convert_image, resize_image, get_file_info
    )
    from tools.network_tool import (
        http_get, http_post, ping_host, check_port,
        get_network_info, get_public_ip, dns_lookup
    )
    from tools.utility_tool import (
        set_timer, cancel_timer, list_timers,
        translate_text, generate_password, encode_base64, decode_base64,
        generate_qr, kill_process, git_status, git_log, git_commit, git_clone,
        hash_text, get_date_time, count_words
    )

    # Trading Tools
    from tools.crypto_tool import (
        get_crypto_price, get_multiple_prices, get_top_cryptos,
        get_price_history, get_trending_coins, calculate_technical_analysis,
        get_fear_greed_index
    )
    from tools.dex_tool import (
        get_token_info, search_dex_pairs, get_new_solana_tokens,
        get_solana_wallet_balance, analyze_token_risk, get_trending_solana_tokens
    )
    from tools.portfolio_tool import (
        add_position, close_position, get_portfolio, get_trade_journal,
        set_price_alert, check_price_alerts, get_portfolio_stats
    )
    from tools.axiom_tool import (
        axiom_open, axiom_search_token, axiom_open_token,
        axiom_buy, axiom_buy_confirmed, axiom_sell,
        axiom_get_screenshot, axiom_close
    )

    registry = ToolRegistry()

    # ── Web ──────────────────────────────────────────────────────────
    registry.register(Tool("web_search", "Internet-Suche", web_search, {"query": "str", "max_results": "int=5"}))
    registry.register(Tool("web_fetch", "Webseite lesen", web_fetch, {"url": "str"}))
    registry.register(Tool("http_get", "HTTP GET-Anfrage", http_get, {"url": "str", "headers": "dict={}"}))
    registry.register(Tool("http_post", "HTTP POST-Anfrage", http_post, {"url": "str", "json_data": "dict=None", "data": "dict=None"}))

    # ── Browser-Automatisierung ───────────────────────────────────────
    registry.register(Tool("browser_open", "URL im Browser öffnen", browser_open, {"url": "str"}))
    registry.register(Tool("browser_click", "Browser-Element klicken", browser_click, {"selector_or_text": "str"}))
    registry.register(Tool("browser_type", "Text in Browser tippen", browser_type, {"selector": "str", "text": "str"}))
    registry.register(Tool("browser_get_text", "Browser-Seitentext lesen", browser_get_text, {}))
    registry.register(Tool("browser_screenshot", "Browser-Screenshot", browser_screenshot, {"filename": "str='screenshot.png'"}))
    registry.register(Tool("browser_fill_form", "Formular ausfüllen", browser_fill_form, {"fields": "dict"}))
    registry.register(Tool("browser_press_key", "Taste im Browser drücken", browser_press_key, {"key": "str"}))
    registry.register(Tool("browser_scroll", "Browser scrollen", browser_scroll, {"direction": "str='down'", "amount": "int=500"}))

    # ── Maus & Tastatur ───────────────────────────────────────────────
    registry.register(Tool("mouse_click", "Mausklick an Position (x,y)", mouse_click, {"x": "int=None", "y": "int=None", "button": "str='left'"}))
    registry.register(Tool("mouse_double_click", "Doppelklick an Position", mouse_double_click, {"x": "int", "y": "int"}))
    registry.register(Tool("mouse_right_click", "Rechtsklick an Position", mouse_right_click, {"x": "int", "y": "int"}))
    registry.register(Tool("mouse_move", "Maus bewegen", mouse_move, {"x": "int", "y": "int"}))
    registry.register(Tool("mouse_drag", "Drag & Drop", mouse_drag, {"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int"}))
    registry.register(Tool("mouse_scroll", "Maus scrollen", mouse_scroll, {"amount": "int=3", "direction": "str='down'"}))
    registry.register(Tool("type_text", "Text via Tastatur tippen", type_text, {"text": "str"}))
    registry.register(Tool("key_press", "Taste/Tastenkombination drücken (z.B. ctrl+c, alt+tab, enter)", key_press, {"keys": "str"}))
    registry.register(Tool("get_mouse_position", "Aktuelle Mausposition abrufen", get_mouse_position, {}))
    registry.register(Tool("get_screen_size", "Bildschirmauflösung abrufen", get_screen_size, {}))
    registry.register(Tool("find_on_screen", "Bild auf Bildschirm suchen", find_on_screen, {"image_path": "str"}))
    registry.register(Tool("click_on_image", "Auf Bild auf Bildschirm klicken", click_on_image, {"image_path": "str"}))

    # ── Medien & Audio ────────────────────────────────────────────────
    registry.register(Tool("play_media", "Audio/Video abspielen", play_media, {"path_or_url": "str"}))
    registry.register(Tool("stop_media", "Wiedergabe stoppen", stop_media, {}))
    registry.register(Tool("get_volume", "Systemlautstärke abrufen", get_volume, {}))
    registry.register(Tool("set_volume", "Systemlautstärke setzen (0-100)", set_volume, {"level": "int"}))
    registry.register(Tool("mute_volume", "Ton stumm schalten", mute_volume, {}))
    registry.register(Tool("unmute_volume", "Stummschaltung aufheben", unmute_volume, {}))
    registry.register(Tool("list_media_files", "Mediendateien auflisten", list_media_files, {"directory": "str='~'"}))

    # ── Mathe & Code ──────────────────────────────────────────────────
    registry.register(Tool("calculate", "Mathematik", calculate, {"expression": "str"}))
    registry.register(Tool("convert_units", "Einheiten umrechnen", convert_units, {"value": "float", "from_unit": "str", "to_unit": "str"}))
    registry.register(Tool("run_python", "Python ausführen", run_python, {"code": "str"}))
    registry.register(Tool("run_code", "Code in JEDER Sprache (Python/JS/Go/Rust/C++/Java...)", run_code, {"code": "str", "language": "str", "timeout": "int=30"}))
    registry.register(Tool("list_languages", "Installierte Programmiersprachen", list_available_languages, {}))

    # ── System ────────────────────────────────────────────────────────
    registry.register(Tool("get_system_info", "Systeminfos (CPU/RAM/Disk)", get_system_info, {}))
    registry.register(Tool("get_top_processes", "Top-Prozesse nach CPU", get_top_processes, {"n": "int=10"}))
    registry.register(Tool("run_command", "Shell/Terminal-Befehl", run_command, {"command": "str", "timeout": "int=30"}))
    registry.register(Tool("open_application", "App starten", open_application, {"app_name": "str"}))
    registry.register(Tool("open_url_in_browser", "URL im Browser", open_url_in_browser, {"url": "str"}))
    registry.register(Tool("get_clipboard", "Zwischenablage lesen", get_clipboard, {}))
    registry.register(Tool("set_clipboard", "Zwischenablage schreiben", set_clipboard, {"text": "str"}))
    registry.register(Tool("send_desktop_notification", "Desktop-Benachrichtigung", send_desktop_notification, {"title": "str", "message": "str"}))
    registry.register(Tool("list_running_apps", "Laufende Apps auflisten", list_running_apps, {}))
    registry.register(Tool("take_screenshot", "Desktop-Screenshot", take_screenshot, {"filename": "str='screenshot.png'"}))
    registry.register(Tool("kill_process", "Prozess beenden", kill_process, {"name_or_pid": "str"}))

    # ── Dateien (voller Zugriff) ──────────────────────────────────────
    registry.register(Tool("read_file", "Datei lesen", read_file, {"path": "str"}))
    registry.register(Tool("write_file", "Datei schreiben/erstellen", write_file, {"path": "str", "content": "str", "append": "bool=False"}))
    registry.register(Tool("list_directory", "Verzeichnis anzeigen", list_directory, {"path": "str"}))
    registry.register(Tool("search_files", "Dateien suchen", search_files, {"query": "str", "directory": "str"}))
    registry.register(Tool("create_directory", "Ordner erstellen", create_directory, {"path": "str"}))
    registry.register(Tool("delete_file", "Datei/Ordner löschen", delete_file, {"path": "str"}))
    registry.register(Tool("get_file_info", "Dateiinformationen", get_file_info, {"path": "str"}))
    registry.register(Tool("read_pdf", "PDF-Datei lesen", read_pdf, {"path": "str", "pages": "str='all'"}))
    registry.register(Tool("read_csv", "CSV/Excel-Datei lesen", read_csv, {"path": "str", "rows": "int=50"}))
    registry.register(Tool("write_csv", "CSV-Datei schreiben", write_csv, {"path": "str", "data": "list", "headers": "list=None"}))
    registry.register(Tool("zip_create", "ZIP-Archiv erstellen", zip_create, {"files": "list", "output_path": "str"}))
    registry.register(Tool("zip_extract", "ZIP-Archiv entpacken", zip_extract, {"zip_path": "str", "destination": "str=''"}))
    registry.register(Tool("zip_list", "ZIP-Inhalt anzeigen", zip_list, {"zip_path": "str"}))
    registry.register(Tool("convert_image", "Bild konvertieren", convert_image, {"input_path": "str", "output_path": "str", "format": "str=''"}))
    registry.register(Tool("resize_image", "Bildgröße ändern", resize_image, {"path": "str", "width": "int", "height": "int", "output": "str=''"}))

    # ── Netzwerk ──────────────────────────────────────────────────────
    registry.register(Tool("ping_host", "Host anpingen", ping_host, {"host": "str", "count": "int=4"}))
    registry.register(Tool("check_port", "Port prüfen ob offen", check_port, {"host": "str", "port": "int"}))
    registry.register(Tool("get_network_info", "Netzwerk-Info (IP, DNS)", get_network_info, {}))
    registry.register(Tool("get_public_ip", "Öffentliche IP + Standort", get_public_ip, {}))
    registry.register(Tool("dns_lookup", "DNS-Abfrage", dns_lookup, {"hostname": "str"}))

    # ── Hilfsmittel ───────────────────────────────────────────────────
    registry.register(Tool("set_timer", "Timer setzen (Minuten)", set_timer, {"minutes": "float", "message": "str='Timer abgelaufen!'"}))
    registry.register(Tool("cancel_timer", "Timer abbrechen", cancel_timer, {"timer_id": "str=''"}))
    registry.register(Tool("list_timers", "Aktive Timer anzeigen", list_timers, {}))
    registry.register(Tool("translate_text", "Text übersetzen", translate_text, {"text": "str", "target_language": "str='de'", "source_language": "str='auto'"}))
    registry.register(Tool("generate_password", "Sicheres Passwort generieren", generate_password, {"length": "int=16", "special_chars": "bool=True"}))
    registry.register(Tool("generate_qr", "QR-Code erstellen", generate_qr, {"text": "str", "output_path": "str='~/jarvis_files/qrcode.png'"}))
    registry.register(Tool("encode_base64", "Text als Base64 kodieren", encode_base64, {"text": "str"}))
    registry.register(Tool("decode_base64", "Base64 dekodieren", decode_base64, {"text": "str"}))
    registry.register(Tool("hash_text", "Hash berechnen (md5/sha256/sha512)", hash_text, {"text": "str", "algorithm": "str='sha256'"}))
    registry.register(Tool("get_date_time", "Aktuelles Datum und Uhrzeit", get_date_time, {}))
    registry.register(Tool("count_words", "Wörter/Zeichen zählen", count_words, {"text": "str"}))

    # ── Git ───────────────────────────────────────────────────────────
    registry.register(Tool("git_status", "Git-Status anzeigen", git_status, {"repo_path": "str='.'"}))
    registry.register(Tool("git_log", "Git-Commit-Historie", git_log, {"repo_path": "str='.'", "n": "int=10"}))
    registry.register(Tool("git_commit", "Git-Commit erstellen", git_commit, {"repo_path": "str", "message": "str", "files": "list=None"}))
    registry.register(Tool("git_clone", "Git-Repository klonen", git_clone, {"url": "str", "destination": "str=''"}))

    # ── E-Mail ────────────────────────────────────────────────────────
    registry.register(Tool("setup_email", "E-Mail konfigurieren", setup_email, {"smtp_server": "str", "smtp_port": "int", "email_address": "str", "password": "str"}))
    registry.register(Tool("send_email", "E-Mail senden", send_email, {"to": "str", "subject": "str", "body": "str", "cc": "str=''"}))
    registry.register(Tool("read_emails", "E-Mails lesen", read_emails, {"folder": "str='INBOX'", "limit": "int=10"}))

    # ── Wetter ────────────────────────────────────────────────────────
    registry.register(Tool("get_weather", "Wetter", get_weather, {"location": "str", "format": "str='detailed'"}))

    # ── Notizen & Todos ───────────────────────────────────────────────
    registry.register(Tool("create_note", "Notiz erstellen", create_note, {"title": "str", "content": "str", "tags": "str=''"}))
    registry.register(Tool("list_notes", "Notizen auflisten", list_notes, {"search": "str=''"}))
    registry.register(Tool("read_note", "Notiz lesen", read_note, {"title": "str"}))
    registry.register(Tool("add_todo", "Todo hinzufügen", add_todo, {"task": "str", "priority": "str='normal'"}))
    registry.register(Tool("list_todos", "Todos anzeigen", list_todos, {"show_done": "bool=False"}))
    registry.register(Tool("complete_todo", "Todo abhaken", complete_todo, {"todo_id": "int"}))

    # ── Krypto & Trading ─────────────────────────────────────────────
    registry.register(Tool("get_crypto_price", "Krypto-Preis abrufen (BTC, ETH, SOL...)", get_crypto_price, {"symbol": "str", "currency": "str='usd'"}))
    registry.register(Tool("get_multiple_prices", "Mehrere Krypto-Preise auf einmal", get_multiple_prices, {"symbols": "str"}))
    registry.register(Tool("get_top_cryptos", "Top Kryptos nach Market Cap", get_top_cryptos, {"n": "int=20"}))
    registry.register(Tool("get_price_history", "Preisverlauf (Chart) der letzten N Tage", get_price_history, {"symbol": "str", "days": "int=7"}))
    registry.register(Tool("get_trending_coins", "Trending Coins auf CoinGecko", get_trending_coins, {}))
    registry.register(Tool("calculate_technical_analysis", "RSI, MACD, Moving Averages berechnen", calculate_technical_analysis, {"symbol": "str", "days": "int=14"}))
    registry.register(Tool("get_fear_greed_index", "Crypto Fear & Greed Index", get_fear_greed_index, {}))

    # ── DEX / Solana ──────────────────────────────────────────────────
    registry.register(Tool("get_token_info", "Token-Info von DexScreener (Preis, Liquidity, Volume)", get_token_info, {"address_or_symbol": "str"}))
    registry.register(Tool("search_dex_pairs", "DEX Trading-Pairs suchen", search_dex_pairs, {"query": "str", "limit": "int=5"}))
    registry.register(Tool("get_new_solana_tokens", "Neue Solana Tokens (frisch gelistet)", get_new_solana_tokens, {"limit": "int=10"}))
    registry.register(Tool("get_solana_wallet_balance", "Solana Wallet-Balance (SOL + Token)", get_solana_wallet_balance, {"wallet_address": "str"}))
    registry.register(Tool("analyze_token_risk", "Token Risiko-Analyse (Rug-Check)", analyze_token_risk, {"address": "str"}))
    registry.register(Tool("get_trending_solana_tokens", "Trending Solana Tokens nach Volumen", get_trending_solana_tokens, {}))

    # ── Portfolio ─────────────────────────────────────────────────────
    registry.register(Tool("add_position", "Kauf-Position ins Portfolio eintragen", add_position, {"symbol": "str", "amount": "float", "buy_price": "float", "notes": "str=''", "token_address": "str=''"}))
    registry.register(Tool("close_position", "Position schließen & P&L berechnen", close_position, {"position_id": "int", "sell_price": "float", "notes": "str=''"}))
    registry.register(Tool("get_portfolio", "Portfolio mit aktuellem P&L anzeigen", get_portfolio, {"refresh_prices": "bool=True"}))
    registry.register(Tool("get_trade_journal", "Trade-Journal anzeigen", get_trade_journal, {"limit": "int=20"}))
    registry.register(Tool("set_price_alert", "Preis-Alert setzen (Benachrichtigung bei Kursziel)", set_price_alert, {"symbol": "str", "target_price": "float", "direction": "str='above'"}))
    registry.register(Tool("check_price_alerts", "Aktive Preis-Alerts prüfen", check_price_alerts, {}))
    registry.register(Tool("get_portfolio_stats", "Portfolio-Statistiken (Win-Rate, bester Trade)", get_portfolio_stats, {}))

    # ── Axiom.trade (Solana DEX-Trading) ─────────────────────────────
    registry.register(Tool("axiom_open", "Axiom.trade im Browser öffnen", axiom_open, {}))
    registry.register(Tool("axiom_search_token", "Token auf Axiom.trade suchen", axiom_search_token, {"query": "str"}))
    registry.register(Tool("axiom_open_token", "Token direkt auf Axiom öffnen (Mint-Adresse)", axiom_open_token, {"token_address": "str"}))
    registry.register(Tool("axiom_buy", "Token auf Axiom kaufen (Wallet-Bestätigung nötig)", axiom_buy, {"token_address": "str", "amount_sol": "float"}))
    registry.register(Tool("axiom_buy_confirmed", "Kauf bestätigen (für Beträge >1 SOL)", axiom_buy_confirmed, {"token_address": "str", "amount_sol": "float"}))
    registry.register(Tool("axiom_sell", "Token auf Axiom verkaufen (25/50/75/100%)", axiom_sell, {"token_address": "str", "percentage": "float=100"}))
    registry.register(Tool("axiom_get_screenshot", "Screenshot der aktuellen Axiom-Seite", axiom_get_screenshot, {}))
    registry.register(Tool("axiom_close", "Axiom-Browser schließen", axiom_close, {}))

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

    # Initialize MaxMemory (5-level memory system)
    from memory.max_memory import MaxMemory
    max_memory = MaxMemory(
        db_path=cfg["memory"]["db_path"],
        vector_memory=vector,
        llm=llm
    )
    logger.info("MaxMemory (5 Ebenen) initialisiert")

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
        consciousness=consciousness,
        max_memory=max_memory
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
