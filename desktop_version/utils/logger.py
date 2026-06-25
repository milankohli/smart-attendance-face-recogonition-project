"""
utils/logger.py
───────────────────────────────────────────────────────────────────────────────
Production-grade logger with:
  • Coloured console output  (INFO=green, WARNING=yellow, ERROR=red)
  • File handler that rotates at 5 MB, keeps 3 backups
  • Single get_logger() factory — call it everywhere with the module name.
  • Log directory comes from Config.LOGS_DIR (consistent with ensure_dirs).

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Embedding generated for Alice")
───────────────────────────────────────────────────────────────────────────────
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ── ANSI colour codes ─────────────────────────────────────────────────────────
class _Colours:
    RESET   = "\033[0m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    CYAN    = "\033[36m"
    BOLD    = "\033[1m"


# ── Custom Formatter with colour support ─────────────────────────────────────
class _ColourFormatter(logging.Formatter):
    LEVEL_COLOURS = {
        logging.DEBUG:    _Colours.CYAN,
        logging.INFO:     _Colours.GREEN,
        logging.WARNING:  _Colours.YELLOW,
        logging.ERROR:    _Colours.RED,
        logging.CRITICAL: _Colours.RED + _Colours.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, _Colours.RESET)
        record.levelname = f"{colour}{record.levelname:<8}{_Colours.RESET}"
        return super().format(record)


# ── Public factory ────────────────────────────────────────────────────────────
_LOG_FORMAT      = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_FILE_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
_DATE_FORMAT     = "%Y-%m-%d %H:%M:%S"

# Use Config.LOGS_DIR so the log file is always co-located with the project.
# We import Config lazily to avoid a circular import at module load time.
def _get_log_dir() -> Path:
    try:
        from utils.config import Config  # local import to avoid circular dependency
        return Config.LOGS_DIR
    except Exception:
        # Fallback: place logs next to the project root
        return Path(__file__).resolve().parent.parent / "logs"

_LOG_FILE_NAME = "attendance_system.log"


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Return (or create) a named logger.

    Parameters
    ----------
    name  : Typically __name__ of the calling module.
    level : Logging level string (DEBUG / INFO / WARNING / ERROR).

    Returns
    -------
    logging.Logger
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # ── Console handler (coloured) ────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ColourFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(console)

    # ── Rotating file handler (structured, no colour codes) ───────────────
    try:
        log_dir  = _get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / _LOG_FILE_NAME
        fh = RotatingFileHandler(
            log_file,
            maxBytes   = 5 * 1024 * 1024,   # 5 MB per file
            backupCount= 3,                  # keep 3 rotated archives
            encoding   = "utf-8",
        )
        fh.setFormatter(
            logging.Formatter(_FILE_LOG_FORMAT, datefmt=_DATE_FORMAT)
        )
        logger.addHandler(fh)
    except (OSError, PermissionError):
        # If we can't write logs to disk, console-only is fine
        logger.warning("Could not create log file – console-only logging active.")

    # Prevent propagation to root logger (avoids duplicate messages)
    logger.propagate = False
    return logger
