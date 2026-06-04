#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║           JARVIS AI - Automatisches Setup-Script             ║
# ║    Installiert alles was du brauchst auf deinem PC           ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log() { echo -e "${CYAN}[JARVIS]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[FEHLER]${NC} $1"; exit 1; }

echo -e "${CYAN}${BOLD}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════╗
║            JARVIS AI SETUP                            ║
║     Lokaler KI-Assistent ohne API                     ║
╚═══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# ─── 1. System-Check ───────────────────────────────────────────
log "Prüfe System..."

if ! command -v python3 &> /dev/null; then
    err "Python3 nicht gefunden! Installiere Python 3.10+: https://python.org"
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "Python $PYTHON_VERSION gefunden"

if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    ok "Python-Version OK"
else
    err "Python 3.10+ benötigt! Aktuell: $PYTHON_VERSION"
fi

# ─── 2. Ollama installieren ─────────────────────────────────────
log "Prüfe Ollama..."

if command -v ollama &> /dev/null; then
    OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "unbekannt")
    ok "Ollama bereits installiert: $OLLAMA_VERSION"
else
    echo ""
    log "Installiere Ollama (lokale LLM-Engine)..."
    if command -v curl &> /dev/null; then
        curl -fsSL https://ollama.ai/install.sh | sh
        ok "Ollama installiert!"
    else
        warn "curl nicht verfügbar. Installiere Ollama manuell:"
        echo "  Linux: curl -fsSL https://ollama.ai/install.sh | sh"
        echo "  macOS: brew install ollama"
        echo "  Windows: https://ollama.ai/download"
    fi
fi

# ─── 3. Python Virtual Environment ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log "Erstelle Python-Umgebung..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    ok "Virtual Environment erstellt"
else
    ok "Virtual Environment vorhanden"
fi

source venv/bin/activate

# ─── 4. Python-Pakete installieren ──────────────────────────────
log "Installiere Python-Abhängigkeiten..."
pip install --upgrade pip --quiet

# Install requirements
pip install -r requirements.txt --quiet

ok "Python-Pakete installiert!"

# ─── 5. Systemabhängigkeiten (Linux) ────────────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    log "Prüfe Linux-Systemabhängigkeiten..."

    # Audio support
    if ! python3 -c "import sounddevice" 2>/dev/null; then
        warn "Für Sprachaufnahme: sudo apt-get install portaudio19-dev python3-pyaudio"
    fi

    # Audio playback
    if ! command -v mpg123 &> /dev/null && ! command -v aplay &> /dev/null; then
        warn "Für Sprachausgabe: sudo apt-get install mpg123"
        warn "Oder: pip install pygame"
    fi
fi

# ─── 6. Ollama starten ──────────────────────────────────────────
log "Starte Ollama-Server..."
if ! pgrep -x "ollama" > /dev/null; then
    if command -v ollama &> /dev/null; then
        ollama serve &>/dev/null &
        sleep 2
        ok "Ollama-Server gestartet"
    fi
else
    ok "Ollama läuft bereits"
fi

# ─── 7. Modelle herunterladen ────────────────────────────────────
log "Lade KI-Modelle herunter..."
echo "   Das kann einige Minuten dauern (je nach Internetgeschwindigkeit)"

if command -v ollama &> /dev/null; then
    # Standard-Modell (3B - schnell, ~2GB)
    echo "📥 Lade llama3.2:3b (2GB, schnell)..."
    ollama pull llama3.2:3b || warn "llama3.2:3b konnte nicht geladen werden"

    # Embedding-Modell (klein, für Gedächtnis)
    echo "📥 Lade nomic-embed-text (274MB, Gedächtnis)..."
    ollama pull nomic-embed-text || warn "nomic-embed-text konnte nicht geladen werden"

    echo ""
    echo "💡 Optional - Größere Modelle (besser, aber langsamer):"
    echo "   ollama pull llama3.1:8b      # 4.7GB - Empfohlen für leistungsstarke PCs"
    echo "   ollama pull mistral:7b       # 4.1GB - Gut für Deutsch"
    echo "   ollama pull qwen2.5:7b       # 4.4GB - Exzellentes Deutsch"
    echo "   ollama pull deepseek-r1:7b   # 4.7GB - Stark beim Denken"
    echo "   ollama pull llama3.1:70b     # 40GB  # Bestes Modell (High-End PC)"
fi

# ─── 8. Daten-Verzeichnisse ──────────────────────────────────────
log "Erstelle Daten-Verzeichnisse..."
mkdir -p data data/chroma data/notes ~/jarvis_files
ok "Verzeichnisse erstellt"

# ─── 9. Start-Script ─────────────────────────────────────────────
cat > start.sh << 'STARTEOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Starte Ollama falls nicht läuft
if command -v ollama &> /dev/null && ! pgrep -x "ollama" > /dev/null; then
    echo "Starte Ollama..."
    ollama serve &>/dev/null &
    sleep 2
fi

source venv/bin/activate
python main.py "$@"
STARTEOF
chmod +x start.sh

# ─── 10. Fertig! ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║      ✅  JARVIS SETUP ABGESCHLOSSEN!                  ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo "🚀 Starten mit:"
echo "   cd jarvis"
echo "   ./start.sh"
echo ""
echo "🌐 Dann öffne: http://localhost:7860"
echo ""
echo "💡 Tipps:"
echo "   • Für bessere Ergebnisse: ollama pull llama3.1:8b"
echo "   • Modell in config.yaml ändern"
echo "   • Logs: ./start.sh --log-level debug"
echo ""
