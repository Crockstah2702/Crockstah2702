#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# ARIA Autostart installieren — startet beim PC-Login automatisch
# ─────────────────────────────────────────────────────────────────────────────
set -e

JARVIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="aria"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     ARIA — Autostart-Installation           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Prüfe ob venv existiert
if [ ! -f "$JARVIS_DIR/venv/bin/python" ]; then
    echo "❌ Virtuelle Umgebung nicht gefunden!"
    echo "   Bitte erst: bash $JARVIS_DIR/setup.sh"
    exit 1
fi

# systemd User-Service-Verzeichnis erstellen
mkdir -p "$SERVICE_DIR"

# Service-Datei mit echtem Pfad kopieren
sed "s|%h|$HOME|g" "$JARVIS_DIR/jarvis.service" > "$SERVICE_DIR/${SERVICE_NAME}.service"

echo "✅ Service-Datei erstellt: $SERVICE_DIR/${SERVICE_NAME}.service"

# systemd neu laden und Service aktivieren
systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}.service"
systemctl --user start "${SERVICE_NAME}.service"

echo "✅ ARIA Autostart aktiviert!"
echo ""
echo "   Status prüfen:    systemctl --user status aria"
echo "   Logs anzeigen:    journalctl --user -u aria -f"
echo "   Stoppen:          systemctl --user stop aria"
echo "   Deinstallieren:   systemctl --user disable aria && rm $SERVICE_DIR/${SERVICE_NAME}.service"
echo ""

# Lingering aktivieren (damit der Service auch ohne Login startet)
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$USER" 2>/dev/null || true
    echo "✅ Linger aktiviert — ARIA startet beim Systemstart (auch ohne Login)"
fi

echo ""
echo "🌐 ARIA erreichbar unter: http://localhost:7860"
echo ""
