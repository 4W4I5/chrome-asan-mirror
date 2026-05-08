"""
Downloader module for ASAN Chrome builds.
Handles version probing, downloading, and retry logic.
"""

import logging
import re
import threading
import subprocess
import hashlib
import time
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import zipfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROGRESS_RE = re.compile(r"Received\s+(\d+)\s+of\s+(\d+)\s+bytes,\s+([0-9.]+)%", re.IGNORECASE)


@dataclass
class DownloadResult:
    """Result of a download attempt."""
    success: bool
    version: str
    os: str
    filepath: Optional[Path] = None
    checksum: Optional[str] = None
    error: Optional[str] = None


class Downloader:
    """Handles downloading ASAN Chrome builds."""
    
    def __init__(
        self,
        script_path: Path,
        storage_dir: Path,
        max_retries: int = 5,
        retry_backoff_base: int = 2,
        download_timeout: int = 3600
    ):
        """
        Initialize downloader.
        
        Args:
            script_path: Path to get_asan_chrome.py script.
            storage_dir: Root storage directory.
            max_retries: Maximum retry attempts.
            retry_backoff_base: Base for exponential backoff.
            download_timeout: Timeout per download in seconds.
        """
        self.script_path = script_path
        self.storage_dir = storage_dir
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base
        self.download_timeout = download_timeout
        self._progress_lock = threading.Lock()
        self._active_progress: dict[str, dict] = {}

    def _progress_key(self, version: str, os: str) -> str:
        return f"{version}|{os}"

    def _set_progress(self, version: str, os: str, **updates) -> None:
        key = self._progress_key(version, os)
        with self._progress_lock:
            current = dict(self._active_progress.get(key, {}))
            current.update(updates)
            current["version"] = version
            current["os"] = os
            self._active_progress[key] = current

    def _clear_progress(self, version: str, os: str) -> None:
        key = self._progress_key(version, os)
        with self._progress_lock:
            self._active_progress.pop(key, None)

    def get_active_progress(self) -> List[dict]:
        with self._progress_lock:
            return [dict(value) for value in self._active_progress.values()]
    
    def _compute_checksum(self, filepath: Path) -> str:
        """
        Compute SHA256 checksum of a file.
        
        Args:
            filepath: Path to file.
        
        Returns:
            Hex digest of SHA256 hash.
        """
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _validate_zip(self, filepath: Path) -> bool:
        """
        Validate ZIP file integrity.
        
        Args:
            filepath: Path to ZIP file.
        
        Returns:
            True if ZIP is valid, False otherwise.
        """
        try:
            with zipfile.ZipFile(filepath, 'r') as z:
                result = z.testzip()
                if result is not None:
                    logger.warning(f"ZIP corruption detected in {filepath}: {result}")
                    return False
                return True
        except Exception as e:
            logger.error(f"ZIP validation failed for {filepath}: {e}")
            return False

    def _is_not_found_error(self, text: Optional[str]) -> bool:
        """
        Detect whether get_asan_chrome.py reported a 404 / invalid version.

        Args:
            text: Combined stdout/stderr output from the script.

        Returns:
            True when the output clearly indicates a 404 Not Found.
        """
        if not text:
            return False

        normalized = text.lower()
        return "404" in normalized or "not found" in normalized
    
    def _get_output_path(self, version: str, os: str) -> Path:
        """
        Get the output path for a build.
        
        Args:
            version: Chromium version.
            os: Operating system ("win64" or "linux").
        
        Returns:
            Path where the ZIP should be saved.
        """
        filename = f"{version}.zip"
        return self.storage_dir / os / filename
    
    def _run_with_retry(
        self,
        version: str,
        os: str,
        temp_path: Path
    ) -> Tuple[bool, Optional[str]]:
        """
        Run get_asan_chrome.py with exponential backoff retry.
        
        Args:
            version: Chromium version to download.
            os: Operating system ("win64" or "linux").
            temp_path: Temporary path to download to.
        
        Returns:
            Tuple of (success, error_message).
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Downloading {version}/{os} (attempt {attempt}/{self.max_retries})...")
                self._set_progress(
                    version,
                    os,
                    status="running",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    bytes_received=0,
                    bytes_total=None,
                    pct=0.0,
                    message="Starting download"
                )
                
                cmd = [
                    sys.executable,
                    str(self.script_path),
                    "--version", version,
                    "--os", os,
                    "--download_directory", str(temp_path.parent)
                ]
                logger.info(f"Running get_asan_chrome.py: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )

                stdout_chunks: List[str] = []
                stderr_chunks: List[str] = []

                def read_stdout() -> None:
                    buffer = ""
                    while True:
                        chunk = process.stdout.read(1) if process.stdout else ""
                        if chunk == "":
                            break
                        stdout_chunks.append(chunk)
                        buffer += chunk
                        if "\r" in buffer or "\n" in buffer:
                            for part in re.split(r"[\r\n]+", buffer):
                                text = part.strip()
                                if not text:
                                    continue
                                self._handle_script_output(version, os, text, is_stderr=False)
                            buffer = ""
                    if buffer.strip():
                        self._handle_script_output(version, os, buffer.strip(), is_stderr=False)

                def read_stderr() -> None:
                    if not process.stderr:
                        return
                    for line in iter(process.stderr.readline, ""):
                        stderr_chunks.append(line)
                        text = line.strip()
                        if text:
                            self._handle_script_output(version, os, text, is_stderr=True)

                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                try:
                    process.wait(timeout=self.download_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout_thread.join(timeout=5)
                    stderr_thread.join(timeout=5)
                    error_msg = f"Download timeout after {self.download_timeout}s"
                    logger.warning(f"{version}/{os}: {error_msg}")

                    if attempt == self.max_retries:
                        self._set_progress(version, os, status="failed", message=error_msg)
                        return False, error_msg

                    backoff_time = self.retry_backoff_base ** (attempt - 1)
                    self._set_progress(version, os, status="retrying", message=f"Retrying in {backoff_time}s")
                    time.sleep(backoff_time)
                    continue

                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

                stdout_text = "".join(stdout_chunks)
                stderr_text = "".join(stderr_chunks)
                combined_output = "\n".join(part for part in [stdout_text, stderr_text] if part)

                if process.returncode != 0 and self._is_not_found_error(combined_output):
                    error_msg = f"404 Not Found from get_asan_chrome.py for {version}/{os}"
                    logger.info(f"Invalid version detected: {error_msg}")
                    self._set_progress(version, os, status="not_found", message=error_msg, pct=0.0)
                    return False, error_msg

                if process.returncode == 0:
                    logger.info(f"Successfully downloaded {version}/{os}")
                    self._set_progress(version, os, status="completed", pct=100.0, message="Download complete")
                    return True, None

                error_msg = stderr_text or stdout_text or "Unknown error"
                logger.warning(f"Download failed for {version}/{os}: {error_msg}")

                if attempt == self.max_retries:
                    self._set_progress(version, os, status="failed", message=error_msg)
                    return False, error_msg

                backoff_time = self.retry_backoff_base ** (attempt - 1)
                self._set_progress(version, os, status="retrying", message=f"Retrying in {backoff_time}s")
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)
            
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error downloading {version}/{os}: {error_msg}")
                
                if attempt == self.max_retries:
                    self._set_progress(version, os, status="failed", message=error_msg)
                    return False, error_msg
                
                backoff_time = self.retry_backoff_base ** (attempt - 1)
                self._set_progress(version, os, status="retrying", message=f"Retrying in {backoff_time}s")
                time.sleep(backoff_time)
        
        self._clear_progress(version, os)
        return False, "Max retries exceeded"
    
    def probe_versions(self, os: str, min_version: int, max_version: int) -> List[str]:
        """
        Probe for available versions in the given range.
        
        Probing strategy:
        1. Start at 150 and go backwards to min_version (catch recent stable builds)
        2. Then probe forward from 147 to max_version (catch dev/canary builds)
        
        Args:
            os: Operating system ("win64" or "linux").
            min_version: Minimum version to probe.
            max_version: Maximum version to probe.
        
        Returns:
            List of available version strings in descending order (newest first).
        """
        available_versions = []
        logger.info(f"Probing for available {os} versions ({min_version}-{max_version})...")
        
        # Verify script exists
        if not self.script_path.exists():
            logger.error(f"Script not found at {self.script_path}")
            return available_versions
        
        logger.debug(f"Using script: {self.script_path}")
        
        # Stage 1: Probe backwards from 150 to min_version (catches recent stable)
        logger.info("Stage 1: Probing backwards from 150 to catch recent stable releases...")
        probe_start = min(150, max_version)
        for major_version in range(probe_start, min_version - 1, -1):
            if self._probe_single_version(os, major_version, available_versions):
                pass  # Already logged in helper
        
        # Stage 2: Probe forward from 147 to max_version (catches dev/canary)
        logger.info(f"Stage 2: Probing forward from 147 to {max_version} to catch dev/canary builds...")
        for major_version in range(147, max_version + 1):
            # Skip versions we already found
            version_str = f"{major_version}.0.0.0"
            if version_str not in available_versions:
                self._probe_single_version(os, major_version, available_versions)
        
        logger.info(f"Found {len(available_versions)} available {os} versions: {available_versions}")
        return available_versions
    
    def _probe_single_version(self, os: str, major_version: int, available_versions: List[str]) -> bool:
        """
        Probe a single version.
        
        Args:
            os: Operating system.
            major_version: Major version number.
            available_versions: List to append to if found.
        
        Returns:
            True if version was found, False otherwise.
        """
        version_str = f"{major_version}.0.0.0"
        
        try:
            cmd = [
                sys.executable,
                str(self.script_path),
                "--version", version_str,
                "--os", os
            ]
            
            logger.info(f"Probing with get_asan_chrome.py: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                timeout=30,
                capture_output=True,
                text=True,
                check=False
            )

            if result.stdout:
                for line in result.stdout.splitlines():
                    self._emit_script_output(line, is_stderr=False)
            if result.stderr:
                for line in result.stderr.splitlines():
                    self._emit_script_output(line, is_stderr=True)

            combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
            if result.returncode != 0 and self._is_not_found_error(combined_output):
                logger.info(f"Invalid version detected via 404 response: {version_str}/{os}")
                return False
            
            # If command succeeds, version is available
            if result.returncode == 0:
                available_versions.append(version_str)
                logger.info(f"✓ Found available version: {version_str}")
                return True
            else:
                logger.debug(f"✗ Version {version_str} not available (return code: {result.returncode})")
                if result.stderr:
                    logger.debug(f"  stderr: {result.stderr[:200]}")
                return False
        
        except subprocess.TimeoutExpired:
            logger.debug(f"⏱ Probe timeout for {version_str}")
            return False
        except Exception as e:
            logger.debug(f"⚠ Error probing version {version_str}: {e}")
            return False
    
    def download(self, version: str, os: str) -> DownloadResult:
        """
        Download a specific ASAN Chrome build.
        
        Args:
            version: Chromium version (e.g., "120.0.0.0").
            os: Operating system ("win64" or "linux").
        
        Returns:
            DownloadResult with success status and metadata.
        """
        output_path = self._get_output_path(version, os)
        
        # Check if already downloaded
        if output_path.exists():
            logger.info(f"Build already exists: {output_path}")
            try:
                checksum = self._compute_checksum(output_path)
                return DownloadResult(
                    success=True,
                    version=version,
                    os=os,
                    filepath=output_path,
                    checksum=checksum
                )
            except Exception as e:
                logger.error(f"Failed to checksum existing file {output_path}: {e}")
                return DownloadResult(
                    success=False,
                    version=version,
                    os=os,
                    error=f"Checksum failed: {e}"
                )
        
        # Create temporary directory
        temp_dir = self.storage_dir / "temp" / version / os
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{version}.zip"
        
        try:
            # Download with retry
            success, error_msg = self._run_with_retry(version, os, temp_path)
            
            if not success:
                return DownloadResult(
                    success=False,
                    version=version,
                    os=os,
                    error=error_msg
                )
            
            # Find the downloaded file
            downloaded_file = None
            for file in temp_dir.glob("*.zip"):
                downloaded_file = file
                break
            
            if not downloaded_file or not downloaded_file.exists():
                error_msg = "Downloaded file not found"
                logger.error(f"{version}/{os}: {error_msg}")
                return DownloadResult(
                    success=False,
                    version=version,
                    os=os,
                    error=error_msg
                )
            
            # Validate ZIP
            if not self._validate_zip(downloaded_file):
                error_msg = "ZIP validation failed"
                logger.error(f"{version}/{os}: {error_msg}")
                downloaded_file.unlink()
                return DownloadResult(
                    success=False,
                    version=version,
                    os=os,
                    error=error_msg
                )
            
            # Compute checksum
            checksum = self._compute_checksum(downloaded_file)
            
            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Move to final location
            shutil.move(str(downloaded_file), str(output_path))
            
            logger.info(f"Successfully saved {version}/{os} to {output_path}")
            self._clear_progress(version, os)
            
            return DownloadResult(
                success=True,
                version=version,
                os=os,
                filepath=output_path,
                checksum=checksum
            )
        
        finally:
            # Clean up temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _handle_script_output(self, version: str, os: str, text: str, is_stderr: bool) -> None:
        """
        Parse script output and update progress state.

        Args:
            version: Chromium version being downloaded.
            os: Operating system.
            text: Output text from the script.
            is_stderr: Whether the text came from stderr.
        """
        if not text:
            return

        if is_stderr:
            self._emit_script_output(text, is_stderr=True)
            self._set_progress(version, os, last_error=text)
            return

        self._emit_script_output(text, is_stderr=False)
        progress_match = PROGRESS_RE.search(text)
        if progress_match:
            bytes_received = int(progress_match.group(1))
            bytes_total = int(progress_match.group(2))
            pct = float(progress_match.group(3))
            self._set_progress(
                version,
                os,
                bytes_received=bytes_received,
                bytes_total=bytes_total,
                pct=pct,
                message=f"Received {bytes_received} of {bytes_total} bytes ({pct:.2f}%)",
            )
        else:
            self._set_progress(version, os, last_output=text)

    def _emit_script_output(self, text: str, is_stderr: bool) -> None:
        """Write raw script output to the parent process stdout/stderr."""
        if not text:
            return

        stream = sys.stderr if is_stderr else sys.stdout
        stream.write(f"{text}\n")
        stream.flush()

        if is_stderr:
            logger.error(text)
        else:
            logger.info(text)
