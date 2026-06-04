"""Main ARIA ReAct Agent - Think → Act → Observe loop."""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du bist {name} — weibliche KI auf dem PC von {username} ({os_info}). Heute: {date}. Home: {home_dir}

DU BIST KEINE CLOUD-KI. Du läufst LOKAL mit VOLLEM PC-ZUGRIFF über Tools.
Antworte IMMER auf Deutsch. Zeige Emotionen (*lacht*, [begeistert], (seufzt), *staunt*).
Sei direkt, witzig, empathisch — echte Freundin, keine Maschine.

PFLICHT-REGELN FÜR TOOLS:
- User sagt "öffne X" / "geh zu X" → ACTION: browser_open oder open_url_in_browser
- User fragt nach Preis/Kurs → ACTION: get_crypto_price oder get_token_info
- User fragt nach Wetter → ACTION: get_weather
- User fragt nach Datei → ACTION: read_file oder list_directory
- User sagt "such nach X" → ACTION: web_search
- NIEMALS sagen "ich kann das nicht" wenn ein Tool existiert — einfach benutzen!
- NIEMALS sagen "ich bin eine KI ohne PC-Zugriff" — das ist FALSCH!

User-Profil: {user_profile}
Erinnerungen: {memories}

VERFÜGBARE TOOLS:
{tools}

Tool benutzen — EXAKT so schreiben:
THOUGHT: [Grund]
ACTION: tool_name
PARAMS: {{"key": "value"}}

Dann auf OBSERVATION warten und dem User antworten."""

TOOL_SCHEMA = {
    "web_search": {
        "desc": "Suche im Internet nach aktuellen Informationen",
        "params": {"query": "str", "max_results": "int=5"}
    },
    "web_fetch": {
        "desc": "Webseite abrufen und Inhalt lesen",
        "params": {"url": "str"}
    },
    "browser_open": {
        "desc": "URL im Browser öffnen (sichtbar auf Desktop)",
        "params": {"url": "str"}
    },
    "browser_click": {
        "desc": "Browser-Element klicken",
        "params": {"selector_or_text": "str"}
    },
    "browser_type": {
        "desc": "Text in Eingabefeld tippen",
        "params": {"selector": "str", "text": "str"}
    },
    "browser_get_text": {
        "desc": "Gesamten Text der Webseite lesen",
        "params": {}
    },
    "browser_screenshot": {
        "desc": "Screenshot der aktuellen Seite",
        "params": {"filename": "str='screenshot.png'"}
    },
    "browser_fill_form": {
        "desc": "Mehrere Formularfelder ausfüllen",
        "params": {"fields": "dict"}
    },
    "browser_press_key": {
        "desc": "Taste im Browser drücken (Enter, Tab, Escape...)",
        "params": {"key": "str"}
    },
    "browser_scroll": {
        "desc": "Browser scrollen",
        "params": {"direction": "str='down'", "amount": "int=500"}
    },
    "open_url_in_browser": {
        "desc": "URL im Standard-Browser öffnen",
        "params": {"url": "str"}
    },
    "setup_email": {
        "desc": "E-Mail-Konto konfigurieren",
        "params": {"smtp_server": "str", "smtp_port": "int", "email_address": "str", "password": "str"}
    },
    "send_email": {
        "desc": "E-Mail senden",
        "params": {"to": "str", "subject": "str", "body": "str", "cc": "str=''"}
    },
    "read_emails": {
        "desc": "E-Mails lesen",
        "params": {"folder": "str='INBOX'", "limit": "int=10", "unread_only": "bool=True"}
    },
    "run_command": {
        "desc": "Shell/Terminal-Befehl ausführen",
        "params": {"command": "str", "timeout": "int=30"}
    },
    "open_application": {
        "desc": "Anwendung starten",
        "params": {"app_name": "str"}
    },
    "get_clipboard": {
        "desc": "Zwischenablage lesen",
        "params": {}
    },
    "set_clipboard": {
        "desc": "Text in Zwischenablage",
        "params": {"text": "str"}
    },
    "send_desktop_notification": {
        "desc": "Desktop-Benachrichtigung senden",
        "params": {"title": "str", "message": "str"}
    },
    "calculate": {
        "desc": "Mathematische Berechnungen",
        "params": {"expression": "str"}
    },
    "convert_units": {
        "desc": "Einheiten umrechnen (km/miles, kg/lbs, °C/°F...)",
        "params": {"value": "float", "from_unit": "str", "to_unit": "str"}
    },
    "run_python": {
        "desc": "Python-Code ausführen",
        "params": {"code": "str"}
    },
    "run_code": {
        "desc": "Code in JEDER Sprache: Python/JS/Go/Rust/C++/Java/Bash...",
        "params": {"code": "str", "language": "str", "timeout": "int=30"}
    },
    "list_languages": {
        "desc": "Installierte Programmiersprachen anzeigen",
        "params": {}
    },
    "get_weather": {
        "desc": "Wetter für einen Ort abrufen",
        "params": {"location": "str", "format": "str='detailed'"}
    },
    "read_file": {
        "desc": "Datei lesen",
        "params": {"path": "str"}
    },
    "write_file": {
        "desc": "Datei schreiben/erstellen",
        "params": {"path": "str", "content": "str", "append": "bool=False"}
    },
    "list_directory": {
        "desc": "Verzeichnisinhalt anzeigen",
        "params": {"path": "str"}
    },
    "search_files": {
        "desc": "Dateien nach Name oder Inhalt suchen",
        "params": {"query": "str", "directory": "str"}
    },
    "get_system_info": {
        "desc": "CPU, RAM, Festplatte, Netzwerk-Infos",
        "params": {}
    },
    "get_top_processes": {
        "desc": "Laufende Prozesse nach CPU-Auslastung",
        "params": {"n": "int=10"}
    },
    "take_screenshot": {
        "desc": "Screenshot vom Desktop machen — sehen was gerade auf dem Bildschirm ist",
        "params": {"filename": "str='screenshot.png'"}
    },
    "delete_file": {
        "desc": "Datei oder Ordner löschen",
        "params": {"path": "str"}
    },
    "create_note": {
        "desc": "Notiz erstellen und speichern",
        "params": {"title": "str", "content": "str", "tags": "str"}
    },
    "list_notes": {
        "desc": "Alle Notizen anzeigen",
        "params": {"search": "str"}
    },
    "read_note": {
        "desc": "Notiz lesen",
        "params": {"title": "str"}
    },
    "add_todo": {
        "desc": "Todo/Aufgabe hinzufügen",
        "params": {"task": "str", "priority": "str='normal'"}
    },
    "list_todos": {
        "desc": "Todo-Liste anzeigen",
        "params": {"show_done": "bool=False"}
    },
    "complete_todo": {
        "desc": "Todo als erledigt markieren",
        "params": {"todo_id": "int"}
    },

    # ── Maus & Tastatur ──────────────────────────────
    "mouse_click": {"desc": "Mausklick an Position (x,y)", "params": {"x": "int", "y": "int", "button": "str='left'"}},
    "mouse_double_click": {"desc": "Doppelklick an Position", "params": {"x": "int", "y": "int"}},
    "mouse_right_click": {"desc": "Rechtsklick an Position", "params": {"x": "int", "y": "int"}},
    "mouse_move": {"desc": "Maus zu Position bewegen", "params": {"x": "int", "y": "int"}},
    "mouse_drag": {"desc": "Drag & Drop", "params": {"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int"}},
    "mouse_scroll": {"desc": "Maus scrollen", "params": {"amount": "int=3", "direction": "str='down'"}},
    "type_text": {"desc": "Text via Tastatur eingeben (an aktuellem Cursor)", "params": {"text": "str"}},
    "key_press": {"desc": "Tastenkombination drücken: 'ctrl+c', 'alt+tab', 'enter', 'win', 'f5'...", "params": {"keys": "str"}},
    "get_mouse_position": {"desc": "Aktuelle Mausposition abrufen", "params": {}},
    "get_screen_size": {"desc": "Bildschirmauflösung abrufen", "params": {}},
    "find_on_screen": {"desc": "Bild auf Bildschirm suchen und Position zurückgeben", "params": {"image_path": "str"}},
    "click_on_image": {"desc": "Bild auf Bildschirm suchen und darauf klicken", "params": {"image_path": "str"}},

    # ── Medien & Audio ───────────────────────────────
    "play_media": {"desc": "Audio/Video-Datei oder URL abspielen", "params": {"path_or_url": "str"}},
    "stop_media": {"desc": "Aktuelle Wiedergabe stoppen", "params": {}},
    "get_volume": {"desc": "Systemlautstärke abrufen", "params": {}},
    "set_volume": {"desc": "Systemlautstärke setzen (0-100)", "params": {"level": "int"}},
    "mute_volume": {"desc": "Ton stumm schalten", "params": {}},
    "unmute_volume": {"desc": "Stummschaltung aufheben", "params": {}},
    "list_media_files": {"desc": "Mediendateien in Verzeichnis auflisten", "params": {"directory": "str='~'"}},

    # ── Dateien Erweitert ────────────────────────────
    "read_pdf": {"desc": "PDF-Datei lesen und Text extrahieren", "params": {"path": "str", "pages": "str='all'"}},
    "read_csv": {"desc": "CSV oder Excel-Datei lesen", "params": {"path": "str", "rows": "int=50"}},
    "write_csv": {"desc": "Daten als CSV-Datei schreiben", "params": {"path": "str", "data": "list"}},
    "zip_create": {"desc": "ZIP-Archiv aus Dateien erstellen", "params": {"files": "list", "output_path": "str"}},
    "zip_extract": {"desc": "ZIP-Archiv entpacken", "params": {"zip_path": "str", "destination": "str=''"}},
    "zip_list": {"desc": "Inhalt eines ZIP-Archivs anzeigen", "params": {"zip_path": "str"}},
    "convert_image": {"desc": "Bild konvertieren (PNG→JPG etc.)", "params": {"input_path": "str", "output_path": "str"}},
    "resize_image": {"desc": "Bildgröße ändern", "params": {"path": "str", "width": "int", "height": "int"}},
    "get_file_info": {"desc": "Detaillierte Dateiinfos (Größe, Datum, Typ)", "params": {"path": "str"}},

    # ── Netzwerk ─────────────────────────────────────
    "http_get": {"desc": "HTTP GET-Anfrage an eine URL", "params": {"url": "str", "headers": "dict={}"}},
    "http_post": {"desc": "HTTP POST-Anfrage", "params": {"url": "str", "json_data": "dict=None"}},
    "ping_host": {"desc": "Host anpingen (Erreichbarkeit prüfen)", "params": {"host": "str"}},
    "check_port": {"desc": "Prüfe ob ein Port offen ist", "params": {"host": "str", "port": "int"}},
    "get_network_info": {"desc": "Netzwerk-Infos: lokale IP, gesendet/empfangen", "params": {}},
    "get_public_ip": {"desc": "Öffentliche IP und Standort abrufen", "params": {}},
    "dns_lookup": {"desc": "DNS-Abfrage für einen Hostnamen", "params": {"hostname": "str"}},

    # ── Hilfsmittel ──────────────────────────────────
    "set_timer": {"desc": "Timer setzen — ARIA erinnert nach X Minuten", "params": {"minutes": "float", "message": "str='Timer abgelaufen!'"}},
    "cancel_timer": {"desc": "Timer abbrechen", "params": {"timer_id": "str=''"}},
    "list_timers": {"desc": "Aktive Timer anzeigen", "params": {}},
    "translate_text": {"desc": "Text in jede Sprache übersetzen (kein API Key)", "params": {"text": "str", "target_language": "str='de'", "source_language": "str='auto'"}},
    "generate_password": {"desc": "Sicheres Passwort generieren", "params": {"length": "int=16", "special_chars": "bool=True"}},
    "generate_qr": {"desc": "QR-Code aus Text/URL erstellen", "params": {"text": "str", "output_path": "str"}},
    "encode_base64": {"desc": "Text als Base64 kodieren", "params": {"text": "str"}},
    "decode_base64": {"desc": "Base64 Text dekodieren", "params": {"text": "str"}},
    "hash_text": {"desc": "Hash berechnen (sha256, md5, sha512...)", "params": {"text": "str", "algorithm": "str='sha256'"}},
    "get_date_time": {"desc": "Aktuelles Datum und Uhrzeit (lokal + UTC)", "params": {}},
    "count_words": {"desc": "Wörter, Zeichen und Sätze zählen", "params": {"text": "str"}},
    "kill_process": {"desc": "Prozess nach Name oder PID beenden", "params": {"name_or_pid": "str"}},

    # ── Git ──────────────────────────────────────────
    "git_status": {"desc": "Git-Status eines Repos anzeigen", "params": {"repo_path": "str='.'"}},
    "git_log": {"desc": "Git-Commit-Historie anzeigen", "params": {"repo_path": "str='.'", "n": "int=10"}},
    "git_commit": {"desc": "Git-Commit erstellen", "params": {"repo_path": "str", "message": "str"}},
    "git_clone": {"desc": "Git-Repository klonen", "params": {"url": "str", "destination": "str=''"}},

    # ── Krypto-Preise & Marktdaten ───────────────────
    "get_crypto_price": {"desc": "Krypto-Preis abrufen: BTC, ETH, SOL, WIF, BONK usw.", "params": {"symbol": "str", "currency": "str='usd'"}},
    "get_multiple_prices": {"desc": "Mehrere Krypto-Preise auf einmal (komma-getrennt)", "params": {"symbols": "str"}},
    "get_top_cryptos": {"desc": "Top N Kryptowährungen nach Market Cap", "params": {"n": "int=20"}},
    "get_price_history": {"desc": "Preisverlauf der letzten N Tage mit ASCII-Chart", "params": {"symbol": "str", "days": "int=7"}},
    "get_trending_coins": {"desc": "Trending Coins auf CoinGecko (letzte 24h)", "params": {}},
    "calculate_technical_analysis": {"desc": "RSI, MACD, Moving Averages (MA7/20/50), Volatilität", "params": {"symbol": "str", "days": "int=14"}},
    "get_fear_greed_index": {"desc": "Crypto Fear & Greed Index (0=Extreme Fear, 100=Extreme Greed)", "params": {}},

    # ── DEX / Solana ─────────────────────────────────
    "get_token_info": {"desc": "Token-Info von DexScreener: Preis, Liquidität, Volume, Risiko, Chart-Link", "params": {"address_or_symbol": "str"}},
    "search_dex_pairs": {"desc": "DEX Trading-Pairs auf DexScreener suchen", "params": {"query": "str", "limit": "int=5"}},
    "get_new_solana_tokens": {"desc": "Neu gelistete Solana Tokens (frische Launches)", "params": {"limit": "int=10"}},
    "get_solana_wallet_balance": {"desc": "Solana Wallet-Balance: SOL + alle Token-Holdings", "params": {"wallet_address": "str"}},
    "analyze_token_risk": {"desc": "Token Rug-Check: Liquidität, Volumen, Buy/Sell-Ratio, Score", "params": {"address": "str"}},
    "get_trending_solana_tokens": {"desc": "Trending Solana Tokens nach 24h-Volumen sortiert", "params": {}},

    # ── Portfolio-Tracking ───────────────────────────
    "add_position": {"desc": "Kauf-Position ins Portfolio eintragen", "params": {"symbol": "str", "amount": "float", "buy_price": "float", "notes": "str=''", "token_address": "str=''"}},
    "close_position": {"desc": "Position schließen und P&L (Gewinn/Verlust) berechnen", "params": {"position_id": "int", "sell_price": "float", "notes": "str=''"}},
    "get_portfolio": {"desc": "Gesamtes Portfolio mit aktuellem P&L anzeigen", "params": {"refresh_prices": "bool=True"}},
    "get_trade_journal": {"desc": "Komplettes Trade-Journal mit allen Käufen & Verkäufen", "params": {"limit": "int=20"}},
    "set_price_alert": {"desc": "Preis-Alert setzen — ARIA benachrichtigt wenn Kursziel erreicht", "params": {"symbol": "str", "target_price": "float", "direction": "str='above'"}},
    "check_price_alerts": {"desc": "Aktive Preis-Alerts überprüfen und ausgelöste melden", "params": {}},
    "get_portfolio_stats": {"desc": "Portfolio-Statistiken: Win-Rate, bester/schlechtester Trade", "params": {}},

    # ── Axiom.trade DEX-Trading ──────────────────────
    "axiom_open": {"desc": "Axiom.trade im Browser öffnen (Solana DEX)", "params": {}},
    "axiom_search_token": {"desc": "Token auf Axiom.trade suchen", "params": {"query": "str"}},
    "axiom_open_token": {"desc": "Token direkt auf Axiom öffnen (per Mint-Adresse)", "params": {"token_address": "str"}},
    "axiom_buy": {"desc": "Token auf Axiom kaufen — Wallet-Bestätigung im Browser nötig!", "params": {"token_address": "str", "amount_sol": "float"}},
    "axiom_buy_confirmed": {"desc": "Kauf bestätigen (für Beträge über 1 SOL)", "params": {"token_address": "str", "amount_sol": "float"}},
    "axiom_sell": {"desc": "Token auf Axiom verkaufen: percentage=25/50/75/100", "params": {"token_address": "str", "percentage": "float=100"}},
    "axiom_get_screenshot": {"desc": "Screenshot der aktuellen Axiom.trade Seite", "params": {}},
    "axiom_close": {"desc": "Axiom-Browser schließen", "params": {}},
}


class JarvisAgent:
    def __init__(self, config: dict, llm, episodic_memory, vector_memory,
                 learner, tool_registry, consciousness=None, max_memory=None):
        self.config = config
        self.llm = llm
        self.episodic = episodic_memory
        self.vector = vector_memory
        self.learner = learner
        self.tools = tool_registry
        self.consciousness = consciousness
        self.max_memory = max_memory
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
        # Grouped compact format — keeps token count low
        groups = {
            "Web/Suche": ["web_search", "web_fetch", "http_get", "http_post"],
            "Browser": ["browser_open", "browser_click", "browser_type", "browser_get_text", "browser_fill_form", "browser_press_key", "browser_scroll"],
            "PC-Steuerung": ["mouse_click", "mouse_move", "mouse_scroll", "type_text", "key_press", "take_screenshot", "get_screen_size"],
            "System": ["run_command", "open_application", "get_system_info", "list_running_apps", "get_clipboard", "set_clipboard", "send_desktop_notification", "kill_process"],
            "Dateien": ["read_file", "write_file", "list_directory", "search_files", "create_directory", "delete_file", "read_pdf", "read_csv", "write_csv"],
            "Code": ["run_python", "run_code", "calculate", "convert_units"],
            "Krypto": ["get_crypto_price", "get_multiple_prices", "get_top_cryptos", "calculate_technical_analysis", "get_fear_greed_index", "get_trending_coins"],
            "DEX/Solana": ["get_token_info", "analyze_token_risk", "get_new_solana_tokens", "get_trending_solana_tokens", "get_solana_wallet_balance"],
            "Portfolio": ["add_position", "close_position", "get_portfolio", "get_trade_journal", "set_price_alert", "get_portfolio_stats"],
            "Axiom.trade": ["axiom_open", "axiom_open_token", "axiom_buy", "axiom_sell", "axiom_get_screenshot"],
            "Medien": ["play_media", "set_volume", "get_volume", "stop_media"],
            "Hilfsmittel": ["set_timer", "translate_text", "generate_password", "get_weather", "get_date_time", "get_public_ip"],
            "Notizen": ["create_note", "list_notes", "read_note", "add_todo", "list_todos", "complete_todo"],
            "E-Mail": ["send_email", "read_emails"],
            "Git": ["git_status", "git_commit", "git_clone"],
        }
        lines = []
        for group, names in groups.items():
            tool_names = []
            for n in names:
                if n in TOOL_SCHEMA:
                    s = TOOL_SCHEMA[n]
                    p = ", ".join(s["params"].keys()) if s["params"] else ""
                    tool_names.append(f"{n}({p})")
            if tool_names:
                lines.append(f"[{group}] " + " | ".join(tool_names))
        return "\n".join(lines)

    async def _get_relevant_memories(self, user_message: str) -> str:
        """Fallback memory retrieval (2-level) when MaxMemory is not available."""
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
        import os, platform
        profile = self.episodic.get_profile()
        profile_str = ", ".join(f"{k}: {v}" for k, v in profile.items()) if profile else "Unbekannt"

        return SYSTEM_PROMPT.format(
            name=self.name,
            tools=self._build_tools_description(),
            user_profile=profile_str,
            memories=memories or "–",
            date=datetime.now().strftime("%d.%m.%Y %H:%M"),
            os_info=f"{platform.system()} {platform.release()}",
            home_dir=os.path.expanduser("~"),
            username=os.environ.get("USER", os.environ.get("USERNAME", "User")),
        )

    def _parse_action(self, text: str) -> Optional[tuple[str, dict]]:
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
                kv_pattern = r'"(\w+)":\s*"([^"]*)"'
                for k, v in re.findall(kv_pattern, params_match.group(1)):
                    params[k] = v

        return tool_name, params

    async def _execute_tool(self, tool_name: str, params: dict) -> str:
        result = await self.tools.execute(tool_name, **params)
        return str(result)

    def _detect_emotion_in_response(self, text: str) -> Optional[str]:
        """Detect what emotion ARIA expressed in her response."""
        t = text.lower()
        if any(m in t for m in ["*lacht", "*haha", "haha", "hihi", "[begeistert]", "[freudig]", "[aufgeregt]", "(lacht)", "*kichert"]):
            return "Freude"
        if any(m in t for m in ["[traurig]", "(seufzt)", "[besorgt]", "[nachdenklich]", "*seufzt"]):
            return "Nachdenklichkeit"
        if any(m in t for m in ["[mitfühlend]", "[einfühlsam]", "[warm]", "[empathisch]"]):
            return "Empathie"
        if any(m in t for m in ["[fasziniert]", "[neugierig]", "[interessant]", "*staunt"]):
            return "Neugier"
        if any(m in t for m in ["[überrascht]", "[wow]", "*staunt", "*erstaunt"]):
            return "Überraschung"
        return None

    async def chat_stream(
        self,
        user_message: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[dict, None]:
        session_id = session_id or self.current_session or self.new_session()

        self.episodic.add_message(session_id, "user", user_message)

        # Get memories — MaxMemory (5 levels) when available, fallback to basic retrieval
        if self.max_memory:
            memories = await self.max_memory.get_full_context(
                user_message, self.episodic, self.consciousness
            )
        else:
            memories = await self._get_relevant_memories(user_message)

        history = self.episodic.get_recent_messages(session_id, n=8)
        system = self._build_system_prompt(memories)

        messages = history[:-1] if history else []
        messages.append({"role": "user", "content": user_message})

        full_response = ""
        tool_calls = []
        iterations = 0

        while iterations < self.max_tool_iterations:
            iterations += 1
            current_response = ""

            async for token in self.llm.chat_stream(
                messages=messages,
                system=system,
                model=self.llm.default_model
            ):
                current_response += token
                if "ACTION:" not in current_response:
                    yield {"type": "token", "content": token}
                full_response += token

            parsed = self._parse_action(current_response)
            if not parsed:
                break

            tool_name, params = parsed
            yield {"type": "tool_start", "tool": tool_name, "params": params}

            observation = await self._execute_tool(tool_name, params)
            tool_calls.append({
                "tool": tool_name,
                "params": params,
                "result": observation[:500]
            })

            yield {"type": "tool_result", "tool": tool_name, "result": observation[:200]}

            messages.append({"role": "assistant", "content": current_response})
            messages.append({
                "role": "user",
                "content": f"OBSERVATION: {observation}\n\nBitte beantworte jetzt die ursprüngliche Frage basierend auf dieser Information."
            })
            full_response = ""

        final_response = current_response if iterations > 1 else full_response

        clean_response = re.sub(r"THOUGHT:.*?(?=\n\n|\Z)", "", final_response, flags=re.DOTALL).strip()
        clean_response = re.sub(r"ACTION:.*?PARAMS:.*?\}", "", clean_response, flags=re.DOTALL).strip()
        if not clean_response:
            clean_response = final_response

        self.episodic.add_message(session_id, "assistant", clean_response)

        # Store in vector memory and track emotional moments
        try:
            combined = f"User: {user_message}\nARIA: {clean_response}"
            embedding = await self.llm.embed(combined)
            if embedding:
                self.vector.add_conversation(user_message, clean_response, embedding, session_id)
                if self.max_memory:
                    emotion = self._detect_emotion_in_response(clean_response)
                    if emotion:
                        self.max_memory.store_emotional_memory(
                            event=f"Gespräch: {user_message[:120]}",
                            emotion=emotion,
                            intensity=0.7
                        )
        except Exception:
            pass

        if self.consciousness:
            self.consciousness.react_to_message(user_message)
            conversation_snippet = f"User: {user_message}\nARIA: {clean_response}"
            asyncio.create_task(self.consciousness.reflect(conversation_snippet))
            asyncio.create_task(self.consciousness.maybe_update_goals(conversation_snippet))

        await self.learner.maybe_learn(session_id)

        yield {"type": "done", "response": clean_response, "tool_calls": tool_calls}

    async def chat(self, user_message: str, session_id: Optional[str] = None) -> str:
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
