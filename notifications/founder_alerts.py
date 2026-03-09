"""
════════════════════════════════════════════════════════════════════════════════
  SRP MediFlow — Founder / Platform Alert System
  Module   : notifications/founder_alerts.py
  Purpose  : Send CRITICAL SYSTEM-LEVEL alerts to the SRP MediFlow founder.
             Completely separate from hospital-level operational notifications.

  ALERT TYPES (ONLY these trigger a founder alert):
    SERVER_START               — server process launched successfully
    SERVER_CRASH               — unhandled exception or unexpected shutdown
    DATABASE_CONNECTION_ERROR  — PostgreSQL unreachable at startup or runtime
    NEW_CLIENT_REGISTERED      — a new hospital/tenant was onboarded
    SECURITY_ALERT             — rate-limit breach, unauthorised access pattern
    BACKUP_FAILED              — scheduled backup could not complete

  NOT SENT HERE (hospital-operational, stay internal):
    IPD admissions / discharges
    Appointments
    Surgery scheduling
    Medicine stock alerts
    Doctor actions

  CREDENTIALS: loaded from environment variables.
    FOUNDER_TELEGRAM_TOKEN   — bot token for the founder-only bot
    FOUNDER_TELEGRAM_CHAT_ID — founder's personal Telegram chat ID

  DESIGN:
    • All sends happen in a daemon background thread → server NEVER blocks.
    • Every alert is also appended to  logs/system_alerts.log.
    • The function is safe to call from any thread; failures are swallowed and
      logged locally so they never propagate to the HTTP handler.
════════════════════════════════════════════════════════════════════════════════
"""

import os
import logging
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── Credentials ───────────────────────────────────────────────────────────────
FOUNDER_TELEGRAM_TOKEN = os.getenv(
    "FOUNDER_TELEGRAM_TOKEN",
    "8768907442:AAHzmIZiEFgr_i-9EUtNCwAf2VQkWzYE2y0",
)
FOUNDER_TELEGRAM_CHAT_ID = os.getenv(
    "FOUNDER_TELEGRAM_CHAT_ID",
    "7144152487",
)

# ── Valid event types (whitelist) ─────────────────────────────────────────────
FOUNDER_ALERT_EVENTS = frozenset({
    "SERVER_START",
    "SERVER_CRASH",
    "DATABASE_CONNECTION_ERROR",
    "NEW_CLIENT_REGISTERED",
    "SECURITY_ALERT",
    "BACKUP_FAILED",
})

# ── Log file setup ────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR  = os.path.join(_BASE_DIR, "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "system_alerts.log")

os.makedirs(_LOG_DIR, exist_ok=True)

logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger("founder_alerts")

# Dedicated file handler — always write to logs/system_alerts.log
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [FOUNDER_ALERT] %(levelname)s %(message)s",
                      datefmt="%Y-%m-%dT%H:%M:%SZ")
)
_logger.addHandler(_file_handler)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _utc_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_message(event_type: str, message: str) -> str:
    """Format the Telegram message body."""
    return (
        "🚨 SRP MEDIFLOW SYSTEM ALERT\n\n"
        f"Event: {event_type}\n\n"
        f"{message}\n\n"
        f"Timestamp: {_utc_now()}"
    )


def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    """
    Send a message via the Telegram Bot API (blocking, called from a thread).
    Returns True on success, False on any error.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        _logger.warning("Telegram HTTP error %s: %s", exc.code, exc.reason)
    except urllib.error.URLError as exc:
        _logger.warning("Telegram URL error: %s", exc.reason)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Telegram unexpected error: %s", exc)
    return False


def _dispatch(event_type: str, message: str) -> None:
    """
    Background worker: write to log file, then push to Telegram.
    Called from a daemon thread — never raises.
    """
    full_text = _build_message(event_type, message)

    # 1. Write to log file
    _logger.info("[%s] %s", event_type, message)

    # 2. Send to founder via Telegram
    success = _send_telegram(FOUNDER_TELEGRAM_TOKEN, FOUNDER_TELEGRAM_CHAT_ID, full_text)
    if success:
        _logger.info("[%s] Founder Telegram alert delivered.", event_type)
    else:
        _logger.warning("[%s] Founder Telegram delivery FAILED — check token/chat_id.", event_type)


# ── Public API ────────────────────────────────────────────────────────────────

def send_founder_alert(event_type: str, message: str) -> None:
    """
    Queue a founder system alert to be sent asynchronously.

    Parameters
    ----------
    event_type : str
        One of FOUNDER_ALERT_EVENTS.  Unknown types are silently normalised to
        SECURITY_ALERT so the message is never lost.
    message : str
        Plain-text description of the event.  Must NOT contain patient data.

    This function returns immediately — the send happens in a daemon thread.
    """
    if not event_type or not isinstance(event_type, str):
        event_type = "SECURITY_ALERT"

    event_type = event_type.strip().upper()
    if event_type not in FOUNDER_ALERT_EVENTS:
        _logger.warning(
            "send_founder_alert called with unknown event_type=%r — "
            "treating as SECURITY_ALERT", event_type
        )
        event_type = "SECURITY_ALERT"

    t = threading.Thread(
        target=_dispatch,
        args=(event_type, message),
        daemon=True,
        name=f"founder-alert-{event_type}",
    )
    t.start()
