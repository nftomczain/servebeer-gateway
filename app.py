#!/usr/bin/env python3
"""
ServeBeer IPFS Gateway - Production Ready with Copyright Plugin System
Features:
 - /ipfs/<path> and /ipns/<path> proxy to local IPFS daemon
 - Multi-jurisdiction copyright compliance (DMCA, DSA, French, Polish)
 - Blacklist with reasons + Official IPFS denylist integration
 - HTTP 451 for blocked content
 - Audit logging to SQLite (GDPR-friendly)
 - Copyright reporting system with country-specific plugins
 - Health check endpoint
 - Admin endpoints for management
"""

from flask import Flask, request, jsonify, Response, render_template_string, redirect, url_for, render_template
from werkzeug.http import HTTP_STATUS_CODES
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

# Register HTTP 451 status code with Werkzeug
HTTP_STATUS_CODES[451] = 'Unavailable For Legal Reasons'

# Import copyright plugin system
from copyright_plugins import CopyrightPluginManager

# --- Load environment variables ---
load_dotenv()

APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '8081'))

IPFS_HTTP_GATEWAY = os.getenv('IPFS_HTTP_GATEWAY', 'http://127.0.0.1:8080')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'database/servebeer.db')
LOG_FILE = os.getenv('LOG_FILE', 'logs/servebeer_audit.log')

# Copyright jurisdiction (US, EU, FR, PL)
COPYRIGHT_COUNTRY = os.getenv('COPYRIGHT_COUNTRY', 'US')

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

# Ensure blacklist files exist
if not os.path.exists(BLACKLIST_FILE):
    with open(BLACKLIST_FILE, 'w') as f:
        f.write("# Local blacklist - one CID per line\n")
        f.write("# Format: CID reason\n")

# Ensure folders exist
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs('copyright_plugins', exist_ok=True)

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30)
)

# --- Copyright Plugin Manager ---
copyright_manager = CopyrightPluginManager(default_country=COPYRIGHT_COUNTRY)

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
    """Log requests to database (GDPR compliant)"""
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
    """Download and parse official IPFS denylist from Nginx config format"""
    try:
        logging.info(f"Downloading IPFS official denylist from {IPFS_DENYLIST_URL}")
        r = requests.get(IPFS_DENYLIST_URL, timeout=30)
        
        if r.status_code != 200:
            logging.error(f"Failed to download denylist: HTTP {r.status_code}")
            return False
        
        logging.info(f"Downloaded {len(r.text)} bytes from IPFS denylist")
        
        cids_found = 0
        lines_processed = 0
        
        with open(IPFS_DENYLIST_FILE, 'w') as f:
            f.write("# IPFS Official Denylist - Auto-generated\n")
            f.write(f"# Source: {IPFS_DENYLIST_URL}\n")
            f.write(f"# Downloaded: {datetime.now(timezone.utc).isoformat()}\n\n")
            
            for line in r.text.split('\n'):
                lines_processed += 1
                line = line.strip()
                
                # Look for location blocks with ipfs/ipns paths
                # Format: location ~ "^/ipfs/QmXXXX" {
                if 'location' in line and ('"/ipfs/' in line or '"/ipns/' in line):
                    try:
                        # Extract CID from regex pattern
                        if '"/ipfs/' in line:
                            cid = line.split('"/ipfs/')[1].split('"')[0].split('/')[0]
                        elif '"/ipns/' in line:
                            cid = line.split('"/ipns/')[1].split('"')[0].split('/')[0]
                        else:
                            continue
                        
                        # Validate CID format (basic check)
                        if cid and len(cid) > 10 and (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
                            # Extract reason from comment above (if present)
                            reason = 'ipfs-official-denylist'
                            f.write(f"{cid} {reason}\n")
                            cids_found += 1
                            
                    except (IndexError, ValueError) as e:
                        logging.debug(f"Could not parse line {lines_processed}: {line[:50]} - {e}")
                        continue
        
        logging.info(f"Successfully parsed {cids_found} CIDs from {lines_processed} lines")
        audit_log('IPFS_DENYLIST_SYNC', details={
            'cids_found': cids_found,
            'lines_processed': lines_processed,
            'file': IPFS_DENYLIST_FILE
        })
        return True
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error downloading IPFS denylist: {e}")
        return False
    except Exception as e:
        logging.error(f"Error processing IPFS denylist: {e}")
        import traceback
        logging.error(traceback.format_exc())
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
    """Return blacklist with cache - merged with IPFS official"""
    cache_key = int(time.time() / BLACKLIST_CACHE_TIME)
    local_blacklist = _cached_load_blacklist(cache_key)
    
    # Merge with official IPFS denylist
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
    plugin = copyright_manager.get_active()
    footer = plugin.get_footer_html() if plugin else ""
    
    return render_template('index.html', footer=footer)

@app.route('/ipfs/', defaults={'ipfs_path': None})
@app.route('/ipfs/<path:ipfs_path>')
def ipfs_gateway(ipfs_path):
    """Handle /ipfs/{cid} requests with blacklist checking"""
    if not ipfs_path:
        ipfs_path = request.args.get('cid', '') or ''
        if not ipfs_path:
            return redirect(url_for('index'))

    # Extract CID
    cid = ipfs_path.split('/')[0]
    audit_log('CID_ACCESS', ip_address=request.remote_addr, cid=cid, details=f"path={ipfs_path}")

    # Blacklist check
    blacklist = load_blacklist()
    if cid in blacklist:
        reason = blacklist[cid]
        audit_log('BLACKLIST_HIT', ip_address=request.remote_addr, 
                 cid=cid, details=f"blocked: {reason}")
        
        # Get localized blocked page from plugin (with fallback)
        try:
            plugin = copyright_manager.get_active()
            if plugin:
                blocked_text = plugin.get_blocked_page_text(reason, language='pl')
            else:
                raise Exception("No plugin available")
        except Exception as e:
            logging.warning(f"Could not get blocked page text from plugin: {e}")
            blocked_text = {
                'title': '451 - Content Blocked',
                'message': 'This content has been blocked due to legal reasons.',
                'reason': reason,
                'law': None
            }
        
        # Render template
        html_content = render_template_string("""
        <!doctype html><html><head>
        <meta charset="utf-8">
        <title>{{ title }}</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #2c3e50;
                color: #ecf0f1;
                text-align: center;
                padding: 60px 20px;
                margin: 0;
            }
            h1 {
                color: #e74c3c;
                font-size: 4em;
                margin: 0;
            }
            .subtitle {
                color: #95a5a6;
                font-size: 1.2em;
                margin: 20px 0;
            }
            .cid-box {
                background: #34495e;
                padding: 20px;
                border-radius: 8px;
                font-family: monospace;
                word-break: break-all;
                margin: 30px auto;
                max-width: 600px;
                font-size: 0.9em;
            }
            .reason-box {
                background: rgba(231, 76, 60, 0.2);
                padding: 15px;
                border-radius: 8px;
                margin: 20px auto;
                max-width: 600px;
                border: 2px solid #e74c3c;
            }
            a {
                color: #4ecdc4;
                text-decoration: none;
                font-weight: bold;
            }
            a:hover {
                text-decoration: underline;
            }
            .actions {
                margin-top: 40px;
            }
            .ref {
                margin-top: 60px;
                color: #7f8c8d;
                font-size: 0.8em;
            }
        </style>
        </head>
        <body>
        <h1>⛔ 451</h1>
        <div class="subtitle">{{ title }}</div>
        
        <div class="reason-box">
            <strong>Reason:</strong> {{ reason }}
        </div>
        
        <div class="cid-box">
            <strong>Blocked CID:</strong><br>
            {{ cid }}
        </div>
        
        <p>{{ message }}</p>
        
        {% if law %}
        <p style="font-size: 0.9em; color: #95a5a6;">{{ law }}</p>
        {% endif %}
        
        <div class="actions">
            <a href="/copyright">📋 Learn about our copyright policy</a>
            <span style="color: #7f8c8d;"> | </span>
            <a href="/">🏠 Return home</a>
        </div>
        
        <div class="ref">
            Reference: {{ request_id }}
        </div>
        </body></html>
        """, 
        title=blocked_text.get('title', '451 - Content Blocked'),
        message=blocked_text.get('message', 'This content has been blocked.'),
        reason=blocked_text.get('reason', reason),
        law=blocked_text.get('law'),
        cid=cid, 
        request_id=uuid.uuid4().hex[:8])
        
        # Create response with explicit headers
        response = Response(html_content, status=451, mimetype='text/html')
        response.status_code = 451
        response.status = '451 Unavailable For Legal Reasons'
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.headers['Content-Length'] = str(len(html_content.encode('utf-8')))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['X-Content-Blocked'] = '451-unavailable-for-legal-reasons'
        return response

    return proxy_ipfs_path(ipfs_path, is_ipns=False)

@app.route('/ipns/<path:ipns_name>')
def ipns_gateway(ipns_name):
    """Handle /ipns/{name} requests"""
    audit_log('IPNS_ACCESS', ip_address=request.remote_addr, details=f"name={ipns_name}")
    return proxy_ipfs_path(ipns_name, is_ipns=True)

@app.route('/health')
def health():
    """Health check: IPFS daemon, database, and blacklist"""
    status = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'ipfs': 'unknown',
        'database': 'unknown',
        'blacklist': 0,
        'copyright_jurisdiction': copyright_manager.get_active().country_code if copyright_manager.get_active() else 'none'
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
    """Force reload blacklist"""
    _cached_load_blacklist.cache_clear()
    new_blacklist = load_blacklist()
    audit_log('BLACKLIST_RELOAD', details=f"Reloaded {len(new_blacklist)} CIDs")
    return jsonify({"status": "reloaded", "count": len(new_blacklist)}), 200

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
        return jsonify({"status": "error", "message": "Failed to download IPFS denylist"}), 500

@app.route('/admin/blacklist-stats')
def blacklist_stats():
    """Blacklist statistics"""
    blacklist = load_blacklist()
    
    reasons = {}
    for reason in blacklist.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    
    return jsonify({
        "total": len(blacklist),
        "by_reason": reasons,
        "sample_cids": list(blacklist.keys())[:10]
    })

@app.route('/admin/test-denylist-download')
def test_denylist_download():
    """Test download and parsing of IPFS official denylist"""
    import tempfile
    
    try:
        # Download to temp file for testing
        r = requests.get(IPFS_DENYLIST_URL, timeout=30)
        
        if r.status_code != 200:
            return jsonify({
                'error': f'HTTP {r.status_code}',
                'url': IPFS_DENYLIST_URL
            }), 500
        
        # Parse in memory
        cids_found = []
        lines_processed = 0
        
        for line in r.text.split('\n'):
            lines_processed += 1
            line = line.strip()
            
            if 'location' in line and ('"/ipfs/' in line or '"/ipns/' in line):
                try:
                    if '"/ipfs/' in line:
                        cid = line.split('"/ipfs/')[1].split('"')[0].split('/')[0]
                    elif '"/ipns/' in line:
                        cid = line.split('"/ipns/')[1].split('"')[0].split('/')[0]
                    else:
                        continue
                    
                    if cid and len(cid) > 10:
                        cids_found.append(cid)
                except:
                    continue
        
        return jsonify({
            'status': 'success',
            'url': IPFS_DENYLIST_URL,
            'bytes_downloaded': len(r.text),
            'lines_processed': lines_processed,
            'cids_found': len(cids_found),
            'sample_cids': cids_found[:10],
            'current_file': IPFS_DENYLIST_FILE,
            'current_file_exists': os.path.exists(IPFS_DENYLIST_FILE)
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/test-blocked-page/<cid>')
def test_blocked_page(cid):
    """Test what the blocked page returns"""
    blacklist = load_blacklist()
    
    # Force block this CID for testing
    reason = blacklist.get(cid, 'test-block')
    
    # Same logic as ipfs_gateway
    try:
        plugin = copyright_manager.get_active()
        if plugin:
            blocked_text = plugin.get_blocked_page_text(reason, language='pl')
        else:
            raise Exception("No plugin available")
    except Exception as e:
        blocked_text = {
            'title': '451 - Content Blocked',
            'message': 'This content has been blocked due to legal reasons.',
            'reason': reason,
            'law': None
        }
    
    # Render template
    html_content = render_template_string("""
    <!doctype html><html><head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #2c3e50;
            color: #ecf0f1;
            text-align: center;
            padding: 60px 20px;
            margin: 0;
        }
        h1 {
            color: #e74c3c;
            font-size: 4em;
            margin: 0;
        }
        .subtitle {
            color: #95a5a6;
            font-size: 1.2em;
            margin: 20px 0;
        }
        .cid-box {
            background: #34495e;
            padding: 20px;
            border-radius: 8px;
            font-family: monospace;
            word-break: break-all;
            margin: 30px auto;
            max-width: 600px;
            font-size: 0.9em;
        }
        .reason-box {
            background: rgba(231, 76, 60, 0.2);
            padding: 15px;
            border-radius: 8px;
            margin: 20px auto;
            max-width: 600px;
            border: 2px solid #e74c3c;
        }
        a {
            color: #4ecdc4;
            text-decoration: none;
            font-weight: bold;
        }
        a:hover {
            text-decoration: underline;
        }
        .actions {
            margin-top: 40px;
        }
        .ref {
            margin-top: 60px;
            color: #7f8c8d;
            font-size: 0.8em;
        }
    </style>
    </head>
    <body>
    <h1>⛔ 451</h1>
    <div class="subtitle">{{ title }}</div>
    
    <div class="reason-box">
        <strong>Reason:</strong> {{ reason }}
    </div>
    
    <div class="cid-box">
        <strong>Blocked CID:</strong><br>
        {{ cid }}
    </div>
    
    <p>{{ message }}</p>
    
    {% if law %}
    <p style="font-size: 0.9em; color: #95a5a6;">{{ law }}</p>
    {% endif %}
    
    <div class="actions">
        <a href="/copyright">📋 Learn about our copyright policy</a>
        <span style="color: #7f8c8d;"> | </span>
        <a href="/">🏠 Return home</a>
    </div>
    
    <div class="ref">
        Reference: {{ request_id }} (TEST MODE)
    </div>
    </body></html>
    """, 
    title=blocked_text.get('title', '451 - Content Blocked'),
    message=blocked_text.get('message', 'This content has been blocked.'),
    reason=blocked_text.get('reason', reason),
    law=blocked_text.get('law'),
    cid=cid, 
    request_id=uuid.uuid4().hex[:8])
    
    # Create response with explicit headers
    response = Response(html_content, status=451, mimetype='text/html')
    response.status_code = 451
    response.status = '451 Unavailable For Legal Reasons'
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Content-Length'] = str(len(html_content.encode('utf-8')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['X-Content-Blocked'] = '451-test-mode'
    return response

@app.route('/admin/test-blacklist/<cid>')
def test_blacklist(cid):
    """Test if CID is blocked"""
    blacklist = load_blacklist()
    is_blocked = cid in blacklist
    reason = blacklist.get(cid, 'not found')
    
    return jsonify({
        'cid': cid,
        'blocked': is_blocked,
        'reason': reason,
        'total_blacklisted': len(blacklist)
    })

@app.route('/admin/set-jurisdiction/<country_code>', methods=['POST'])
def set_jurisdiction(country_code):
    """Change active copyright jurisdiction"""
    success = copyright_manager.set_country(country_code.upper())
    
    if success:
        plugin = copyright_manager.get_active()
        audit_log('JURISDICTION_CHANGED', details=f"Changed to {country_code} - {plugin.law_name}")
        return jsonify({
            'status': 'success',
            'country': plugin.country_code,
            'law': plugin.law_name,
            'reference': plugin.law_reference
        }), 200
    else:
        return jsonify({
            'status': 'error',
            'message': f'Plugin for {country_code} not found'
        }), 404

@app.route('/admin/list-jurisdictions')
def list_jurisdictions():
    """List all available copyright jurisdictions"""
    jurisdictions = copyright_manager.list_available()
    active = copyright_manager.get_active()
    
    return jsonify({
        'available': jurisdictions,
        'active': active.country_code if active else None
    })

# --- Copyright/DMCA pages ---
@app.route('/copyright')
def copyright_policy():
    """Copyright policy page with jurisdiction-specific information"""
    plugin = copyright_manager.get_active()
    
    if not plugin:
        return "No copyright plugin active", 500
    
    template = plugin.get_notice_template()
    footer = plugin.get_footer_html()
    
    return render_template_string("""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Copyright Policy - {{ law_name }}</title>
        <style>
            body { font-family: Arial; max-width: 900px; margin: 40px auto; 
                   background: #2c3e50; color: #ecf0f1; padding: 30px; }
            h1 { color: #4ecdc4; }
            h2 { color: #e74c3c; margin-top: 30px; }
            pre { background: #34495e; padding: 20px; border-radius: 5px; 
                  overflow-x: auto; white-space: pre-wrap; }
            a { color: #4ecdc4; }
            .badge { margin: 30px 0; }
        </style>
    </head>
    <body>
        <h1>Copyright Compliance Policy</h1>
        <p><strong>Jurisdiction:</strong> {{ country }} - {{ law_name }}</p>
        <p><strong>Legal Reference:</strong> {{ law_reference }}</p>
        
        <h2>How to Report Copyright Infringement</h2>
        <p><a href="/copyright/report" style="font-size: 18px; font-weight: bold;">
            📝 Submit Copyright Report</a></p>
        
        <h2>Notice Template</h2>
        <pre>{{ template }}</pre>
        
        <div class="badge">{{ footer | safe }}</div>
        
        <p><a href="/">← Back to Home</a></p>
    </body>
    </html>
    """, 
    country=plugin.country_code,
    law_name=plugin.law_name,
    law_reference=plugin.law_reference,
    template=template,
    footer=footer)

@app.route('/copyright/report', methods=['GET', 'POST'])
def copyright_report():
    """Copyright takedown notice submission"""
    plugin = copyright_manager.get_active()
    
    if not plugin:
        return "No copyright plugin active", 500
    
    if request.method == 'GET':
        template = plugin.get_notice_template()
        required_fields = plugin.get_required_fields()
        
        return render_template_string("""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Report Copyright Infringement</title>
            <style>
                body { font-family: Arial; max-width: 900px; margin: 40px auto;
                       background: #2c3e50; color: #ecf0f1; padding: 30px; }
                h1 { color: #e74c3c; }
                label { display: block; margin-top: 20px; color: #4ecdc4; font-weight: bold; }
                input, textarea { width: 100%; padding: 10px; margin-top: 5px;
                                 background: #34495e; border: none; color: #ecf0f1;
                                 border-radius: 5px; }
                button { background: #e74c3c; color: white; padding: 15px 30px;
                        border: none; border-radius: 5px; margin-top: 30px;
                        cursor: pointer; font-size: 16px; font-weight: bold; }
                button:hover { background: #c0392b; }
                .info { background: rgba(52, 152, 219, 0.2); padding: 15px;
                       border-radius: 5px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <h1>Report Copyright Infringement</h1>
            <div class="info">
                <strong>Jurisdiction:</strong> {{ country }} - {{ law }}<br>
                <strong>Response Time:</strong> {{ sla }} hours
            </div>
            
            <form method="POST">
                {% for field in fields %}
                <label for="{{ field }}">{{ field | replace('_', ' ') | title }}*</label>
                {% if 'description' in field or 'statement' in field or 'justification' in field %}
                <textarea name="{{ field }}" id="{{ field }}" rows="4" required></textarea>
                {% else %}
                <input type="text" name="{{ field }}" id="{{ field }}" required>
                {% endif %}
                {% endfor %}
                
                <button type="submit">Submit Report</button>
            </form>
            
            <p style="margin-top: 30px;"><a href="/copyright" style="color:#4ecdc4;">← View Full Template</a></p>
        </body>
        </html>
        """,
        country=plugin.country_code,
        law=plugin.law_name,
        sla=plugin.get_sla_hours(),
        fields=required_fields)
    
    # POST handling
    notice_data = request.form.to_dict()
    notice_data['timestamp'] = datetime.now(timezone.utc).isoformat()
    notice_data['reference_id'] = f"{plugin.country_code}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    
    # Validate using plugin
    is_valid, error = plugin.validate_notice(notice_data)
    
    if not is_valid:
        return jsonify({'error': error}), 400
    
    # Log to audit
    audit_log('COPYRIGHT_REPORT',
             ip_address=request.remote_addr,
             cid=notice_data.get('infringing_cid'),
             details={'jurisdiction': plugin.country_code, **notice_data})
    
    # Send email if configured
    if DMCA_SMTP_USER and DMCA_SMTP_PASS:
        send_copyright_mail(notice_data, plugin)
    
    return render_template_string("""
    <!doctype html>
    <html>
    <head><meta charset="utf-8"><title>Report Submitted</title></head>
    <body style="font-family:Arial;max-width:900px;margin:40px auto;background:#2c3e50;color:#ecf0f1;padding:40px;">
    <h1 style="color:#4ecdc4;">Copyright Report Submitted</h1>
    <p><strong>Reference ID:</strong> {{ ref }}</p>
    <p><strong>Jurisdiction:</strong> {{ jurisdiction }}</p>
    <p>We will review and respond within <strong>{{ sla }} hours</strong>.</p>
    <p><a href="/" style="color:#4ecdc4;">← Back to Home</a></p>
    </body>
    </html>
    """, 
    ref=notice_data['reference_id'],
    jurisdiction=f"{plugin.country_code} ({plugin.law_name})",
    sla=plugin.get_sla_hours())

# --- Static pages ---
@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/cookies')
def cookies():
    return render_template('cookies.html')

# --- Helper functions ---
def create_ssl_context():
    """Create SSL context for HTTPS"""
    # Try multiple certificate locations
    cert_locations = [
        ('/home/premp/cert/fullchain.pem', '/home/premp/cert/privkey.pem'),
        ('/etc/letsencrypt/live/ipfs.servebeer.com/fullchain.pem', '/etc/letsencrypt/live/ipfs.servebeer.com/privkey.pem'),
        ('/etc/letsencrypt/live/servebeer.com/fullchain.pem', '/etc/letsencrypt/live/servebeer.com/privkey.pem'),
    ]
    
    for cert_path, key_path in cert_locations:
        if os.path.exists(cert_path) and os.path.exists(key_path):
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(cert_path, key_path)
                print(f"✅ SSL certificates loaded from: {cert_path}")
                return context
            except Exception as e:
                print(f"⚠️  Failed to load SSL from {cert_path}: {e}")
                continue
    
    print(f"⚠️  No valid SSL certificates found")
    print(f"   Tried locations:")
    for cert, key in cert_locations:
        exists_cert = "✓" if os.path.exists(cert) else "✗"
        exists_key = "✓" if os.path.exists(key) else "✗"
        print(f"   {exists_cert} {cert}")
        print(f"   {exists_key} {key}")
    
    return None

def send_copyright_mail(data, plugin):
    """Send copyright notice email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = data.get('contact_email', DMCA_SMTP_USER)
        msg['To'] = DMCA_NOTIFY_TO
        msg['Subject'] = f"Copyright Notice [{plugin.country_code}] - {data.get('infringing_cid', '')[:12]}"

        body = f"""COPYRIGHT NOTICE RECEIVED

Jurisdiction: {plugin.country_code} - {plugin.law_name}
Legal Reference: {plugin.law_reference}
Reference ID: {data.get('reference_id')}
Timestamp: {data.get('timestamp')}

Contact: {data.get('contact_email')}
CID: {data.get('infringing_cid')}

Full Details:
{str(data)}

---
Response required within {plugin.get_sla_hours()} hours.
"""
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(DMCA_SMTP_HOST, DMCA_SMTP_PORT, timeout=10)
        server.starttls()
        server.login(DMCA_SMTP_USER, DMCA_SMTP_PASS)
        server.send_message(msg)
        server.quit()

        logging.info(f"Copyright notice email sent [{plugin.country_code}] to {DMCA_NOTIFY_TO}")
        return True
    except Exception as e:
        logging.error(f"Failed to send copyright email: {e}")
        return False

# --- Main ---
if __name__ == '__main__':
    setup_database()
    
    # Download IPFS denylist on startup
    print(f"🔍 Checking IPFS official denylist...")
    if not os.path.exists(IPFS_DENYLIST_FILE):
        print(f"   Denylist file not found, downloading...")
        success = download_ipfs_denylist()
        if success:
            print(f"   ✅ Downloaded successfully!")
        else:
            print(f"   ⚠️  Download failed (will try again in 24h)")
    else:
        file_age = time.time() - os.path.getmtime(IPFS_DENYLIST_FILE)
        age_hours = int(file_age / 3600)
        print(f"   Denylist age: {age_hours} hours")
        if file_age > 86400:
            print(f"   Denylist older than 24h, updating...")
            success = download_ipfs_denylist()
            if success:
                print(f"   ✅ Updated successfully!")
            else:
                print(f"   ⚠️  Update failed (will try again in 24h)")
        else:
            print(f"   ✅ Denylist is fresh")
    
    # Load and display blacklist stats
    try:
        initial_blacklist = load_blacklist()
        print(f"📋 Blacklist loaded: {len(initial_blacklist)} total CIDs")
        
        # Count by source
        local_count = 0
        official_count = 0
        for reason in initial_blacklist.values():
            if 'official' in reason:
                official_count += 1
            else:
                local_count += 1
        
        print(f"   • Local: {local_count} CIDs")
        print(f"   • Official IPFS: {official_count} CIDs")
    except Exception as e:
        print(f"⚠️  Error loading blacklist: {e}")
    
    # Start background denylist updater
    update_thread = threading.Thread(target=scheduled_denylist_update, daemon=True)
    update_thread.start()
    print(f"⏰ Started background denylist updater (24h interval)")
    
    logging.info("Starting IPFS Gateway Flask app")
    audit_log('SERVICE_STARTUP', details={
        'host': APP_HOST, 
        'port': APP_PORT,
        'copyright_jurisdiction': COPYRIGHT_COUNTRY
    })
    
    ssl_ctx = create_ssl_context()
    if ssl_ctx:
        print(f"\n🔒 Starting with SSL on port 443...")
        print(f"📋 Copyright jurisdiction: {COPYRIGHT_COUNTRY}")
        app.run(host='0.0.0.0', port=443, ssl_context=ssl_ctx, debug=False)
    else:
        print(f"\n🌐 Starting HTTP on port {APP_PORT}...")
        print(f"📋 Copyright jurisdiction: {COPYRIGHT_COUNTRY}")
        app.run(host=APP_HOST, port=APP_PORT, debug=False)
