"""
SRP MediFlow — Notifications Package
======================================
Separates founder/platform alerts from hospital-level operational notifications.

Public surface:
  from notifications.service         import NotificationService, send_notification
  from notifications.telegram_provider import TelegramProvider
  from notifications.whatsapp_provider import WhatsAppProvider
  from notifications.founder_alerts   import send_founder_alert
"""

from notifications.service import NotificationService, send_notification

__all__ = [
    "NotificationService",
    "send_notification",
]
