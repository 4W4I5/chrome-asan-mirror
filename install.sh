#!/bin/bash

# Installation script for ASAN Chrome Mirror service
# Must be run as root: sudo ./install.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation paths
INSTALL_DIR="/opt/asan-chrome-mirror"
STORAGE_DIR="/storage"
LOG_DIR="/var/log/asan-chrome-mirror"
SERVICE_USER="asan-mirror"
SERVICE_GROUP="asan-mirror"
SERVICE_FILE="systemd/asan-chrome-mirror.service"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}ASAN Chrome Mirror Installation${NC}"
echo -e "${GREEN}================================${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run as root${NC}"
    exit 1
fi

# Create service user and group
echo -e "${YELLOW}Creating system user and group...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    groupadd --system "$SERVICE_GROUP" 2>/dev/null || true
    useradd --system --gid "$SERVICE_GROUP" --shell /usr/sbin/nologin --home-dir /var/lib/asan-mirror "$SERVICE_USER"
    echo -e "${GREEN}Created user: $SERVICE_USER${NC}"
else
    echo -e "${YELLOW}User $SERVICE_USER already exists${NC}"
fi

# Create directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$STORAGE_DIR/win64"
mkdir -p "$STORAGE_DIR/linux"
mkdir -p "$LOG_DIR"

# Copy project files
echo -e "${YELLOW}Copying project files...${NC}"
cp -r app "$INSTALL_DIR/"
cp -r data "$INSTALL_DIR/" 2>/dev/null || mkdir -p "$INSTALL_DIR/data"
cp config.yaml.example "$INSTALL_DIR/" || true
cp requirements.txt "$INSTALL_DIR/"
cp -r systemd "$INSTALL_DIR/"

# Create config.yaml from example if it doesn't exist
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    echo -e "${YELLOW}Creating config.yaml...${NC}"
    cp "$INSTALL_DIR/config.yaml.example" "$INSTALL_DIR/config.yaml"
fi

# Set permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$STORAGE_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$STORAGE_DIR"
chmod 755 "$LOG_DIR"

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python"
elif [[ -x "$INSTALL_DIR/.venv/bin/python" ]]; then
    PYTHON_CMD="$INSTALL_DIR/.venv/bin/python"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
else
    PYTHON_CMD="python3"
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD -m pip install --upgrade pip setuptools wheel > /dev/null
$PYTHON_CMD -m pip install -r "$INSTALL_DIR/requirements.txt"
echo -e "${GREEN}Python dependencies installed${NC}"

# Copy systemd service file
echo -e "${YELLOW}Installing systemd service...${NC}"
SYSTEMD_DEST="/etc/systemd/system/asan-chrome-mirror.service"
cp "$INSTALL_DIR/systemd/asan-chrome-mirror.service" "$SYSTEMD_DEST"
chmod 644 "$SYSTEMD_DEST"

# Reload systemd
echo -e "${YELLOW}Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable service
echo -e "${YELLOW}Enabling service...${NC}"
systemctl enable asan-chrome-mirror.service

# Print summary
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Installation Directory: $INSTALL_DIR"
echo "Storage Directory: $STORAGE_DIR"
echo "Log Directory: $LOG_DIR"
echo "Service User: $SERVICE_USER"
echo "Systemd Service: asan-chrome-mirror.service"
echo ""
echo "Next steps:"
echo "1. Review and edit the configuration: vim $INSTALL_DIR/config.yaml"
echo "2. Start the service: sudo systemctl start asan-chrome-mirror"
echo "3. Check service status: sudo systemctl status asan-chrome-mirror"
echo "4. View logs: sudo journalctl -u asan-chrome-mirror -f"
echo ""
echo "HTTP Server will be available at: http://localhost:8000"
echo "  - Root: http://localhost:8000/"
echo "  - Windows builds: http://localhost:8000/win64/"
echo "  - Linux builds: http://localhost:8000/linux/"
echo "  - Health check: http://localhost:8000/health"
echo "  - Metrics: http://localhost:8000/metrics"
echo ""
