# Solana Wallet Token Scanner

Ein Python-CLI-Tool, das eine **Solana-Wallet** überwacht und meldet, sobald
**neue Tokens gekauft** werden. Für jede Position wird der **Gewinn/Verlust
(P&L)** berechnet und bei neuen Käufen/Verkäufen eine **Benachrichtigung**
ausgegeben (Konsole + optional Telegram).

## Features

- 🟢 Erkennt **neue Token-Käufe** und **Zukäufe**
- 🔴 Erkennt **Verkäufe** und berechnet den realisierten P&L
- 📊 Laufende **Portfolio-Übersicht** mit unrealisiertem P&L pro Token und gesamt
- 🔔 **Benachrichtigungen** über Konsole und optional **Telegram**
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

### Telegram einrichten (optional)

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
