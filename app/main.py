"""
Main application entry point.
Orchestrates initialization of all components and runs the service.
"""

import logging
import logging.handlers
import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn

from app.config import get_config, Config
from app.database import Database
from app.updater import Updater
from app.downloader import Downloader
from app.scheduler import Scheduler
from app.server import create_app

logger = logging.getLogger(__name__)


class Application:
    """Main application class."""
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize application.
        
        Args:
            config: Optional config object. If None, loads from config.yaml.
        """
        self.config = config or get_config()
        self.db: Optional[Database] = None
        self.updater: Optional[Updater] = None
        self.downloader: Optional[Downloader] = None
        self.scheduler: Optional[Scheduler] = None
        self._shutdown_event = asyncio.Event()
    
    def _setup_logging(self) -> None:
        """Configure logging to file and stdout."""
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Format
        log_format = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
        )
        
        # File handler (rotating)
        log_file = self.config.log_dir / "asan-chrome-mirror.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.config.log_max_bytes,
            backupCount=self.config.log_backup_count
        )
        file_handler.setLevel(getattr(logging, self.config.logging_level, logging.INFO))
        file_handler.setFormatter(log_format)
        root_logger.addHandler(file_handler)
        
        # Stream handler (stdout)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(getattr(logging, self.config.logging_level, logging.INFO))
        stream_handler.setFormatter(log_format)
        root_logger.addHandler(stream_handler)
        
        logger.info("Logging configured")
    
    def _init_components(self) -> None:
        """Initialize all application components."""
        logger.info("Initializing components...")
        
        # Database
        db_path = self.config.data_dir / "builds.db"
        self.db = Database(db_path)
        logger.info(f"Database initialized: {db_path}")
        
        # Updater
        self.updater = Updater(self.config.data_dir)
        logger.info(f"Updater initialized: {self.updater.script_path}")
        
        # Downloader
        self.downloader = Downloader(
            script_path=self.updater.script_path,
            storage_dir=self.config.storage_dir,
            max_retries=self.config.max_retries,
            retry_backoff_base=self.config.retry_backoff_base,
            download_timeout=self.config.download_timeout_seconds
        )
        logger.info("Downloader initialized")
        
        # Scheduler
        self.scheduler = Scheduler(
            config=self.config,
            db=self.db,
            updater=self.updater,
            downloader=self.downloader
        )
        logger.info("Scheduler initialized")

    def _recover_in_progress_downloads(self) -> None:
        """Mark any leftover in-progress downloads as interrupted on startup."""
        if not self.db:
            return

        interrupted_builds = self.db.mark_all_in_progress_interrupted(
            "Interrupted by service restart"
        )
        if interrupted_builds:
            logger.warning(
                f"Recovered {len(interrupted_builds)} interrupted download(s) from a prior run"
            )
    
    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        logger.info("Shutdown request received")
        self._shutdown_event.set()
        if self.scheduler:
            self.scheduler.request_shutdown()
    
    async def _run_server(self) -> None:
        """Run the FastAPI HTTP server."""
        app = create_app(self.config, self.db, self.scheduler, self.downloader)
        
        config = uvicorn.Config(
            app,
            host=self.config.http_host,
            port=self.config.http_port,
            log_level=self.config.logging_level.lower(),
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        # Create shutdown task
        async def shutdown_waiter():
            await self._shutdown_event.wait()
            logger.info("Shutting down server...")
            server.should_exit = True
        
        # Run server and shutdown waiter concurrently
        await asyncio.gather(
            server.serve(),
            shutdown_waiter(),
            return_exceptions=True
        )
    
    async def _run_async(self) -> None:
        """Run async components (scheduler and server)."""
        logger.info("Starting async components...")
        
        # Create tasks for scheduler and server
        scheduler_task = asyncio.create_task(self.scheduler.run_scheduler())
        server_task = asyncio.create_task(self._run_server())
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        
        try:
            # Wait for either task to complete or for shutdown to be requested.
            done, pending = await asyncio.wait(
                [scheduler_task, server_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            if shutdown_task in done:
                logger.info("Shutdown requested, cancelling running tasks")
            else:
                logger.warning("One of the main tasks completed unexpectedly")
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
            
            await asyncio.gather(*pending, return_exceptions=True)
        
        except asyncio.CancelledError:
            logger.info("Async tasks cancelled")
            raise
        finally:
            shutdown_task.cancel()
    
    def run(self) -> None:
        """Main run method."""
        logger.info("=" * 60)
        logger.info("ASAN Chrome Mirror Service Starting")
        logger.info("=" * 60)
        
        try:
            # Setup signal handlers
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            def handle_signal(signum, frame):
                logger.info(f"Received signal {signum}")
                self.request_shutdown()
            
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
            
            # Run application
            loop.run_until_complete(self._run_async())
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
        finally:
            logger.info("=" * 60)
            logger.info("ASAN Chrome Mirror Service Stopped")
            logger.info("=" * 60)


def main() -> None:
    """Entry point for the application."""
    app = Application()
    app._setup_logging()
    app._init_components()
    app._recover_in_progress_downloads()
    app.run()


if __name__ == "__main__":
    main()
