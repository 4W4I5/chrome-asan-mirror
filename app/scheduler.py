"""
Scheduler module for periodic checks and downloads.
Runs async tasks for polling every 12 hours.
"""

import logging
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
import signal

from app.database import Database, DownloadStatus
from app.updater import Updater
from app.downloader import Downloader
from app.config import Config

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages periodic downloads and maintenance tasks."""
    
    def __init__(self, config: Config, db: Database, updater: Updater, downloader: Downloader):
        """
        Initialize scheduler.
        
        Args:
            config: Application configuration.
            db: Database instance.
            updater: Updater instance.
            downloader: Downloader instance.
        """
        self.config = config
        self.db = db
        self.updater = updater
        self.downloader = downloader
        self._shutdown_event = asyncio.Event()
        self._last_check: Optional[datetime] = None
        self._next_check: Optional[datetime] = None
    
    def request_shutdown(self) -> None:
        """Signal the scheduler to shut down gracefully."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()
    
    async def _check_shutdown(self) -> bool:
        """
        Check if shutdown was requested.
        
        Returns:
            True if shutdown requested, False otherwise.
        """
        return self._shutdown_event.is_set()
    
    async def _update_script(self) -> bool:
        """
        Update get_asan_chrome.py script.
        
        Returns:
            True if update was performed or script exists, False on error.
        """
        try:
            logger.info("Checking for script updates...")
            updated = self.updater.fetch_latest()
            if updated:
                logger.info("✓ Script was updated from Chromium source")
            else:
                logger.info("✓ Script is already up-to-date")
            
            script_exists = self.updater.verify_script_exists()
            if not script_exists:
                logger.error("✗ Script verification failed - file not found or not executable")
                return False
            
            logger.info(f"✓ Script verified at {self.updater.script_path}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to update script: {e}", exc_info=True)
            return False
    
    async def _cleanup_temp_files(self) -> None:
        """Clean up temporary files."""
        try:
            temp_dir = self.config.storage_dir / "temp"
            if temp_dir.exists():
                logger.info("Cleaning up temporary files...")
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info("Temporary files cleaned")
        except Exception as e:
            logger.error(f"Error cleaning temporary files: {e}")
    
    async def _log_statistics(self) -> None:
        """Log download statistics."""
        try:
            stats = self.db.get_stats()
            logger.info(
                f"Download statistics: {stats['total_downloads']} builds, "
                f"{stats['total_size_bytes'] / (1024**3):.2f}GB total, "
                f"per-OS: {stats['per_os']}"
            )
        except Exception as e:
            logger.error(f"Error logging statistics: {e}")
    
    async def run_check(self) -> None:
        """
        Run a single check cycle:
        1. Update script
        2. Clean temp files
        3. Log statistics
        """
        logger.info("=" * 60)
        logger.info("Starting check cycle")
        logger.info("=" * 60)
        logger.info(f"Storage: {self.config.storage_dir}")
        logger.info(f"Data: {self.config.data_dir}")
        
        self._last_check = datetime.utcnow()
        
        try:
            # Step 1: Update script
            logger.info("STEP 1: Updating script...")
            if not await self._update_script():
                logger.error("✗ Script update failed, skipping downloads")
                return
            
            # Verify script is actually executable
            import os
            script_path = self.updater.script_path
            logger.info(f"✓ Script path: {script_path}")
            logger.info(f"✓ Script exists: {script_path.exists()}")
            logger.info(f"✓ Script is executable: {os.access(script_path, os.X_OK)}")
            logger.info(f"✓ Script size: {script_path.stat().st_size if script_path.exists() else 'N/A'} bytes")
            
            logger.info("Automatic probing/downloads are disabled; dashboard downloads only")
            
            # Step 2: Clean temp files
            await self._cleanup_temp_files()
            
            # Step 3: Log statistics
            await self._log_statistics()
            
            logger.info("=" * 60)
            logger.info("Check cycle completed: maintenance-only run")
            logger.info("=" * 60)
        
        except Exception as e:
            logger.error(f"Error during check cycle: {e}", exc_info=True)
    
    async def run_scheduler(self) -> None:
        """
        Run the main scheduler loop.
        Checks every 12 hours (or configured interval).
        """
        logger.info(f"Scheduler started with {self.config.check_interval_seconds}s interval")
        
        # Run first check immediately
        await self.run_check()
        
        # Main loop
        while not await self._check_shutdown():
            # Calculate next check time
            check_interval = self.config.check_interval_seconds
            self._next_check = datetime.utcnow().timestamp() + check_interval
            
            logger.info(f"Next check in {check_interval}s")
            
            try:
                # Wait for interval or shutdown
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=check_interval
                )
                # Shutdown requested
                break
            except asyncio.TimeoutError:
                # Time for next check
                await self.run_check()
        
        logger.info("Scheduler loop exited")
    
    def get_status(self) -> dict:
        """
        Get current scheduler status.
        
        Returns:
            Dictionary with status information.
        """
        # Get in-progress and failed downloads
        in_progress = self.db.get_builds_by_status(DownloadStatus.IN_PROGRESS)
        failed = self.db.get_builds_by_status(DownloadStatus.FAILED)
        
        return {
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "next_check": self._next_check.isoformat() if isinstance(self._next_check, datetime) else None,
            "check_interval_seconds": self.config.check_interval_seconds,
            "in_progress": [
                {
                    "version": b.version,
                    "os": b.os,
                    "timestamp": b.timestamp.isoformat() if b.timestamp else None
                }
                for b in in_progress
            ],
            "failed": [
                {
                    "version": b.version,
                    "os": b.os,
                    "error": b.error_message,
                    "retry_count": b.retry_count,
                    "timestamp": b.timestamp.isoformat() if b.timestamp else None
                }
                for b in failed
            ]
        }
