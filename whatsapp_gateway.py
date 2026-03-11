"""
════════════════════════════════════════════════════════════════════════════════
  SRP MediFlow — WhatsApp Business API Gateway
  Hospital : Star Hospital, Kothagudem, Telangana
  Module   : whatsapp_gateway.py
  Version  : 1.0 (Placeholder / Ready-to-Activate)
════════════════════════════════════════════════════════════════════════════════

HOW TO ACTIVATE:
  1. Obtain a WhatsApp Business API key from Meta / a BSP (e.g., Twilio, Gupshup).
  2. Set environment variables:
       WHATSAPP_API_KEY       = "<your_api_key>"
       WHATSAPP_PHONE_NUMBER_ID = "<your_phone_number_id>"
       WHATSAPP_WEBHOOK_SECRET  = "<your_webhook_verify_token>"
  3. Expose the server publicly (ngrok / static IP).
  4. Register POST /api/whatsapp/webhook with Meta Developer Console.
  5. The gateway will activate automatically once WHATSAPP_API_KEY is set.

WORKFLOW (once active):
  Patient sends WhatsApp → Webhook receives → Language detected →
  Chatbot processes symptoms → Doctor suggested → Appointment created →
  Confirmation sent back via WhatsApp

LANGUAGE SUPPORT:
  English / Telugu (తెలుగు) / Hindi (हिंदी)
════════════════════════════════════════════════════════════════════════════════
"""

import os
import json
import hmac
import hashlib
import logging
from typing import Optional

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("whatsapp_gateway")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WhatsApp] %(levelname)s %(message)s",
)

# ── Configuration (loaded from environment) ───────────────────────────────────
WHATSAPP_API_KEY          = os.getenv("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE_NUMBER_ID  = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WEBHOOK_SECRET   = os.getenv("WHATSAPP_WEBHOOK_SECRET", "")  # Set in .env — no default
WHATSAPP_API_VERSION      = os.getenv("WHATSAPP_API_VERSION", "v18.0")
WHATSAPP_BASE_URL         = (
    f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
    f"/{WHATSAPP_PHONE_NUMBER_ID}/messages"
)

# Gateway is active only when the API key is provided
_GATEWAY_ACTIVE = bool(WHATSAPP_API_KEY)

if _GATEWAY_ACTIVE:
    logger.info("✅ WhatsApp gateway ACTIVE (API key found)")
else:
    logger.info("⚠️  WhatsApp gateway in PLACEHOLDER mode — set WHATSAPP_API_KEY to activate")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — LANGUAGE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

# Telugu Unicode block: U+0C00–U+0C7F
# Hindi (Devanagari): U+0900–U+097F
_TELUGU_RANGE   = (0x0C00, 0x0C7F)
_DEVANAGARI_RANGE = (0x0900, 0x097F)


def detect_language(text: str) -> str:
    """
    Detect language from text.
    Returns: 'telugu' | 'hindi' | 'english'
    """
    telugu_chars = sum(
        1 for ch in text if _TELUGU_RANGE[0] <= ord(ch) <= _TELUGU_RANGE[1]
    )
    hindi_chars = sum(
        1 for ch in text if _DEVANAGARI_RANGE[0] <= ord(ch) <= _DEVANAGARI_RANGE[1]
    )
    if telugu_chars > hindi_chars and telugu_chars > 0:
        return "telugu"
    if hindi_chars > 0:
        return "hindi"
    return "english"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — SEND MESSAGE
# ══════════════════════════════════════════════════════════════════════════════

def send_message(phone_number: str, message_text: str) -> dict:
    """
    Send a WhatsApp message to a phone number.

    Args:
        phone_number  : Recipient phone in E.164 format (e.g., "919876543210")
        message_text  : Plain text message to send

    Returns:
        dict with 'status': 'sent' | 'placeholder' | 'error'
             and optional 'message_id' or 'error' fields
    """
    phone_number = _normalise_phone(phone_number)

    if not _GATEWAY_ACTIVE:
        logger.info(
            "📤 [PLACEHOLDER] Would send to %s: %s",
            phone_number, message_text[:80]
        )
        return {
            "status":   "placeholder",
            "to":       phone_number,
            "message":  message_text,
            "note":     "WhatsApp gateway not active — set WHATSAPP_API_KEY to enable sending",
        }

    # ── Real API call (Meta Cloud API) ───────────────────────────────────────
    try:
        import urllib.request
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "to":                phone_number,
            "type":              "text",
            "text":              {"body": message_text},
        }).encode("utf-8")

        req = urllib.request.Request(
            WHATSAPP_BASE_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {WHATSAPP_API_KEY}",
                "Content-Type":  "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
            msg_id = (
                response_data.get("messages", [{}])[0].get("id", "")
            )
            logger.info("📤 Message sent to %s | id=%s", phone_number, msg_id)
            return {"status": "sent", "to": phone_number, "message_id": msg_id}

    except Exception as exc:
        logger.error("❌ send_message failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — RECEIVE MESSAGE (webhook processing)
# ══════════════════════════════════════════════════════════════════════════════

def receive_message(phone_number: str, message_text: str) -> dict:
    """
    Process an inbound WhatsApp message.

    Steps:
      1. Detect language
      2. Pass through SRP MediFlow chatbot
      3. Auto-book appointment if chatbot returns a booking record
      4. Return reply text so the webhook handler can send it back

    Args:
        phone_number  : Sender phone (E.164 or local)
        message_text  : Raw text from the patient

    Returns:
        dict with 'reply' (text to send back) and optional 'appointment' data
    """
    phone_number = _normalise_phone(phone_number)
    language     = detect_language(message_text)

    logger.info(
        "📥 Received from %s [lang=%s]: %s",
        phone_number, language, message_text[:100]
    )

    # ── Attempt chatbot processing ───────────────────────────────────────────
    try:
        from chatbot import generate_chatbot_response, get_last_booking_record, clear_last_booking_record

        # Note: chatbot uses a global state — each WhatsApp session
        # is handled sequentially. Multi-session support requires
        # upgrading chatbot.py with per-user state (future enhancement).
        state = {}

        result = generate_chatbot_response(message_text, state)
        reply  = result.get("response", _fallback_reply(language))
        new_state = result.get("state", {})

        # Check if an appointment was booked
        booking = get_last_booking_record()
        if booking:
            clear_last_booking_record()
            confirmation = _build_confirmation(booking, language)
            reply = confirmation
            return {
                "reply":       reply,
                "appointment": booking,
                "language":    language,
                "phone":       phone_number,
            }

        return {"reply": reply, "language": language, "phone": phone_number}

    except ImportError:
        logger.warning("Chatbot module not available — returning fallback reply")
        return {
            "reply":    _fallback_reply(language),
            "language": language,
            "phone":    phone_number,
        }
    except Exception as exc:
        logger.error("receive_message chatbot error: %s", exc)
        return {
            "reply":    _fallback_reply(language),
            "language": language,
            "error":    str(exc),
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — WEBHOOK VERIFICATION (Meta GET challenge)
# ══════════════════════════════════════════════════════════════════════════════

def verify_webhook_challenge(query_params: dict) -> Optional[str]:
    """
    Handle Meta's webhook verification GET request.
    Returns the hub.challenge string if the token matches, else None.
    """
    mode      = query_params.get("hub.mode", "")
    token     = query_params.get("hub.verify_token", "")
    challenge = query_params.get("hub.challenge", "")

    if mode == "subscribe" and token == WHATSAPP_WEBHOOK_SECRET:
        logger.info("✅ WhatsApp webhook verified")
        return challenge
    logger.warning("❌ WhatsApp webhook verification failed (token mismatch)")
    return None


def verify_webhook_signature(payload_bytes: bytes, x_hub_signature: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header on inbound webhook POSTs.
    Returns True if signature is valid (or if API key not yet configured).
    """
    if not WHATSAPP_API_KEY:
        return True  # Placeholder mode — skip verification

    try:
        expected = (
            "sha256="
            + hmac.new(
                WHATSAPP_WEBHOOK_SECRET.encode(),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, x_hub_signature)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — PARSE INCOMING WEBHOOK PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════

def parse_inbound_payload(payload: dict) -> list:
    """
    Parse a Meta Cloud API webhook payload and extract messages.

    Returns:
        List of dicts: [{'phone': str, 'text': str, 'timestamp': str}]
    """
    messages = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        messages.append({
                            "phone":     msg.get("from", ""),
                            "text":      msg.get("text", {}).get("body", ""),
                            "timestamp": msg.get("timestamp", ""),
                            "msg_id":    msg.get("id", ""),
                        })
    except Exception as exc:
        logger.error("parse_inbound_payload error: %s", exc)
    return messages


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _normalise_phone(phone: str) -> str:
    """Strip spaces/dashes and ensure country code for Indian numbers."""
    phone = phone.replace(" ", "").replace("-", "").replace("+", "")
    if phone.startswith("0"):
        phone = "91" + phone[1:]
    if len(phone) == 10:
        phone = "91" + phone
    return phone


def _fallback_reply(language: str) -> str:
    """Return a fallback greeting in the detected language."""
    messages = {
        "english": (
            "Hello! Welcome to Star Hospital, Kothagudem. "
            "I'm your AI health assistant. "
            "Please describe your symptoms or type 'appointment' to book a visit."
        ),
        "telugu": (
            "నమస్కారం! స్టార్ హాస్పిటల్, కొత్తగూడెంకు స్వాగతం. "
            "మీ లక్షణాలు చెప్పండి లేదా అపాయింట్‌మెంట్ బుక్ చేయడానికి 'appointment' అని లేఖించండి."
        ),
        "hindi": (
            "नमस्ते! स्टार हॉस्पिटल, कोठागुडेम में आपका स्वागत है। "
            "अपने लक्षण बताएं या अपॉइंटमेंट बुक करने के लिए 'appointment' लिखें।"
        ),
    }
    return messages.get(language, messages["english"])


def _build_confirmation(booking: dict, language: str) -> str:
    """Build appointment confirmation message in the detected language."""
    name   = booking.get("name",   "Patient")
    doctor = booking.get("doctor", "our doctor")
    time   = booking.get("appointment_time", "")
    date   = booking.get("appointment_date", "")
    slot   = f"{date} {time}".strip() or "as soon as possible"

    messages = {
        "english": (
            f"✅ Appointment confirmed!\n"
            f"Patient: {name}\n"
            f"Doctor: {doctor}\n"
            f"Slot: {slot}\n\n"
            f"📍 Star Hospital\n"
            f"Karur Vysya Bank Lane, Ganesh Basthi,\n"
            f"Kothagudem, Telangana 507101\n"
            f"📞 +91 7981971015\n\n"
            f"Please arrive 15 minutes before your appointment."
        ),
        "telugu": (
            f"✅ అపాయింట్‌మెంట్ నిర్ధారించబడింది!\n"
            f"పేషెంట్: {name}\n"
            f"డాక్టర్: {doctor}\n"
            f"సమయం: {slot}\n\n"
            f"📍 స్టార్ హాస్పిటల్, కొత్తగూడెం\n"
            f"📞 +91 7981971015"
        ),
        "hindi": (
            f"✅ अपॉइंटमेंट की पुष्टि हुई!\n"
            f"मरीज: {name}\n"
            f"डॉक्टर: {doctor}\n"
            f"समय: {slot}\n\n"
            f"📍 स्टार हॉस्पिटल, कोठागुडेम\n"
            f"📞 +91 7981971015"
        ),
    }
    return messages.get(language, messages["english"])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — GATEWAY STATUS
# ══════════════════════════════════════════════════════════════════════════════

def get_gateway_status() -> dict:
    """Return current WhatsApp gateway configuration status."""
    return {
        "active":        _GATEWAY_ACTIVE,
        "mode":          "live" if _GATEWAY_ACTIVE else "placeholder",
        "api_version":   WHATSAPP_API_VERSION,
        "phone_id_set":  bool(WHATSAPP_PHONE_NUMBER_ID),
        "webhook_secret_set": bool(WHATSAPP_WEBHOOK_SECRET),
        "languages_supported": ["english", "telugu", "hindi"],
        "activation_instructions": (
            "Set WHATSAPP_API_KEY and WHATSAPP_PHONE_NUMBER_ID environment variables."
            if not _GATEWAY_ACTIVE else "Gateway is active."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# QUICK SELF-TEST (run as script)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== WhatsApp Gateway Self-Test ===")
    print("Status:", json.dumps(get_gateway_status(), indent=2))
    print()

    # Language detection tests
    tests = [
        ("Hello I have fever",                      "english"),
        ("నాకు జ్వరం వస్తోంది",                      "telugu"),
        ("मुझे बुखार है",                             "hindi"),
    ]
    print("Language detection:")
    for text, expected in tests:
        detected = detect_language(text)
        status = "✅" if detected == expected else "❌"
        print(f"  {status} '{text[:30]}' → {detected} (expected: {expected})")

    print()
    # receive_message test (placeholder mode)
    result = receive_message("+91 7981971015", "Hello I need an appointment")
    print("receive_message result:", json.dumps(result, indent=2, ensure_ascii=False))

    result2 = send_message("+91 7981971015", "Test message from SRP MediFlow")
    print("send_message result:", json.dumps(result2, indent=2, ensure_ascii=False))
