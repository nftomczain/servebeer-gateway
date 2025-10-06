#!/bin/bash
# ServeBeer IPFS Gateway - Installation Script
# For Ubuntu/Debian-based systems

set -e

echo "=========================================="
echo "ServeBeer IPFS Gateway - Installation"
echo "=========================================="
echo ""

# Check if running as root for port 443
if [ "$EUID" -ne 0 ] && [ "$1" != "--user" ]; then 
    echo "Note: Running without sudo. Port 443 will require sudo to run."
    echo "Run with --user flag to skip this warning."
    echo ""
fi

# Check Python version
echo "[1/8] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Installing..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv
else
    echo "Python 3 found: $(python3 --version)"
fi

# Create virtual environment
echo ""
echo "[2/8] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Activate venv and install requirements
echo ""
echo "[3/8] Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Check IPFS
echo ""
echo "[4/8] Checking IPFS installation..."
if ! command -v ipfs &> /dev/null; then
    echo "IPFS not found. Do you want to install it? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Installing IPFS Kubo..."
        wget https://dist.ipfs.tech/kubo/v0.24.0/kubo_v0.24.0_linux-amd64.tar.gz
        tar -xvzf kubo_v0.24.0_linux-amd64.tar.gz
        cd kubo
        sudo bash install.sh
        cd ..
        rm -rf kubo kubo_v0.24.0_linux-amd64.tar.gz
        
        # Initialize IPFS
        ipfs init
        echo "IPFS installed and initialized"
    else
        echo "Skipping IPFS installation. You'll need to install it manually."
    fi
else
    echo "IPFS found: $(ipfs version --number)"
fi

# Create directories
echo ""
echo "[5/8] Creating directories..."
mkdir -p database logs
touch blacklist.txt
echo "Directories created: database/, logs/, blacklist.txt"

# Setup .env
echo ""
echo "[6/8] Setting up configuration..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo ".env created from .env.example"
        echo "Please edit .env with your configuration"
    else
        echo "Warning: .env.example not found"
    fi
else
    echo ".env already exists"
fi

# Initialize database
echo ""
echo "[7/8] Initializing database..."
python3 -c "from gateway-v1 import setup_database; setup_database()" 2>/dev/null || echo "Database will be created on first run"

# Setup systemd service (optional)
echo ""
echo "[8/8] Setup systemd service? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    cat > servebeer-gateway.service <<EOF
[Unit]
Description=ServeBeer IPFS Gateway
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python3 $(pwd)/gateway-v1.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo cp servebeer-gateway.service /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "Systemd service installed"
    echo "Start with: sudo systemctl start servebeer-gateway"
    echo "Enable on boot: sudo systemctl enable servebeer-gateway"
fi

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env with your configuration"
echo "2. Configure SSL certificates (if using HTTPS)"
echo "3. Start IPFS daemon: ipfs daemon &"
echo "4. Run gateway: sudo python3 gateway-v1.py"
echo ""
echo "For more info, see README.md"
