# ServeBeer IPFS Gateway

Public IPFS HTTP Gateway running on community-powered infrastructure. Decentralized content access with HTTPS, DSA compliance, and minimal logging.

## Features

- **IPFS/IPNS Gateway** - Access any IPFS content via HTTP/HTTPS
- **SSL/TLS Support** - Secure access with Let's Encrypt certificates
- **DSA Compliant** - Takedown notice process with 48h response
- **Content Blacklist** - File-based CID blocking system
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

```bash
# Install IPFS Kubo
# wget https://dist.ipfs.tech/kubo/v0.24.0/kubo_v0.24.0_linux-amd64.tar.gz
# tar -xvzf kubo_v0.24.0_linux-amd64.tar.gz
# Install IPFS Kubo
Follow the official installation guide for your architecture:
https://docs.ipfs.tech/install/command-line/#install-official-binary-distributions
cd kubo
sudo bash install.sh
**Note:** This gateway runs on Raspberry Pi (ARM64 architecture).

# Initialize and start
ipfs init
ipfs daemon
```

## Configuration

Edit `.env` file:

```bash
# Server
APP_HOST=0.0.0.0
APP_PORT=443

# IPFS Gateway
IPFS_HTTP_GATEWAY=http://127.0.0.1:8080

# Database & Logs
DATABASE_PATH=database/servebeer.db
LOG_FILE=logs/servebeer_audit.log
BLACKLIST_FILE=blacklist.txt

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

Or modify paths in `bpp.py` function `create_ssl_context()`.

## Usage

### Run Development Server

```bash
source venv/bin/activate
sudo python3 bpp.py
```

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

Add CIDs to `blacklist.txt` (one per line):

```bash
echo "QmBadContentCID123..." >> blacklist.txt
```

Gateway automatically loads blacklist on each request. Blocked content returns HTTP 451.

## Monitoring

### Check Logs

```bash
# Audit log
tail -f logs/servebeer_audit.log

# Database logs
sqlite3 database/servebeer.db "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10"
```

### Health Check

```
https://your-domain.com/health
```

Returns JSON with IPFS and database status.

### Abuse Monitoring

```bash
# Run abuse check script
./check_abuse.sh

# Shows:
# - Top requested CIDs
# - Top IPs by request count
# - Blacklist hits
```

## DSA Compliance

### File Takedown Notice

Users can file DSA notices at:
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
3. Valid CID added to blacklist
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

## Project Structure

```
servebeer-gateway/
├── bpp.py                 # Main application
├── requirements.txt       # Python dependencies
├── .env.example          # Configuration template
├── .gitignore            # Git ignore rules
├── README.md             # This file
├── LICENSE               # License
├── install.sh            # Installation script
├── check_abuse.sh        # Monitoring script
├── blacklist.txt         # Blocked CIDs
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── copyright.html
│   ├── copyright_report.html
│   ├── cookies.html
│   └── terms.html
├── database/             # SQLite database (gitignored)
└── logs/                 # Log files (gitignored)
```

## Security Considerations

- **Content Responsibility**: Gateway operator is not responsible for user content
- **DSA Protection**: Implement takedown process to maintain safe harbor
- **Rate Limiting**: Consider adding Flask-Limiter for production
- **Monitoring**: Regular log review recommended
- **Blacklist**: Keep updated based on reports

## Performance

Tested on Raspberry Pi 4 (4GB RAM):
- 50-100 concurrent requests
- ~10ms response time (cached content)
- 99%+ uptime

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
python3 bpp.py  # Will recreate on startup
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

## Support

- GitHub Issues: Report bugs and feature requests
- Community: Join IPFS community forums
- DMCA: Use /dmca/report endpoint

---

Made with 🍺 for the decentralized web
