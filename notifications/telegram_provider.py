"""
notifications/telegram_provider.py — SRP MediFlow Telegram Notification Provider
==================================================================================
Active provider. Uses Telegram Bot API to deliver messages.

Credentials:
  TELEGRAM_BOT_TOKEN  — bot token from @BotFather
  TELEGRAM_CHAT_ID    — group or personal chat ID to send to

Priority of credential resolution:
  1. Passed-in config dict (from DB notification_settings)
  2. Environment variables
  3. Falls back to existing telegram_bot.py constants
"""

from __future__ import annotations

import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import threading
from typing import Optional

from notifications.base_provider import BaseNotificationProvider

logger = logging.getLogger("notifications.telegram")

# Fallback credentials (used only when DB config is empty)
_ENV_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN",   "8535042281:AAG6koMQ17LVJPigw8TNzJq5fAGZNEYObkE")
_ENV_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID",     "7144152487")
_API_TIMEOUT = 8  # seconds


class TelegramProvider(BaseNotificationProvider):
    """
    Telegram Bot API notification provider.

    Usage:
        provider = TelegramProvider(token="...", chat_id="...")
        result   = provider.send_safe("7144152487", "Hello!")
    """

    name = "telegram"

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token   = token or _ENV_TOKEN
        self.chat_id = chat_id or _ENV_CHAT_ID

    # ── Configuration check ───────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(self.token and self.token != "" and
                    self.chat_id and self.chat_id != "")

    # ── Core send ─────────────────────────────────────────────────────────────
    def send(self, recipient: str, message: str, **kwargs) -> dict:
        """
        Send message to a Telegram chat.

        Args:
            recipient: Telegram chat ID (uses self.chat_id if blank)
            message:   MarkdownV2-safe or plain text message

        Returns:
            {"status": "sent"|"failed", "message_id": int, "raw": dict}
        """
        target_chat = recipient or self.chat_id
        if not target_chat:
            return {"status": "failed", "error": "No chat_id available"}

        url  = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id":    target_chat,
            "text":       message,
            "parse_mode": "Markdown"
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=_API_TIMEOUT) as resp:
                raw = json.loads(resp.read().decode())
                if raw.get("ok"):
                    msg_id = raw.get("result", {}).get("message_id", 0)
                    logger.info(f"[Telegram] Sent to {target_chat}: message_id={msg_id}")
                    return {"status": "sent", "message_id": msg_id, "raw": raw}
                else:
                    logger.warning(f"[Telegram] API error: {raw}")
                    return {"status": "failed", "error": str(raw), "raw": raw}
        except urllib.error.HTTPError as exc:
            logger.error(f"[Telegram] HTTP error {exc.code}: {exc.reason}")
            return {"status": "failed", "error": f"HTTP {exc.code}: {exc.reason}"}
        except Exception as exc:
            logger.error(f"[Telegram] Exception: {exc}")
            return {"status": "failed", "error": str(exc)}

    # ── Background (non-blocking) send ────────────────────────────────────────
    def send_async(self, recipient: str, message: str, **kwargs) -> None:
        """Fire-and-forget — sends in a daemon thread."""
        t = threading.Thread(
            target=self.send_safe,
            args=(recipient, message),
            kwargs=kwargs,
            daemon=True,
        )
        t.start()

    # ── Broadcast: same message to multiple chat IDs ──────────────────────────
    def broadcast(self, chat_ids: list[str], message: str) -> list[dict]:
        results = []
        for chat in chat_ids:
            results.append(self.send_safe(chat, message))
        return results

    # ── Named event helpers ───────────────────────────────────────────────────
    def send_appointment_confirmation(self, patient_name: str, date_str: str,
                                      time_str: str, doctor_name: str,
                                      hospital_name: str, hospital_phone: str,
                                      recipient: str = "") -> dict:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your appointment is confirmed.\n"
            f"📅 Date: {date_str}\n"
            f"⏰ Time: {time_str}\n"
            f"👨‍⚕️ Doctor: {doctor_name}\n\n"
            f"Please arrive 10 minutes early.\n"
            f"📞 {hospital_phone}"
        )
        return self.send_safe(recipient or self.chat_id, msg)

    def send_prescription_share(self, patient_name: str, doctor_name: str,
                                 pdf_url: str, hospital_name: str,
                                 hospital_phone: str, recipient: str = "") -> dict:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your prescription from Dr. {doctor_name} is ready.\n"
            f"📄 [View Prescription]({pdf_url})\n\n"
            f"Follow prescribed medicines carefully.\n"
            f"📞 {hospital_phone} for any queries."
        )
        return self.send_safe(recipient or self.chat_id, msg)

    def send_lab_ready(self, patient_name: str, test_name: str,
                        hospital_name: str, hospital_phone: str,
                        recipient: str = "") -> dict:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your lab report for *{test_name}* is ready.\n"
            f"Please collect from the lab counter.\n"
            f"📞 {hospital_phone}"
        )
        return self.send_safe(recipient or self.chat_id, msg)

    def send_follow_up_reminder(self, patient_name: str, doctor_name: str,
                                  follow_up_date: str, hospital_name: str,
                                  hospital_phone: str, recipient: str = "") -> dict:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your follow-up is due today.\n"
            f"👨‍⚕️ Dr. {doctor_name} advised follow-up on {follow_up_date}.\n\n"
            f"Call {hospital_phone} to book your appointment."
        )
        return self.send_safe(recipient or self.chat_id, msg)

    def send_daily_summary(self, hospital_name: str, date_str: str,
                            opd_count: int, ipd_count: int, collections: str,
                            pending_bills: int, notif_count: int,
                            recipient: str = "") -> dict:
        msg = (
            f"📊 *{hospital_name} — Daily Report ({date_str})*\n\n"
            f"🧑‍⚕️ OPD Patients: {opd_count}\n"
            f"🏥 IPD Patients:  {ipd_count}\n"
            f"💰 Collections:   ₹{collections}\n"
            f"⚠️ Pending Bills: {pending_bills}\n"
            f"🔔 Notifications: {notif_count}\n\n"
            f"_Powered by SRP MediFlow_"
        )
        return self.send_safe(recipient or self.chat_id, msg)
