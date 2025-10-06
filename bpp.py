#!/usr/bin/env python3
"""
Minimalny, poprawiony ServeBeer-ish IPFS Gateway (Flask).
Zachowuje:
 - /ipfs/<path> i /ipns/<path> proxy do lokalnego HTTP gateway (127.0.0.1:8080)
 - blacklist z pliku blacklist.txt (blokowanie CID => 451)
 - logging do pliku + audit_log i request_log w SQLite (GDPR-friendly)
 - DMCA report + stronę DMCA (wysyłanie maila opcjonalne, zależne od env)
 - prostą stronę główną, cookies i terms
 - health endpoint
 - bez upload/pinning/auth (oddzielne rzeczy)
"""

from flask import Flask, request, jsonify, Response, render_template_string, redirect, url_for
import requests
import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, Response, render_template, redirect, url_for

# --- Load env ---
load_dotenv()

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '8081'))

IPFS_HTTP_GATEWAY = os.getenv('IPFS_HTTP_GATEWAY', 'http://127.0.0.1:8080')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'database/servebeer.db')
LOG_FILE = os.getenv('LOG_FILE', 'logs/servebeer_audit.log')

# DMCA email settings (optional)
DMCA_SMTP_HOST = os.getenv('DMCA_SMTP_HOST', 'smtp.gmail.com')
DMCA_SMTP_PORT = int(os.getenv('DMCA_SMTP_PORT', 587))
DMCA_SMTP_USER = os.getenv('DMCA_SMTP_USER')  # set to enable sending
DMCA_SMTP_PASS = os.getenv('DMCA_SMTP_PASS')
DMCA_NOTIFY_TO = os.getenv('DMCA_NOTIFY_TO', DMCA_SMTP_USER or 'admin@example.com')

# Ensure folders
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30)
)

# --- Logging setup ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def setup_database():
    """Create minimal tables: audit_log, request_log, blacklist (optional file-based)."""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id TEXT,
            ip_address TEXT,
            cid TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            method TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT
        )
    ''')
    conn.commit()
    conn.close()

def db_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def audit_log(event_type, user_id=None, ip_address=None, cid=None, details=None):
    """Log to file and DB - safe fallback if DB fails."""
    entry = {
        'event': event_type,
        'user_id': user_id,
        'ip': ip_address or request.remote_addr if request else ip_address,
        'cid': cid,
        'details': details,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    logging.info(f"AUDIT: {entry}")
    try:
        conn = db_conn()
        conn.execute('''
            INSERT INTO audit_log (event_type, user_id, ip_address, cid, details)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_type, user_id, entry['ip'], cid, str(details)))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to write audit_log to DB: {e}")

@app.before_request
def log_request_gdpr():
    # avoid logging static assets for brevity
    if request.endpoint and request.endpoint.startswith('static'):
        return
    try:
        conn = db_conn()
        conn.execute('''
            INSERT INTO request_log (ip_address, method, endpoint, user_agent, user_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            request.remote_addr,
            request.method,
            request.path,
            request.headers.get('User-Agent','')[:500],
            None
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"request_log failed: {e}")

# --- Blacklist (file-based) ---
BLACKLIST_FILE = os.getenv('BLACKLIST_FILE', 'blacklist.txt')

def load_blacklist():
    """Return a set of blacklisted CIDs (first token per line)."""
    try:
        with open(BLACKLIST_FILE, 'r') as f:
            lines = [line.strip().split()[0] for line in f if line.strip() and not line.strip().startswith('#')]
            return set(lines)
    except FileNotFoundError:
        return set()
    except Exception as e:
        logging.error(f"Error loading blacklist: {e}")
        return set()

# --- Utility: proxy to IPFS HTTP gateway ---
def proxy_ipfs_path(path, is_ipns=False, stream_timeout=60):
    # build URL
    kind = 'ipns' if is_ipns else 'ipfs'
    target = f"{IPFS_HTTP_GATEWAY}/{kind}/{path}"
    try:
        r = requests.get(target, stream=True, timeout=stream_timeout)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error contacting IPFS gateway {target}: {e}")
        audit_log('IPFS_GATEWAY_ERROR', ip_address=request.remote_addr, details=str(e))
        return (f"IPFS gateway error: {e}", 503)

    if r.status_code == 404:
        return ("Content not found", 404)

    def generate():
        try:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        except requests.exceptions.RequestException as e:
            logging.error(f"Stream error from IPFS gateway: {e}")
            # end generator

    # choose sensible content type
    content_type = r.headers.get('Content-Type', 'application/octet-stream')
    headers = {
        'Content-Type': content_type,
        'Cache-Control': 'public, max-age=29030400, immutable',
        'Access-Control-Allow-Origin': '*'
    }
    return Response(generate(), status=r.status_code, headers=headers)

# --- Routes ---
INDEX_HTML = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Simple IPFS Gateway</title>
<style>body{font-family:Arial;max-width:900px;margin:40px auto;background:#f7f8fb;padding:30px;border-radius:8px}input{padding:8px;width:60%}button{padding:8px}</style>
</head>
<body>
<h1>Simple IPFS Gateway</h1>
<p>Wpisz CID lub kliknij przykład:</p>
<form action="/ipfs/" method="get" onsubmit="event.preventDefault(); if(cid.value) window.location='/ipfs/'+cid.value;">
<input id="cid" name="cid" placeholder="Qm... or bafy..." required> <button>Fetch</button>
</form>
<p>Przykład: <a href="/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG">IPFS logo</a></p>
<hr>
<p><a href="/health">Health</a> | <a href="/terms">Terms</a> | <a href="/cookies">Cookies</a> | <a href="/dmca">DMCA</a></p>
</body></html>
"""

@app.route('/')
def index():
    return render_template('index.html')

# IPFS path - support both /ipfs/<path> and /ipfs?cid=...
@app.route('/ipfs/', defaults={'ipfs_path': None})
@app.route('/ipfs/<path:ipfs_path>')
def ipfs_gateway(ipfs_path):
    # support query param
    if not ipfs_path:
        ipfs_path = request.args.get('cid', '') or ''
        if not ipfs_path:
            return redirect(url_for('index'))

    # extract CID top-level token
    cid = ipfs_path.split('/')[0]
    audit_log('CID_ACCESS', ip_address=request.remote_addr, cid=cid, details=f"path={ipfs_path}")

    # blacklist check
    blacklist = load_blacklist()
    if cid in blacklist:
        audit_log('BLACKLIST_HIT', ip_address=request.remote_addr, cid=cid, details="blocked")
        # 451 Unavailable For Legal Reasons
        return render_template_string("""
        <!doctype html><html><head><meta charset="utf-8"><title>451 - Blocked</title></head>
        <body style="font-family:Arial;text-align:center;padding:60px;background:#2c3e50;color:#ecf0f1;">
        <h1 style="color:#e74c3c">451 - Content Blocked</h1>
        <p>Treść z tego CID została zablokowana z przyczyn prawnych/policy.</p>
        <p><a href="/dmca" style="color:#4ecdc4">Zgłoś DMCA / sprawdź procedury</a></p>
        </body></html>
        """), 451

    return proxy_ipfs_path(ipfs_path, is_ipns=False)

@app.route('/ipns/<path:ipns_name>')
def ipns_gateway(ipns_name):
    audit_log('IPNS_ACCESS', ip_address=request.remote_addr, details=f"name={ipns_name}")
    return proxy_ipfs_path(ipns_name, is_ipns=True)

@app.route('/health')
def health():
    """Basic health: check local IPFS HTTP gateway and DB connectivity"""
    status = {'timestamp': datetime.now(datetime.UTC).isoformat(), 'ipfs': 'unknown', 'database': 'unknown'}
    # check IPFS HTTP Gateway
    try:
        r = requests.get(f"{IPFS_HTTP_GATEWAY}/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG", timeout=4)
        status['ipfs'] = 'ok' if r.status_code in (200, 301, 302, 404) else f'error({r.status_code})'
    except Exception as e:
        status['ipfs'] = f'error: {e}'

    try:
        conn = db_conn()
        conn.execute('SELECT 1').fetchone()
        conn.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {e}'

    return jsonify(status)

# Terms & Cookies - minimal templates
@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/cookies')
def cookies():
    return render_template('cookies.html')

# DMCA pages & report
@app.route('/dmca')
def dmca_policy():
    return render_template('dmca.html')

@app.route('/dmca/report', methods=['GET','POST'])
def dmca_report():
    if request.method == 'GET':
        return render_template('dmca_report.html')
    
    # POST handling
    data = {
        'copyright_owner': request.form.get('copyright_owner'),
        'contact_email': request.form.get('contact_email'),
        'infringing_cid': request.form.get('infringing_cid'),
        'description': request.form.get('description'),
        'signature': request.form.get('signature'),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    audit_log('DMCA_REPORT', ip_address=request.remote_addr, cid=data.get('infringing_cid'), details=data)
    
    sent = False
    if DMCA_SMTP_USER and DMCA_SMTP_PASS and DMCA_NOTIFY_TO:
        sent = send_dmca_mail(data)
    
    return render_template_string("""
    <!doctype html>
    <html>
    <head><meta charset="utf-8"><title>DMCA Submitted</title></head>
    <body style="font-family:Arial;max-width:900px;margin:40px auto;background:#2c3e50;color:#ecf0f1;padding:40px;">
    <h1>DMCA Notice Submitted</h1>
    <p>Reference: {{ref}}</p>
    <p>We will review and respond within 48 hours.</p>
    <p><a href="/" style="color:#4ecdc4;">Home</a></p>
    </body>
    </html>
    """, ref=f"DMCA-{datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')}")
        
import ssl

def create_ssl_context():
    """Create SSL context for HTTPS"""
    cert_path = '/home/premp/cert/fullchain.pem'
    key_path = '/home/premp/cert/privkey.pem'
    
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        return None
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context

def send_dmca_mail(data):
    """Send DMCA email to configured address. Returns True on success."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        msg = MIMEMultipart()
        msg['From'] = data.get('contact_email')
        msg['To'] = DMCA_NOTIFY_TO
        msg['Subject'] = f"DMCA Notice - {data.get('infringing_cid', '')[:12]}"

        body = f"""DMCA NOTICE RECEIVED

Timestamp: {data.get('timestamp')}
Copyright owner: {data.get('copyright_owner')}
Contact: {data.get('contact_email')}
CID: {data.get('infringing_cid')}
Description:
{data.get('description')}

Signature:
{data.get('signature')}
"""
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(DMCA_SMTP_HOST, DMCA_SMTP_PORT, timeout=10)
        server.starttls()
        server.login(DMCA_SMTP_USER, DMCA_SMTP_PASS)
        server.send_message(msg)
        server.quit()

        logging.info("DMCA email sent to %s", DMCA_NOTIFY_TO)
        return True
    except Exception as e:
        logging.error(f"Failed to send DMCA email: {e}")
        return False

if __name__ == '__main__':
    setup_database()
    logging.info("Starting IPFS Gateway Flask app")
    audit_log('SERVICE_STARTUP', details={'host': '0.0.0.0', 'port': 443})
    
    ssl_ctx = create_ssl_context()
    if ssl_ctx:
        print("Starting with SSL on port 443...")
        app.run(host='0.0.0.0', port=443, ssl_context=ssl_ctx, debug=True)
    else:
        print("SSL not available, starting HTTP on 8081...")
        app.run(host='0.0.0.0', port=8081)
