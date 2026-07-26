# Build-Prompt: Solana Memecoin Signal- & Wallet-Bot mit WhatsApp

> Kopiere den gesamten Text unterhalb der Linie und gib ihn einem Coding-Agenten
> (z. B. Claude Code) als Auftrag. Er ist vollständig — ohne Platzhalter.

---

## AUFTRAG

Baue ein produktionsreifes Python-Kommandozeilen-Projekt namens **`solana-bot`**,
das zwei Funktionen in **einem** Tool vereint und beide über **WhatsApp**
(via CallMeBot) benachrichtigt:

1. **Wallet-Scanner** – überwacht eine feste Solana-Wallet und meldet neue
   Token-Käufe/-Verkäufe samt Gewinn/Verlust (P&L).
2. **Memecoin-Signale** – findet neue/trendende Solana-Memecoins und schickt
   Kauf-Signale, sobald sie definierte Kriterien erfüllen.

Beide Teile teilen sich Konfiguration, Preisquelle und Benachrichtigungs-Layer.

## GRUNDPRINZIPIEN

- Python 3.10+. Einzige Pflicht-Abhängigkeit: `requests`. Kein schweres
  Solana-SDK — Solana wird direkt per JSON-RPC angesprochen.
- Sauberer, modularer Code mit Typannotationen und Docstrings. Deutschsprachige
  Konsolen- und WhatsApp-Ausgaben.
- Robust gegen Netzfehler: Timeouts, Wiederholungen mit exponentiellem Backoff,
  niemals wegen eines fehlgeschlagenen API-Calls abstürzen.
- Zustand persistent in JSON-Dateien, damit ein Neustart keine Doppel-Alerts
  auslöst und Kostenbasis erhalten bleibt.
- Secrets ausschließlich über `.env` / Umgebungsvariablen, niemals hart im Code.
  `.env` und alle State-/Log-Dateien gehören in `.gitignore`.

## FESTE KONFIGURATIONSWERTE (real, so übernehmen)

Lege eine `.env` mit exakt diesen Werten an (zusätzlich eine `.env.example` mit
denselben Schlüsseln, aber leeren Geheimwerten):

    # Wallet & RPC
    WALLET_ADDRESS=CWNXGmsLBjFzYf9vz8BtnhHw9pf2nex4N6LiRiw2PFb7
    SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

    # WhatsApp via CallMeBot
    WHATSAPP_PROVIDER=callmebot
    CALLMEBOT_APIKEY=2115030
    WHATSAPP_TO=4915678354158

    # Memecoin-Signal-Filter (Standardwerte, per .env überschreibbar)
    SIGNAL_CHAIN=solana
    SIGNAL_MIN_LIQUIDITY_USD=10000
    SIGNAL_MIN_VOLUME_H1_USD=20000
    SIGNAL_MIN_PRICE_CHANGE_H1=20
    SIGNAL_MAX_AGE_HOURS=48
    SIGNAL_MIN_TXNS_H1=50
    SIGNAL_POLL_SECONDS=60

    # Wallet-Scan
    WALLET_POLL_SECONDS=30
    WALLET_MIN_VALUE_USD=1.0

    # Optional zusätzliche Kanäle (leer lassen, wenn ungenutzt)
    TELEGRAM_BOT_TOKEN=
    TELEGRAM_CHAT_ID=

## PROJEKTSTRUKTUR

    solana-bot/
      bot.py             # einheitlicher CLI-Einstieg mit Subcommands
      config.py          # lädt .env + Umgebungsvariablen in ein Config-Objekt
      solana_rpc.py      # Solana JSON-RPC Client
      prices.py          # DexScreener Preis-/Metadaten-Provider (Cache)
      notifier.py        # Konsole + WhatsApp (CallMeBot/Twilio/Meta) + Telegram
      wallet_scanner.py  # Wallet-Überwachung + P&L
      signals.py         # Memecoin-Signal-Scanner
      requirements.txt
      .env               # echte Werte (gitignored)
      .env.example
      .gitignore
      README.md
      tests/
        test_logic.py    # Offline-Tests ohne Netzwerk (siehe unten)

## MODUL: config.py

- Lädt eine `.env` im Projektverzeichnis (einfacher eigener Parser: Zeilen
  `KEY=VALUE`, `#`-Kommentare ignorieren, umschließende Quotes entfernen),
  danach überschreibbar durch echte Umgebungsvariablen.
- Stellt ein `Config`-Dataclass mit allen oben genannten Schlüsseln bereit,
  typisiert (float/int/str), inkl. sinnvoller Defaults, falls ein Wert fehlt.

## MODUL: solana_rpc.py

- Klasse `SolanaRPC(url, timeout=20)` mit `requests.Session`.
- Methode `get_token_accounts(owner) -> dict[mint, (ui_amount, decimals)]`:
  ruft `getTokenAccountsByOwner` per JSON-RPC für **beide** Token-Programme auf
  und summiert mehrere Konten desselben Mints:
    - Klassisch: `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`
    - Token-2022: `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`
  - Params: `[owner, {"programId": <id>}, {"encoding": "jsonParsed"}]`
  - Menge aus `account.data.parsed.info.tokenAmount.uiAmount`, Nullbestände
    überspringen.
- Methode `get_sol_balance(owner) -> float` über `getBalance` (Lamports/1e9).
- Wrapped-SOL-Mint als Konstante: `So11111111111111111111111111111111111111112`
  (bei der Kaufanalyse ignorieren – ist nur "Cash").
- Bei RPC-Fehlern eine aussagekräftige Exception werfen.

## MODUL: prices.py

- Quelle: öffentliche DexScreener-API (kein API-Key).
- Klasse `PriceProvider(ttl=20)` mit kurzem In-Memory-Cache pro Mint.
- `get(mint) -> (price_usd, symbol)`:
    - GET `https://api.dexscreener.com/latest/dex/tokens/<mint>`
    - aus `pairs` das Paar mit **höchster** `liquidity.usd` wählen; `priceUsd`
      und Symbol (aus `baseToken`/`quoteToken` passend zum Mint) übernehmen.
    - Bei Fehler/kein Paar: Preis `0.0`, Symbol = erste 4 Zeichen des Mints.

## MODUL: notifier.py

- Klasse `Notifier` liest die Kanäle aus der Config.
- `send(text_console, text_plain)`: gibt immer auf der Konsole aus und schickt
  zusätzlich an alle aktiven Kanäle (WhatsApp, Telegram).
- **WhatsApp mit drei Anbietern**, Auto-Erkennung über gesetzte Variablen,
  erzwingbar via `WHATSAPP_PROVIDER` (`callmebot` | `twilio` | `cloud`):
    - **callmebot** (Standard hier): GET
      `https://api.callmebot.com/whatsapp.php` mit Query
      `phone=<WHATSAPP_TO>&text=<text>&apikey=<CALLMEBOT_APIKEY>`.
      Text URL-enkodieren. HTTP >= 400 als Fehler behandeln.
    - **twilio**: POST
      `https://api.twilio.com/2010-04-01/Accounts/<SID>/Messages.json`,
      HTTP-Basic-Auth (SID, Token), Form-Felder `From` (`whatsapp:<from>`),
      `To` (`whatsapp:<to>`), `Body`. Env: `TWILIO_ACCOUNT_SID`,
      `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `WHATSAPP_TO`.
    - **cloud** (Meta): POST
      `https://graph.facebook.com/v20.0/<PHONE_NUMBER_ID>/messages`,
      Header `Authorization: Bearer <WHATSAPP_CLOUD_TOKEN>`, JSON
      `{messaging_product:"whatsapp", to:<digits>, type:"text",
      text:{body:<text>}}`. Env: `WHATSAPP_CLOUD_TOKEN`,
      `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TO`.
- **Telegram** (optional, zusätzlich): POST
  `https://api.telegram.org/bot<token>/sendMessage` mit `chat_id`, `text`.
- Ein fehlgeschlagener Versand darf den Bot nicht stoppen: fangen, warnen,
  weiterlaufen.
- WhatsApp-Nachrichten ohne ANSI-Farbcodes senden (Konsolenfarben strippen).

## MODUL: wallet_scanner.py

Überwacht `WALLET_ADDRESS` und erkennt Bestandsänderungen.

- `Position`-Dataclass: `mint, symbol, amount, avg_cost_usd,
  realized_pnl_usd, first_seen, last_price_usd`.
- State-Datei `wallet_state.json` (laden/speichern atomar über temp+rename).
- Ein Scan-Durchlauf (`scan_once`):
    1. Aktuelle Bestände via `SolanaRPC.get_token_accounts`. Wrapped-SOL
       überspringen.
    2. Für jeden Mint Preis+Symbol holen und mit gespeichertem Bestand
       vergleichen:
        - **Neuer Token** (unbekannt) über `WALLET_MIN_VALUE_USD`: Position mit
          aktuellem Preis als Einstand anlegen → Alert "🟢 NEUER TOKEN GEKAUFT".
        - **Zukauf** (Bestand gestiegen): gewichteten Durchschnitts-Einstand neu
          berechnen `avg = (alte_kostenbasis + delta*preis) / neue_menge` →
          Alert "🟢 ZUKAUF".
        - **Verkauf** (Bestand gesunken): realisierten P&L fortschreiben
          `realized += verkauft*(preis - avg)` → Alert "🔴 VERKAUF".
        - **Komplett verschwunden**: als Vollverkauf behandeln.
    3. State speichern, danach Alerts versenden, danach Portfolio-Tabelle
       ausgeben (Menge, Preis, Wert, Ø Einstand, unrealisierter P&L in $ und %,
       plus Summen für Gesamtwert/unrealisiert/realisiert).
- **Erster Lauf**: aktuellen Bestand nur als Ausgangsbasis erfassen, KEINE
  Alerts für Alt-Bestände senden.
- Unrealisierter P&L = `amount * (aktueller_preis - avg_cost_usd)`.
- Hinweis im README: Kaufpreis = Marktpreis zum Erkennungszeitpunkt (Näherung).

## MODUL: signals.py

Findet neue/trendende Solana-Memecoins und sendet Kauf-Signale.

- Quellen (öffentliche DexScreener-Endpunkte, kein Key):
    - `https://api.dexscreener.com/token-boosts/latest/v1`
    - `https://api.dexscreener.com/token-profiles/latest/v1`
  Beide liefern Token mit `chainId` und `tokenAddress`. Nur Einträge mit
  `chainId == SIGNAL_CHAIN` ("solana") verwenden.
- Für jede Kandidaten-`tokenAddress` die Paardaten laden:
  `https://api.dexscreener.com/latest/dex/tokens/<address>` und das Paar mit
  höchster Liquidität nehmen. Daraus lesen: `priceUsd`, `liquidity.usd`,
  `volume.h1`, `priceChange.h1`, `txns.h1` (buys+sells), `pairCreatedAt`
  (Alter in Stunden), `baseToken.symbol`, `baseToken.name`, `url`.
- **Signal-Kriterien** (alle müssen erfüllt sein; Werte aus Config):
    - `liquidity.usd >= SIGNAL_MIN_LIQUIDITY_USD`
    - `volume.h1 >= SIGNAL_MIN_VOLUME_H1_USD`
    - `priceChange.h1 >= SIGNAL_MIN_PRICE_CHANGE_H1`
    - Alter des Paares `<= SIGNAL_MAX_AGE_HOURS`
    - `txns.h1 (buys+sells) >= SIGNAL_MIN_TXNS_H1`
- **Deduplizierung**: bereits gemeldete Mints in `signals_state.json` speichern;
  denselben Token nicht erneut melden (optional erneut, wenn er nach
  Abklingzeit die Kriterien wieder frisch erfüllt — Standard: nur einmal).
- Bei einem Treffer WhatsApp-Alert mit: Symbol, Name, Preis, Liquidität,
  1h-Volumen, 1h-Änderung in %, Alter, Contract-Adresse und DexScreener-Link.
  Format-Beispiel (Klartext):
      🚀 MEMECOIN-SIGNAL: <SYMBOL> (<NAME>)
      Preis: $<preis>   1h: +<x>%
      Liquidität: $<liq>   Vol 1h: $<vol>   Alter: <h>h
      CA: <mint>
      <dexscreener-url>
- **Erster Lauf**: aktuelle Treffer als bekannt markieren, aber der Nutzer soll
  per Flag `--alert-on-first-run` erzwingen können, dass auch beim ersten Lauf
  gesendet wird (Default: still erfassen). Für Signale ist es meist erwünscht,
  auch beim ersten Lauf zu melden — mach das per Config `SIGNAL_ALERT_FIRST_RUN`
  (Default `true`) einstellbar.

## MODUL/CLI: bot.py

Ein einheitlicher Einstieg mit Subcommands (argparse subparsers):

    python bot.py wallet            # nur Wallet-Scan (Dauerbetrieb)
    python bot.py signals           # nur Memecoin-Signale (Dauerbetrieb)
    python bot.py both              # beides parallel in einer Schleife
    python bot.py test-notify       # Testnachricht an alle Kanäle, dann Ende
    python bot.py wallet --once     # einmaliger Wallet-Scan (für cron)
    python bot.py signals --once    # einmaliger Signal-Scan (für cron)

Gemeinsame Optionen: `--interval` (überschreibt Poll-Sekunden), `--env <pfad>`
(alternative .env). Beim Start eine Übersicht ausgeben: Wallet, RPC, aktiver
WhatsApp-Anbieter, Empfänger (maskiert, letzte 4 Stellen), aktive Kanäle,
Intervalle.

`both` führt in jeder Schleifeniteration erst den Wallet-Scan, dann den
Signal-Scan aus (jeweils eigener Fehler-Catch), respektiert aber getrennte
Poll-Intervalle (z. B. via einfacher Zeitstempel-Logik, damit Signale mit
`SIGNAL_POLL_SECONDS` und Wallet mit `WALLET_POLL_SECONDS` laufen).

Sauberes Beenden bei Ctrl+C.

## FEHLERBEHANDLUNG & NETZWERK

- Alle HTTP-Calls mit Timeout (15–20 s).
- RPC- und DexScreener-Aufrufe mit bis zu 4 Wiederholungen und Backoff
  (2 s, 4 s, 8 s, 16 s) bei `requests`-Ausnahmen.
- In der Dauerschleife jeden Durchlauf in try/except kapseln, Fehler loggen,
  weiterlaufen. Der Bot darf nie wegen eines einzelnen Fehlversuchs sterben.
- Öffentlicher Solana-RPC ist stark rate-limitiert: im README auf einen eigenen
  Endpunkt (Helius/QuickNode) hinweisen; per `SOLANA_RPC_URL` konfigurierbar.

## TESTS (tests/test_logic.py, ohne Netzwerk)

Schreibe Offline-Tests, die die Kernlogik mit gefälschten RPC-/Preis-Objekten
prüfen (kein echter Netzzugriff):

- Wallet-P&L: Kauf 1000@$0.01, Zukauf 1000@$0.02 → Ø-Einstand $0.015; danach
  Verkauf 1500@$0.03 → realisierter P&L = 22.5, Restbestand 500, unrealisiert
  bei $0.03 = 7.5. Per assert prüfen.
- Signal-Filter: ein Token, der alle Schwellen knapp erfüllt, löst ein Signal
  aus; einer, der bei einem Kriterium darunter liegt, nicht. Dedup: derselbe
  Token wird nicht doppelt gemeldet.
- Notifier-Anbieter-Erkennung: nur CallMeBot-Vars gesetzt → Anbieter
  "callmebot"; erzwungener Anbieter ohne Vars → deaktiviert (kein Crash).

Tests müssen ohne Internet grün sein.

## README.md

Vollständige Anleitung auf Deutsch: Installation (`pip install -r
requirements.txt`), `.env`-Setup, CallMeBot-Aktivierung (Nummer speichern,
"I allow callmebot to send me messages" senden, API-Key eintragen), alle
Subcommands mit Beispielen, Erklärung der Signal-Kriterien und der
P&L-Berechnung inkl. Näherungs-Hinweis, Twilio/Meta als Alternativen,
Cron-Beispiel für `--once`, Hinweis auf eigenen RPC-Endpunkt.

## ABNAHMEKRITERIEN

- `python bot.py test-notify` schickt mit der hinterlegten CallMeBot-Config eine
  echte WhatsApp-Nachricht an 4915678354158.
- `python bot.py wallet` erfasst beim ersten Lauf still den Bestand und meldet
  danach neue Käufe/Verkäufe der Wallet CWNXGmsLBjFzYf9vz8BtnhHw9pf2nex4N6LiRiw2PFb7
  inkl. P&L-Tabelle.
- `python bot.py signals` meldet neue Solana-Memecoins, die die Kriterien
  erfüllen, ohne Duplikate.
- `python bot.py both` betreibt beides dauerhaft und stabil.
- `pytest -q` (bzw. `python -m pytest`) ist grün, ohne Internet.
- Keine Secrets im committeten Code; `.env` ist gitignored.

Erstelle alle Dateien vollständig und lauffähig.
