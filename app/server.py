"""
HTTP server module for serving downloaded builds.
Provides auto-indexed directories and file downloads.
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import aiofiles
import os

from app.config import Config
from app.database import Database, Build, DownloadStatus
from app.scheduler import Scheduler

logger = logging.getLogger(__name__)


class ManualDownloadRequest(BaseModel):
    version: str = Field(..., description="Chromium version, for example 146.0.7578.0")
    os: str = Field(..., pattern="^(win64|linux)$", description="Target operating system")


def create_app(
    config: Config,
    db: Database,
    scheduler: Optional[Scheduler] = None,
    downloader=None,
) -> FastAPI:
    """
    Create FastAPI application.
    
    Args:
        config: Application configuration.
        db: Database instance.
        scheduler: Optional scheduler instance for status endpoints.
    
    Returns:
        FastAPI application instance.
    """
    app = FastAPI(
        title="ASAN Chrome Mirror",
        description="HTTP server for ASAN Chrome builds",
        version="1.0.0"
    )
    app.state.background_tasks = set()

    def build_status_payload() -> dict:
        stale_builds = db.clear_stale_in_progress(config.in_progress_timeout_seconds)
        in_progress_builds = db.get_builds_by_status(DownloadStatus.IN_PROGRESS)
        failed_builds = db.get_builds_by_status(DownloadStatus.FAILED)
        downloader_progress = {}
        if downloader is not None and hasattr(downloader, "get_active_progress"):
            downloader_progress = {
                f"{item.get('version')}|{item.get('os')}": item
                for item in downloader.get_active_progress()
            }

        now = datetime.utcnow()

        def build_progress_item(build: Build) -> dict:
            started_at = build.timestamp or now
            elapsed_seconds = max(0, int((now - started_at).total_seconds()))
            progress_key = f"{build.version}|{build.os}"
            active_progress = downloader_progress.get(progress_key, {})
            actual_pct = active_progress.get("pct")
            estimated_pct = int(
                min(95, max(2, (elapsed_seconds / max(1, config.download_timeout_seconds)) * 100))
            )
            return {
                "version": build.version,
                "os": build.os,
                "timestamp": started_at.isoformat() if started_at else None,
                "elapsed_seconds": elapsed_seconds,
                "estimated_pct": estimated_pct,
                "progress_pct": actual_pct if actual_pct is not None else estimated_pct,
                "bytes_received": active_progress.get("bytes_received"),
                "bytes_total": active_progress.get("bytes_total"),
                "progress_message": active_progress.get("message"),
                "last_output": active_progress.get("last_output"),
                "last_error": active_progress.get("last_error"),
                "progress_state": active_progress.get("status"),
            }

        return {
            "in_progress": [build_progress_item(build) for build in in_progress_builds],
            "failed": [
                {
                    "version": build.version,
                    "os": build.os,
                    "error": build.error_message,
                    "retry_count": build.retry_count,
                    "timestamp": build.timestamp.isoformat() if build.timestamp else None,
                }
                for build in failed_builds
            ],
            "active_manual_tasks": len(app.state.background_tasks),
            "expired_stale_builds": [
                {
                    "version": build.version,
                    "os": build.os,
                    "timestamp": build.timestamp.isoformat() if build.timestamp else None,
                }
                for build in stale_builds
            ],
        }

    def track_background_task(task: asyncio.Task) -> None:
        app.state.background_tasks.add(task)

        def _cleanup(completed_task: asyncio.Task) -> None:
            app.state.background_tasks.discard(completed_task)
            try:
                completed_task.result()
            except Exception:
                logger.exception("Background download task failed")

        task.add_done_callback(_cleanup)

    async def run_manual_download(version: str, os_name: str) -> None:
        logger.info(f"Manual download requested for {version}/{os_name}")

        if downloader is None:
            logger.error("Manual download requested but downloader is unavailable")
            return

        stale_builds = db.clear_stale_in_progress(config.in_progress_timeout_seconds)
        if stale_builds:
            logger.warning(
                f"Cleared {len(stale_builds)} stale in-progress build(s) before manual retry for {version}/{os_name}"
            )

        existing = db.get_build(version, os_name)
        if existing and existing.status == DownloadStatus.SUCCESS:
            logger.info(f"Manual download skipped because build already exists: {version}/{os_name}")
            return

        # Always reset IN_PROGRESS to allow manual retry (handles stale or hung state)
        if existing and existing.status == DownloadStatus.IN_PROGRESS:
            logger.info(
                f"Resetting in-progress state for manual retry: {version}/{os_name}"
            )
            db.mark_failed(version, os_name, "Reset for manual retry", retry_count=0)

        db.insert_build(
            Build(
                version=version,
                os=os_name,
                filepath=downloader._get_output_path(version, os_name),
                status=DownloadStatus.IN_PROGRESS,
            )
        )

        logger.info(f"Starting manual download task for {version}/{os_name}")
        result = await asyncio.to_thread(downloader.download, version, os_name)

        if result.success:
            db.mark_success(result.version, result.os, result.checksum)
            logger.info(f"Manual download completed successfully for {version}/{os_name}")
        else:
            db.mark_failed(result.version, result.os, result.error or "Unknown error", retry_count=1)
            logger.error(f"Manual download failed for {version}/{os_name}: {result.error}")
    
    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        """
        Root endpoint with dashboard.
        
        Returns:
            HTML dashboard with build listings.
        """
        # Get file counts
        win64_dir = config.storage_dir / "win64"
        linux_dir = config.storage_dir / "linux"
        
        win64_count = len([f for f in win64_dir.iterdir() if f.is_file()]) if win64_dir.exists() else 0
        linux_count = len([f for f in linux_dir.iterdir() if f.is_file()]) if linux_dir.exists() else 0
        
        # Get status snapshot for progress display
        status_snapshot = build_status_payload()
        in_progress = status_snapshot.get("in_progress", [])
        failed = status_snapshot.get("failed", [])
        
        # Generate initial progress content
        progress_section = ""
        if in_progress:
            progress_section += '<div style="margin-bottom: 20px;"><strong>In Progress:</strong><br>'
            for item in in_progress:
                progress_section += f'<span style="display: inline-block; background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; margin: 2px; font-size: 0.9em;">{item["version"]} ({item["os"]})</span>'
            progress_section += '</div>'

        if failed:
            progress_section += '<div style="margin-top: 15px;"><strong>Failed (Retrying):</strong><br>'
            for item in failed:
                progress_section += f'<span style="display: inline-block; background: #f44336; color: white; padding: 4px 8px; border-radius: 4px; margin: 2px; font-size: 0.9em;">{item["version"]} ({item["os"]}) - {item.get("retry_count", 0)} retries</span>'
            progress_section += '</div>'

        if not progress_section:
            progress_section = '<p style="color:#666;">No downloads are currently in progress.</p>'
        
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="30">
            <title>ASAN Chrome Mirror</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 40px 20px;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .header {
                    text-align: center;
                    color: white;
                    margin-bottom: 50px;
                }
                .header h1 {
                    font-size: 2.5em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                }
                .header p {
                    font-size: 1.1em;
                    opacity: 0.95;
                }
                .grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                    gap: 30px;
                    margin-bottom: 40px;
                }
                .card {
                    background: white;
                    border-radius: 12px;
                    padding: 30px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    transition: transform 0.3s, box-shadow 0.3s;
                }
                .card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 15px 50px rgba(0,0,0,0.3);
                }
                .card-title {
                    font-size: 1.5em;
                    margin-bottom: 15px;
                    color: #333;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .card-icon {
                    font-size: 1.8em;
                }
                .card-count {
                    font-size: 2em;
                    font-weight: bold;
                    color: #667eea;
                    margin-bottom: 20px;
                }
                .card-description {
                    color: #666;
                    margin-bottom: 20px;
                    line-height: 1.5;
                }
                .btn {
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    transition: transform 0.2s, box-shadow 0.2s;
                    font-weight: 600;
                    border: none;
                    cursor: pointer;
                    font-size: 1em;
                }
                .btn:hover {
                    transform: scale(1.05);
                    box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
                }
                .stats {
                    background: white;
                    border-radius: 12px;
                    padding: 30px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    margin-top: 30px;
                }
                .stats h2 {
                    margin-bottom: 20px;
                    color: #333;
                }
                .stat-row {
                    display: flex;
                    justify-content: space-between;
                    padding: 10px 0;
                    border-bottom: 1px solid #eee;
                }
                .stat-row:last-child {
                    border-bottom: none;
                }
                .stat-label {
                    color: #666;
                }
                .stat-value {
                    color: #333;
                    font-weight: 600;
                }
                .progress-list {
                    display: grid;
                    gap: 16px;
                }
                .progress-card {
                    border: 1px solid #ececec;
                    border-radius: 10px;
                    padding: 16px;
                    background: #fafafa;
                }
                .progress-meta {
                    display: flex;
                    justify-content: space-between;
                    gap: 12px;
                    flex-wrap: wrap;
                    margin-bottom: 10px;
                    color: #555;
                    font-size: 0.95em;
                }
                .progress-bar-track {
                    width: 100%;
                    height: 12px;
                    background: #e7e7e7;
                    border-radius: 999px;
                    overflow: hidden;
                    position: relative;
                }
                .progress-bar-fill {
                    height: 100%;
                    background: linear-gradient(90deg, #4CAF50 0%, #7ed957 100%);
                    border-radius: 999px;
                    transition: width 0.5s ease;
                    width: 0%;
                }
                .progress-bar-indeterminate {
                    position: relative;
                    overflow: hidden;
                }
                .progress-bar-indeterminate::after {
                    content: '';
                    position: absolute;
                    inset: 0;
                    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.45) 50%, transparent 100%);
                    animation: slide 1.1s infinite;
                    transform: translateX(-100%);
                }
                @keyframes slide {
                    from { transform: translateX(-100%); }
                    to { transform: translateX(100%); }
                }
                a {
                    color: #667eea;
                    text-decoration: none;
                }
                a:hover {
                    text-decoration: underline;
                }
                @media (max-width: 768px) {
                    .grid {
                        grid-template-columns: 1fr;
                    }
                    .header h1 {
                        font-size: 2em;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🌐 ASAN Chrome Mirror</h1>
                    <p>Download ASAN-instrumented Chromium builds for your platform</p>
                </div>
                
                <div class="grid">
                    <div class="card">
                        <div class="card-title">
                            <span class="card-icon">🪟</span>
                            Windows (x64)
                        </div>
                        <div class="card-count">""" + str(win64_count) + """ builds</div>
                        <div class="card-description">
                            Download ASAN-instrumented Chromium builds for Windows x64 architecture.
                        </div>
                        <a href="/win64/" class="btn">Browse Windows Builds →</a>
                    </div>
                    
                    <div class="card">
                        <div class="card-title">
                            <span class="card-icon">🐧</span>
                            Linux (x64)
                        </div>
                        <div class="card-count">""" + str(linux_count) + """ builds</div>
                        <div class="card-description">
                            Download ASAN-instrumented Chromium builds for Linux x64 architecture.
                        </div>
                        <a href="/linux/" class="btn">Browse Linux Builds →</a>
                    </div>
                </div>

                <div class="stats">
                    <h2>Automatic Probing</h2>
                    <p style="color: #666; margin-bottom: 18px; line-height: 1.5;">
                        Enable automatic probing to have the service discover and download new ASAN Chromium versions on every scheduled check cycle (every 12 hours). When disabled, only manual downloads are available.
                    </p>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <button id="toggle-auto-probing" class="btn" style="background: #f44336; padding: 12px 30px; height: auto;" data-enabled="false">
                            <span>🔴 Auto-Probing: OFF</span>
                        </button>
                        <span id="toggle-status" style="color: #999; font-size: 0.95em;">Initializing...</span>
                    </div>
                </div>
                
                <div class="stats">
                    <h2>Manual Download</h2>
                    <p style="color: #666; margin-bottom: 18px; line-height: 1.5;">
                        Enter a Chromium version and OS to start a separate get_asan_chrome.py download in the background.
                    </p>
                    <form id="manual-download-form" style="display: grid; grid-template-columns: 2fr 1fr auto; gap: 12px; align-items: end;">
                        <label style="display: block;">
                            <span style="display:block; margin-bottom:8px; color:#666; font-weight:600;">Version</span>
                            <input id="version-input" name="version" type="text" placeholder="146.0.7578.0" required style="width:100%; padding:12px 14px; border:1px solid #ddd; border-radius:8px; font-size:1rem;">
                        </label>
                        <label style="display: block;">
                            <span style="display:block; margin-bottom:8px; color:#666; font-weight:600;">OS</span>
                            <select id="os-input" name="os" style="width:100%; padding:12px 14px; border:1px solid #ddd; border-radius:8px; font-size:1rem; background:white;">
                                <option value="win64">Windows (win64)</option>
                                <option value="linux">Linux</option>
                            </select>
                        </label>
                        <button class="btn" type="submit" style="height: 48px; white-space: nowrap;">Start Download</button>
                    </form>
                    <div id="manual-download-status" style="margin-top: 14px; color: #333; font-weight: 600;"></div>
                </div>
                
                <div class="stats" id="progress-panel">
                    <h2>⏳ Download Progress</h2>
                    <div id="progress-content">
                        """ + progress_section + """
                    </div>
                </div>
                
                <div class="stats">
                    <h2>Service Status</h2>
                    <div class="stat-row">
                        <span class="stat-label">Status</span>
                        <span class="stat-value">✓ Operational</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Timestamp</span>
                        <span class="stat-value">""" + datetime.utcnow().isoformat() + """</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Total Builds</span>
                        <span class="stat-value">""" + str(win64_count + linux_count) + """</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">API Endpoints</span>
                        <span class="stat-value"><a href="/docs">/docs</a> | <a href="/health">/health</a> | <a href="/metrics">/metrics</a></span>
                    </div>
                    <div style="margin-top: 12px; display:flex; gap:12px; align-items:center;">
                        <button id="run-check-now" class="btn" style="background:#2196F3; padding:10px 18px;">▶ Run Check Now</button>
                        <span id="run-check-status" style="color:#666; font-size:0.95em;">No manual run requested</span>
                    </div>
                </div>
            </div>
            <script>
                const toggleBtn = document.getElementById('toggle-auto-probing');
                const toggleStatus = document.getElementById('toggle-status');
                const manualDownloadForm = document.getElementById('manual-download-form');
                const manualDownloadStatus = document.getElementById('manual-download-status');
                const progressContent = document.getElementById('progress-content');

                async function loadAutoProbeStatus() {
                    try {
                        const response = await fetch('/api/config/auto-probing');
                        if (!response.ok) throw new Error('Failed to load status');
                        const data = await response.json();
                        updateToggleUI(data.enable_auto_probing);
                    } catch (error) {
                        console.error(error);
                        toggleStatus.textContent = 'Error loading status';
                    }
                }

                function updateToggleUI(enabled) {
                    toggleBtn.dataset.enabled = String(enabled);
                    if (enabled) {
                        toggleBtn.style.background = '#4CAF50';
                        toggleBtn.innerHTML = '<span>🟢 Auto-Probing: ON</span>';
                        toggleStatus.textContent = 'Service will automatically probe and download on next check cycle';
                    } else {
                        toggleBtn.style.background = '#f44336';
                        toggleBtn.innerHTML = '<span>🔴 Auto-Probing: OFF</span>';
                        toggleStatus.textContent = 'Only manual downloads are enabled';
                    }
                }

                toggleBtn.addEventListener('click', async () => {
                    const currentState = toggleBtn.dataset.enabled === 'true';
                    const newState = !currentState;
                    toggleBtn.disabled = true;
                    try {
                        const response = await fetch('/api/config/auto-probing', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ enable: newState })
                        });
                        if (!response.ok) throw new Error('Failed to update status');
                        const data = await response.json();
                        updateToggleUI(data.enable_auto_probing);
                    } catch (error) {
                        console.error(error);
                        toggleStatus.textContent = 'Error updating status';
                    } finally {
                        toggleBtn.disabled = false;
                    }
                });

                loadAutoProbeStatus();

                // Run Check Now button
                const runCheckBtn = document.getElementById('run-check-now');
                const runCheckStatus = document.getElementById('run-check-status');
                if (runCheckBtn) {
                    runCheckBtn.addEventListener('click', async () => {
                        runCheckBtn.disabled = true;
                        runCheckStatus.textContent = 'Scheduling check...';
                        try {
                            const resp = await fetch('/api/scheduler/run-now', { method: 'POST' });
                            const data = await resp.json();
                            if (!resp.ok) throw new Error(data.detail || data.message || 'Failed to schedule');
                            runCheckStatus.textContent = data.message || 'Check scheduled';
                            await refreshStatus();
                        } catch (err) {
                            console.error(err);
                            runCheckStatus.textContent = err.message || 'Error scheduling check';
                        } finally {
                            runCheckBtn.disabled = false;
                            setTimeout(() => { runCheckStatus.textContent = 'No manual run requested'; }, 8000);
                        }
                    });
                }

                function escapeHtml(value) {
                    return String(value)
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#39;');
                }

                function renderProgress(snapshot) {
                    const inProgress = snapshot.in_progress || [];
                    const failed = snapshot.failed || [];
                    const expiredStaleBuilds = snapshot.expired_stale_builds || [];

                    if (!inProgress.length && !failed.length) {
                        progressContent.innerHTML = '<p style="color:#666;">No downloads are currently in progress.</p>';
                    } else {
                        let html = '';

                        if (inProgress.length) {
                            html += '<div style="margin-bottom: 20px;"><strong>In Progress:</strong></div><div class="progress-list">';
                            for (const item of inProgress) {
                                        const pct = Number(item.progress_pct || item.estimated_pct || 0);
                                const elapsed = Number(item.elapsed_seconds || 0);
                                        const message = item.progress_message || '';
                                        const bytesText = (item.bytes_received != null && item.bytes_total != null)
                                            ? `${escapeHtml(item.bytes_received)} / ${escapeHtml(item.bytes_total)} bytes`
                                            : 'Waiting for progress data';
                                html += `
                                    <div class="progress-card">
                                        <div class="progress-meta">
                                            <span><strong>${escapeHtml(item.version)}</strong> (${escapeHtml(item.os)})</span>
                                            <span>${escapeHtml(pct)}%</span>
                                        </div>
                                        <div class="progress-bar-track progress-bar-indeterminate">
                                            <div class="progress-bar-fill" style="width: ${escapeHtml(pct)}%"></div>
                                        </div>
                                        <div style="margin-top: 8px; color: #666; font-size: 0.9em;">
                                                    ${escapeHtml(bytesText)}. Running for ${escapeHtml(elapsed)}s.
                                        </div>
                                                ${message ? `<div style="margin-top: 6px; color: #444; font-size: 0.9em;">${escapeHtml(message)}</div>` : ''}
                                    </div>
                                `;
                            }
                            html += '</div>';
                        }

                        if (failed.length) {
                            html += '<div style="margin-top: 15px;"><strong>Failed (Retrying):</strong><br>';
                            for (const item of failed) {
                                html += `<span style="display: inline-block; background: #f44336; color: white; padding: 4px 8px; border-radius: 4px; margin: 2px; font-size: 0.9em;">${escapeHtml(item.version)} (${escapeHtml(item.os)}) - ${escapeHtml(item.retry_count)} retries</span>`;
                            }
                            html += '</div>';
                        }

                        progressContent.innerHTML = html || '<p style="color:#666;">No downloads are currently in progress.</p>';
                    }

                    if (snapshot.active_manual_tasks) {
                        progressContent.innerHTML += `<div style="margin-top: 15px; color: #666;"><strong>Active manual tasks:</strong> ${escapeHtml(snapshot.active_manual_tasks)}</div>`;
                    }

                    if (expiredStaleBuilds.length) {
                        const staleNote = `<div style="margin-top: 15px; padding: 12px; border-left: 4px solid #ff9800; background: #fff8e1; color: #6b4e00;"><strong>Recovered stale download(s):</strong> ${escapeHtml(expiredStaleBuilds.length)} job(s) looked stuck and were marked failed so you can retry them.</div>`;
                        progressContent.insertAdjacentHTML('afterbegin', staleNote);
                    }
                }

                async function refreshStatus() {
                    try {
                        const response = await fetch('/api/status');
                        if (!response.ok) {
                            throw new Error('Failed to load status');
                        }

                        const snapshot = await response.json();
                        renderProgress(snapshot);
                    } catch (error) {
                        console.error(error);
                    }
                }

                manualDownloadForm.addEventListener('submit', async (event) => {
                    event.preventDefault();

                    const version = document.getElementById('version-input').value.trim();
                    const os = document.getElementById('os-input').value;

                    manualDownloadStatus.textContent = 'Starting download...';

                    try {
                        const response = await fetch('/api/download', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ version, os })
                        });

                        const payload = await response.json();

                        if (!response.ok) {
                            throw new Error(payload.detail || 'Failed to start download');
                        }

                        manualDownloadStatus.textContent = payload.message || `Download queued for ${version} (${os})`;
                        await refreshStatus();
                    } catch (error) {
                        manualDownloadStatus.textContent = error.message;
                        await refreshStatus();
                    }
                });

                refreshStatus();
                setInterval(refreshStatus, 5000);
                setInterval(loadAutoProbeStatus, 30000);
            </script>
        </body>
        </html>
        """
        return html
    
    @app.get("/health", response_class=JSONResponse)
    async def health() -> dict:
        """
        Health check endpoint.
        
        Returns:
            JSON with health status.
        """
        return {
            "status": "ok",
            "service": "ASAN Chrome Mirror",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/metrics", response_class=JSONResponse)
    async def metrics() -> dict:
        """
        Metrics endpoint with download statistics.
        
        Returns:
            JSON with statistics.
        """
        try:
            stats = db.get_stats()
            
            scheduler_status = {}
            if scheduler:
                scheduler_status = scheduler.get_status()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "downloads": {
                    "total_count": stats['total_downloads'],
                    "total_size_bytes": stats['total_size_bytes'],
                    "per_os": stats['per_os']
                },
                "status": build_status_payload(),
                "scheduler": scheduler_status
            }
        except Exception as e:
            logger.error(f"Error generating metrics: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate metrics")

    @app.get("/api/status", response_class=JSONResponse)
    async def api_status() -> dict:
        """Return live download status for dashboard polling."""
        snapshot = build_status_payload()
        if scheduler:
            snapshot["scheduler"] = scheduler.get_status()
        return snapshot

    @app.post("/api/download", response_class=JSONResponse)
    async def start_manual_download(request: ManualDownloadRequest) -> dict:
        """Start a manual download in the background."""
        if downloader is None:
            raise HTTPException(status_code=503, detail="Downloader is not available")

        existing = db.get_build(request.version, request.os)
        if existing and existing.status == DownloadStatus.IN_PROGRESS:
            raise HTTPException(status_code=409, detail="That download is already in progress")

        if existing and existing.status == DownloadStatus.SUCCESS:
            raise HTTPException(status_code=409, detail="That build already exists locally")

        db.insert_build(Build(
            version=request.version,
            os=request.os,
            filepath=downloader._get_output_path(request.version, request.os),
            status=DownloadStatus.IN_PROGRESS
        ))

        task = asyncio.create_task(run_manual_download(request.version, request.os))
        track_background_task(task)

        return {
            "status": "queued",
            "message": f"Queued {request.version} for {request.os}",
            "version": request.version,
            "os": request.os
        }
    
    @app.get("/api/config/auto-probing", response_class=JSONResponse)
    async def get_auto_probing_status() -> dict:
        """Get the current auto-probing toggle state."""
        return {
            "enable_auto_probing": config.enable_auto_probing
        }
    
    @app.post("/api/config/auto-probing", response_class=JSONResponse)
    async def set_auto_probing_status(payload: dict) -> dict:
        """Set the auto-probing toggle state."""
        enable = payload.get("enable", False)
        config.enable_auto_probing = enable
        logger.info(f"Auto-probing toggled to: {enable}")
        return {
            "enable_auto_probing": config.enable_auto_probing,
            "message": f"Auto-probing is now {('enabled' if enable else 'disabled')}"
        }
    
    @app.post("/api/scheduler/run-now", response_class=JSONResponse)
    async def trigger_scheduler_run() -> dict:
        """Trigger the scheduler to run a check cycle immediately."""
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler is not available")

        # Schedule the check to run in background
        task = asyncio.create_task(scheduler.run_check())
        track_background_task(task)
        logger.info("Manual scheduler run requested via API")
        return {"status": "queued", "message": "Scheduled check cycle started"}

    def generate_directory_listing(directory: Path, url_prefix: str) -> str:
        """
        Generate HTML directory listing.
        
        Args:
            directory: Directory path to list.
            url_prefix: URL prefix for links.
        
        Returns:
            HTML string.
        """
        if not directory.exists():
            return "<html><body><h1>Directory not found</h1></body></html>"
        
        files = []
        try:
            for item in sorted(directory.iterdir()):
                if item.name.startswith('.'):
                    continue
                
                stat = item.stat()
                size_bytes = stat.st_size
                
                # Format size
                if size_bytes > 1024**3:
                    size_str = f"{size_bytes / (1024**3):.2f} GB"
                elif size_bytes > 1024**2:
                    size_str = f"{size_bytes / (1024**2):.2f} MB"
                else:
                    size_str = f"{size_bytes / 1024:.2f} KB"
                
                # Format modification time
                mtime = datetime.fromtimestamp(stat.st_mtime)
                mtime_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
                
                url = f"{url_prefix}{item.name}"
                files.append({
                    "name": item.name,
                    "url": url,
                    "size": size_str,
                    "modified": mtime_str
                })
        except Exception as e:
            logger.error(f"Error listing directory {directory}: {e}")
        
        # Generate HTML
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>ASAN Chrome Mirror</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #4CAF50; color: white; }
                tr:nth-child(even) { background-color: #f2f2f2; }
                a { color: #2196F3; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>ASAN Chrome Builds</h1>
            <p>Directory: <code>""" + str(directory) + """</code></p>
            <table>
                <tr>
                    <th>File</th>
                    <th>Size</th>
                    <th>Modified</th>
                </tr>
        """
        
        for file_info in files:
            html += f"""
                <tr>
                    <td><a href="{file_info['url']}">{file_info['name']}</a></td>
                    <td>{file_info['size']}</td>
                    <td>{file_info['modified']}</td>
                </tr>
            """
        
        html += """
            </table>
            <hr>
            <p><a href="/">Back to root</a></p>
        </body>
        </html>
        """
        
        return html
    
    @app.get("/win64/", response_class=HTMLResponse)
    async def list_win64() -> str:
        """Windows builds directory listing."""
        win64_dir = config.storage_dir / "win64"
        return generate_directory_listing(win64_dir, "/win64/")
    
    @app.get("/linux/", response_class=HTMLResponse)
    async def list_linux() -> str:
        """Linux builds directory listing."""
        linux_dir = config.storage_dir / "linux"
        return generate_directory_listing(linux_dir, "/linux/")
    
    @app.get("/win64/{file_name}")
    async def download_win64(file_name: str) -> FileResponse:
        """Download Windows build."""
        file_path = config.storage_dir / "win64" / file_name
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not str(file_path).startswith(str(config.storage_dir / "win64")):
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.info(f"Serving file: {file_path}")
        
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type="application/zip"
        )
    
    @app.get("/linux/{file_name}")
    async def download_linux(file_name: str) -> FileResponse:
        """Download Linux build."""
        file_path = config.storage_dir / "linux" / file_name
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not str(file_path).startswith(str(config.storage_dir / "linux")):
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.info(f"Serving file: {file_path}")
        
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type="application/zip"
        )
    
    return app
