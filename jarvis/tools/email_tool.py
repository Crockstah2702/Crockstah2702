"""E-Mail Tool — senden und empfangen über SMTP/IMAP."""
import asyncio
import email as emaillib
import imaplib
import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

EMAIL_CONFIG_FILE = Path("./data/email_config.json")


def _load_config() -> dict:
    if EMAIL_CONFIG_FILE.exists():
        try:
            return json.loads(EMAIL_CONFIG_FILE.read_text())
        except Exception:
            return {}
    return {}


def setup_email(smtp_server: str, smtp_port: int, email_address: str,
                password: str, imap_server: str = "") -> str:
    """Speichere E-Mail-Konfiguration."""
    config = {
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "email": email_address,
        "password": password,
        "imap_server": imap_server or smtp_server.replace("smtp.", "imap.")
    }
    EMAIL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    return f"E-Mail konfiguriert für {email_address}. Einstellungen gespeichert."


def send_email(to: str, subject: str, body: str, cc: str = "", html: bool = False) -> str:
    """Sende eine E-Mail."""
    cfg = _load_config()
    if not cfg:
        return ("E-Mail nicht konfiguriert. Bitte zuerst setup_email aufrufen:\n"
                "z.B. setup_email('smtp.gmail.com', 587, 'deine@email.de', 'passwort')\n"
                "Für Gmail: App-Passwort unter myaccount.google.com/apppasswords erstellen.")

    try:
        msg = MIMEMultipart("alternative" if html else "mixed")
        msg["From"] = cfg["email"]
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc

        part = MIMEText(body, "html" if html else "plain", "utf-8")
        msg.attach(part)

        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["email"], cfg["password"])
            recipients = [to] + ([cc] if cc else [])
            server.sendmail(cfg["email"], recipients, msg.as_string())

        return f"✅ E-Mail gesendet an {to}\nBetreff: {subject}"
    except Exception as e:
        return f"❌ E-Mail-Fehler: {e}"


def read_emails(folder: str = "INBOX", limit: int = 10, unread_only: bool = True) -> str:
    """Lese E-Mails vom Server."""
    cfg = _load_config()
    if not cfg:
        return "E-Mail nicht konfiguriert. Bitte zuerst setup_email aufrufen."

    try:
        mail = imaplib.IMAP4_SSL(cfg["imap_server"])
        mail.login(cfg["email"], cfg["password"])
        mail.select(folder)

        criteria = "UNSEEN" if unread_only else "ALL"
        _, data = mail.search(None, criteria)
        msg_ids = data[0].split()
        if not msg_ids:
            return f"Keine {'ungelesenen ' if unread_only else ''}E-Mails in {folder}."

        results = []
        for mid in msg_ids[-limit:]:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            msg = emaillib.message_from_bytes(msg_data[0][1])
            subject = msg.get("Subject", "(kein Betreff)")
            sender = msg.get("From", "Unbekannt")
            date = msg.get("Date", "")

            # Body extrahieren
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")[:300]
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")[:300]

            results.append(f"📧 Von: {sender}\n   Betreff: {subject}\n   Datum: {date}\n   {body[:200]}...")

        mail.logout()
        return f"E-Mails ({len(results)}):\n\n" + "\n\n---\n\n".join(results)
    except Exception as e:
        return f"E-Mail-Lesefehler: {e}"


def compose_email_draft(to: str, subject: str, context: str) -> str:
    """Gibt eine Vorlage für eine E-Mail zurück (ohne zu senden)."""
    return (f"E-Mail-Entwurf:\n"
            f"An: {to}\n"
            f"Betreff: {subject}\n"
            f"Inhalt-Kontext: {context}\n\n"
            f"Zum Senden: send_email(to='{to}', subject='{subject}', body='...')")
