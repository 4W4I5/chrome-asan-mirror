"""
Updater module for downloading and managing get_asan_chrome.py script.
"""

import logging
import base64
import hashlib
import os
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)

# URL to fetch get_asan_chrome.py from Chromium source
ASAN_SCRIPT_URL = (
    "https://chromium.googlesource.com/chromium/src/+/"
    "refs/heads/main/tools/get_asan_chrome/get_asan_chrome.py?format=TEXT"
)


class Updater:
    """Manages fetching and updating the get_asan_chrome.py script."""
    
    def __init__(self, script_dir: Path, timeout: int = 30):
        """
        Initialize updater.
        
        Args:
            script_dir: Directory to store the script.
            timeout: HTTP request timeout in seconds.
        """
        self.script_dir = script_dir
        self.script_path = script_dir / "get_asan_chrome.py"
        self.timeout = timeout
        self.script_dir.mkdir(parents=True, exist_ok=True)
    
    def _compute_hash(self, content: bytes) -> str:
        """
        Compute SHA256 hash of content.
        
        Args:
            content: Bytes to hash.
        
        Returns:
            Hex digest of SHA256 hash.
        """
        return hashlib.sha256(content).hexdigest()
    
    def get_local_hash(self) -> Optional[str]:
        """
        Get hash of locally stored script.
        
        Returns:
            Hash string if script exists, None otherwise.
        """
        if not self.script_path.exists():
            return None
        
        with open(self.script_path, "rb") as f:
            return self._compute_hash(f.read())
    
    def fetch_latest(self) -> bool:
        """
        Fetch the latest get_asan_chrome.py from Chromium source.
        
        The Chromium source returns base64-encoded content when ?format=TEXT is used.
        
        Returns:
            True if script was updated or newly downloaded, False if already up-to-date.
        """
        try:
            logger.info(f"Fetching latest get_asan_chrome.py from {ASAN_SCRIPT_URL}...")
            
            response = requests.get(ASAN_SCRIPT_URL, timeout=self.timeout)
            response.raise_for_status()
            logger.debug(f"  Response status: {response.status_code}, length: {len(response.text)}")
            
            # The response is base64-encoded when using ?format=TEXT
            script_content = base64.b64decode(response.text).decode("utf-8")
            script_bytes = script_content.encode("utf-8")
            logger.debug(f"  Decoded script size: {len(script_bytes)} bytes")
            
            # Check if script has changed
            remote_hash = self._compute_hash(script_bytes)
            local_hash = self.get_local_hash()
            logger.debug(f"  Remote hash: {remote_hash[:16]}..., Local hash: {local_hash[:16] if local_hash else 'None'}...")
            
            if remote_hash == local_hash:
                logger.info("✓ get_asan_chrome.py is up-to-date")
                return False
            
            # Write new script
            with open(self.script_path, "wb") as f:
                f.write(script_bytes)
            
            # Make script executable
            self.script_path.chmod(0o755)
            
            logger.info(f"✓ Successfully updated get_asan_chrome.py (hash: {remote_hash[:8]}...)")
            return True
            
        except requests.RequestException as e:
            logger.error(f"✗ Failed to fetch get_asan_chrome.py from network: {e}")
            raise
        except Exception as e:
            logger.error(f"✗ Error updating get_asan_chrome.py: {e}", exc_info=True)
            raise
    
    def verify_script_exists(self) -> bool:
        """
        Verify that get_asan_chrome.py exists locally.
        
        Returns:
            True if script exists and is executable, False otherwise.
        """
        if not self.script_path.exists():
            logger.error("get_asan_chrome.py not found locally")
            return False
        
        if not os.access(self.script_path, os.X_OK):
            logger.warning("get_asan_chrome.py exists but is not executable")
            self.script_path.chmod(0o755)
        
        return True

