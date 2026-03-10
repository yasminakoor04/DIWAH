"""
Logging configuration for DIWAH Dashboard.

This module provides centralized logging configuration with:
- Console output for development
- File output for production
- Configurable log levels via environment variable

Usage:
    from src.logging_config import setup_logging, get_logger
    
    # At application startup:
    setup_logging()
    
    # In modules:
    logger = get_logger(__name__)
    logger.info("Dashboard started")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional


# Default log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log file location (relative to project root)
DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"
DEFAULT_LOG_FILE = "diwah_dashboard.log"

# Maximum log file size before rotation (5 MB)
MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024

# Number of backup log files to keep
BACKUP_COUNT = 3


def get_log_level() -> int:
    """
    Get log level from environment variable.
    
    Supports: DEBUG, INFO, WARNING, ERROR, CRITICAL
    Default: INFO
    
    Returns:
        Logging level constant
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_name, logging.INFO)


def setup_logging(
    log_to_file: bool = True,
    log_dir: Optional[Path] = None,
    log_file: Optional[str] = None,
    level: Optional[int] = None
) -> None:
    """
    Configure logging for the application.
    
    Sets up both console and file handlers with appropriate formatting.
    Should be called once at application startup.
    
    Args:
        log_to_file: Whether to write logs to file (default True)
        log_dir: Directory for log files (default: project_root/logs)
        log_file: Log filename (default: diwah_dashboard.log)
        level: Logging level (default: from LOG_LEVEL env var or INFO)
    
    Example:
        # Basic setup
        setup_logging()
        
        # Debug mode without file logging
        setup_logging(log_to_file=False, level=logging.DEBUG)
    """
    if level is None:
        level = get_log_level()
    
    if log_dir is None:
        log_dir = DEFAULT_LOG_DIR
    
    if log_file is None:
        log_file = DEFAULT_LOG_FILE
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers (avoid duplicates on reload)
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_to_file:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / log_file
            
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=MAX_LOG_SIZE_BYTES,
                backupCount=BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            
            root_logger.debug(f"Log file: {log_path}")
        except (OSError, PermissionError) as e:
            root_logger.warning(f"Could not create log file: {e}")
    
    # Reduce verbosity of third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("influxdb_client").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    root_logger.info(f"Logging configured at {logging.getLevelName(level)} level")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    return logging.getLogger(name)


# Convenience function to disable logging (for tests)
def disable_logging() -> None:
    """Disable all logging output. Useful for tests."""
    logging.disable(logging.CRITICAL)


def enable_logging() -> None:
    """Re-enable logging after disable_logging()."""
    logging.disable(logging.NOTSET)
