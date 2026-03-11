"""
════════════════════════════════════════════════════════════════════════════════
  SRP MediFlow — Telegram Bot Integration
  Module   : telegram_bot.py
  Version  : 1.0
════════════════════════════════════════════════════════════════════════════════

PURPOSE:
  Give hospital admin/staff instant WhatsApp-like alerts on Telegram.
  Much faster to set up than WhatsApp Business API.

SETUP:
  Set credentials in your .env file (never hardcode here):
    TELEGRAM_BOT_TOKEN=<your_bot_token>
    TELEGRAM_CHAT_ID=<your_chat_id>

WHAT IT SENDS:
  ✅ New OPD patient registration
  ✅ New appointment booked (chatbot/WhatsApp)
  ✅ WhatsApp patient inquiry received
  ✅ IPD admission / discharge alerts
  ✅ Low stock / expiry warnings
  ✅ Surgery scheduled
  ✅ Manual admin alerts

HOW TO TEST:
  python telegram_bot.py
════════════════════════════════════════════════════════════════════════════════
"""

import os
import json
import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional

# ── Dynamic hospital branding (SRP MediFlow multi-client) ─────────────────────
def _hospital() -> dict:
    """
    Return lightweight hospital config dict.
    Tries client_config first; falls back to hospital_config.py;
    ultimate fallback to hardcoded Star Hospital defaults.
    """
    try:
        from client_config import get_cached_config
        return get_cached_config()
    except Exception:
        pass
    try:
        import hospital_config as hc
        return {
            'hospital_name':    getattr(hc, 'HOSPITAL_NAME',    'Star Hospital'),
            'city':             'Kothagudem',
            'hospital_phone':   getattr(hc, 'HOSPITAL_PHONE',   '+91 7981971015'),
            'hospital_address': getattr(hc, 'HOSPITAL_ADDRESS', ''),
        }
    except Exception:
        return {
            'hospital_name': 'Star Hospital',
            'city':          'Kothagudem',
            'hospital_phone': '+91 7981971015',
        }

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("telegram_bot")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Telegram] %(levelname)s %(message)s",
)

# ── Credentials — MUST be set in .env (never hardcode here) ──────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

_BOT_ACTIVE = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

if _BOT_ACTIVE:
    logger.info("✅ Telegram bot active | Chat ID: %s", TELEGRAM_CHAT_ID)
else:
    logger.warning("⚠️  Telegram bot not configured")

# ── Founder / Platform-owner notification channel ─────────────────────────────
# FOUNDER_BOT_TOKEN uses the dedicated founder bot (8768907442).
# Falls back to FOUNDER_TELEGRAM_TOKEN, then TELEGRAM_BOT_TOKEN as last resort.
FOUNDER_CHAT_ID   = os.getenv("FOUNDER_CHAT_ID", os.getenv("FOUNDER_TELEGRAM_CHAT_ID", ""))
FOUNDER_BOT_TOKEN = (
    os.getenv("FOUNDER_BOT_TOKEN")
    or os.getenv("FOUNDER_TELEGRAM_TOKEN")
    or TELEGRAM_BOT_TOKEN
)
_FOUNDER_ACTIVE   = bool(FOUNDER_CHAT_ID and FOUNDER_BOT_TOKEN)

if _FOUNDER_ACTIVE:
    logger.info("✅ Founder channel active | Chat ID: %s", FOUNDER_CHAT_ID)
else:
    logger.info("ℹ️  Founder channel not configured (set FOUNDER_CHAT_ID env var to enable)")


# ══════════════════════════════════════════════════════════════════════════════
# CORE SEND FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram_message(
    text: str,
    chat_id: str = TELEGRAM_CHAT_ID,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
) -> dict:
    """
    Send a message to the configured Telegram chat.
    Fires in a background daemon thread so it NEVER blocks the HTTP response.

    Args:
        text                 : Message text (supports HTML tags)
        chat_id              : Override chat ID (default: TELEGRAM_CHAT_ID)
        parse_mode           : 'HTML' or 'Markdown'
        disable_notification : Send silently (no sound)

    Returns:
        dict with 'status': 'queued' (always immediate; actual send is async)
    """
    if not _BOT_ACTIVE:
        logger.info("📤 [PLACEHOLDER] Would send: %s", text[:80])
        return {"status": "placeholder", "message": text}

    def _send():
        try:
            payload = json.dumps({
                "chat_id":              chat_id,
                "text":                 text,
                "parse_mode":           parse_mode,
                "disable_notification": disable_notification,
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{TELEGRAM_API_BASE}/sendMessage",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    msg_id = result.get("result", {}).get("message_id", "")
                    logger.info("📤 Telegram sent | msg_id=%s", msg_id)
                else:
                    logger.error("Telegram API error: %s", result)
        except Exception as exc:
            logger.error("send_telegram_message error: %s", exc)

    import threading
    threading.Thread(target=_send, daemon=True).start()
    return {"status": "queued"}


# ══════════════════════════════════════════════════════════════════════════════
# HOSPITAL EVENT NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    """Current time string for messages."""
    return datetime.now().strftime("%d %b %Y %I:%M %p")


def _forward_to_founder(text: str, hospital_name: str = "") -> None:
    """
    Mirror any hospital notification to the platform founder's personal chat.
    Prefixes the message with a [CLIENT] tag so the founder knows which hospital.
    Silent fire-and-forget — never blocks the main notification.
    Skipped automatically if FOUNDER_CHAT_ID == TELEGRAM_CHAT_ID (same person)
    to avoid duplicate messages.
    """
    if not _FOUNDER_ACTIVE:
        return
    # Don't double-send if founder IS the hospital admin
    if FOUNDER_CHAT_ID == TELEGRAM_CHAT_ID:
        return
    try:
        prefix = f"<b>[CLIENT: {hospital_name}]</b>\n" if hospital_name else ""
        payload = json.dumps({
            "chat_id":              FOUNDER_CHAT_ID,
            "text":                 prefix + text,
            "parse_mode":           "HTML",
            "disable_notification": True,   # silent for founder — no buzz
        }).encode("utf-8")
        api = f"https://api.telegram.org/bot{FOUNDER_BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(api, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as _exc:
        logger.debug("Founder forward skipped: %s", _exc)


def notify_new_registration(name: str, phone: str, issue: str, doctor: str = "") -> dict:
    """
    Alert staff when a new OPD patient registers (chatbot / walk-in).
    """
    h = _hospital()
    doc_line = f"\n👨\u200d⚕️ <b>Doctor:</b> {doctor}" if doctor else ""
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"🆕 <b>NEW OPD REGISTRATION</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Patient:</b> {name}\n"
        f"📞 <b>Phone:</b> {phone}\n"
        f"💬 <b>Complaint:</b> {issue[:100]}"
        f"{doc_line}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_appointment_booked(
    name: str,
    phone: str,
    doctor: str,
    slot: str,
    source: str = "chatbot",
) -> dict:
    """
    Alert staff when an appointment is booked.
    """
    h = _hospital()
    source_icon = {"chatbot": "🤖", "whatsapp": "📱", "walk-in": "🚶", "phone": "📞"}.get(source, "📋")
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"📅 <b>APPOINTMENT BOOKED</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Patient:</b> {name}\n"
        f"📞 <b>Phone:</b> {phone}\n"
        f"👨‍⚕️ <b>Doctor:</b> {doctor}\n"
        f"🕐 <b>Slot:</b> {slot}\n"
        f"{source_icon} <b>Source:</b> {source.capitalize()}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_whatsapp_inquiry(phone: str, message: str, bot_reply: str = "") -> dict:
    """
    Alert staff when a patient sends a WhatsApp message.
    """
    h = _hospital()
    reply_line = f"\n🤖 <b>Bot replied:</b> {bot_reply[:80]}..." if bot_reply else ""
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"📱 <b>WHATSAPP INQUIRY</b>\n"
        f"──────────────────────\n"
        f"📞 <b>From:</b> +{phone}\n"
        f"💬 <b>Message:</b> {message[:150]}"
        f"{reply_line}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_ipd_admission(
    name: str,
    phone: str,
    ward: str,
    bed: str,
    doctor: str,
) -> dict:
    """
    Alert staff when a patient is admitted (IPD).
    """
    h = _hospital()
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"🛏️ <b>PATIENT ADMITTED (IPD)</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Patient:</b> {name}\n"
        f"📞 <b>Phone:</b> {phone}\n"
        f"🛏️ <b>Ward / Bed:</b> {ward} / {bed}\n"
        f"👨‍⚕️ <b>Doctor:</b> {doctor}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_ipd_discharge(name: str, phone: str, bill_amount: float = 0.0) -> dict:
    """
    Alert staff when a patient is discharged.
    """
    h = _hospital()
    bill_line = f"\n💰 <b>Bill:</b> ₹{bill_amount:,.2f}" if bill_amount else ""
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"✅ <b>PATIENT DISCHARGED</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Patient:</b> {name}\n"
        f"📞 <b>Phone:</b> {phone}"
        f"{bill_line}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_low_stock(items: list) -> dict:
    """
    Alert stock manager about low stock items.
    items: list of dicts with 'medicine_name', 'quantity', 'min_quantity'
    """
    if not items:
        return {"status": "skipped", "reason": "no low stock items"}
    h = _hospital()
    lines = "\n".join(
        f"  • {i.get('medicine_name','?')} — qty: {i.get('quantity',0)} "
        f"(min: {i.get('min_quantity',10)})"
        for i in items[:10]
    )
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"⚠️ <b>LOW STOCK ALERT</b>\n"
        f"──────────────────────\n"
        f"{lines}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"� {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"📦 Please reorder from supplier\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_expiry_alert(items: list) -> dict:
    """
    Alert stock manager about medicines expiring within 90 days.
    """
    if not items:
        return {"status": "skipped", "reason": "no expiry alerts"}
    h = _hospital()
    lines = "\n".join(
        f"  • {i.get('medicine_name','?')} — Exp: {i.get('expiry_date','?')} "
        f"qty: {i.get('quantity',0)}"
        for i in items[:10]
    )
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"📅 <b>MEDICINE EXPIRY ALERT</b>\n"
        f"──────────────────────\n"
        f"{lines}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"� {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"🗑️ Remove/return items before expiry\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_surgery_scheduled(
    patient: str,
    surgery_type: str,
    surgeon: str,
    date: str,
    cost: float = 0.0,
) -> dict:
    """
    Alert admin when a surgery is scheduled.
    """
    h = _hospital()
    cost_line = f"\n💰 <b>Estimated Cost:</b> ₹{cost:,.2f}" if cost else ""
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"🔪 <b>SURGERY SCHEDULED</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Patient:</b> {patient}\n"
        f"💉 <b>Procedure:</b> {surgery_type}\n"
        f"👨‍⚕️ <b>Surgeon:</b> {surgeon}\n"
        f"📅 <b>Date:</b> {date}"
        f"{cost_line}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_admin(message: str) -> dict:
    """Send a custom admin notification."""
    h = _hospital()
    text = (
        f"📢 <b>ADMIN ALERT — {h['hospital_name']}</b>\n"
        f"──────────────────────\n"
        f"{message}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"📍 {h.get('city', '')}   📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    result = send_telegram_message(text)
    _forward_to_founder(text, h['hospital_name'])
    return result


def notify_founder_platform(message: str) -> dict:
    """
    Send PLATFORM-LEVEL event directly to the founder only.
    Use this for: new client onboarded, server started, billing alerts etc.
    Does NOT fire to any hospital's channel.
    """
    if not _FOUNDER_ACTIVE:
        logger.info("[FOUNDER-ONLY] Would send: %s", message[:80])
        return {"status": "founder_not_configured"}
    h = _hospital()
    text = (
        f"🏢 <b>SRP MEDIFLOW PLATFORM</b>\n"
        f"📣 <b>FOUNDER ALERT</b>\n"
        f"──────────────────────\n"
        f"{message}\n"
        f"──────────────────────\n"
        f"⏰ {_ts()}\n"
        f"<i>SRP Technologies — Platform Event</i>"
    )
    try:
        payload = json.dumps({
            "chat_id":    FOUNDER_CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }).encode("utf-8")
        api = f"https://api.telegram.org/bot{FOUNDER_BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(api, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                return {"status": "sent"}
            return {"status": "error", "error": str(result)}
    except Exception as exc:
        logger.error("notify_founder_platform error: %s", exc)
        return {"status": "error", "error": str(exc)}


def send_daily_summary(stats: dict) -> dict:
    """
    Send end-of-day hospital summary to admin.
    stats: dict with keys like total_appointments, active_admissions, etc.
    """
    h = _hospital()
    text = (
        f"🏥 <b>{h['hospital_name'].upper()}</b>\n"
        f"📊 <b>DAILY SUMMARY</b>\n"
        f"──────────────────────\n"
        f"📅 {datetime.now().strftime('%d %B %Y')}\n\n"
        f"🏥 OPD Patients     : {stats.get('total_appointments', 0)}\n"
        f"🛏️  IPD Admissions  : {stats.get('total_admissions', 0)}\n"
        f"💊 Pharmacy Sales   : {stats.get('pharmacy_sales', 0)}\n"
        f"🧪 Lab Tests        : {stats.get('lab_orders', 0)}\n"
        f"💰 Total Revenue    : ₹{float(stats.get('total_revenue', 0)):,.2f}\n"
        f"⚠️  Low Stock Items  : {stats.get('low_stock_count', 0)}\n"
        f"📅 Expiry Alerts    : {stats.get('expiry_alert_count', 0)}\n"
        f"──────────────────────\n"
        f"📍 {h.get('city', 'Kothagudem')}\n"
        f"📞 {h['hospital_phone']}\n"
        f"<i>Powered by SRP MediFlow</i>"
    )
    return send_telegram_message(text)


# ══════════════════════════════════════════════════════════════════════════════
# BOT STATUS
# ══════════════════════════════════════════════════════════════════════════════

def get_bot_status() -> dict:
    """Return current Telegram bot status."""
    return {
        "active":            _BOT_ACTIVE,
        "chat_id":           TELEGRAM_CHAT_ID,
        "bot_token_set":     bool(TELEGRAM_BOT_TOKEN),
        "founder_active":    _FOUNDER_ACTIVE,
        "founder_chat_id":   FOUNDER_CHAT_ID or "not configured",
        "notifications": [
            "new_registration",
            "appointment_booked",
            "whatsapp_inquiry",
            "ipd_admission",
            "ipd_discharge",
            "low_stock",
            "expiry_alert",
            "surgery_scheduled",
            "admin_alert",
            "daily_summary",
        ],
    }


def test_connection() -> bool:
    """
    Test bot connection by calling getMe API.
    Returns True if bot is reachable.
    """
    try:
        req = urllib.request.Request(
            f"{TELEGRAM_API_BASE}/getMe",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                bot_info = result.get("result", {})
                logger.info(
                    "✅ Telegram bot connected: @%s (%s)",
                    bot_info.get("username", "?"),
                    bot_info.get("first_name", "?"),
                )
                return True
            return False
    except Exception as exc:
        logger.error("Telegram connection test failed: %s", exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  SRP MediFlow — Telegram Bot Self-Test")
    print("=" * 60)
    print(f"  Bot Token  : {TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"  Chat ID    : {TELEGRAM_CHAT_ID}")
    print()

    # Test connectivity
    print("Testing connection to Telegram API...")
    ok = test_connection()
    print(f"Connection: {'✅ SUCCESS' if ok else '❌ FAILED (check token)'}")
    print()

    if ok:
        # Send a real test message
        _h = _hospital()
        print("Sending test message to hospital admin chat...")
        result = send_telegram_message(
            f"🧪 <b>SRP MediFlow — Test Message</b>\n\n"
            f"✅ Telegram bot is active!\n"
            f"🏥 {_h['hospital_name']}\n"
            f"📍 {_h.get('city', 'Kothagudem')}\n"
            f"📞 {_h['hospital_phone']}\n\n"
            "All hospital alerts will appear here.\n"
            "─────────────────────\n"
            "<i>Powered by SRP MediFlow</i>"
        )
        print(f"Result: {result}")
        print()

        # Test a sample notification
        time.sleep(1)
        print("Sending sample registration alert...")
        result2 = notify_new_registration(
            name="Test Patient",
            phone="+91 9876543210",
            issue="Fever and cold",
            doctor="Dr. Srujan",
        )
        print(f"Result: {result2}")
    else:
        print("⚠️  Could not connect. Check token and internet access.")

    print()
    print("Bot Status:", json.dumps(get_bot_status(), indent=2))
