"""
====================================================================
  SRP MEDIFLOW - White-Label Hospital Configuration
  Product : SRP MediFlow – Hospital Management System
  Version : 2.0 (Multi-Hospital Platform)
====================================================================

HOW TO DEPLOY FOR A NEW CLIENT:
  1. Copy this file — keep one copy per hospital installation.
  2. Update SECTION 1 (identity, phone, logo, location).
  3. Update SECTION 3 (brand colors to match the hospital's logo).
  4. Update SECTION 4 (welcome messages in local languages).
  5. No server changes needed — everything reads from this file.

EXAMPLE CLIENTS:
  Client 1: Star Hospital        – Hyderabad
  Client 2: Sai Care Hospital    – Khammam
  Client 3: Apollo Clinic        – Warangal
====================================================================
"""

# ------------------------------------------------------------------
# SECTION 1: HOSPITAL IDENTITY
# Change these fields for every new hospital client.
# ------------------------------------------------------------------
HOSPITAL_NAME     = "Star Hospital"
HOSPITAL_NAME_TE  = "స్టార్ హాస్పిటల్"      # Telugu
HOSPITAL_NAME_HI  = "स्टार अस्पताल"           # Hindi

HOSPITAL_LOCATION = "Kothagudem, Telangana"
HOSPITAL_ADDRESS  = (
    "Karur Vysya Bank Lane, Ganesh Basthi, "
    "Kothagudem, Telangana 507101, India"
)
HOSPITAL_PHONE    = "+91 7981971015"           # Main reception number
HOSPITAL_EMAIL    = ""
HOSPITAL_WEBSITE  = ""
HOSPITAL_LOGO     = ""                         # Path or URL to logo image
                                               # e.g. "/static/logo.png"
HOSPITAL_TAGLINE  = "24x7 Emergency Medical Services Available"

# Legacy aliases (keep for backwards compatibility with chatbot.py)
LOCATION      = HOSPITAL_LOCATION
ADDRESS       = HOSPITAL_ADDRESS
CONTACT_PHONE = HOSPITAL_PHONE
CONTACT_EMAIL = HOSPITAL_EMAIL
WEBSITE       = HOSPITAL_WEBSITE
TAGLINE       = HOSPITAL_TAGLINE

# ------------------------------------------------------------------
# SECTION 2: SUPPORTED LANGUAGES
# Options: 'english', 'telugu', 'hindi', 'kannada', 'tamil'
# ------------------------------------------------------------------
SUPPORTED_LANGUAGES = ['english', 'telugu', 'hindi']
DEFAULT_LANGUAGE    = 'english'

# ------------------------------------------------------------------
# SECTION 3: BRAND COLORS
# Used in dashboards and the patient chatbot UI.
# ------------------------------------------------------------------
PRIMARY_COLOR   = "#1a73e8"    # Header / button background
SECONDARY_COLOR = "#00b896"    # Accent / success highlight
BRAND_TEXT      = "#ffffff"    # Text on colored backgrounds

# Legacy aliases
BRAND_PRIMARY   = PRIMARY_COLOR
BRAND_SECONDARY = SECONDARY_COLOR

# ------------------------------------------------------------------
# SECTION 4: CHATBOT WELCOME MESSAGES (per language)
# ------------------------------------------------------------------
WELCOME_MESSAGES = {
    'english': (
        f"Hello! Welcome to {HOSPITAL_NAME}, {HOSPITAL_LOCATION}. "
        f"{HOSPITAL_TAGLINE}. "
        "I'm your SRP MediFlow AI assistant. How can I help you today?"
    ),
    'telugu': (
        f"నమస్కారం! {HOSPITAL_NAME}కు స్వాగతం. "
        "24x7 అత్యవసర వైద్య సేవలు అందుబాటులో ఉన్నాయి. "
        "నేను మీ SRP MediFlow AI సహాయకుడిని. మీకు ఎలా సహాయపడగలను?"
    ),
    'hindi': (
        f"नमस्ते! {HOSPITAL_NAME} में आपका स्वागत है। "
        "24x7 आपातकालीन चिकित्सा सेवाएं उपलब्ध हैं। "
        "मैं आपका SRP MediFlow AI सहायक हूँ। मैं आपकी कैसे मदद कर सकता हूँ?"
    ),
}

# ------------------------------------------------------------------
# SECTION 5: HOSPITAL SERVICES
# ------------------------------------------------------------------
SERVICES = [
    "OPD Consultation",
    "Orthopedics (Dr. Srujan – DNB Ortho FIJR)",
    "General Medicine & Diabetology (Dr. K. Ramyanadh)",
    "General Surgery (Dr. B. Ramachandra Nayak)",
    "Dental Consultant",
    "ENT Consultant",
    "X-Ray & Imaging (9 AM - 7 PM)",
    "Lab / Blood Tests (8 AM - 6 PM)",
    "Pharmacy",
    "Emergency (24x7)",
]

# ------------------------------------------------------------------
# SECTION 6: EMERGENCY / AMBULANCE
# ------------------------------------------------------------------
EMERGENCY_NUMBER = "108"
AMBULANCE_NUMBER = HOSPITAL_PHONE

# ------------------------------------------------------------------
# SECTION 7: HOSPITAL TYPE & CAPACITY
# Used to configure feature flags per deployment.
# ------------------------------------------------------------------
HOSPITAL_TYPE     = "General Hospital"    # General Hospital / Clinic / Diagnostic Centre
BED_CAPACITY      = 50                    # Approximate bed count
DEPARTMENTS       = [
    "General Medicine",
    "Diabetology",
    "Orthopedics",
    "General Surgery",
    "Dental",
    "ENT",
    "Gynecology",
    "Pediatrics",
    "Radiology",
    "Pathology",
    "Pharmacy",
    "Emergency",
]

# ------------------------------------------------------------------
# SECTION 8: DOCTOR DIRECTORY
# Real doctor records for Star Hospital deployment
# ------------------------------------------------------------------
DOCTORS = [
    {
        "name":            "Dr. Srujan",
        "specialization":  "Orthopedics",
        "qualifications":  "DNB Ortho FIJR",
        "registration_no": "87679",
        "department":      "Orthopedics",
    },
    {
        "name":            "Dr. K. Ramyanadh",
        "specialization":  "General Medicine / Diabetology",
        "qualifications":  "General Medicine (UK), Diabetology",
        "registration_no": "111431",
        "department":      "General Medicine",
    },
    {
        "name":            "Dr. B. Ramachandra Nayak",
        "specialization":  "General Surgery",
        "qualifications":  "M.B.B.S., M.S.",
        "registration_no": "13888",
        "department":      "General Surgery",
    },
]

# ------------------------------------------------------------------
# MULTI-HOSPITAL DEPLOYMENT REFERENCE
# ------------------------------------------------------------------
# CLIENT 1 — Star Hospital, Hyderabad
#   HOSPITAL_NAME     = "Star Hospital"
#   HOSPITAL_LOCATION = "Hyderabad, Telangana"
#   HOSPITAL_PHONE    = "040-12345678"
#   PRIMARY_COLOR     = "#1a73e8"
#
# CLIENT 2 — Sai Care Hospital, Khammam
#   HOSPITAL_NAME     = "Sai Care Hospital"
#   HOSPITAL_LOCATION = "Khammam, Telangana"
#   HOSPITAL_PHONE    = "08742-XXXXXX"
#   PRIMARY_COLOR     = "#16a34a"
#
# CLIENT 3 — Apollo Clinic, Warangal
#   HOSPITAL_NAME     = "Apollo Clinic"
#   HOSPITAL_LOCATION = "Warangal, Telangana"
#   HOSPITAL_PHONE    = "0870-XXXXXXX"
#   PRIMARY_COLOR     = "#003087"
#
# Each client gets their own copy of this file.
# One codebase, multiple deployments.
# ------------------------------------------------------------------
