#!/usr/bin/env python3
"""
ServeBeer IPFS Gateway - Production Ready
Features:
 - /ipfs/<path> and /ipns/<path> proxy to local IPFS daemon
 - Blacklist with reasons (malware, phishing, dmca, copyright, policy_violation)
 - Official IPFS denylist integration (auto-sync every 24h)
 - HTTP 451 for blocked content
 - Audit logging to SQLite (GDPR-friendly)
 - DMCA/Copyright reporting system
 - Health check endpoint
 - Admin endpoints for blacklist management
"""

from flask import Flask, request, jsonify, Response, render_template_string, redirect, url_for, render_template
import requests
import os
import sqlite3
import logging
import smtplib
import uuid
import ssl
import time
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Load environment variables ---
load_dotenv()

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '8081'))

IPFS_HTTP_GATEWAY = os.getenv('IPFS_HTTP_GATEWAY', 'http://127.0.0.1:8080')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'database/servebeer.db')
LOG_FILE = os.getenv('LOG_FILE', 'logs/servebeer_audit.log')

# DMCA email settings (optional)
DMCA_SMTP_HOST = os.getenv('DMCA_SMTP_HOST', 'smtp.gmail.com')
DMCA_SMTP_PORT = int(os.getenv('DMCA_SMTP_PORT', 587))
DMCA_SMTP_USER = os.getenv('DMCA_SMTP_USER')
DMCA_SMTP_PASS = os.getenv('DMCA_SMTP_PASS')
DMCA_NOTIFY_TO = os.getenv('DMCA_NOTIFY_TO', DMCA_SMTP_USER or 'admin@example.com')

# Blacklist settings
BLACKLIST_FILE = os.getenv('BLACKLIST_FILE', 'blacklist.txt')
IPFS_DENYLIST_FILE = os.getenv('IPFS_DENYLIST_FILE', 'blacklist-ipfs-official.txt')
IPFS_DENYLIST_URL = "https://raw.githubusercontent.com/ipfs/infra/master/ipfs/gateway/denylist.conf"
BLACKLIST_CACHE_TIME = 300  # 5 minutes

# Ensure folders exist
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

# --- Database setup ---
def setup_database():
    """Create minimal tables: audit_log, request_log"""
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
    """Log to file and DB - safe fallback if DB fails"""
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
    """Log requests to database (GDPR compliant - no PII except IP for security)"""
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
            request.headers.get('User-Agent', '')[:500],
            None
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"request_log failed: {e}")

# --- IPFS Official Denylist Integration ---
def download_ipfs_denylist():
    """Download and parse official IPFS denylist from Nginx format to CIDs"""
    try:
        logging.info(f"Downloading IPFS official denylist from {IPFS_DENYLIST_URL}")
        r = requests.get(IPFS_DENYLIST_URL, timeout=30)
        
        if r.status_code != 200:
            logging.error(f"Failed to download denylist: HTTP {r.status_code}")
            return False
        
        cids_found = 0
        with open(IPFS_DENYLIST_FILE, 'w') as f:
            f.write("# IPFS Official Denylist - Auto-generated\n")
            f.write(f"# Source: {IPFS_DENYLIST_URL}\n")
            f.write(f"# Downloaded: {datetime.now(timezone.utc).isoformat()}\n\n")
            
            for line in r.text.split('\n'):
                line = line.strip()
                
                # Parse Nginx location format:
                # location ~ "^/ipfs/QmXXX" { return 410; }
                # location ~ "^/ipns/QmXXX" { return 410; }
                if 'location' in line and ('ipfs' in line or 'ipns' in line):
                    try:
                        # Extract CID from location path
                        if '/ipfs/' in line:
                            cid = line.split('/ipfs/')[1].split('"')[0].split('/')[0]
                        elif '/ipns/' in line:
                            cid = line.split('/ipns/')[1].split('"')[0].split('/')[0]
                        else:
                            continue
                        
                        # Validate CID format (basic check)
                        if cid and (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
                            f.write(f"{cid} ipfs-official-denylist\n")
                            cids_found += 1
                    except (IndexError, ValueError) as e:
                        logging.debug(f"Could not parse line: {line} - {e}")
                        continue
        
        logging.info(f"Successfully downloaded {cids_found} CIDs from IPFS official denylist")
        audit_log('IPFS_DENYLIST_SYNC', details=f"Downloaded {cids_found} CIDs")
        return True
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error downloading IPFS denylist: {e}")
        return False
    except Exception as e:
        logging.error(f"Error processing IPFS denylist: {e}")
        return False

def scheduled_denylist_update():
    """Update denylist every 24h in background"""
    while True:
        time.sleep(86400)  # 24 hours
        logging.info("Scheduled IPFS denylist update")
        download_ipfs_denylist()
        _cached_load_blacklist.cache_clear()

# --- Blacklist (file-based with caching) ---
@lru_cache(maxsize=1)
def _cached_load_blacklist(cache_key):
    """Cached blacklist loader - local blacklist only"""
    try:
        blacklist = {}
        with open(BLACKLIST_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(maxsplit=1)
                cid = parts[0]
                reason = parts[1] if len(parts) > 1 else "policy_violation"
                blacklist[cid] = reason
        return blacklist
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Error loading blacklist: {e}")
        return {}

def load_blacklist():
    """Return blacklist with cache (refreshes every 5 min) - merged with IPFS official"""
    cache_key = int(time.time() / BLACKLIST_CACHE_TIME)
    local_blacklist = _cached_load_blacklist(cache_key)
    
    # Merge with official IPFS denylist (if exists)
    try:
        if os.path.exists(IPFS_DENYLIST_FILE):
            with open(IPFS_DENYLIST_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(maxsplit=1)
                    cid = parts[0]
                    reason = parts[1] if len(parts) > 1 else 'ipfs-official-denylist'
                    
                    # Don't overwrite local reasons (local blacklist has priority)
                    if cid not in local_blacklist:
                        local_blacklist[cid] = reason
    except Exception as e:
        logging.error(f"Error loading IPFS official denylist: {e}")
    
    return local_blacklist

# --- Utility: proxy to IPFS HTTP gateway ---
def proxy_ipfs_path(path, is_ipns=False, stream_timeout=120):
    """Proxy request to IPFS daemon"""
    kind = 'ipns' if is_ipns else 'ipfs'
    target = f"{IPFS_HTTP_GATEWAY}/{kind}/{path}"
    
    try:
        r = requests.get(target, stream=True, timeout=stream_timeout)
    except requests.exceptions.Timeout:
        logging.error(f"IPFS gateway timeout for {target}")
        audit_log('IPFS_GATEWAY_TIMEOUT', details=target)
        return ("IPFS gateway timeout - content may be unavailable or too large", 504)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error contacting IPFS gateway {target}: {e}")
        audit_log('IPFS_GATEWAY_ERROR', details=str(e))
        return (f"IPFS gateway error: {e}", 503)

    if r.status_code == 404:
        return ("Content not found on IPFS network", 404)

    def generate():
        try:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        except requests.exceptions.RequestException as e:
            logging.error(f"Stream error from IPFS gateway: {e}")

    content_type = r.headers.get('Content-Type', 'application/octet-stream')
    headers = {
        'Content-Type': content_type,
        'Cache-Control': 'public, max-age=29030400, immutable',
        'Access-Control-Allow-Origin': '*'
    }
    return Response(generate(), status=r.status_code, headers=headers)

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ipfs/', defaults={'ipfs_path': None})
@app.route('/ipfs/<path:ipfs_path>')
def ipfs_gateway(ipfs_path):
    """Handle /ipfs/{cid} requests with blacklist checking"""
    if not ipfs_path:
        ipfs_path = request.args.get('cid', '') or ''
        if not ipfs_path:
            return redirect(url_for('index'))

    # Extract CID (first part of path)
    cid = ipfs_path.split('/')[0]
    audit_log('CID_ACCESS', ip_address=request.remote_addr, cid=cid, details=f"path={ipfs_path}")

    # Blacklist check
    blacklist = load_blacklist()
    if cid in blacklist:
        reason = blacklist[cid]
        audit_log('BLACKLIST_HIT', ip_address=request.remote_addr, 
                 cid=cid, details=f"blocked: {reason}")
        
        # Map reasons to Polish
        reason_pl = {
            'malware': 'Wykryto złośliwe oprogramowanie',
            'phishing': 'Próba wyłudzenia danych (phishing)',
            'dmca': 'Naruszenie praw autorskich (DMCA)',
            'copyright': 'Naruszenie praw autorskich',
            'policy_violation': 'Naruszenie regulaminu',
            'ipfs-official-denylist': 'Zablokowane przez oficjalną listę IPFS'
        }
        
        return render_template_string("""
        <!doctype html><html><head>
        <meta charset="utf-8">
        <title>451 - Blocked</title>
        <link rel="icon" href="data:,">
        </head>
        <body style="font-family:Arial;text-align:center;padding:60px;background:#2c3e50;color:#ecf0f1;">
        <h1 style="color:#e74c3c">⛔ 451 - Content Blocked</h1>
        <p><strong>Powód:</strong> {{ reason_text }}</p>
        <p>Treść z CID <code>{{ cid }}</code> została zablokowana.</p>
        <p><a href="/copyright" style="color:#4ecdc4">Zgłoś DMCA / sprawdź procedury</a></p>
        <hr>
        <small>Reference: {{ request_id }}</small>
        </body></html>
        """, reason_text=reason_pl.get(reason, reason), 
             cid=cid, 
             request_id=uuid.uuid4().hex[:8]), 451

    return proxy_ipfs_path(ipfs_path, is_ipns=False)

@app.route('/ipns/<path:ipns_name>')
def ipns_gateway(ipns_name):
    """Handle /ipns/{name} requests"""
    audit_log('IPNS_ACCESS', ip_address=request.remote_addr, details=f"name={ipns_name}")
    return proxy_ipfs_path(ipns_name, is_ipns=True)

@app.route('/health')
def health():
    """Health check: IPFS daemon and database connectivity"""
    status = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'ipfs': 'unknown',
        'database': 'unknown',
        'blacklist': 0
    }
    
    # Check IPFS
    try:
        r = requests.get(f"{IPFS_HTTP_GATEWAY}/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG", timeout=4)
        status['ipfs'] = 'ok' if r.status_code in (200, 301, 302, 404) else f'error({r.status_code})'
    except Exception as e:
        status['ipfs'] = f'error: {e}'

    # Check database
    try:
        conn = db_conn()
        conn.execute('SELECT 1').fetchone()
        conn.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {e}'
    
    # Blacklist stats
    try:
        blacklist = load_blacklist()
        status['blacklist'] = len(blacklist)
    except Exception as e:
        status['blacklist'] = f'error: {e}'

    return jsonify(status)

# --- Admin endpoints ---
@app.route('/admin/reload-blacklist', methods=['POST'])
def reload_blacklist():
    """Force reload blacklist (clears cache)"""
    _cached_load_blacklist.cache_clear()
    new_blacklist = load_blacklist()
    audit_log('BLACKLIST_RELOAD', details=f"Reloaded {len(new_blacklist)} CIDs")
    return jsonify({
        "status": "reloaded",
        "count": len(new_blacklist)
    }), 200

@app.route('/admin/sync-ipfs-denylist', methods=['POST'])
def sync_ipfs_denylist():
    """Synchronize with official IPFS denylist"""
    success = download_ipfs_denylist()
    
    if success:
        _cached_load_blacklist.cache_clear()
        new_blacklist = load_blacklist()
        
        return jsonify({
            "status": "success",
            "message": "IPFS official denylist synchronized",
            "total_blocked": len(new_blacklist),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to download IPFS denylist"
        }), 500

@app.route('/admin/blacklist-stats')
def blacklist_stats():
    """Blacklist statistics"""
    blacklist = load_blacklist()
    
    # Count by reason
    reasons = {}
    for reason in blacklist.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    
    return jsonify({
        "total": len(blacklist),
        "by_reason": reasons,
        "sample_cids": list(blacklist.keys())[:10]
    })

@app.route('/admin/test-blacklist/<cid>')
def test_blacklist(cid):
    """Test if CID is on blacklist"""
    blacklist = load_blacklist()
    is_blocked = cid in blacklist
    reason = blacklist.get(cid, 'not found')
    
    return jsonify({
        'cid': cid,
        'blocked': is_blocked,
        'reason': reason,
        'total_blacklisted': len(blacklist),
        'sample_cids': list(blacklist.keys())[:5]
    })

# --- Static pages ---
@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/cookies')
def cookies():
    return render_template('cookies.html')

@app.route('/copyright')
def copyright_policy():
    return render_template('copyright.html')

@app.route('/copyright/report', methods=['GET', 'POST'])
def copyright_report():
    """DMCA/Copyright takedown notice submission"""
    if request.method == 'GET':
        return render_template('copyright_report.html')
    
    # POST handling
    data = {
        'copyright_owner': request.form.get('copyright_owner'),
        'contact_email': request.form.get('contact_email'),
        'infringing_cid': request.form.get('infringing_cid'),
        'description': request.form.get('description'),
        'signature': request.form.get('signature'),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    audit_log('DMCA_REPORT', ip_address=request.remote_addr, 
             cid=data.get('infringing_cid'), details=data)
    
    # Send email if configured
    sent = False
    if DMCA_SMTP_USER and DMCA_SMTP_PASS and DMCA_NOTIFY_TO:
        sent = send_dmca_mail(data)
    
    return render_template_string("""
    <!doctype html>
    <html>
    <head><meta charset="utf-8"><title>Copyright Notice Submitted</title></head>
    <body style="font-family:Arial;max-width:900px;margin:40px auto;background:#2c3e50;color:#ecf0f1;padding:40px;">
    <h1>Copyright Notice Submitted</h1>
    <p>Reference: {{ref}}</p>
    <p>We will review and respond within 48 hours.</p>
    <p><a href="/" style="color:#4ecdc4;">Home</a></p>
    </body>
    </html>
    """, ref=f"DMCA-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")

# --- Helper functions ---
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
    """Send DMCA email notification"""
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

# --- Main ---
if __name__ == '__main__':
    setup_database()
    
    # Download IPFS official denylist on startup if missing or old
    if not os.path.exists(IPFS_DENYLIST_FILE):
        logging.info("IPFS official denylist not found, downloading...")
        download_ipfs_denylist()
    else:
        # Check if file is older than 24h
        file_age = time.time() - os.path.getmtime(IPFS_DENYLIST_FILE)
        if file_age > 86400:  # 24 hours
            logging.info("IPFS official denylist older than 24h, updating...")
            download_ipfs_denylist()
    
    # Start scheduled denylist update in background
    update_thread = threading.Thread(target=scheduled_denylist_update, daemon=True)
    update_thread.start()
    logging.info("Started background denylist updater (24h interval)")
    
    logging.info("Starting IPFS Gateway Flask app")
    audit_log('SERVICE_STARTUP', details={'host': APP_HOST, 'port': APP_PORT})
    
    ssl_ctx = create_ssl_context()
    if ssl_ctx:
        print("🔒 Starting with SSL on port 443...")
        app.run(host='0.0.0.0', port=443, ssl_context=ssl_ctx, debug=False)
    else:
        print(f"🌐 Starting HTTP on port {APP_PORT}...")
        app.run(host=APP_HOST, port=APP_PORT, debug=False)
