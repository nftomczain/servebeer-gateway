# ServeBeer IPFS Gateway

Public IPFS HTTP Gateway running on community-powered infrastructure. Decentralized content access with HTTPS, copyright compliance, and minimal logging.

## Features

- **IPFS/IPNS Gateway** - Access any IPFS content via HTTP/HTTPS
- **Official IPFS Denylist** - Auto-syncs with IPFS community blocklist (156+ CIDs)
- **Smart Blacklist** - Local + official lists merged, categorized by reason
- **HTTP 451 Blocking** - Legal-compliant content blocking
- **SSL/TLS Support** - Secure access with Let's Encrypt certificates
- **Copyright Compliance** - DMCA/DSA takedown notice process
- **Auto-sync** - Background updates every 24h
- **Admin API** - Blacklist management endpoints
- **GDPR Logging** - Minimal request logging for compliance
- **Privacy-First** - No tracking, no analytics, no third-party cookies
- **Lightweight** - Runs on Raspberry Pi hardware

## Requirements

- Python 3.8+
- IPFS Kubo (go-ipfs) daemon
- SSL certificates (for HTTPS)
- SQLite3

## Installation

### Quick Install

```bash
# Clone repository
git clone https://github.com/nftomczain/servebeer-gateway.git
cd servebeer-gateway

# Run installer
chmod +x install.sh
./install.sh
```

### Manual Install

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create directories
mkdir -p database logs
touch blacklist.txt

# Setup configuration
cp .env.example .env
nano .env  # Edit with your settings
```

### IPFS Setup

Follow the official installation guide for your architecture:
https://docs.ipfs.tech/install/command-line/#install-official-binary-distributions

**Note:** This gateway runs on Raspberry Pi (ARM64 architecture).

```bash
# Initialize and start IPFS daemon
ipfs init
ipfs daemon
```

## Configuration

Edit `.env` file:

```bash
# Server
APP_HOST=0.0.0.0
APP_PORT=8081  # Used if no SSL certificates found

# IPFS Gateway
IPFS_HTTP_GATEWAY=http://127.0.0.1:8080

# Database & Logs
DATABASE_PATH=database/servebeer.db
LOG_FILE=logs/servebeer_audit.log

# Blacklist
BLACKLIST_FILE=blacklist.txt
IPFS_DENYLIST_FILE=blacklist-ipfs-official.txt

# DMCA Email (optional)
DMCA_SMTP_HOST=smtp.gmail.com
DMCA_SMTP_PORT=587
DMCA_SMTP_USER=your@email.com
DMCA_SMTP_PASS=your-app-password
DMCA_NOTIFY_TO=dmca@yourdomain.com
```

### SSL Certificates

Place certificates in `/home/user/cert/`:
- `fullchain.pem` - Full certificate chain
- `privkey.pem` - Private key

Or modify paths in `app.py` function `create_ssl_context()`.

## Usage

### Run Development Server

```bash
source venv/bin/activate
sudo python3 app.py
```

The application will:
1. Download official IPFS denylist (if missing or older than 24h)
2. Start background auto-updater (syncs every 24h)
3. Launch on port 443 (HTTPS) or 8081 (HTTP fallback)

### Run as Systemd Service

```bash
# Copy service file
sudo cp servebeer-gateway.service /etc/systemd/system/

# Edit paths in service file
sudo nano /etc/systemd/system/servebeer-gateway.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable servebeer-gateway
sudo systemctl start servebeer-gateway

# Check status
sudo systemctl status servebeer-gateway
```

### Access Gateway

```
https://your-domain.com/ipfs/{CID}
https://your-domain.com/ipns/{NAME}
```

Example:
```
https://ipfs.servebeer.com/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG
```

## Blacklist Management

### Local Blacklist

Add CIDs with reasons to `blacklist.txt`:

```bash
# Format: CID reason
QmBadContentCID123 malware
QmAnotherBadCID456 copyright
QmPhishingSite789 phishing
```

**Available reasons:**
- `malware` - Malicious software
- `phishing` - Phishing attempts
- `copyright` - Copyright violations
- `dmca` - DMCA takedowns
- `policy_violation` - Terms of Service violations

### Official IPFS Denylist

Automatically synced from: https://github.com/ipfs/infra/blob/master/ipfs/gateway/denylist.conf

- **Auto-downloaded** on first startup
- **Auto-updated** every 24 hours in background
- **Merged** with local blacklist (local has priority)
- **156+ CIDs** from IPFS community reports

### Manual Sync

Force synchronization with official denylist:

```bash
curl -X POST https://your-domain.com/admin/sync-ipfs-denylist
```

### Blacklist Priority

1. **Local blacklist** (`blacklist.txt`) - custom reasons
2. **Official IPFS denylist** - community-identified malware/abuse
3. If CID in both lists, local reason takes priority

Blocked content returns **HTTP 451 (Unavailable For Legal Reasons)**.

## Admin API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/blacklist-stats` | GET | Blacklist statistics by reason |
| `/admin/test-blacklist/{cid}` | GET | Test if CID is blocked |
| `/admin/reload-blacklist` | POST | Reload local blacklist (clears cache) |
| `/admin/sync-ipfs-denylist` | POST | Force sync with official IPFS denylist |

**Examples:**

```bash
# View statistics
curl https://ipfs.servebeer.com/admin/blacklist-stats

# Test CID
curl https://ipfs.servebeer.com/admin/test-blacklist/QmXXX...

# Reload local blacklist
curl -X POST https://ipfs.servebeer.com/admin/reload-blacklist

# Sync official denylist
curl -X POST https://ipfs.servebeer.com/admin/sync-ipfs-denylist
```

## Monitoring

### Check Logs

```bash
# Audit log
tail -f logs/servebeer_audit.log

# Database logs
sqlite3 database/servebeer.db "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10"

# Filter blacklist hits
tail -f logs/servebeer_audit.log | grep BLACKLIST
```

### Health Check

```
https://your-domain.com/health
```

Returns JSON with IPFS, database, and blacklist status:

```json
{
  "timestamp": "2025-10-11T01:35:51.677081+00:00",
  "ipfs": "ok",
  "database": "ok",
  "blacklist": 146
}
```

### Abuse Monitoring

```bash
# Run abuse check script
./check_abuse.sh

# Shows:
# - Top requested CIDs
# - Top IPs by request count
# - Blacklist hits
```

## Copyright Compliance

### File Takedown Notice

Users can file copyright notices at:
```
https://your-domain.com/copyright/report
```

Required information:
- Copyright owner name
- Contact email
- Infringing CID
- Description of copyrighted work
- Good faith statement
- Signature

### Response Process

1. Notice logged to database and sent via email
2. Review within 48 hours
3. Valid CID added to `blacklist.txt`
4. Complainant notified of action taken

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with CID input |
| `/ipfs/{cid}` | GET | IPFS content proxy |
| `/ipns/{name}` | GET | IPNS content proxy |
| `/health` | GET | Service health status |
| `/copyright` | GET | Copyright policy page |
| `/copyright/report` | GET/POST | Copyright report form |
| `/terms` | GET | Terms of Service |
| `/cookies` | GET | Cookie Policy |
| `/admin/blacklist-stats` | GET | Blacklist statistics |
| `/admin/test-blacklist/{cid}` | GET | Test if CID is blocked |
| `/admin/reload-blacklist` | POST | Reload blacklist cache |
| `/admin/sync-ipfs-denylist` | POST | Sync official denylist |

## Project Structure

```
servebeer-gateway/
├── app.py                      # Main application
├── requirements.txt            # Python dependencies
├── .env.example               # Configuration template
├── .gitignore                 # Git ignore rules
├── README.md                  # This file
├── LICENSE                    # License
├── install.sh                 # Installation script
├── check_abuse.sh             # Monitoring script
├── blacklist.txt              # Local blocked CIDs
├── blacklist-ipfs-official.txt # Auto-synced IPFS denylist
├── templates/                 # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── copyright.html
│   ├── copyright_report.html
│   ├── cookies.html
│   └── terms.html
├── database/                  # SQLite database (gitignored)
└── logs/                      # Log files (gitignored)
```

## Blacklist Categories

The gateway categorizes blocked content:

| Category | Count | Description |
|----------|-------|-------------|
| `dmca` | 106 | DMCA takedown notices |
| `malware/phishing` | 17 | Malicious content |
| `copyright` | 8 | Copyright violations |
| `malware` | 4 | Malware only |
| `ipfs-official-denylist` | 156+ | IPFS community blocklist |

## Security Considerations

- **Content Responsibility**: Gateway operator is not responsible for user content
- **HTTP 451**: Legal-compliant blocking with proper status code
- **Copyright Protection**: Maintain safe harbor through takedown process
- **Rate Limiting**: Consider adding Flask-Limiter for production
- **Monitoring**: Regular log review recommended
- **Auto-updates**: Official denylist syncs every 24h
- **Blacklist Priority**: Local list overrides official for custom reasons

## Performance

Tested on Raspberry Pi 4 (4GB RAM):
- 50-100 concurrent requests
- ~10ms response time (cached content)
- 99%+ uptime
- 5-minute blacklist cache
- Background denylist sync (24h interval)

For higher loads, consider:
- Multiple backend IPFS nodes
- Nginx reverse proxy
- CDN for static content

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/name`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push to branch (`git push origin feature/name`)
5. Open Pull Request

## Troubleshooting

### Gateway Returns 503

```bash
# Check IPFS daemon
ipfs id

# Restart if needed
pkill ipfs
ipfs daemon
```

### Gateway Returns 504 (Timeout)

```bash
# Content may be slow to fetch or unavailable
# Check IPFS daemon logs
ipfs log tail

# Increase timeout in app.py if needed
# proxy_ipfs_path(..., stream_timeout=180)
```

### Blacklist Not Updating

```bash
# Force reload local blacklist
curl -X POST http://localhost:8081/admin/reload-blacklist

# Force sync official denylist
curl -X POST http://localhost:8081/admin/sync-ipfs-denylist

# Check logs
tail -f logs/servebeer_audit.log | grep -i denylist
```

### SSL Certificate Errors

```bash
# Check certificate paths
ls -la /home/user/cert/

# Verify certificate validity
openssl x509 -in fullchain.pem -text -noout
```

### Database Errors

```bash
# Check database
sqlite3 database/servebeer.db ".tables"

# Rebuild if corrupted
rm database/servebeer.db
python3 app.py  # Will recreate on startup
```

## License

MIT License - See LICENSE file for details

## Credits

Built by NFTomczain for the decentralized web community.

**Philosophy**: "Fire beneath the ashes, code as memory"

## Links

- GitHub: https://github.com/nftomczain/servebeer-gateway
- IPFS Docs: https://docs.ipfs.tech
- Gateway Spec: https://specs.ipfs.tech/http-gateways/
- IPFS Official Denylist: https://github.com/ipfs/infra/blob/master/ipfs/gateway/denylist.conf

## Support

- GitHub Issues: Report bugs and feature requests
- Community: Join IPFS community forums
- Copyright: Use /copyright/report endpoint

---

Made with 🍺 for the decentralized web
