# Vodafone D2D – Meta Lead Generator

All-in-One Tool zur automatischen Kundengewinnung über Meta Ads für Vodafone D2D Vertrieb.

## Was ist enthalten

| Komponente | Beschreibung |
|---|---|
| `frontend/` | Landing Page mit 3-Schritt Formular (Internet, TV, Mobilfunk, Strom) |
| `dashboard/` | Admin Dashboard – alle Leads verwalten, Status setzen, CSV Export |
| `backend/` | Flask API + Meta Lead Ads Webhook |

## Schnellstart

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env anpassen (Admin Passwort, Meta Token)
python app.py
```

Dann öffne:
- Landing Page: http://localhost:5000
- Dashboard: http://localhost:5000/dashboard

## Meta Ads einrichten

1. Meta Business Manager → Formulare erstellen
2. App in Meta Developer Console anlegen
3. Webhook URL eintragen: `https://DEINE-DOMAIN.de/webhook/meta`
4. Verify Token aus `.env` eintragen
5. Leads kommen automatisch ins Dashboard

## Dashboard Zugriff

Das Dashboard ist mit einem Token geschützt. Standardmäßig wird der Token als URL-Parameter übergeben:

```
http://localhost:5000/dashboard?token=changeme123
```

## Produkte

- **Internet / Glasfaser** – DSL & Glasfaser bis 1.000 Mbit/s
- **Kabel TV** – Über 100 Sender inkl. HD
- **Mobilfunk** – 5G Netz, unbegrenzt telefonieren
- **Strom & Gas** – Ökostrom & Erdgas Tarife

## Lead Status

| Status | Bedeutung |
|---|---|
| Neu | Gerade eingegangen, noch nicht bearbeitet |
| Kontaktiert | Erstkontakt wurde hergestellt |
| Termin vereinbart | Hausbesuch ist geplant |
| Abgeschlossen | Vertrag abgeschlossen ✓ |
| Kein Interesse | Lead möchte kein Angebot |
