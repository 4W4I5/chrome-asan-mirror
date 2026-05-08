"""
Configuration management for ASAN Chrome Mirror service.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml


class Config(BaseModel):
    """Application configuration."""
    
    # Storage and paths
    storage_dir: Path = Field(default=Path("/storage"), description="Root storage directory for downloads")
    log_dir: Path = Field(default=Path("/var/log/asan-chrome-mirror"), description="Directory for log files")
    data_dir: Path = Field(default=Path("./data"), description="Directory for application data (SQLite)")
    
    # Version discovery
    min_version: int = Field(default=140, description="Minimum Chromium version to probe")
    max_version: int = Field(default=160, description="Maximum Chromium version to probe")
    
    # Scheduling
    check_interval_seconds: int = Field(default=43200, description="Seconds between checks (12 hours)")
    
    # HTTP server
    http_host: str = Field(default="0.0.0.0", description="HTTP server bind address")
    http_port: int = Field(default=8000, description="HTTP server port")
    
    # Retry policy
    max_retries: int = Field(default=5, description="Maximum retry attempts per download")
    retry_backoff_base: int = Field(default=2, description="Base for exponential backoff (2^n)")
    
    # Download behavior
    download_timeout_seconds: int = Field(default=3600, description="Timeout per download (1 hour)")
    in_progress_timeout_seconds: int = Field(default=1800, description="Age in seconds after which an in-progress build is treated as stale")
    
    # Logging
    logging_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    log_max_bytes: int = Field(default=10485760, description="Max log file size (10MB)")
    log_backup_count: int = Field(default=5, description="Number of backup log files to keep")
    
    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create OS-specific subdirectories
        (self.storage_dir / "win64").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "linux").mkdir(parents=True, exist_ok=True)
    
    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file or environment.
    
    Args:
        config_path: Path to config.yaml file. If None, looks for ./config.yaml or uses defaults.
    
    Returns:
        Config object with settings.
    """
    if config_path is None:
        config_path = "config.yaml"
    
    config_data = {}
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f)
            if yaml_data:
                config_data.update(yaml_data)
    
    # Override with environment variables if present
    for field_name in Config.__fields__:
        env_var = f"ASAN_{field_name.upper()}"
        if env_var in os.environ:
            config_data[field_name] = os.environ[env_var]
    
    config = Config(**config_data)
    config.ensure_directories()
    
    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or initialize the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance (useful for testing)."""
    global _config
    _config = config
