# Solana Wallet Token Scanner

Ein Python-CLI-Tool, das eine **Solana-Wallet** überwacht und meldet, sobald
**neue Tokens gekauft** werden. Für jede Position wird der **Gewinn/Verlust
(P&L)** berechnet und bei neuen Käufen/Verkäufen eine **Benachrichtigung**
ausgegeben (Konsole + optional Telegram).

## Features

- 🟢 Erkennt **neue Token-Käufe** und **Zukäufe**
- 🔴 Erkennt **Verkäufe** und berechnet den realisierten P&L
- 📊 Laufende **Portfolio-Übersicht** mit unrealisiertem P&L pro Token und gesamt
- 🔔 **Benachrichtigungen** über Konsole, **WhatsApp** und optional **Telegram**
- 💾 Speichert den Zustand (`wallet_state.json`), übersteht Neustarts
- 🪶 Nur eine Abhängigkeit (`requests`) – kein schweres Solana-SDK nötig

## Installation

```bash
cd wallet_scanner
pip install -r requirements.txt
```

## Nutzung

```bash
# Dauerbetrieb, alle 30 Sekunden scannen
python scanner.py <WALLET_ADRESSE>

# Intervall anpassen
python scanner.py <WALLET_ADRESSE> --interval 15

# Einmaliger Scan (z.B. für einen cron-Job)
python scanner.py <WALLET_ADRESSE> --once
```

Die Wallet-Adresse kann auch per Umgebungsvariable gesetzt werden:

```bash
export WALLET_ADDRESS="DeineWalletAdresse..."
python scanner.py
```

## Konfiguration (Umgebungsvariablen)

| Variable            | Zweck                                                            |
|---------------------|-----------------------------------------------------------------|
| `SOLANA_RPC_URL`    | Eigener RPC-Endpunkt (empfohlen, der öffentliche ist limitiert) |
| `WALLET_ADDRESS`    | Zu überwachende Wallet, falls nicht als Argument übergeben       |
| `TELEGRAM_BOT_TOKEN`| Bot-Token für Telegram-Benachrichtigungen                       |
| `TELEGRAM_CHAT_ID`  | Ziel-Chat-ID für Telegram                                        |

## 📲 WhatsApp-Benachrichtigungen

Es gibt drei Wege, WhatsApp anzusteuern. Setze die Variablen des gewünschten
Anbieters – der Scanner erkennt ihn automatisch. Mit `WHATSAPP_PROVIDER`
kannst du ihn auch erzwingen (`callmebot` | `twilio` | `cloud`).

Test jederzeit ohne echten Kauf:

```bash
python scanner.py --test-notify
```

### Option A – CallMeBot (am einfachsten, kostenlos, an die eigene Nummer)

Ideal, um dir selbst Alerts zu schicken. Kein Account, keine Bot-Nummer nötig.

1. Speichere die Nummer **+34 621 331 709** in deinen Kontakten.
2. Schick ihr über WhatsApp die Nachricht: **`I allow callmebot to send me messages`**
3. Du bekommst einen **API-Key** zurück.
4. Konfigurieren:
   ```bash
   export CALLMEBOT_APIKEY="123456"
   export WHATSAPP_TO="+491701234567"   # deine eigene Nummer mit Ländervorwahl
   ```

> CallMeBot sendet nur an **deine eigene** Nummer – perfekt für persönliche Alerts.

### Option B – Twilio (eigene/dedizierte Bot-Nummer)

Der richtige Weg, wenn du eine **Nummer als Bot** nutzen willst. Zum Testen
gibt es eine kostenlose Sandbox-Nummer.

1. Kostenlosen Account auf [twilio.com](https://www.twilio.com/) anlegen.
2. **Messaging → Try it out → WhatsApp Sandbox** öffnen, mit deinem Handy der
   Sandbox beitreten (Code an die angezeigte Nummer senden).
3. Konfigurieren:
   ```bash
   export TWILIO_ACCOUNT_SID="ACxxxxxxxx"
   export TWILIO_AUTH_TOKEN="dein_auth_token"
   export TWILIO_WHATSAPP_FROM="+14155238886"   # Sandbox- oder deine eigene Nummer
   export WHATSAPP_TO="+491701234567"           # Empfänger
   ```
   Für den Produktivbetrieb kannst du später deine **eigene Bot-Nummer** bei
   Twilio registrieren und bei `TWILIO_WHATSAPP_FROM` eintragen.

### Option C – WhatsApp Business Cloud API (Meta, offiziell, eigene Nummer)

Wenn du **deine eigene Nummer offiziell** als Absender registrieren willst.

1. In der [Meta for Developers](https://developers.facebook.com/) Konsole eine
   App vom Typ *Business* anlegen und *WhatsApp* hinzufügen.
2. Du erhältst eine **Phone Number ID** und einen **Access Token**.
3. Konfigurieren:
   ```bash
   export WHATSAPP_CLOUD_TOKEN="EAAG..."
   export WHATSAPP_PHONE_NUMBER_ID="123456789012345"
   export WHATSAPP_TO="+491701234567"
   ```

> ⚠️ **Wichtig bei Twilio & Meta:** Außerhalb eines 24-Stunden-Fensters (in dem
> *du* dem Bot zuletzt geschrieben hast) dürfen nur vorab **genehmigte
> Template-Nachrichten** verschickt werden – so schreibt es WhatsApp vor. Für
> reine Eigen-Alerts ist **CallMeBot** deshalb am unkompliziertesten, weil es
> diese Einschränkung nicht hat.

## Telegram einrichten (optional)

1. Bei [@BotFather](https://t.me/BotFather) einen Bot erstellen → **Token**.
2. Dem Bot einmal schreiben, dann Chat-ID ermitteln (z.B. über
   `https://api.telegram.org/bot<TOKEN>/getUpdates`).
3. Variablen setzen:
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC..."
   export TELEGRAM_CHAT_ID="987654321"
   ```

## Wie P&L berechnet wird

- Beim ersten Lauf wird der aktuelle Bestand als **Ausgangsbasis** erfasst
  (es werden keine "alten" Käufe rückwirkend gemeldet).
- Wird danach ein neuer Token oder ein höherer Bestand erkannt, gilt das als
  **Kauf**. Der Marktpreis zum Erkennungszeitpunkt wird als Kostenbasis
  gespeichert (gewichteter Durchschnitt bei Zukäufen).
- **Unrealisierter P&L** = Menge × (aktueller Preis − Ø Einstandspreis)
- **Realisierter P&L** wird bei Verkäufen fortgeschrieben.

> **Hinweis:** Als Kaufpreis wird der Marktpreis zum Zeitpunkt der Erkennung
> verwendet (Näherung, abhängig vom Scan-Intervall). Auf die Sekunde exakte
> Ausführungspreise würden das Parsen jeder einzelnen Swap-Transaktion
> erfordern.

Preise stammen von der öffentlichen [DexScreener](https://dexscreener.com)-API
(kein API-Key erforderlich).

## Dauerbetrieb als Cron-Job

```cron
*/1 * * * * cd /pfad/zu/wallet_scanner && /usr/bin/python3 scanner.py <WALLET> --once >> scan.log 2>&1
```
