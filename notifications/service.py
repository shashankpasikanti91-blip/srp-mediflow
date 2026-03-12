"""
notifications/service.py — SRP MediFlow Notification Service
=============================================================
Central dispatcher for all hospital notification events.

Usage:
    from notifications.service import NotificationService
    svc = NotificationService(tenant_slug="star_hospital")
    svc.appointment_confirmed(patient_name="Ravi", ...)

Provider priority:
  1. active_provider setting from DB
  2. If telegram is enabled → TelegramProvider
  3. If whatsapp is enabled and configured → WhatsAppProvider
  4. Else → NullProvider (logs to notification_logs with status=skipped)

All sends are logged to notification_logs table automatically.
All sends are non-blocking (fire-and-forget in daemon threads).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger("notifications.service")

# ── Lazy imports (providers) ──────────────────────────────────────────────────
from notifications.base_provider import BaseNotificationProvider, NullProvider
from notifications.telegram_provider import TelegramProvider
from notifications.whatsapp_provider import WhatsAppProvider


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load settings from DB
# ─────────────────────────────────────────────────────────────────────────────

def _load_settings_from_db(tenant_slug: str) -> dict:
    """Load notification_settings rows for tenant into a flat dict."""
    try:
        from db import get_connection
        conn = get_connection()
        if not conn:
            return {}
        cur = conn.cursor()
        cur.execute(
            "SELECT setting_key, setting_value FROM notification_settings "
            "WHERE tenant_slug = %s OR tenant_slug = ''",
            (tenant_slug,)
        )
        rows = cur.fetchall()
        conn.close()
        # tenant-specific rows override global defaults
        settings: dict = {}
        for key, val in rows:
            settings[key] = val
        return settings
    except Exception as exc:
        logger.warning(f"[NotificationService] Could not load settings: {exc}")
        return {}


def _log_notification(tenant_slug: str, channel: str, event_type: str,
                       recipient: str, message_preview: str,
                       status: str, provider_response: str = "") -> None:
    """Write a row to notification_logs. Non-blocking; errors silently swallowed."""
    try:
        from db import get_connection
        conn = get_connection()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notification_logs
                (tenant_slug, channel, event_type, recipient, message_preview,
                 status, provider_response)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (tenant_slug, channel, event_type, recipient,
             message_preview[:300], status, str(provider_response)[:300])
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug(f"[NotificationService] log write failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
class NotificationService:
    """
    Hospital notification orchestrator.

    tenant_slug: identifies this hospital in the DB (e.g. "star_hospital")
    config:      optional override dict (use DB settings if omitted)
    """

    def __init__(self, tenant_slug: str = "", config: dict | None = None):
        self.tenant_slug = tenant_slug
        self._cfg        = config if config is not None else _load_settings_from_db(tenant_slug)
        self._provider   = self._build_provider()

    # ── Provider factory ──────────────────────────────────────────────────────
    def _build_provider(self) -> BaseNotificationProvider:
        cfg = self._cfg
        active = cfg.get("active_provider", "telegram").lower().strip()

        if active == "telegram":
            p = TelegramProvider(
                token   = cfg.get("telegram_bot_token", ""),
                chat_id = cfg.get("telegram_chat_id", ""),
            )
            if p.is_configured():
                logger.info("[NotificationService] Using Telegram provider")
                return p
            # Fall through to WhatsApp if Telegram not configured
            logger.warning("[NotificationService] Telegram chosen but not configured — trying WhatsApp")

        if active in ("whatsapp", "telegram"):   # fallback also tries WA
            p_wa = WhatsAppProvider(config=cfg)
            if p_wa.is_configured():
                logger.info("[NotificationService] Using WhatsApp provider")
                return p_wa

        logger.warning("[NotificationService] No provider configured — using NullProvider")
        return NullProvider()

    # ── Internal dispatcher ───────────────────────────────────────────────────
    def _dispatch(self, event_type: str, recipient: str, message: str) -> None:
        """Send via active provider and log result — in a daemon thread."""
        def _worker():
            result = self._provider.send_safe(recipient, message)
            status = result.get("status", "failed")
            resp   = str(result.get("error") or result.get("message_id") or "")
            _log_notification(
                tenant_slug=self.tenant_slug,
                channel=self._provider.name,
                event_type=event_type,
                recipient=recipient,
                message_preview=message[:200],
                status=status,
                provider_response=resp,
            )

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # ── Default recipient: hospital Telegram chat ─────────────────────────────
    @property
    def _default_recipient(self) -> str:
        return self._cfg.get("telegram_chat_id", "") or \
               self._cfg.get("owner_contact_number", "")

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC EVENT METHODS
    # ─────────────────────────────────────────────────────────────────────────

    def appointment_confirmed(self, patient_name: str, date_str: str,
                               time_str: str, doctor_name: str,
                               hospital_name: str, hospital_phone: str,
                               recipient: str = "") -> None:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your appointment is confirmed.\n"
            f"📅 Date: {date_str}\n"
            f"⏰ Time: {time_str}\n"
            f"👨‍⚕️ Doctor: {doctor_name}\n\n"
            f"Please arrive 10 minutes early.\n📞 {hospital_phone}"
        )
        self._dispatch("appointment_created", recipient or self._default_recipient, msg)

    def prescription_created(self, patient_name: str, doctor_name: str,
                              pdf_url: str, hospital_name: str,
                              hospital_phone: str, recipient: str = "") -> None:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your digital prescription from Dr. {doctor_name} is ready.\n"
            f"📄 [View Prescription]({pdf_url})\n\n"
            f"Take medicines as prescribed.\n📞 {hospital_phone}"
        )
        self._dispatch("prescription_created", recipient or self._default_recipient, msg)

    def lab_result_ready(self, patient_name: str, test_name: str,
                          hospital_name: str, hospital_phone: str,
                          recipient: str = "") -> None:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, your lab report for *{test_name}* is now ready.\n"
            f"Please collect from the lab counter.\n📞 {hospital_phone}"
        )
        self._dispatch("lab_result_ready", recipient or self._default_recipient, msg)

    def follow_up_reminder(self, patient_name: str, doctor_name: str,
                            follow_up_date: str, hospital_name: str,
                            hospital_phone: str, recipient: str = "") -> None:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, friendly reminder — your follow-up is due.\n"
            f"👨‍⚕️ Dr. {doctor_name} advised follow-up on {follow_up_date}.\n\n"
            f"Call {hospital_phone} to book your appointment."
        )
        self._dispatch("follow_up_reminder", recipient or self._default_recipient, msg)

    def discharge_completed(self, patient_name: str, discharge_date: str,
                             follow_up_date: str, hospital_name: str,
                             hospital_phone: str, recipient: str = "") -> None:
        msg = (
            f"🏥 *{hospital_name}*\n\n"
            f"Dear {patient_name}, you have been successfully discharged on {discharge_date}.\n"
            f"Follow discharge instructions carefully.\n"
            f"Next follow-up: {follow_up_date}\n📞 {hospital_phone}"
        )
        self._dispatch("discharge_completed", recipient or self._default_recipient, msg)

    def daily_summary(self, hospital_name: str, opd_count: int, ipd_count: int,
                       collections: str, pending_bills: int, notif_count: int,
                       recipient: str = "") -> None:
        today = date.today().strftime("%d %b %Y")
        msg = (
            f"📊 *{hospital_name} — Daily Report ({today})*\n\n"
            f"🧑‍⚕️ OPD: {opd_count}\n"
            f"🏥 IPD: {ipd_count}\n"
            f"💰 Collections: ₹{collections}\n"
            f"⚠️ Pending Bills: {pending_bills}\n"
            f"🔔 Notifications Sent: {notif_count}\n\n"
            f"_SRP MediFlow_"
        )
        self._dispatch("end_of_day_summary", recipient or self._default_recipient, msg)

    def custom_alert(self, event_type: str, message: str, recipient: str = "") -> None:
        """Send a custom/admin-created message."""
        self._dispatch(event_type, recipient or self._default_recipient, message)

    # ── Test notification ─────────────────────────────────────────────────────
    def test_send(self, recipient: str = "", channel: str = "",
                  message: str = "") -> dict:
        """
        Synchronous test send. Returns result dict immediately.
        Used by /api/settings/notifications/test endpoint.

        Args:
            recipient: Telegram chat_id or phone number (defaults to configured chat)
            channel:   Ignored (provider is already selected at build time) — kept
                       for API compatibility with the handler that passes it.
            message:   Optional custom message body; defaults to a standard test msg.
        """
        # If a specific channel override was requested and we're using the wrong
        # provider, rebuild with that channel's env creds (best-effort).
        if channel and channel != self._provider.name:
            from notifications.telegram_provider import TelegramProvider as _TGProv
            import os as _os
            if channel == "telegram":
                self._provider = _TGProv(
                    token   = _os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    chat_id = _os.getenv("TELEGRAM_CHAT_ID", ""),
                )

        if not self._provider.is_configured():
            return {"status": "failed", "error": f"{self._provider.name} not configured — check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env"}
        msg = message or (
            "🔔 *SRP MediFlow Test Notification*\n\n"
            f"Provider: {self._provider.name}\n"
            f"Tenant: {self.tenant_slug or 'default'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "_If you received this, notifications are working!_"
        )
        result = self._provider.send_safe(recipient or self._default_recipient, msg)
        _log_notification(
            tenant_slug=self.tenant_slug,
            channel=self._provider.name,
            event_type="test",
            recipient=recipient or self._default_recipient,
            message_preview=msg[:200],
            status=result.get("status", "failed"),
            provider_response=str(result),
        )
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions (backward compatibility with founder_alerts.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def send_notification(event_type: str, message: str, recipient: str = "",
                       tenant_slug: str = "") -> None:
    """One-liner fire-and-forget. Loads config from DB automatically."""
    svc = NotificationService(tenant_slug=tenant_slug)
    svc.custom_alert(event_type, message, recipient)


def get_notification_log_count_today(tenant_slug: str = "") -> int:
    """Return count of notifications sent today for the tenant."""
    try:
        from db import get_connection
        conn = get_connection()
        if not conn:
            return 0
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM notification_logs "
            "WHERE (tenant_slug=%s OR tenant_slug='') "
            "  AND created_at::date = CURRENT_DATE "
            "  AND status = 'sent'",
            (tenant_slug,)
        )
        count = cur.fetchone()[0]
        conn.close()
        return int(count)
    except Exception:
        return 0
