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

    # Memecoin-Signal – Basis-Sanity-Filter (Standardwerte, per .env überschreibbar)
    SIGNAL_CHAIN=solana
    SIGNAL_MIN_LIQUIDITY_USD=10000
    SIGNAL_MAX_AGE_HOURS=48
    SIGNAL_POLL_SECONDS=60
    SIGNAL_ALERT_FIRST_RUN=false
    # Wie viele Kandidaten pro Zyklus mit Kerzen geprüft werden (Rate-Limit-Schutz)
    SIGNAL_MAX_TOKENS_PER_CYCLE=12
    # Kandidatenquellen: new,trending (kommagetrennt)
    SIGNAL_SOURCES=new,trending

    # Candle/OHLCV-Signale (GeckoTerminal, kostenlos, ohne Key)
    # Timeframes, die geprüft werden (1m,5m,15m). Ein Signal auf EINEM reicht.
    SIGNAL_TIMEFRAMES=1m,5m,15m
    # Volumen-Spike: Volumen der letzten Kerze >= Faktor * Ø der vorherigen N Kerzen
    SIGNAL_VOLUME_SPIKE_FACTOR=3.0
    SIGNAL_VOLUME_SPIKE_LOOKBACK=10
    # Grüne-Kerzen-Serie: mind. so viele grüne Kerzen in Folge am Ende
    SIGNAL_GREEN_STREAK=3
    # Ausbruch: letzter Close > höchstes High der vorherigen N Kerzen
    SIGNAL_BREAKOUT_LOOKBACK=10
    # So viele der letzten Kerzen mit in die WhatsApp-Nachricht schreiben
    SIGNAL_CANDLES_IN_ALERT=5
    # Pause zwischen GeckoTerminal-Calls in ms (Rate-Limit ~30/min)
    SIGNAL_GECKO_DELAY_MS=300

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
      geckoterminal.py   # GeckoTerminal-Client: new/trending Pools + OHLCV-Kerzen
      candles.py         # Candle-Analyse: Volumen-Spike, grüne Serie, Breakout
      notifier.py        # Konsole + WhatsApp (CallMeBot/Twilio/Meta) + Telegram
      wallet_scanner.py  # Wallet-Überwachung + P&L
      signals.py         # Memecoin-Signal-Scanner (nutzt geckoterminal + candles)
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

## MODUL: geckoterminal.py

Client für die kostenlose GeckoTerminal-API (kein API-Key; Rate-Limit ~30
Anfragen/Minute – daher `SIGNAL_GECKO_DELAY_MS` zwischen Calls einhalten).
Basis-URL `https://api.geckoterminal.com/api/v2`. Header
`Accept: application/json`.

- `get_new_pools(network="solana") -> list[Pool]`:
  GET `/networks/solana/new_pools?page=1`.
- `get_trending_pools(network="solana") -> list[Pool]`:
  GET `/networks/solana/trending_pools?page=1`.
  Beide liefern `data` (Liste). Pro Eintrag ein `Pool`-Objekt bauen aus
  `attributes` und `relationships`:
    - `pool_address` = `attributes.address`
    - `name` = `attributes.name` (z. B. "PEPE / SOL")
    - `price_usd` = float(`attributes.base_token_price_usd`)
    - `liquidity_usd` = float(`attributes.reserve_in_usd`)
    - `volume_h1_usd` = float(`attributes.volume_usd.h1`)
    - `price_change_h1` = float(`attributes.price_change_percentage.h1`)
    - `created_at` = `attributes.pool_created_at` (ISO → Alter in Stunden)
    - `base_mint` = aus `relationships.base_token.data.id`
      (Format `"solana_<MINT>"` → Präfix `solana_` entfernen)
    - `symbol`/`name` des Tokens soweit vorhanden; sonst aus `name` ableiten.
  Fehlende/None-Felder tolerant auf 0.0 bzw. "" defaulten.
- `get_ohlcv(pool_address, timeframe, aggregate, limit=50) -> list[Candle]`:
  GET `/networks/solana/pools/<pool_address>/ohlcv/<tf>?aggregate=<agg>&limit=<n>`
  mit Mapping der Timeframe-Kürzel:
    - `1m`  → tf=`minute`, aggregate=`1`
    - `5m`  → tf=`minute`, aggregate=`5`
    - `15m` → tf=`minute`, aggregate=`15`
    - `1h`  → tf=`hour`,   aggregate=`1`
  Antwort: `data.attributes.ohlcv_list` = Liste von
  `[timestamp, open, high, low, close, volume]`. GeckoTerminal liefert
  **neueste zuerst** – im Client nach `timestamp` **aufsteigend** sortieren, so
  dass das letzte Listenelement die aktuellste Kerze ist. Jede Kerze als
  `Candle`-Dataclass `(ts, open, high, low, close, volume)` mit floats.
- Alle Calls mit Timeout, Retry+Backoff; bei Fehler leere Liste zurückgeben
  (nie werfen, damit der Scan weiterläuft).

## MODUL: candles.py

Reine Rechenlogik auf einer Candle-Liste (aufsteigend sortiert, letzte =
aktuellste). Keine Netzwerkzugriffe → voll offline testbar. Alle Schwellen
kommen aus der Config.

- `volume_spike(candles, factor, lookback) -> (bool, float)`:
  Vergleiche das Volumen der **letzten** Kerze mit dem Durchschnitt der
  vorherigen `lookback` Kerzen. Rückgabe `(spike, ratio)` mit
  `ratio = last_volume / avg_prev` (avg_prev>0). `spike = ratio >= factor`.
  Der Volumen-Spike ist der **Hauptfaktor** (= erhöhter Kaufdruck/Interesse).
- `green_streak(candles) -> int`: Anzahl der grünen Kerzen (`close > open`) am
  Ende der Liste in Folge.
- `breakout(candles, lookback) -> bool`: `True`, wenn der `close` der letzten
  Kerze größer ist als das höchste `high` der davor liegenden `lookback` Kerzen.
- `last_change_pct(candles, n) -> float`: prozentuale Änderung von `close` der
  Kerze vor `n` Perioden bis zur letzten Kerze.
- `format_candles(candles, count) -> str`: die letzten `count` Kerzen als
  kompakte Textzeilen für die WhatsApp-Nachricht, z. B.
  `HH:MM  O:0.0012 H:0.0015 L:0.0011 C:0.0014  Vol:$3.2k  ▲`
  (grün ▲ wenn close>=open, sonst rot ▼).
- `evaluate(candles, cfg) -> CandleSignal|None`: kombiniert die obigen Checks
  für **einen** Timeframe. Ein Signal entsteht, wenn **Volumen-Spike** vorliegt
  **UND** mindestens eine Bestätigung (grüne Serie `>= SIGNAL_GREEN_STREAK`
  ODER Breakout). Rückgabe enthält: Timeframe, ratio, green_streak, breakout
  (bool), last_change_pct und eine kurze Begründung als Text, z. B.
  `"Vol-Spike 4.2× · 3 grüne Kerzen · Breakout (5m)"`. Kein Signal → `None`.
  Zu wenige Kerzen (weniger als `lookback+1`) → `None`.

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

Beobachtet **alle** neuen und trendenden Solana-Memecoins, prüft sie anhand von
**Candle-Daten** und sendet nur bei echten Signalen einen WhatsApp-Alert
(Prinzip: „alles scannen, aber nur bei Signal melden" – kein Spam).

Ablauf eines Durchlaufs (`scan_once`), nutzt `GeckoTerminal` + `candles`:

1. **Kandidaten sammeln (alles erkennen):** Je nach `SIGNAL_SOURCES` die Pools
   aus `get_new_pools()` und/oder `get_trending_pools()` laden und zu einer
   Kandidatenliste zusammenführen (nach `pool_address` deduplizieren).
2. **Basis-Sanity-Filter** direkt aus den Pool-Daten (ohne Zusatz-Call), um die
   Menge sinnvoll zu begrenzen:
    - `liquidity_usd >= SIGNAL_MIN_LIQUIDITY_USD`
    - Alter `<= SIGNAL_MAX_AGE_HOURS`
   (Rugs/Staub mit Mini-Liquidität fallen so raus.)
3. Übrige Kandidaten nach `volume_h1_usd` absteigend sortieren und auf
   `SIGNAL_MAX_TOKENS_PER_CYCLE` kürzen (schützt das GeckoTerminal-Rate-Limit).
4. **Candle-Prüfung:** Für jeden verbleibenden Kandidaten über die in
   `SIGNAL_TIMEFRAMES` gelisteten Timeframes (`1m,5m,15m`) je `get_ohlcv(...)`
   holen (zwischen Calls `SIGNAL_GECKO_DELAY_MS` warten) und mit
   `candles.evaluate(...)` bewerten. Ein **Signal** entsteht, sobald **ein**
   Timeframe anschlägt (Volumen-Spike + Bestätigung, siehe candles.py).
5. **Deduplizierung** über `signals_state.json`: pro Mint Zeitpunkt des letzten
   Alerts speichern; denselben Token frühestens nach `SIGNAL_MAX_AGE_HOURS`
   (bzw. einem festen Cooldown, Standard 6 h) erneut melden.
6. **Alert** bei Treffer (Klartext-Format):
       🚀 MEMECOIN-SIGNAL: <SYMBOL>
       Grund: <candle-begründung, z. B. Vol-Spike 4.2× · 3 grüne Kerzen (5m)>
       Preis: $<preis>   1h: <±x>%
       Liquidität: $<liq>   Vol 1h: $<vol>   Alter: <h>h
       Kerzen (<tf>):
       <die letzten SIGNAL_CANDLES_IN_ALERT Kerzen via candles.format_candles>
       CA: <mint>
       Chart: https://www.geckoterminal.com/solana/pools/<pool_address>
   Zusätzlich ein DexScreener-Link
   `https://dexscreener.com/solana/<mint>`.
7. State speichern; Konsolen-Zusammenfassung ausgeben (geprüfte Kandidaten,
   gefundene Signale).

- **Erster Lauf:** Standard `SIGNAL_ALERT_FIRST_RUN=false` → bereits laufende
  Pumps beim Start nicht nachträglich melden, nur ab jetzt neue Signale.
  Per `.env` auf `true` setzbar bzw. per CLI-Flag `--alert-on-first-run`
  erzwingbar.
- Der Volumen-Spike ist der zentrale „Warum-gekauft-wird"-Faktor; grüne Serie
  und Breakout dienen als Bestätigung, dass die Bewegung nach oben trägt.

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
- RPC-, DexScreener- und GeckoTerminal-Aufrufe mit bis zu 4 Wiederholungen und
  Backoff (2 s, 4 s, 8 s, 16 s) bei `requests`-Ausnahmen.
- GeckoTerminal-Rate-Limit (~30/min) beachten: `SIGNAL_GECKO_DELAY_MS` zwischen
  Kerzen-Calls, Kandidaten pro Zyklus auf `SIGNAL_MAX_TOKENS_PER_CYCLE` begrenzen.
  Bei HTTP 429 zusätzlich kurz warten und den betroffenen Kandidaten überspringen.
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
- Candle-Logik (candles.py, mit handgebauten Kerzenlisten):
    - `volume_spike`: letzte Kerze mit z. B. 5× Volumen der vorherigen erkennt
      Spike (ratio korrekt); flaches Volumen erkennt keinen.
    - `green_streak`: zählt die grünen Kerzen am Ende korrekt; eine rote am Ende
      ergibt 0.
    - `breakout`: neuer Höchst-Close über vorheriges Hoch = True; darunter False.
    - `evaluate`: Volumen-Spike + 3 grüne Kerzen → Signal; Spike allein ohne
      Bestätigung → kein Signal; kein Spike → kein Signal; zu wenige Kerzen →
      None (kein Crash).
- Signal-Dedup: derselbe Mint wird innerhalb des Cooldowns nicht doppelt
  gemeldet; Basis-Sanity-Filter (Liquidität/Alter) verwirft Kandidaten korrekt.
- Notifier-Anbieter-Erkennung: nur CallMeBot-Vars gesetzt → Anbieter
  "callmebot"; erzwungener Anbieter ohne Vars → deaktiviert (kein Crash).

Tests müssen ohne Internet grün sein.

## README.md

Vollständige Anleitung auf Deutsch: Installation (`pip install -r
requirements.txt`), `.env`-Setup, CallMeBot-Aktivierung (Nummer speichern,
"I allow callmebot to send me messages" senden, API-Key eintragen), alle
Subcommands mit Beispielen, Erklärung der Candle-Signale (Volumen-Spike als
Hauptfaktor, grüne Serie + Breakout als Bestätigung) und aller Signal-Parameter,
der P&L-Berechnung inkl. Näherungs-Hinweis, Twilio/Meta als Alternativen,
Cron-Beispiel für `--once`, Hinweis auf eigenen RPC-Endpunkt und auf das
GeckoTerminal-Rate-Limit. Deutlicher Disclaimer: Signale sind Heuristik auf
Marktdaten, keine Finanzberatung/Kaufempfehlung – DYOR.

## ABNAHMEKRITERIEN

- `python bot.py test-notify` schickt mit der hinterlegten CallMeBot-Config eine
  echte WhatsApp-Nachricht an 4915678354158.
- `python bot.py wallet` erfasst beim ersten Lauf still den Bestand und meldet
  danach neue Käufe/Verkäufe der Wallet CWNXGmsLBjFzYf9vz8BtnhHw9pf2nex4N6LiRiw2PFb7
  inkl. P&L-Tabelle.
- `python bot.py signals` beobachtet alle neuen/trendenden Solana-Memecoins,
  prüft sie über 1m/5m/15m-Kerzen und meldet nur bei Volumen-Spike-Signal
  (mit Bestätigung) – inkl. der letzten Kerzen und Chart-Link, ohne Duplikate.
- `python bot.py both` betreibt beides dauerhaft und stabil.
- `pytest -q` (bzw. `python -m pytest`) ist grün, ohne Internet.
- Keine Secrets im committeten Code; `.env` ist gitignored.

Erstelle alle Dateien vollständig und lauffähig.
