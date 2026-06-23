import os
import json
import hmac
import hashlib
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

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
                raw_meta     TEXT,   -- raw Meta webhook payload
                created_at   TEXT DEFAULT (datetime("now", "localtime"))
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
               zip, city, products, best_time, note, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
                      (first_name, last_name, phone, products, source, raw_meta)
                    VALUES (?,?,?,?,?,?)
                ''', (
                    'Meta', 'Lead',
                    f'meta_{lead_id_meta}',
                    json.dumps([]),
                    'meta_ads',
                    json.dumps(value),
                ))
                conn.commit()

    return 'OK', 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
