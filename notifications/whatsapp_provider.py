"""
notifications/whatsapp_provider.py — SRP MediFlow WhatsApp Notification Provider
==================================================================================
PLACEHOLDER-READY implementation.
WhatsApp API token is NOT available yet — this provider is safe to have installed.

Enable later by:
  1. Add credentials in Admin > Notification Settings
  2. Set active_provider = 'whatsapp' in notification_settings table
  3. No code changes required.

Supports:
  - Twilio WhatsApp Business API
  - Direct Meta/360dialog-style API (configurable via api_base_url)
  - Any provider with a simple POST body and bearer token auth

Config keys (from notification_settings table):
  whatsapp_enabled         true / false
  whatsapp_provider_name   twilio / meta / 360dialog / custom
  whatsapp_api_base_url    e.g. https://api.twilio.com/2010-04-01/…
  whatsapp_api_key         bearer token or account SID:auth_token
  whatsapp_sender_number   from phone number / WhatsApp Business ID
  whatsapp_template_id     optional — template name for regulated messages
"""

from __future__ import annotations

import json
import logging
import base64
import urllib.request
import urllib.error
from typing import Optional

from notifications.base_provider import BaseNotificationProvider

logger = logging.getLogger("notifications.whatsapp")

_API_TIMEOUT = 10  # seconds


class WhatsAppProvider(BaseNotificationProvider):
    """
    WhatsApp Business API notification provider.
    Safe to use even when credentials are missing — returns clear errors.

    Initialise with config dict (from notification_settings DB rows):
        provider = WhatsAppProvider(config={...})
    """

    name = "whatsapp"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.enabled        = str(cfg.get("whatsapp_enabled", "false")).lower() == "true"
        self.provider_name  = cfg.get("whatsapp_provider_name", "twilio").strip().lower()
        self.api_base_url   = (cfg.get("whatsapp_api_base_url") or "").strip()
        self.api_key        = (cfg.get("whatsapp_api_key") or "").strip()
        self.sender_number  = (cfg.get("whatsapp_sender_number") or "").strip()
        self.template_id    = (cfg.get("whatsapp_template_id") or "").strip()

    # ── Configuration check ───────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(
            self.enabled and
            self.api_base_url and
            self.api_key and
            self.sender_number
        )

    # ── Core send ─────────────────────────────────────────────────────────────
    def send(self, recipient: str, message: str, **kwargs) -> dict:
        """
        Send a WhatsApp message to a recipient phone number.

        recipient: E.164 format phone (e.g. +919876543210)
        message:   plain text body

        Returns:
            {"status": "sent"|"failed"|"skipped", ...}
        """
        if not self.is_configured():
            reason = self._missing_config_reason()
            logger.warning(f"[WhatsApp] Not configured: {reason}")
            return {"status": "skipped", "error": reason}

        # Dispatch to correct provider API
        if self.provider_name == "twilio":
            return self._send_twilio(recipient, message)
        elif self.provider_name in ("meta", "360dialog", "custom"):
            return self._send_generic(recipient, message)
        else:
            return self._send_generic(recipient, message)

    # ── Twilio WhatsApp Send ──────────────────────────────────────────────────
    def _send_twilio(self, to: str, body: str) -> dict:
        """
        Twilio Conversations / Messaging API
        api_base_url example:
          https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json
        api_key format:  ACCOUNT_SID:AUTH_TOKEN
        sender_number:   whatsapp:+14155238886
        """
        try:
            credentials = base64.b64encode(self.api_key.encode()).decode()
            payload = urllib.parse.urlencode({   # type: ignore[attr-defined]
                "From": f"whatsapp:{self.sender_number}" if not self.sender_number.startswith("whatsapp") else self.sender_number,
                "To":   f"whatsapp:{to}" if not to.startswith("whatsapp") else to,
                "Body": body,
            }).encode("utf-8")

            req = urllib.request.Request(
                self.api_base_url,
                data=payload,
                method="POST"
            )
            req.add_header("Authorization", f"Basic {credentials}")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(req, timeout=_API_TIMEOUT) as resp:
                raw = json.loads(resp.read().decode())
                sid = raw.get("sid", "")
                logger.info(f"[WhatsApp/Twilio] Sent to {to}: SID={sid}")
                return {"status": "sent", "message_sid": sid, "raw": raw}

        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode() if exc else ""
            logger.error(f"[WhatsApp/Twilio] HTTP {exc.code}: {body_text[:200]}")
            return {"status": "failed", "error": f"HTTP {exc.code}", "detail": body_text[:200]}
        except Exception as exc:
            logger.error(f"[WhatsApp/Twilio] Exception: {exc}")
            return {"status": "failed", "error": str(exc)}

    # ── Generic/Meta/360dialog Send ───────────────────────────────────────────
    def _send_generic(self, to: str, body: str) -> dict:
        """
        Generic WhatsApp Cloud API / 360dialog style.
        POST to api_base_url with JSON body and Bearer auth.
        """
        try:
            payload = json.dumps({
                "messaging_product": "whatsapp",
                "to":   to.lstrip("+"),
                "type": "text",
                "text": {"body": body},
            }).encode("utf-8")

            req = urllib.request.Request(
                self.api_base_url,
                data=payload,
                method="POST"
            )
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("Content-Type",  "application/json")

            with urllib.request.urlopen(req, timeout=_API_TIMEOUT) as resp:
                raw = json.loads(resp.read().decode())
                logger.info(f"[WhatsApp/Generic] Sent to {to}")
                return {"status": "sent", "raw": raw}

        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode() if exc else ""
            logger.error(f"[WhatsApp/Generic] HTTP {exc.code}: {body_text[:200]}")
            return {"status": "failed", "error": f"HTTP {exc.code}", "detail": body_text[:200]}
        except Exception as exc:
            logger.error(f"[WhatsApp/Generic] Exception: {exc}")
            return {"status": "failed", "error": str(exc)}

    # ── Helper ────────────────────────────────────────────────────────────────
    def _missing_config_reason(self) -> str:
        parts = []
        if not self.enabled:
            parts.append("WhatsApp disabled in settings")
        if not self.api_base_url:
            parts.append("api_base_url missing")
        if not self.api_key:
            parts.append("api_key/token missing")
        if not self.sender_number:
            parts.append("sender_number missing")
        return "; ".join(parts) if parts else "not configured"
