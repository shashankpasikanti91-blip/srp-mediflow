"""
notifications/base_provider.py — SRP MediFlow Notification Base Provider
=========================================================================
Abstract base class for all notification channels.
Concrete implementations: TelegramProvider, WhatsAppProvider.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger("notifications.base")


class BaseNotificationProvider(ABC):
    """
    Abstract notification provider.
    All providers must implement send() and is_configured().
    """

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the provider has all required credentials."""
        ...

    @abstractmethod
    def send(self, recipient: str, message: str, **kwargs) -> dict:
        """
        Send a notification message.

        Args:
            recipient: phone number, chat_id, or identifier
            message:   plain text or markdown message body

        Returns:
            dict with keys: status (sent|failed|skipped), error (optional), raw (optional)
        """
        ...

    def send_safe(self, recipient: str, message: str, **kwargs) -> dict:
        """
        Wrapper around send() that catches all exceptions.
        Guarantees a result dict is always returned.
        """
        if not self.is_configured():
            logger.warning(f"[{self.name}] Provider not configured — skipping send")
            return {"status": "skipped", "error": f"{self.name} provider not configured"}
        try:
            return self.send(recipient, message, **kwargs)
        except Exception as exc:
            logger.error(f"[{self.name}] send_safe caught exception: {exc}")
            return {"status": "failed", "error": str(exc)}


class NullProvider(BaseNotificationProvider):
    """No-op provider used when no channel is configured."""

    name = "none"

    def is_configured(self) -> bool:
        return False

    def send(self, recipient: str, message: str, **kwargs) -> dict:
        logger.info(f"[NullProvider] No channel active — notification not sent to {recipient}")
        return {"status": "skipped", "error": "no active provider configured"}
