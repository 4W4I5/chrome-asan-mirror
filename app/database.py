"""
Database layer for tracking ASAN Chrome builds.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DownloadStatus(Enum):
    """Status of a download."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class Build:
    """Represents a downloaded ASAN Chrome build."""
    version: str
    os: str  # "win64" or "linux"
    filepath: Path
    checksum: Optional[str] = None
    timestamp: Optional[datetime] = None
    status: DownloadStatus = DownloadStatus.PENDING
    error_message: Optional[str] = None
    retry_count: int = 0


class Database:
    """SQLite database for tracking builds."""
    
    def __init__(self, db_path: Path):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_schema(self) -> None:
        """Initialize database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS builds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                os TEXT NOT NULL,
                filepath TEXT NOT NULL,
                checksum TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                UNIQUE(version, os)
            )
        """)
        
        # Create indices for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_version_os 
            ON builds(version, os)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON builds(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON builds(timestamp DESC)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def insert_build(self, build: Build) -> None:
        """
        Insert or update a build record.
        
        Args:
            build: Build object to insert/update.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO builds 
                (version, os, filepath, checksum, timestamp, status, error_message, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                build.version,
                build.os,
                str(build.filepath),
                build.checksum,
                build.timestamp or datetime.utcnow(),
                build.status.value,
                build.error_message,
                build.retry_count
            ))
            conn.commit()
            logger.debug(f"Inserted build: {build.version}/{build.os}")
        except Exception as e:
            logger.error(f"Error inserting build: {e}")
            raise
        finally:
            conn.close()
    
    def get_build(self, version: str, os: str) -> Optional[Build]:
        """
        Retrieve a build record.
        
        Args:
            version: Chromium version (e.g., "120.0.0.0").
            os: Operating system ("win64" or "linux").
        
        Returns:
            Build object if found, None otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM builds WHERE version = ? AND os = ?
            """, (version, os))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return Build(
                version=row['version'],
                os=row['os'],
                filepath=Path(row['filepath']),
                checksum=row['checksum'],
                timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                status=DownloadStatus(row['status']),
                error_message=row['error_message'],
                retry_count=row['retry_count']
            )
        finally:
            conn.close()
    
    def list_downloads(self, os: Optional[str] = None, status: Optional[DownloadStatus] = None) -> List[Build]:
        """
        List all downloaded builds.
        
        Args:
            os: Filter by OS ("win64", "linux", or None for all).
            status: Filter by download status or None for all.
        
        Returns:
            List of Build objects.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT * FROM builds"
            params = []
            
            conditions = []
            if os:
                conditions.append("os = ?")
                params.append(os)
            if status:
                conditions.append("status = ?")
                params.append(status.value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            builds = []
            for row in rows:
                builds.append(Build(
                    version=row['version'],
                    os=row['os'],
                    filepath=Path(row['filepath']),
                    checksum=row['checksum'],
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                    status=DownloadStatus(row['status']),
                    error_message=row['error_message'],
                    retry_count=row['retry_count']
                ))
            
            return builds
        finally:
            conn.close()
    
    def mark_success(self, version: str, os: str, checksum: Optional[str] = None) -> None:
        """
        Mark a build as successfully downloaded.
        
        Args:
            version: Chromium version.
            os: Operating system.
            checksum: SHA256 checksum (optional).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE builds 
                SET status = ?, timestamp = ?, retry_count = 0, error_message = NULL, checksum = ?
                WHERE version = ? AND os = ?
            """, (DownloadStatus.SUCCESS.value, datetime.utcnow(), checksum, version, os))
            conn.commit()
            logger.debug(f"Marked success: {version}/{os}")
        finally:
            conn.close()
    
    def mark_failed(self, version: str, os: str, error_message: str, retry_count: int) -> None:
        """
        Mark a build as failed.
        
        Args:
            version: Chromium version.
            os: Operating system.
            error_message: Error description.
            retry_count: Number of retries attempted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE builds 
                SET status = ?, error_message = ?, retry_count = ?
                WHERE version = ? AND os = ?
            """, (DownloadStatus.FAILED.value, error_message, retry_count, version, os))
            conn.commit()
            logger.debug(f"Marked failed: {version}/{os}")
        finally:
            conn.close()
    
    def get_stats(self) -> dict:
        """
        Get download statistics.
        
        Returns:
            Dictionary with count, size, and per-OS breakdown.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Count successful downloads
            cursor.execute("""
                SELECT COUNT(*) as count FROM builds WHERE status = ?
            """, (DownloadStatus.SUCCESS.value,))
            total_count = cursor.fetchone()['count']
            
            # Per-OS counts
            cursor.execute("""
                SELECT os, COUNT(*) as count FROM builds 
                WHERE status = ?
                GROUP BY os
            """, (DownloadStatus.SUCCESS.value,))
            os_counts = {row['os']: row['count'] for row in cursor.fetchall()}
            
            # Total size in bytes
            total_size = 0
            cursor.execute("""
                SELECT filepath FROM builds WHERE status = ?
            """, (DownloadStatus.SUCCESS.value,))
            
            for row in cursor.fetchall():
                filepath = Path(row['filepath'])
                if filepath.exists():
                    total_size += filepath.stat().st_size
            
            return {
                'total_downloads': total_count,
                'total_size_bytes': total_size,
                'per_os': os_counts,
                'last_modified': datetime.utcnow().isoformat()
            }
        finally:
            conn.close()
    
    def get_builds_by_status(self, status: DownloadStatus) -> List[Build]:
        """
        Get all builds with a specific status.
        
        Args:
            status: Status to filter by.
        
        Returns:
            List of Build objects with the specified status.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM builds WHERE status = ?
                ORDER BY timestamp DESC
            """, (status.value,))
            
            rows = cursor.fetchall()
            builds = []
            
            for row in rows:
                builds.append(Build(
                    version=row['version'],
                    os=row['os'],
                    filepath=Path(row['filepath']),
                    checksum=row['checksum'],
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                    status=DownloadStatus(row['status']),
                    error_message=row['error_message'],
                    retry_count=row['retry_count']
                ))
            
            return builds
        finally:
            conn.close()

    def clear_stale_in_progress(self, max_age_seconds: int) -> List[Build]:
        """
        Mark stale in-progress builds as failed so they do not block retries.

        Args:
            max_age_seconds: Maximum allowed age for an in-progress build.

        Returns:
            List of builds that were marked stale.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM builds
                WHERE status = ? AND timestamp < ?
            """, (DownloadStatus.IN_PROGRESS.value, cutoff))
            rows = cursor.fetchall()

            stale_builds = []
            for row in rows:
                stale_builds.append(Build(
                    version=row['version'],
                    os=row['os'],
                    filepath=Path(row['filepath']),
                    checksum=row['checksum'],
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                    status=DownloadStatus(row['status']),
                    error_message=row['error_message'],
                    retry_count=row['retry_count']
                ))

            if not stale_builds:
                return []

            cursor.execute("""
                UPDATE builds
                SET status = ?, error_message = ?, timestamp = ?
                WHERE status = ? AND timestamp < ?
            """, (
                DownloadStatus.FAILED.value,
                f"Stale in-progress build expired after {max_age_seconds} seconds",
                datetime.utcnow(),
                DownloadStatus.IN_PROGRESS.value,
                cutoff,
            ))
            conn.commit()
            logger.warning(
                f"Expired {len(stale_builds)} stale in-progress builds older than {max_age_seconds}s"
            )
            return stale_builds
        finally:
            conn.close()

    def mark_all_in_progress_interrupted(self, reason: str) -> List[Build]:
        """
        Mark every in-progress build as interrupted.

        This is used on service startup because any active downloads from a prior
        process were almost certainly terminated by the restart.

        Args:
            reason: Human-readable interruption reason.

        Returns:
            List of builds that were recovered.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM builds
                WHERE status = ?
                ORDER BY timestamp DESC
            """, (DownloadStatus.IN_PROGRESS.value,))
            rows = cursor.fetchall()

            interrupted_builds = []
            for row in rows:
                interrupted_builds.append(Build(
                    version=row['version'],
                    os=row['os'],
                    filepath=Path(row['filepath']),
                    checksum=row['checksum'],
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                    status=DownloadStatus(row['status']),
                    error_message=row['error_message'],
                    retry_count=row['retry_count']
                ))

            if not interrupted_builds:
                return []

            cursor.execute("""
                UPDATE builds
                SET status = ?, error_message = ?, timestamp = ?
                WHERE status = ?
            """, (
                DownloadStatus.FAILED.value,
                reason,
                datetime.utcnow(),
                DownloadStatus.IN_PROGRESS.value,
            ))
            conn.commit()
            logger.warning(
                f"Recovered {len(interrupted_builds)} in-progress build(s) on startup: {reason}"
            )
            return interrupted_builds
        finally:
            conn.close()
