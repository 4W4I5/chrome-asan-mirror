# ASAN Chrome Mirror - Project Summary

## ✅ Implementation Complete

A production-ready Python system service has been successfully created that continuously mirrors Chromium ASAN (AddressSanitizer) Chrome builds for both Windows and Linux.

**Location:** `/tmp/asan-chrome-mirror/`

---

## 📦 Deliverables

### Core Application Files

| File | Purpose |
|------|---------|
| `app/__init__.py` | Package initialization |
| `app/config.py` | Configuration management (Pydantic + YAML) |
| `app/database.py` | SQLite schema and CRUD operations |
| `app/updater.py` | Fetch and manage get_asan_chrome.py script |
| `app/downloader.py` | Version probing, downloading, validation |
| `app/scheduler.py` | 12-hour async polling loop |
| `app/server.py` | FastAPI HTTP server with auto-indexing |
| `app/main.py` | Application orchestrator and entry point |

### Configuration & Deployment

| File | Purpose |
|------|---------|
| `config.yaml.example` | Configuration template with all options |
| `requirements.txt` | Python package dependencies |
| `systemd/asan-chrome-mirror.service` | Systemd service unit file |
| `install.sh` | Automated installation script (root required) |

### Documentation & Testing

| File | Purpose |
|------|---------|
| `README.md` | Complete user documentation |
| `DEPLOYMENT.md` | Production deployment guide |
| `verify.py` | Component verification and testing script |
| `quickstart_test.py` | Quick startup and HTTP endpoint testing |
| `.gitignore` | Version control exclusions |

### Directory Structure

```
asan-chrome-mirror/
├── app/                              # Application package
│   ├── __init__.py
│   ├── config.py                    # Configuration management
│   ├── database.py                  # SQLite operations
│   ├── updater.py                   # Script updater
│   ├── downloader.py                # Download logic
│   ├── scheduler.py                 # Async scheduler
│   ├── server.py                    # FastAPI server
│   └── main.py                      # Orchestrator
├── systemd/
│   └── asan-chrome-mirror.service   # Systemd unit file
├── data/                            # Application data (created at runtime)
├── logs/                            # Log files (created at runtime)
├── config.yaml.example              # Configuration template
├── requirements.txt                 # Python dependencies
├── install.sh                       # Installation script
├── verify.py                        # Verification tests
├── quickstart_test.py               # Quick start tests
├── README.md                        # User documentation
├── DEPLOYMENT.md                    # Deployment guide
├── PROJECT_SUMMARY.md               # This file
└── .gitignore                       # Git exclusions
```

---

## 🎯 Key Features Implemented

### ✅ Core Functionality
- [x] Automatically downloads latest `get_asan_chrome.py` from Chromium source
- [x] Checks every 12 hours for new ASAN Chrome builds
- [x] Uses downloaded script to fetch builds via subprocess
- [x] Downloads ALL available ASAN Chrome versions for Windows and Linux
- [x] Downloads Windows (win64) first, then Linux (sequential)
- [x] Continuous monitoring for newer versions
- [x] Maintains local SQLite database of downloaded versions
- [x] Preserves all downloaded ZIP archives permanently
- [x] Organized storage: `/storage/win64/`, `/storage/linux/`

### ✅ Download Management
- [x] Version range probing (configurable min/max version)
- [x] ZIP file integrity validation
- [x] SHA256 checksum computation and storage
- [x] Exponential backoff retry logic (3-5 attempts)
- [x] Partial download resumption support
- [x] Failed download tracking and reporting

### ✅ HTTP Server
- [x] FastAPI-based async web server
- [x] Auto-indexed directory listings with HTML display
- [x] File serving with large file streaming support
- [x] Health check endpoint (`/health`)
- [x] Metrics endpoint (`/metrics`) with statistics
- [x] Binds to 0.0.0.0:8000 (configurable)
- [x] Concurrent request handling

### ✅ System Integration
- [x] Systemd service unit file with auto-restart
- [x] Graceful shutdown on SIGTERM/SIGINT
- [x] Restart on failure with backoff
- [x] Unprivileged `asan-mirror` system user
- [x] Rotating log files (10MB, 5 backups)
- [x] Systemd journal logging
- [x] Security hardening (resource limits, no new privileges)

### ✅ Persistence & Tracking
- [x] SQLite database schema for build tracking
- [x] Tracks: version, OS, filepath, checksum, timestamp, status
- [x] CRUD operations for build management
- [x] Download statistics queries
- [x] Database migration support

### ✅ Configuration
- [x] YAML-based configuration system
- [x] Pydantic-based validation
- [x] Environment variable overrides
- [x] Configurable version range probing
- [x] Configurable check intervals
- [x] Adjustable retry policies
- [x] Logging level configuration

### ✅ Documentation
- [x] Comprehensive README with architecture overview
- [x] Detailed deployment guide
- [x] API documentation
- [x] Troubleshooting guide
- [x] Configuration examples
- [x] Service management instructions
- [x] Monitoring procedures

### ✅ Testing & Verification
- [x] Component verification script
- [x] Syntax checking for all modules
- [x] Import tests for all packages
- [x] Configuration loading tests
- [x] Database functionality tests
- [x] FastAPI application tests
- [x] Quick start endpoint tests

---

## 📋 Technical Stack

### Dependencies
```
fastapi==0.104.1          # Web framework
uvicorn[standard]==0.24.0 # ASGI server
pydantic==2.5.0           # Data validation
pyyaml==6.0.1             # Configuration parsing
aiofiles==23.2.1          # Async file operations
requests==2.31.0          # HTTP client
```

### Python Requirements
- Python 3.11+ (tested with 3.12)
- asyncio (stdlib - async scheduler)
- sqlite3 (stdlib - database)
- subprocess (stdlib - script execution)
- logging (stdlib - rotating file logs)

### System Requirements
- Ubuntu Server 22.04 LTS or later
- Root access for installation
- ~200GB+ storage (configurable)
- Internet connectivity

---

## 🚀 Quick Start

### 1. Installation

```bash
cd /tmp/asan-chrome-mirror
sudo ./install.sh
```

This will:
- Create `asan-mirror` system user
- Create directories: `/opt/asan-chrome-mirror`, `/storage/`, `/var/log/asan-chrome-mirror`
- Install Python dependencies
- Copy systemd service file
- Enable service for auto-start

### 2. Configuration

```bash
sudo nano /opt/asan-chrome-mirror/config.yaml
```

Key settings to review:
- `storage_dir`: Where builds are saved (default: `/storage`)
- `min_version` / `max_version`: Version range to probe (default: 100-200)
- `check_interval_seconds`: How often to check for updates (default: 43200 = 12 hours)
- `http_host` / `http_port`: HTTP server binding

### 3. Start Service

```bash
sudo systemctl start asan-chrome-mirror
sudo systemctl status asan-chrome-mirror
```

### 4. Test HTTP Server

```bash
# Health check
curl http://localhost:8000/health

# Root info
curl http://localhost:8000/

# Metrics
curl http://localhost:8000/metrics | jq

# Directory listing (HTML)
curl http://localhost:8000/win64/
```

### 5. View Logs

```bash
# Real-time logs
sudo journalctl -u asan-chrome-mirror -f

# Or rotating log file
tail -f /var/log/asan-chrome-mirror/asan-chrome-mirror.log
```

---

## 📊 Architecture

```
┌──────────────────────────────────────────────┐
│      ASAN Chrome Mirror Service              │
├──────────────────────────────────────────────┤
│  Application Entry Point (main.py)           │
│  • Signal handling (SIGTERM, SIGINT)         │
│  • Component initialization                  │
│  • Async event loop management               │
├────────────────────┬─────────────────────────┤
│  Scheduler Task    │  HTTP Server Task       │
├────────────────────┼─────────────────────────┤
│ • 12-hour loop     │ • FastAPI app           │
│ • Update script    │ • File serving          │
│ • Probe versions   │ • Auto-indexing         │
│ • Download builds  │ • Health/Metrics        │
│ • Update DB        │ • 0.0.0.0:8000          │
└────────────────────┴─────────────────────────┘
         ↓                      ↓
    ┌──────────────────────────────────────────┐
    │  Shared Resources                        │
    ├──────────────────────────────────────────┤
    │ • SQLite Database (builds.db)            │
    │ • Storage (/storage/win64, /linux)       │
    │ • Configuration (config.yaml)            │
    │ • Logs (/var/log/asan-chrome-mirror)     │
    └──────────────────────────────────────────┘
```

---

## 🔄 Scheduler Workflow (Every 12 Hours)

```
Start Check Cycle
   ↓
[1] Update get_asan_chrome.py from Chromium source
   ↓
[2] Probe for Windows (win64) versions in range
   ↓
[3] Download all missing Windows builds (sequential)
   ↓
[4] Probe for Linux versions in range
   ↓
[5] Download all missing Linux builds (sequential)
   ↓
[6] Validate ZIP files and compute SHA256
   ↓
[7] Update database with status and checksums
   ↓
[8] Clean temporary files
   ↓
[9] Log statistics
   ↓
End Check Cycle - Wait 12 hours
```

---

## 🌐 HTTP API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Service info and available resources |
| `/health` | GET | Health check (always 200 OK) |
| `/metrics` | GET | Download statistics and scheduler status |
| `/win64/` | GET | Windows builds directory listing (HTML) |
| `/linux/` | GET | Linux builds directory listing (HTML) |
| `/win64/{filename}` | GET | Download specific Windows build |
| `/linux/{filename}` | GET | Download specific Linux build |

---

## 💾 Database Schema

SQLite table: `builds`

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Auto-increment primary key |
| version | TEXT | Chromium version (e.g., "120.0.0.0") |
| os | TEXT | Operating system ("win64" or "linux") |
| filepath | TEXT | Local file path |
| checksum | TEXT | SHA256 hash |
| timestamp | DATETIME | Download timestamp |
| status | TEXT | "success", "failed", "pending", "in_progress" |
| error_message | TEXT | Error details if failed |
| retry_count | INTEGER | Retry attempts |

---

## ⚙️ Retry Logic

Failed downloads use exponential backoff:

```
Attempt 1: Wait 2^0  = 1 second
Attempt 2: Wait 2^1  = 2 seconds
Attempt 3: Wait 2^2  = 4 seconds
Attempt 4: Wait 2^3  = 8 seconds
Attempt 5: Wait 2^4  = 16 seconds
Max: 5 retries total
```

Configuration:
- `max_retries`: 5 (adjustable)
- `retry_backoff_base`: 2 (adjustable)

---

## 📝 Configuration Reference

See `config.yaml.example` for full documentation.

```yaml
# Storage and paths
storage_dir: /storage                    # Root for downloads
log_dir: /var/log/asan-chrome-mirror     # Log files
data_dir: ./data                         # Application data

# Version discovery
min_version: 100                         # Start probing at version 100
max_version: 200                         # Stop probing at version 200

# Scheduling
check_interval_seconds: 43200            # 12 hours = 43200 seconds

# HTTP server
http_host: 0.0.0.0                      # Bind to all interfaces
http_port: 8000                          # Port number

# Retry policy
max_retries: 5                           # Max retry attempts
retry_backoff_base: 2                    # Exponential backoff base

# Download behavior
download_timeout_seconds: 3600           # 1 hour timeout

# Logging
logging_level: INFO                      # DEBUG/INFO/WARNING/ERROR
log_max_bytes: 10485760                  # 10MB before rotation
log_backup_count: 5                      # Keep 5 backups
```

---

## 🧪 Verification & Testing

### Run Tests

```bash
cd /tmp/asan-chrome-mirror

# Full verification suite
python3 verify.py

# Expected output: 5/5 tests passed
```

### Quick Startup Test

```bash
# Test with HTTP server running
python3 quickstart_test.py
```

---

## 📚 Documentation

### Main Documentation
- **README.md** (14KB) - Complete user guide with examples
- **DEPLOYMENT.md** (10KB) - Production deployment guide
- **PROJECT_SUMMARY.md** (this file) - High-level overview

### Configuration Files
- **config.yaml.example** - Documented configuration template

### Installation & Scripts
- **install.sh** - Automated setup (bash)
- **verify.py** - Component tests (Python)
- **quickstart_test.py** - HTTP server tests (Python)

---

## 🔐 Security Features

- Runs as unprivileged `asan-mirror` system user
- Restrictive file permissions (755 on storage)
- SELinux and AppArmor compatible
- No privileged operations after startup
- Resource limits enforced via systemd
- Secure subprocess execution with timeouts
- No hardcoded credentials
- Input validation via Pydantic

---

## 📈 Monitoring & Maintenance

### System Health

```bash
# Service status
sudo systemctl status asan-chrome-mirror

# Active connections
sudo ss -tlnp | grep 8000

# CPU/Memory usage
top -p $(pgrep -f app.main)

# Disk usage
du -sh /storage
```

### Database Queries

```bash
# Download statistics
sqlite3 /opt/asan-chrome-mirror/data/builds.db \
  "SELECT os, COUNT(*) FROM builds WHERE status='success' GROUP BY os;"

# Failed downloads
sqlite3 /opt/asan-chrome-mirror/data/builds.db \
  "SELECT version, error_message FROM builds WHERE status='failed' LIMIT 10;"
```

### Log Analysis

```bash
# Error summary
sudo journalctl -u asan-chrome-mirror | grep ERROR

# Performance metrics
sudo journalctl -u asan-chrome-mirror | grep "Check cycle"

# Recent activity
sudo journalctl -u asan-chrome-mirror -n 50 --no-pager
```

---

## 🎓 Usage Examples

### Example 1: Download Specific Build

```bash
curl -O http://localhost:8000/win64/120.0.0.0.zip
```

### Example 2: Check Latest Downloads

```bash
curl http://localhost:8000/metrics | jq '.downloads.per_os'
# Output: { "linux": 21, "win64": 21 }
```

### Example 3: View Available Windows Builds

```bash
curl -s http://localhost:8000/win64/ | grep -oP '(?<=href=")[^"]*\.zip'
```

### Example 4: Restart Service

```bash
sudo systemctl restart asan-chrome-mirror
sudo journalctl -u asan-chrome-mirror -f --lines 50
```

---

## 🐛 Common Issues & Solutions

### Issue: Service won't start
**Solution:** Check logs with `sudo journalctl -u asan-chrome-mirror -n 100`

### Issue: Port 8000 already in use
**Solution:** Change `http_port` in config.yaml or find process: `sudo lsof -i :8000`

### Issue: Storage disk full
**Solution:** Check with `du -sh /storage` and adjust `min_version`/`max_version` to probe fewer versions

### Issue: Downloads not starting
**Solution:** Verify script exists: `ls -la /opt/asan-chrome-mirror/data/get_asan_chrome.py`

See DEPLOYMENT.md for comprehensive troubleshooting.

---

## 📞 Support

### For Installation Issues
See `DEPLOYMENT.md` - Detailed Installation section

### For Usage Questions
See `README.md` - Comprehensive user guide

### For API Documentation
See `README.md` - HTTP API section

### For Troubleshooting
See `DEPLOYMENT.md` - Troubleshooting section

---

## ✨ What's Next?

1. **Review** the code and configuration
2. **Test** locally: `python3 verify.py`
3. **Install** on target system: `sudo ./install.sh`
4. **Configure** as needed: `sudo nano /opt/asan-chrome-mirror/config.yaml`
5. **Start** the service: `sudo systemctl start asan-chrome-mirror`
6. **Monitor** the service: `sudo journalctl -u asan-chrome-mirror -f`

---

## 📄 License & Attribution

This project implements mirroring of official Chromium ASAN builds. See Chromium's licensing for build and source code details.

Chromium source: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/tools/get_asan_chrome/

---

## ✅ Implementation Status

All requirements have been implemented and tested:

- [x] Python 3.11+ with async architecture
- [x] Automatic version discovery and downloading
- [x] 12-hour polling scheduler
- [x] Windows (win64) and Linux build support
- [x] Sequential download behavior
- [x] SQLite persistence and tracking
- [x] HTTP server with auto-indexing
- [x] FastAPI for async web serving
- [x] Systemd service integration
- [x] Graceful shutdown handling
- [x] Comprehensive logging (file + stdout)
- [x] Health check and metrics endpoints
- [x] Exponential backoff retry logic
- [x] ZIP file validation and checksums
- [x] Installation script and documentation

**Project is production-ready for Ubuntu Server 22.04 LTS or later.**

