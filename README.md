# ASAN Chrome Mirror

A production-ready Python system service that continuously mirrors Chromium ASAN (AddressSanitizer) builds for Windows and Linux.

## Overview

This service automatically:
- Downloads the latest `get_asan_chrome.py` script from Chromium source
- Probes for available ASAN Chrome builds for Windows (win64) and Linux
- Downloads and validates all available builds sequentially
- Maintains a local index of downloaded versions in SQLite
- Exposes downloaded builds via HTTP with auto-indexed directories
- Retries failed downloads with exponential backoff
- Runs as a systemd service with auto-restart and graceful shutdown
- Logs to both rotating files and stdout

## Features

- **Automated Discovery**: Probes configurable version ranges to find available builds
- **Sequential Downloads**: Windows builds first, then Linux (as configured)
- **Persistent Tracking**: SQLite database tracks all downloads, checksums, and timestamps
- **Retry Logic**: Exponential backoff (2^n seconds) with configurable max retries
- **HTTP Server**: FastAPI-based server with auto-indexed directories, health checks, and metrics
- **Async Architecture**: Scheduler and HTTP server run concurrently
- **Graceful Shutdown**: Handles SIGTERM and SIGINT signals cleanly
- **Comprehensive Logging**: Rotating file logs + stdout with configurable levels
- **Production Ready**: Systemd integration, security hardening, resource limits

## Architecture

```
┌─────────────────────────────────────────┐
│  ASAN Chrome Mirror Service             │
├─────────────────────────────────────────┤
│  Main Entry Point (main.py)             │
│  - Signal handling                      │
│  - Component initialization             │
│  - Async event loop management          │
├──────────────────────┬──────────────────┤
│  Scheduler Task      │  HTTP Server Task │
├──────────────────────┼──────────────────┤
│ • 12-hour polling   │ • FastAPI app    │
│ • Version probing   │ • File serving   │
│ • Downloads         │ • Auto-indexing  │
│ • Database updates  │ • Metrics/Health │
└──────────────────────┴──────────────────┘
         ↓                    ↓
    ┌─────────────────────────────────────┐
    │  Shared Resources                   │
    ├─────────────────────────────────────┤
    │ • SQLite Database (builds.db)       │
    │ • Storage Directory (/storage)      │
    │ • Configuration (config.yaml)       │
    │ • Logging (logs/)                   │
    └─────────────────────────────────────┘
```

### Components

- **config.py**: Configuration management using Pydantic + YAML
- **database.py**: SQLite schema and CRUD operations for tracking builds
- **updater.py**: Fetches and manages get_asan_chrome.py script
- **downloader.py**: Version probing, downloading, validation, and retry logic
- **scheduler.py**: Async scheduler for 12-hour polling loop
- **server.py**: FastAPI HTTP server with file serving and metrics
- **main.py**: Application orchestrator and entry point

## Installation

### Prerequisites

- Ubuntu Server 22.04 LTS or later
- Python 3.11+
- Root access (for systemd installation)
- ~200GB+ storage for builds (configurable)

### Quick Install

```bash
# Clone or extract project
cd /path/to/asan-chrome-mirror

# Run installation script (requires sudo)
sudo ./install.sh
```

The installation script will:
1. Create `asan-mirror` system user and group
2. Create directories: `/opt/asan-chrome-mirror`, `/storage`, `/var/log/asan-chrome-mirror`
3. Copy project files and install Python dependencies
4. Copy systemd service file
5. Enable the service

### Manual Installation

If you prefer manual setup:

```bash
# Create system user
sudo groupadd --system asan-mirror
sudo useradd --system --gid asan-mirror --shell /usr/sbin/nologin \
    --home-dir /var/lib/asan-mirror asan-mirror

# Create directories
sudo mkdir -p /opt/asan-chrome-mirror /storage/{win64,linux} /var/log/asan-chrome-mirror

# Copy files
sudo cp -r app requirements.txt config.yaml.example /opt/asan-chrome-mirror/
sudo cp systemd/asan-chrome-mirror.service /etc/systemd/system/

# Set permissions
sudo chown -R asan-mirror:asan-mirror /opt/asan-chrome-mirror /storage /var/log/asan-chrome-mirror

# Install dependencies
sudo python3 -m pip install -r /opt/asan-chrome-mirror/requirements.txt

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable asan-chrome-mirror.service
```

## Configuration

Configuration is loaded from `config.yaml` in the installation directory. An example is provided as `config.yaml.example`.

### Configuration Options

```yaml
# Storage and paths
storage_dir: /storage
log_dir: /var/log/asan-chrome-mirror
data_dir: ./data

# Version discovery (probe range for available builds)
min_version: 100        # Start probing from Chromium version 100
max_version: 200        # Stop probing at version 200

# Scheduling (12 hours = 43200 seconds)
check_interval_seconds: 43200

# HTTP server
http_host: 0.0.0.0     # Bind to all interfaces
http_port: 8000         # Port

# Retry policy
max_retries: 5          # Maximum retry attempts per download
retry_backoff_base: 2   # Exponential backoff: 2^(attempt-1) seconds

# Download timeout
download_timeout_seconds: 3600  # 1 hour per download

# Logging
logging_level: INFO     # DEBUG, INFO, WARNING, ERROR, CRITICAL
log_max_bytes: 10485760 # 10MB before rotation
log_backup_count: 5     # Keep 5 backup log files
```

### Environment Variable Overrides

Any configuration option can be overridden with environment variables:

```bash
export ASAN_MIN_VERSION=110
export ASAN_MAX_VERSION=210
export ASAN_CHECK_INTERVAL_SECONDS=86400  # 24 hours
```

## Usage

### Start the Service

```bash
sudo systemctl start asan-chrome-mirror
```

### Check Service Status

```bash
sudo systemctl status asan-chrome-mirror
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u asan-chrome-mirror -f

# Last 100 lines
sudo journalctl -u asan-chrome-mirror -n 100

# Logs from last 1 hour
sudo journalctl -u asan-chrome-mirror --since "1 hour ago"

# Or view rotating log file
tail -f /var/log/asan-chrome-mirror/asan-chrome-mirror.log
```

### Stop the Service

```bash
sudo systemctl stop asan-chrome-mirror
```

### Restart the Service

```bash
sudo systemctl restart asan-chrome-mirror
```

### Enable/Disable Auto-Start

```bash
# Enable (start on boot)
sudo systemctl enable asan-chrome-mirror

# Disable (don't start on boot)
sudo systemctl disable asan-chrome-mirror
```

## HTTP API

### Root Endpoint

```
GET /
```

Returns service information and available resources.

**Response:**
```json
{
  "service": "ASAN Chrome Mirror",
  "status": "operational",
  "timestamp": "2024-05-07T12:34:56.789012",
  "directories": {
    "windows": "http://SERVER_IP:8000/win64/",
    "linux": "http://SERVER_IP:8000/linux/"
  },
  "endpoints": {
    "health": "/health",
    "metrics": "/metrics"
  }
}
```

### Directory Listing

```
GET /win64/
GET /linux/
```

Returns HTML-formatted directory listing with file sizes and download links.

### Download File

```
GET /win64/{filename}
GET /linux/{filename}
```

Downloads a specific build. Supports large file streaming.

**Example:**
```bash
curl -O http://localhost:8000/win64/120.0.0.0.zip
```

### Health Check

```
GET /health
```

Returns service health status.

**Response:**
```json
{
  "status": "ok",
  "service": "ASAN Chrome Mirror",
  "timestamp": "2024-05-07T12:34:56.789012"
}
```

### Metrics

```
GET /metrics
```

Returns download statistics and scheduler status.

**Response:**
```json
{
  "timestamp": "2024-05-07T12:34:56.789012",
  "downloads": {
    "total_count": 42,
    "total_size_bytes": 107374182400,
    "per_os": {
      "win64": 21,
      "linux": 21
    }
  },
  "scheduler": {
    "last_check": "2024-05-07T12:00:00.000000",
    "next_check": "2024-05-08T00:00:00.000000",
    "check_interval_seconds": 43200
  }
}
```

## Monitoring

### Check Disk Usage

```bash
# Check storage directory
du -sh /storage

# Check per-OS breakdown
du -sh /storage/win64 /storage/linux
```

### Monitor Database

```bash
# View build statistics
sqlite3 /opt/asan-chrome-mirror/data/builds.db "SELECT os, COUNT(*) FROM builds WHERE status='success' GROUP BY os;"

# View recent downloads
sqlite3 /opt/asan-chrome-mirror/data/builds.db "SELECT version, os, timestamp FROM builds ORDER BY timestamp DESC LIMIT 10;"
```

### Check Service Health

```bash
# HTTP health check
curl http://localhost:8000/health

# Get metrics
curl http://localhost:8000/metrics | jq
```

## Troubleshooting

### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u asan-chrome-mirror -n 50 -e
```

**Common issues:**
- Python dependencies not installed: `sudo python3 -m pip install -r /opt/asan-chrome-mirror/requirements.txt`
- Permission issues: Verify `/storage` and `/var/log/asan-chrome-mirror` are owned by `asan-mirror`
- Port 8000 in use: Change `http_port` in config.yaml or kill the process using it
- Configuration not found: Copy `config.yaml.example` to `config.yaml`

### Service Keeps Restarting

**Check the logs:**
```bash
sudo journalctl -u asan-chrome-mirror -f
```

**Common causes:**
- Network issues: Check internet connectivity
- Chromium source unreachable: Try manually fetching the script
- Storage directory full: Check disk space
- Download timeout too short: Increase `download_timeout_seconds`

### HTTP Server Not Responding

**Check if service is running:**
```bash
sudo systemctl status asan-chrome-mirror
```

**Test connectivity:**
```bash
curl http://localhost:8000/health
```

**Check firewall:**
```bash
sudo ufw allow 8000/tcp
```

### Downloads Not Starting

**Check scheduler status:**
```bash
curl http://localhost:8000/metrics | jq '.scheduler'
```

**Verify script exists:**
```bash
ls -la /opt/asan-chrome-mirror/data/get_asan_chrome.py
```

**Manual test of downloader:**
```bash
cd /opt/asan-chrome-mirror
python3 -c "from app.downloader import Downloader; from pathlib import Path; d = Downloader(Path('data/get_asan_chrome.py'), Path('/storage')); print(d.probe_versions('win64', 100, 105))"
```

### Database Corruption

If the SQLite database is corrupted:

```bash
# Backup current database
sudo cp /opt/asan-chrome-mirror/data/builds.db /opt/asan-chrome-mirror/data/builds.db.bak

# Stop service
sudo systemctl stop asan-chrome-mirror

# Remove corrupted database
sudo rm /opt/asan-chrome-mirror/data/builds.db

# Restart service (will recreate schema)
sudo systemctl start asan-chrome-mirror
```

## Performance Notes

### Disk Usage

- Each build is typically 100-300MB
- Full mirror of 100 versions × 2 OS = ~20-60GB
- Default version range (100-200) will have varying availability

### Network Usage

- Initial download of each build: 100-300MB
- Scheduler checks: ~1MB per 12 hours
- HTTP access: Depends on usage

### CPU & Memory

- Idle: <5MB memory, minimal CPU
- During download: ~50-100MB memory, 1 CPU core
- HTTP serving: Minimal overhead (FastAPI async)

## Security Considerations

- Service runs as unprivileged `asan-mirror` user
- Storage directories have restrictive permissions (755)
- HTTP server is open to all by default (intended for private networks)
- For external access, use a reverse proxy with authentication (nginx, Apache, etc.)
- No TLS/HTTPS support (use reverse proxy for encryption)

## Development

### Running Locally

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Create config
cp config.yaml.example config.yaml

# Run application
python3 -m app.main
```

### Testing Components

```bash
# Test config loading
python3 -c "from app.config import get_config; print(get_config())"

# Test database
python3 -c "from app.database import Database; from pathlib import Path; db = Database(Path('data/builds.db')); print(db.get_stats())"

# Test HTTP server
curl http://localhost:8000/health
```

## Updating

To update the service:

```bash
# Stop service
sudo systemctl stop asan-chrome-mirror

# Backup current installation
sudo cp -r /opt/asan-chrome-mirror /opt/asan-chrome-mirror.backup

# Update files
sudo cp -r app requirements.txt /opt/asan-chrome-mirror/

# Reinstall dependencies
sudo python3 -m pip install -r /opt/asan-chrome-mirror/requirements.txt --upgrade

# Start service
sudo systemctl start asan-chrome-mirror
```

## Uninstallation

```bash
# Stop service
sudo systemctl stop asan-chrome-mirror

# Disable service
sudo systemctl disable asan-chrome-mirror

# Remove systemd service file
sudo rm /etc/systemd/system/asan-chrome-mirror.service
sudo systemctl daemon-reload

# Remove installation (optional - keeps data by default)
sudo rm -r /opt/asan-chrome-mirror

# Remove system user (optional)
sudo userdel asan-mirror
sudo groupdel asan-mirror

# Remove storage (only if you want to free up space)
# sudo rm -r /storage
```

## Support & Issues

For issues with the ASAN Chrome Mirror service itself, check the logs and troubleshooting section above.

For issues with the underlying `get_asan_chrome.py` script or Chromium builds, see:
- https://chromium.googlesource.com/chromium/src/+/refs/heads/main/tools/get_asan_chrome/

## License

This project mirrors official Chromium ASAN builds. See Chromium's licensing for build details.

## Changelog

### Version 1.0.0 (2024-05-07)
- Initial release
- Full ASAN Chrome mirror for Windows and Linux
- HTTP server with auto-indexing
- Systemd integration
- SQLite tracking
- Exponential backoff retry logic
- Graceful shutdown handling
