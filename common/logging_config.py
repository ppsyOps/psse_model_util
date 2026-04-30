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
    """
    Configure and return a logger instance that writes to both console and file.

    Parameters
    ----------
    name : str, optional
        The logger name. If None, returns the root logger.
    loglevel : int, optional
        The logging level to use. Defaults to logging.INFO.
    logformat : str, optional
        Custom log format string. If None, uses default format.

    Returns
    -------
    logging.Logger
        Configured logger instance.

    Examples
    --------
    # >>> from logging_config import setup_logger
    # >>> logger = setup_logger("my_module")
    # >>> logger.info("Hello, logging!")
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
