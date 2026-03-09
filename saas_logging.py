"""
saas_logging.py — SRP MediFlow Centralized Logging
===================================================
Creates three rotating log files under  logs/

  logs/system.log        — all major system events (start, login, CRUD)
  logs/security.log      — auth failures, rate-limit breaches, injection attempts
  logs/system_alerts.log — founder alerts  (also written by notifications/founder_alerts.py)

Usage
-----
    from saas_logging import system_log, security_log, alerts_log
    system_log.info("Server started on port 7500")
    security_log.warning("Failed login: user=hacker ip=1.2.3.4")
"""

from __future__ import annotations
import os
import logging
from logging.handlers import RotatingFileHandler

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR  = os.path.join(_BASE_DIR, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_FMT = logging.Formatter(
    "%(asctime)s [%(name)-14s] %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ"
)

_MAX_BYTES   = 10 * 1024 * 1024   # 10 MB per file
_BACKUP_CNT  = 5                   # keep 5 rotated files


def _make_logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    """Create (or return existing) a rotating-file logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger                   # already configured — avoid duplicate handlers
    logger.setLevel(level)
    logger.propagate = False            # don't bubble up to root logger

    fh = RotatingFileHandler(
        os.path.join(_LOG_DIR, filename),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_CNT,
        encoding="utf-8",
    )
    fh.setFormatter(_FMT)
    fh.setLevel(level)
    logger.addHandler(fh)
    return logger


# ── Public convenience loggers ────────────────────────────────────────────────
def get_system_logger()   -> logging.Logger: return _make_logger("srp.system",   "system.log")
def get_security_logger() -> logging.Logger: return _make_logger("srp.security", "security.log")
def get_alerts_logger()   -> logging.Logger: return _make_logger("srp.alerts",   "system_alerts.log")

# Ready-to-use singletons
system_log   = get_system_logger()
security_log = get_security_logger()
alerts_log   = get_alerts_logger()


def log_event(category: str, message: str, level: str = "info") -> None:
    """
    Unified log helper.
    category: 'system' | 'security' | 'alert'
    level    : 'info'  | 'warning'  | 'error'  | 'critical'
    """
    _loggers = {
        "system":   system_log,
        "security": security_log,
        "alert":    alerts_log,
    }
    logger = _loggers.get(category.lower(), system_log)
    getattr(logger, level.lower(), logger.info)(message)
