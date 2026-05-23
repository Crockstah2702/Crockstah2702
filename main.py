"""
Copy-Trading Web-Terminal — Einstiegspunkt.

Startet einen lokalen Webserver und öffnet das Terminal im Browser.
Alle Keys/Einstellungen werden im Browser eingetragen und in .env gespeichert.

Start:
    pip install -r requirements.txt
    python main.py
    → Browser öffnet automatisch http://localhost:8080
"""

import logging
import sys
import threading
import time
import webbrowser

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log")],
)

PORT = 8080
URL = f"http://localhost:{PORT}"


def _open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main():
    print("=" * 60)
    print("  COPY-TRADING WEB-TERMINAL")
    print("=" * 60)
    print(f"\n  Öffne im Browser:  {URL}\n")
    print("  Trage dort deine Keys ein, speichere und drücke ▶ Start.")
    print("  Beenden mit STRG+C.\n")

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "web_app:app",
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
