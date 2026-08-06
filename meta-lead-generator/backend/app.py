import os
import json
import hmac
import hashlib
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'leads.db')
META_VERIFY_TOKEN = os.environ.get('META_VERIFY_TOKEN', 'vodafone_d2d_token')
META_APP_SECRET   = os.environ.get('META_APP_SECRET', '')
ADMIN_TOKEN       = os.environ.get('ADMIN_TOKEN', 'changeme123')

# E-Mail Einstellungen (in .env setzen)
SMTP_HOST     = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT     = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER     = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
NOTIFY_EMAIL  = os.environ.get('NOTIFY_EMAIL', '')  # Wohin die Benachrichtigung geht


PRODUCT_NAMES = {
    'internet':  'Internet / Glasfaser',
    'tv':        'GigaTV',
    'mobilfunk': 'GigaMobil',
    'gigacube':  'GigaCube',
}

BEST_TIME_NAMES = {
    'vormittag':  'Vormittags (8–12 Uhr)',
    'mittag':     'Mittags (12–14 Uhr)',
    'nachmittag': 'Nachmittags (14–18 Uhr)',
    'abend':      'Abends (18–20 Uhr)',
}


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name   TEXT,
                last_name    TEXT,
                phone        TEXT NOT NULL,
                email        TEXT,
                street       TEXT,
                house_number TEXT,
                zip          TEXT,
                city         TEXT,
                products     TEXT,
                best_time    TEXT,
                note         TEXT,
                status       TEXT DEFAULT "neu",
                source       TEXT DEFAULT "landing_page",
                raw_meta     TEXT,
                created_at   TEXT
            )
        ''')
        conn.commit()

init_db()


# ── E-Mail Benachrichtigung ───────────────────────────────────────────────────

def send_lead_email(data):
    if not SMTP_USER or not NOTIFY_EMAIL:
        return  # E-Mail nicht konfiguriert

    products = [PRODUCT_NAMES.get(p, p) for p in data.get('products', [])]
    best_time = BEST_TIME_NAMES.get(data.get('best_time', ''), 'Beliebig')
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
    adresse = f"{data.get('street', '')} {data.get('house_number', '')}, {data.get('zip', '')} {data.get('city', '')}"
    kanal = 'Meta Ads' if data.get('source') == 'meta_ads' else 'Website'

    subject = f"🔥 Neuer Lead: {name} ({kanal})"

    body = f"""Neuer vorqualifizierter Lead:

Name:       {name}
Rufnummer:  {data.get('phone', '–')}
E-Mail:     {data.get('email') or '–'}
Bedarf:     {', '.join(products) if products else '–'}
Adresse:    {adresse.strip(', ')}
Rückruf:    {best_time}
Kanal:      {kanal}
"""
    if data.get('note'):
        body += f"\nNotiz:      {data['note']}"

    body += f"\n\nEingegangen: {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = SMTP_USER
    msg['To']      = NOTIFY_EMAIL

    # Plaintext
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # HTML-Version
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto">
      <div style="background:#E60000;padding:20px 24px;border-radius:10px 10px 0 0">
        <h2 style="color:white;margin:0;font-size:20px">🔥 Neuer Lead: {name}</h2>
        <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px">Über {kanal} · {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr</p>
      </div>
      <div style="background:#fff;border:1px solid #eee;border-top:none;padding:24px;border-radius:0 0 10px 10px">
        <table style="width:100%;border-collapse:collapse;font-size:15px">
          <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 0;color:#888;width:110px">Name</td>
            <td style="padding:10px 0;font-weight:600">{name}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f0;background:#fff5f5">
            <td style="padding:10px 0;color:#888">📞 Rufnummer</td>
            <td style="padding:10px 0;font-weight:700;color:#E60000;font-size:17px">{data.get('phone', '–')}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 0;color:#888">Bedarf</td>
            <td style="padding:10px 0;font-weight:600">{', '.join(products) if products else '–'}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 0;color:#888">Adresse</td>
            <td style="padding:10px 0">{adresse.strip(', ')}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 0;color:#888">Rückruf</td>
            <td style="padding:10px 0">{best_time}</td>
          </tr>
          {"<tr><td style='padding:10px 0;color:#888'>Notiz</td><td style='padding:10px 0'>" + data['note'] + "</td></tr>" if data.get('note') else ""}
        </table>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f'E-Mail Fehler: {e}')


# ── Helper ────────────────────────────────────────────────────────────────────

def lead_to_dict(row):
    d = dict(row)
    try:
        d['products'] = json.loads(d.get('products') or '[]')
    except Exception:
        d['products'] = []
    return d

def require_admin(req):
    token = req.headers.get('X-Admin-Token') or req.args.get('token')
    return token == ADMIN_TOKEN


# ── Landing Page ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/dashboard')
@app.route('/dashboard/')
def dashboard():
    return send_from_directory('../dashboard', 'index.html')

@app.route('/dashboard/<path:filename>')
def dashboard_static(filename):
    return send_from_directory('../dashboard', filename)


# ── Lead API ──────────────────────────────────────────────────────────────────

@app.route('/api/leads', methods=['POST'])
def create_lead():
    data = request.get_json(force=True) or {}

    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'phone required'}), 400

    with get_db() as conn:
        conn.execute('''
            INSERT INTO leads
              (first_name, last_name, phone, email, street, house_number,
               zip, city, products, best_time, note, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            data.get('first_name', ''),
            data.get('last_name', ''),
            phone,
            data.get('email', ''),
            data.get('street', ''),
            data.get('house_number', ''),
            data.get('zip', ''),
            data.get('city', ''),
            json.dumps(data.get('products', [])),
            data.get('best_time', ''),
            data.get('note', ''),
            data.get('source', 'landing_page'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        conn.commit()

    send_lead_email(data)

    return jsonify({'success': True}), 201


@app.route('/api/leads', methods=['GET'])
def get_leads():
    if not require_admin(request):
        return jsonify({'error': 'unauthorized'}), 401

    with get_db() as conn:
        rows = conn.execute('SELECT * FROM leads ORDER BY id DESC').fetchall()
    return jsonify({'leads': [lead_to_dict(r) for r in rows]})


@app.route('/api/leads/<int:lead_id>/status', methods=['PATCH'])
def update_status(lead_id):
    if not require_admin(request):
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(force=True) or {}
    status = data.get('status', 'neu')
    allowed = {'neu', 'kontaktiert', 'termin', 'abgeschlossen', 'kein_interesse'}
    if status not in allowed:
        return jsonify({'error': 'invalid status'}), 400

    with get_db() as conn:
        conn.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
        conn.commit()
    return jsonify({'success': True})


# ── Meta Lead Ads Webhook ─────────────────────────────────────────────────────

@app.route('/webhook/meta', methods=['GET'])
def meta_verify():
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == META_VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403


@app.route('/webhook/meta', methods=['POST'])
def meta_webhook():
    if META_APP_SECRET:
        sig = request.headers.get('X-Hub-Signature-256', '')
        expected = 'sha256=' + hmac.new(
            META_APP_SECRET.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return 'Invalid signature', 403

    payload = request.get_json(force=True) or {}

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            if change.get('field') != 'leadgen':
                continue

            lead_id_meta = value.get('leadgen_id')

            with get_db() as conn:
                conn.execute('''
                    INSERT INTO leads
                      (first_name, last_name, phone, products, source, raw_meta, created_at)
                    VALUES (?,?,?,?,?,?,?)
                ''', (
                    'Meta', 'Lead',
                    f'meta_{lead_id_meta}',
                    json.dumps([]),
                    'meta_ads',
                    json.dumps(value),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ))
                conn.commit()

            send_lead_email({
                'first_name': 'Meta', 'last_name': 'Lead',
                'phone': f'meta_{lead_id_meta}',
                'source': 'meta_ads', 'products': []
            })

    return 'OK', 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'leads.db')
META_VERIFY_TOKEN = os.environ.get('META_VERIFY_TOKEN', 'vodafone_d2d_token')
META_APP_SECRET   = os.environ.get('META_APP_SECRET', '')
ADMIN_TOKEN       = os.environ.get('ADMIN_TOKEN', 'changeme123')


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name   TEXT,
                last_name    TEXT,
                phone        TEXT NOT NULL,
                email        TEXT,
                street       TEXT,
                house_number TEXT,
                zip          TEXT,
                city         TEXT,
                products     TEXT,   -- JSON array
                best_time    TEXT,
                note         TEXT,
                status       TEXT DEFAULT "neu",
                source       TEXT DEFAULT "landing_page",
                raw_meta     TEXT,
                created_at   TEXT
            )
        ''')
        conn.commit()

init_db()


# ── Helper ────────────────────────────────────────────────────────────────────

def lead_to_dict(row):
    d = dict(row)
    try:
        d['products'] = json.loads(d.get('products') or '[]')
    except Exception:
        d['products'] = []
    return d

def require_admin(req):
    token = req.headers.get('X-Admin-Token') or req.args.get('token')
    return token == ADMIN_TOKEN


# ── Landing Page ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/dashboard')
@app.route('/dashboard/')
def dashboard():
    return send_from_directory('../dashboard', 'index.html')

@app.route('/dashboard/<path:filename>')
def dashboard_static(filename):
    return send_from_directory('../dashboard', filename)


# ── Lead API ──────────────────────────────────────────────────────────────────

@app.route('/api/leads', methods=['POST'])
def create_lead():
    data = request.get_json(force=True) or {}

    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'phone required'}), 400

    with get_db() as conn:
        conn.execute('''
            INSERT INTO leads
              (first_name, last_name, phone, email, street, house_number,
               zip, city, products, best_time, note, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            data.get('first_name', ''),
            data.get('last_name', ''),
            phone,
            data.get('email', ''),
            data.get('street', ''),
            data.get('house_number', ''),
            data.get('zip', ''),
            data.get('city', ''),
            json.dumps(data.get('products', [])),
            data.get('best_time', ''),
            data.get('note', ''),
            data.get('source', 'landing_page'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        conn.commit()

    return jsonify({'success': True}), 201


@app.route('/api/leads', methods=['GET'])
def get_leads():
    if not require_admin(request):
        return jsonify({'error': 'unauthorized'}), 401

    with get_db() as conn:
        rows = conn.execute('SELECT * FROM leads ORDER BY id DESC').fetchall()
    return jsonify({'leads': [lead_to_dict(r) for r in rows]})


@app.route('/api/leads/<int:lead_id>/status', methods=['PATCH'])
def update_status(lead_id):
    if not require_admin(request):
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(force=True) or {}
    status = data.get('status', 'neu')
    allowed = {'neu', 'kontaktiert', 'termin', 'abgeschlossen', 'kein_interesse'}
    if status not in allowed:
        return jsonify({'error': 'invalid status'}), 400

    with get_db() as conn:
        conn.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
        conn.commit()
    return jsonify({'success': True})


# ── Meta Lead Ads Webhook ─────────────────────────────────────────────────────

@app.route('/webhook/meta', methods=['GET'])
def meta_verify():
    """Meta webhook verification handshake."""
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == META_VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403


@app.route('/webhook/meta', methods=['POST'])
def meta_webhook():
    """Receive leads from Meta Lead Ads."""
    # Verify signature if secret is configured
    if META_APP_SECRET:
        sig = request.headers.get('X-Hub-Signature-256', '')
        expected = 'sha256=' + hmac.new(
            META_APP_SECRET.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return 'Invalid signature', 403

    payload = request.get_json(force=True) or {}

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            if change.get('field') != 'leadgen':
                continue

            lead_id_meta = value.get('leadgen_id')
            form_id      = value.get('form_id')

            # In production: fetch full lead data from Meta Graph API
            # For now we store the raw payload and create a stub lead
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO leads
                      (first_name, last_name, phone, products, source, raw_meta, created_at)
                    VALUES (?,?,?,?,?,?,?)
                ''', (
                    'Meta', 'Lead',
                    f'meta_{lead_id_meta}',
                    json.dumps([]),
                    'meta_ads',
                    json.dumps(value),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ))
                conn.commit()

    return 'OK', 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
