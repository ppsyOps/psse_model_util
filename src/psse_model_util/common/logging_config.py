"""Logging configuration for psse_model_util.

Provides ``setup_logger`` to build a logger that writes to both the console and
a rotating file under the user log directory, plus ``get_log_file_path`` to
discover the active log file from a logger's handlers.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from psse_model_util.common.dirs import user_log_dir

# You can adjust the log directory and file name as needed
LOG_FILE = user_log_dir / "application.log"

def setup_logger(
    name: Optional[str] = None,
    loglevel: int = logging.INFO,
    logformat: Optional[str] = None,
    log_file: Optional[Path] = LOG_FILE,
) -> logging.Logger:
    """Configure and return a logger that writes to both console and file.

    Args:
        name: The logger name. If None, returns the root logger.
        loglevel: The logging level to use. Defaults to ``logging.INFO``.
        logformat: Custom log format string. If None, a default format is used.
        log_file: Path to the rotating log file. Defaults to ``LOG_FILE`` under
            the user log directory.

    Returns:
        logging.Logger: The configured logger instance.

    Examples:
        >>> from logging_config import setup_logger  # doctest: +SKIP
        >>> logger = setup_logger("my_module")  # doctest: +SKIP
        >>> logger.info("Hello, logging!")  # doctest: +SKIP
    """
    user_log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(loglevel)
        fmt = logformat or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(fmt)

        # Rotating file handler (10MB per file, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger



def get_log_file_path(logger):
    """Get the path of the log file from a logger object.

    Args:
        logger: A logging.Logger instance

    Returns:
        Path: Path object for the log file, or None if no file handler found
    """
    # Look through all handlers for FileHandlers
    for handler in logger.handlers:
        # Check for both FileHandler and RotatingFileHandler
        if hasattr(handler, 'baseFilename'):
            return Path(handler.baseFilename)
    return None
