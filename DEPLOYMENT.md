# ASAN Chrome Mirror - Deployment Guide

Complete step-by-step guide for deploying the ASAN Chrome Mirror service in a production environment.

## Quick Deployment

For the fastest setup, run:

```bash
cd /path/to/asan-chrome-mirror
sudo ./install.sh
sudo systemctl start asan-chrome-mirror
sudo systemctl status asan-chrome-mirror
```

Then access the HTTP server:
```bash
curl http://localhost:8000/health
```

## Detailed Deployment Steps

### 1. Prerequisites

Verify your system meets the requirements:

```bash
# Check Python version (need 3.11+)
python3 --version

# Check available disk space (need ~200GB+)
df -h /storage 2>/dev/null || df -h /

# Check Internet connectivity
ping -c 1 chromium.googlesource.com
```

### 2. System Preparation

Create storage directory with appropriate permissions:

```bash
sudo mkdir -p /storage/{win64,linux}
sudo chmod 755 /storage
ls -la /storage/
```

### 3. Installation

#### Option A: Automated Installation (Recommended)

```bash
# Download or extract project
cd /tmp
git clone <repository> asan-chrome-mirror
cd asan-chrome-mirror

# Run installer
sudo ./install.sh

# Verify installation
ls -la /opt/asan-chrome-mirror/
ls -la /etc/systemd/system/asan-chrome-mirror.service
```

#### Option B: Manual Installation

```bash
# Create system user
sudo groupadd --system asan-mirror
sudo useradd --system --gid asan-mirror \
    --shell /usr/sbin/nologin \
    --home-dir /var/lib/asan-mirror asan-mirror

# Create directories
sudo mkdir -p /opt/asan-chrome-mirror
sudo mkdir -p /storage/win64 /storage/linux
sudo mkdir -p /var/log/asan-chrome-mirror

# Copy files
sudo cp -r app requirements.txt config.yaml.example /opt/asan-chrome-mirror/
sudo cp systemd/asan-chrome-mirror.service /etc/systemd/system/

# Set permissions
sudo chown -R asan-mirror:asan-mirror \
    /opt/asan-chrome-mirror \
    /storage \
    /var/log/asan-chrome-mirror

# Install Python dependencies
cd /opt/asan-chrome-mirror
sudo python3 -m pip install -r requirements.txt

# Enable systemd service
sudo systemctl daemon-reload
sudo systemctl enable asan-chrome-mirror.service
```

### 4. Configuration

Copy and customize the configuration:

```bash
sudo cp /opt/asan-chrome-mirror/config.yaml.example \
        /opt/asan-chrome-mirror/config.yaml

sudo nano /opt/asan-chrome-mirror/config.yaml
```

Key configuration options to review:

```yaml
# Storage location - ensure ~200GB+ available
storage_dir: /storage

# Logging
log_dir: /var/log/asan-chrome-mirror
logging_level: INFO

# Check interval (12 hours = 43200 seconds)
check_interval_seconds: 43200

# Version range to probe
min_version: 100
max_version: 200

# HTTP server
http_host: 0.0.0.0
http_port: 8000
```

### 5. Service Management

#### Start Service

```bash
sudo systemctl start asan-chrome-mirror
```

#### Check Status

```bash
sudo systemctl status asan-chrome-mirror
sudo journalctl -u asan-chrome-mirror -n 50
```

#### View Live Logs

```bash
# Via systemd journal
sudo journalctl -u asan-chrome-mirror -f

# Via log file
tail -f /var/log/asan-chrome-mirror/asan-chrome-mirror.log
```

#### Stop Service

```bash
sudo systemctl stop asan-chrome-mirror
```

#### Restart Service

```bash
sudo systemctl restart asan-chrome-mirror
```

### 6. Verification

Test that everything is working:

```bash
# 1. Service is running
sudo systemctl is-active asan-chrome-mirror

# 2. HTTP server is responding
curl http://localhost:8000/health

# 3. Directories are created
ls -la /storage/{win64,linux}

# 4. Logs are being written
tail -5 /var/log/asan-chrome-mirror/asan-chrome-mirror.log

# 5. Database is created
sqlite3 /opt/asan-chrome-mirror/data/builds.db ".tables"
```

## Monitoring & Maintenance

### Health Checks

```bash
# HTTP health check
curl http://localhost:8000/health

# Comprehensive metrics
curl http://localhost:8000/metrics | jq

# Service status
sudo systemctl status asan-chrome-mirror

# Recent log entries
sudo journalctl -u asan-chrome-mirror -n 20
```

### Disk Space Management

Monitor and manage disk usage:

```bash
# Check total usage
du -sh /storage

# Per-OS breakdown
du -sh /storage/win64 /storage/linux

# List largest files
find /storage -type f -exec ls -lhS {} + | head -20

# Cleanup old temporary files (if needed)
sudo find /storage/temp -type f -mtime +7 -delete
```

### Database Maintenance

Check database health:

```bash
# View download statistics
sqlite3 /opt/asan-chrome-mirror/data/builds.db \
  "SELECT os, COUNT(*) as count, SUM(LENGTH(filepath)) as total_size 
   FROM builds WHERE status='success' GROUP BY os;"

# List recent downloads
sqlite3 /opt/asan-chrome-mirror/data/builds.db \
  "SELECT version, os, timestamp FROM builds 
   ORDER BY timestamp DESC LIMIT 10;"

# Count failed downloads
sqlite3 /opt/asan-chrome-mirror/data/builds.db \
  "SELECT COUNT(*) FROM builds WHERE status='failed';"
```

### Log Management

View and manage logs:

```bash
# View entire log
cat /var/log/asan-chrome-mirror/asan-chrome-mirror.log

# Search for errors
grep ERROR /var/log/asan-chrome-mirror/asan-chrome-mirror.log

# View by time range
journalctl -u asan-chrome-mirror --since "2024-05-07 10:00:00" \
           --until "2024-05-07 12:00:00"

# Real-time monitoring
sudo journalctl -u asan-chrome-mirror -f --lines 50
```

## Advanced Configuration

### Environment Variable Overrides

Set environment variables to override config.yaml:

```bash
export ASAN_MIN_VERSION=110
export ASAN_MAX_VERSION=210
export ASAN_CHECK_INTERVAL_SECONDS=86400  # 24 hours
export ASAN_LOGGING_LEVEL=DEBUG

sudo systemctl restart asan-chrome-mirror
```

### Systemd Service Customization

Edit the service file for custom settings:

```bash
sudo nano /etc/systemd/system/asan-chrome-mirror.service
```

Common customizations:

```ini
# Increase memory limit
MemoryLimit=4G

# Add environment variables
Environment="ASAN_LOGGING_LEVEL=DEBUG"

# Change nice/priority
Nice=-5

# Add restart conditions
RestartForceExitStatus=1 6
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart asan-chrome-mirror
```

### Reverse Proxy Setup (nginx)

For external access with authentication and HTTPS:

```nginx
server {
    listen 443 ssl http2;
    server_name asan-mirror.example.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    auth_basic "ASAN Chrome Mirror";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Large file handling
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
}
```

Then enable:

```bash
sudo ln -s /etc/nginx/sites-available/asan-mirror \
           /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u asan-chrome-mirror -n 100

# Verify permissions
ls -la /opt/asan-chrome-mirror
ls -la /storage
ls -la /var/log/asan-chrome-mirror

# Test manually
cd /opt/asan-chrome-mirror
sudo -u asan-mirror python3 -m app.main

# Check port availability
sudo ss -tlnp | grep 8000
```

### HTTP Server Not Responding

```bash
# Check if service is running
ps aux | grep "app.main"

# Check port
sudo ss -tlnp | grep 8000

# Test connectivity
nc -zv localhost 8000

# Try connecting
curl -v http://localhost:8000/health
```

### Downloads Not Starting

```bash
# Check scheduler logs
sudo journalctl -u asan-chrome-mirror | grep -i "scheduler\|download\|probe"

# Verify script exists
ls -la /opt/asan-chrome-mirror/data/get_asan_chrome.py

# Check network connectivity
wget -q -O /dev/null https://chromium.googlesource.com/chromium/src

# Check database
sqlite3 /opt/asan-chrome-mirror/data/builds.db "SELECT COUNT(*) FROM builds;"
```

### High Disk Usage

```bash
# Find large files
find /storage -type f -size +1G -exec ls -lh {} +

# Check for duplicates
find /storage -name "*.zip" -exec md5sum {} + | sort | uniq -d -w 32

# Monitor in real-time
watch -n 5 'du -sh /storage'
```

## Backup & Recovery

### Backup Database

```bash
# Manual backup
sudo cp /opt/asan-chrome-mirror/data/builds.db \
        /opt/asan-chrome-mirror/data/builds.db.backup

# Automated daily backup
sudo crontab -e
# Add: 0 2 * * * cp /opt/asan-chrome-mirror/data/builds.db /opt/asan-chrome-mirror/data/builds.db.$(date +\%Y\%m\%d)
```

### Restore From Backup

```bash
sudo systemctl stop asan-chrome-mirror

sudo cp /opt/asan-chrome-mirror/data/builds.db.backup \
        /opt/asan-chrome-mirror/data/builds.db

sudo chown asan-mirror:asan-mirror /opt/asan-chrome-mirror/data/builds.db

sudo systemctl start asan-chrome-mirror
```

## Performance Tuning

### Increase Download Concurrency

Currently downloads are sequential by design. To change to parallel downloads (edit `app/scheduler.py`):

```python
# Run win64 and linux downloads in parallel
await asyncio.gather(
    self._probe_and_download("win64"),
    self._probe_and_download("linux")
)
```

### Optimize Systemd Service

For systems with limited resources:

```ini
# Reduce CPU usage
CPUQuota=50%

# Reduce memory
MemoryLimit=1G

# Lower priority
Nice=10
```

### Network Optimization

```bash
# Check network MTU
ip link show | grep mtu

# Increase buffer sizes (if needed)
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
```

## Uninstallation

Complete removal of the service:

```bash
# Stop service
sudo systemctl stop asan-chrome-mirror

# Disable service
sudo systemctl disable asan-chrome-mirror

# Remove systemd service file
sudo rm /etc/systemd/system/asan-chrome-mirror.service
sudo systemctl daemon-reload

# Remove application directory
sudo rm -r /opt/asan-chrome-mirror

# Remove system user
sudo userdel asan-mirror
sudo groupdel asan-mirror

# Remove storage (optional - preserves data if not run)
# sudo rm -r /storage

# Remove log directory (optional)
# sudo rm -r /var/log/asan-chrome-mirror
```

## Support

For issues, check:
1. [README.md](README.md) - General documentation
2. Service logs: `sudo journalctl -u asan-chrome-mirror -f`
3. Application logs: `tail -f /var/log/asan-chrome-mirror/asan-chrome-mirror.log`
4. Chromium build issues: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/tools/get_asan_chrome/
