"""
HOSPITAL CHATBOT - Simple, Smart, Multilingual (English / Telugu / Hindi)
Supports white-label deployment - change hospital_config.py for each client.
"""

import re
from datetime import datetime, timedelta

# Load hospital identity from config (falls back gracefully if config missing)
try:
    from hospital_config import (
        HOSPITAL_NAME, HOSPITAL_NAME_TE, HOSPITAL_NAME_HI,
        WELCOME_MESSAGES, SUPPORTED_LANGUAGES
    )
except ImportError:
    HOSPITAL_NAME    = "Star Hospital"
    HOSPITAL_NAME_TE = "స్టార్ హాస్పిటల్"
    HOSPITAL_NAME_HI = "स्टार अस्पताल"
    WELCOME_MESSAGES = {
        'english': f"Hello! Welcome to Star Hospital. 🏥 I'm your AI assistant. How can I help?",
        'telugu':  f"నమస్కారం! స్టార్ హాస్పిటల్‌కు స్వాగతం. 🏥 మీకు ఎలా సహాయపడగలను?",
        'hindi':   f"नमस्ते! स्टार अस्पताल में आपका स्वागत है। 🏥 मैं आपकी कैसे मदद कर सकता हूँ?",
    }
    SUPPORTED_LANGUAGES = ['english', 'telugu', 'hindi']

DOCTORS = {
    'srujan': {
        'name': 'Dr. Srujan',
        'specialty': 'Orthopedics',
        'qualifications': 'DNB Ortho FIJR',
        'timings': 'Monday to Saturday, 5:00 PM - 8:30 PM',
        'timings_te': 'సోమవారం నుండి శనివారం, సాయంత్రం 5:00 - 8:30 PM',
        'timings_hi': 'सोमवार से शनिवार, शाम 5:00 - 8:30 PM',
        'hours': [(17, 20.5)],
        'days': [0, 1, 2, 3, 4, 5],  # Monday-Saturday
        'keywords': [
            # English
            'orthopedic', 'ortho', 'srujan', 'knee pain', 'knee', 'joint pain', 'joint',
            'fracture', 'bone', 'back pain', 'shoulder pain', 'shoulder', 'ankle',
            'sports injury', 'neck pain', 'back', 'bone and joint', 'dnb ortho',
            # Telugu
            'నొప్పి', 'పెనుపు', 'చేతి', 'కాలు', 'ఎముక', 'పెయిన్', 'బ్యాక్', 'తుదకు', 'మోకాలు',
            'ఆర్థోపెడిక్', 'సృజన్',
            # Hindi
            'हड्डी', 'जोड़', 'घुटना', 'घुटने', 'कमर दर्द', 'पीठ दर्द', 'कंधा', 'फ्रैक्चर',
            'हाथ दर्द', 'पैर दर्द', 'ओर्थोपेडिक'
        ]
    },
    'ramyanadh': {
        'name': 'Dr. K. Ramyanadh',
        'specialty': 'General Medicine & Diabetology',
        'qualifications': 'General Medicine (UK), Diabetology',
        'timings': 'All days: 10:00 AM - 1:00 PM, 6:00 PM - 9:00 PM',
        'timings_te': 'ప్రతిరోజు: 10:00 AM - 1:00 PM, 6:00 PM - 9:00 PM',
        'timings_hi': 'सभी दिन: 10:00 AM - 1:00 PM, 6:00 PM - 9:00 PM',
        'hours': [(10, 13), (18, 21)],
        'days': [0, 1, 2, 3, 4, 5, 6],  # All days
        'keywords': [
            # English
            'general medicine', 'general', 'ramyanadh', 'ramyana', 'fever', 'cold', 'cough',
            'headache', 'bp', 'blood pressure', 'diabetes', 'diabetology', 'sugar',
            'infection', 'weakness', 'vomiting', 'stomach pain', 'loose motion', 'diarrhea',
            'body pain', 'fatigue', 'thyroid',
            # Telugu
            'జ్వరం', 'దగ్గు', 'తల నొప్పి', 'సంక్రమణ', 'ఆరోగ్య', 'మందు', 'జలుబు', 'వాంతి',
            'మధుమేహం', 'రామ్యనాధ్',
            # Hindi
            'बुखार', 'जुकाम', 'खांसी', 'सर्दी', 'सिर दर्द', 'मधुमेह', 'शुगर',
            'कमजोरी', 'उल्टी', 'दस्त', 'पेट दर्द', 'बीपी', 'संक्रमण', 'बीमार',
            'थकान', 'थायराइड'
        ]
    },
    'ramachandra': {
        'name': 'Dr. B. Ramachandra Nayak',
        'specialty': 'General Surgery',
        'qualifications': 'M.B.B.S., M.S.',
        'timings': 'Monday to Saturday, 9:00 AM - 1:00 PM, 5:00 PM - 8:00 PM',
        'timings_te': 'సోమవారం నుండి శనివారం, 9:00 AM - 1:00 PM, 5:00 PM - 8:00 PM',
        'timings_hi': 'सोमवार से शनिवार, 9:00 AM - 1:00 PM, 5:00 PM - 8:00 PM',
        'hours': [(9, 13), (17, 20)],
        'days': [0, 1, 2, 3, 4, 5],  # Monday-Saturday
        'keywords': [
            # English
            'general surgery', 'surgery', 'surgical', 'ramachandra', 'nayak', 'appendix',
            'hernia', 'gallbladder', 'gall bladder', 'gallstone', 'abscess', 'wound',
            'operation', 'piles', 'fissure', 'fistula', 'lump', 'swelling',
            # Telugu
            'శస్త్రచికిత్స', 'ఆపరేషన్', 'రామచంద్ర', 'నాయక్', 'వాపు',
            # Hindi
            'सर्जरी', 'ऑपरेशन', 'सूजन', 'गांठ', 'हर्निया', 'पथरी', 'बवासीर',
            'अपेंडिक्स', 'घाव', 'रामचंद्र'
        ]
    },
    'dental_ent': {
        'name': 'Dental & ENT',
        'specialty': 'Dental & ENT',
        'qualifications': 'Visiting Consultants',
        'timings': 'By appointment – call +91 7981971015',
        'timings_te': 'అపాయింట్‌మెంట్ ద్వారా – +91 7981971015 కు కాల్ చేయండి',
        'timings_hi': 'अपॉइंटमेंट द्वारा – +91 7981971015 पर कॉल करें',
        'hours': [(9, 18)],
        'days': [0, 1, 2, 3, 4, 5],  # Monday-Saturday (visiting)
        'keywords': [
            # English
            'dental', 'dentist', 'tooth', 'teeth', 'toothache', 'tooth pain', 'cavity',
            'ent', 'ear', 'nose', 'throat', 'tonsil', 'sinus', 'hearing', 'ear pain',
            'nose bleed', 'snoring', 'gum', 'gums',
            # Telugu
            'దంత', 'పళ్ళు', 'పళ్ళ నొప్పి', 'చెవి', 'ముక్కు', 'గొంతు', 'టాన్సిల్',
            # Hindi
            'दांत', 'दांत दर्द', 'कान', 'नाक', 'गला', 'टॉन्सिल', 'साइनस',
            'दंत', 'दंत चिकित्सक', 'कान दर्द', 'गले में खराश'
        ]
    }
}


# Telugu translations
TELUGU_RESPONSES = {
    'welcome': 'నమస్కారం! నేను స్టార్ హాస్పిటల్ AI సహాయకుడు. మీకు ఎలా సహాయపడగలను?',
    'tell_symptom': 'మీ లక్షణం చెప్పండి లేదా సహాయం కోసం చెప్పండి.',
    'book_confirm': 'ఆపాయింట్‌మెంట్ నిర్ధారించబడింది! దయచేసి నిర్ణీత సమయానికి 10 నిమిషాల ముందు వచ్చండి.',
    'ask_time': 'ఏ సమయం సరిపోతుంది? (ఉదా: 6:00 PM)',
    'ask_name': 'దయచేసి మీ పూర్తి పేరు చెప్పండి:',
    'ask_age': 'మీ వయస్సు? (సంఖ్య చెప్పండి)',
    'ask_phone': 'దయచేసి 10-అంకెల ఫోన్ నంబర్ చెప్పండి:',
    'ask_aadhar': 'దయచేసి 12-అంకెల ఆధార్ సంఖ్య చెప్పండి:',
    'ask_issue': 'మీ ఆరోగ్య సమస్య ఏమిటి?',
    'greet_morning': 'శుభోదయం! మీకు ఎలా సహాయపడగలను?',
    'greet_afternoon': 'శుభ మధ్యాహ్నం! మీకు ఎలా సహాయపడగలను?',
    'greet_evening': 'శుభ సాయంత్రం! మీకు ఎలా సహాయపడగలను?',
    'default': 'మీ లక్షణం చెప్పండి. నేను ఆపాయింట్‌మెంట్ బుక్ చేయడంలో సహాయం చేయగలను.',
}

# Hindi translations
HINDI_RESPONSES = {
    'welcome': 'नमस्कार! मैं स्टार अस्पताल AI सहायक हूँ। मैं आपकी कैसे मदद कर सकता हूँ?',
    'tell_symptom': 'अपने लक्षण बताएं या मदद मांगें।',
    'book_confirm': 'नियुक्ति की पुष्टि की गई! कृपया निर्धारित समय से 10 मिनट पहले आएं।',
    'ask_time': 'कौन सा समय आपके लिए सुविधाजनक है? (उदा: 6:00 PM)',
    'ask_name': 'कृपया अपना पूरा नाम बताएं:',
    'ask_age': 'आपकी आयु? (संख्या बताएं)',
    'ask_phone': 'कृपया 10-अंकीय फोन नंबर बताएं:',
    'ask_aadhar': 'कृपया 12-अंकीय आधार संख्या बताएं:',
    'ask_issue': 'आपकी स्वास्थ्य समस्या क्या है?',
    'greet_morning': 'सुप्रभात! मैं आपकी कैसे मदद कर सकता हूँ?',
    'greet_afternoon': 'दोपहर की शुभकामनाएं! मैं आपकी कैसे मदद कर सकता हूँ?',
    'greet_evening': 'शाम की शुभकामनाएं! मैं आपकी कैसे मदद कर सकता हूँ?',
    'default': 'अपने लक्षण बताएं। मैं नियुक्ति बुक करने में मदद कर सकता हूँ।',
}

# Global state for booking
last_booking_record = None

state = {
    'booking_active': False,
    'doctor_selected': None,
    'name': None,
    'age': None,
    'phone': None,
    'issue': None,
    'aadhar': None,
    'appointment_time': None,
    'appointment_date': None,  # 'YYYY-MM-DD'
    'appointment_day': None,   # 'Monday', 'Tuesday', etc.
    'lang': 'english'          # Persisted language across conversation
}

def reset_state():
    global state
    # Preserve language when resetting
    prev_lang = state.get('lang', 'english')
    state = {
        'booking_active': False,
        'doctor_selected': None,
        'name': None,
        'age': None,
        'phone': None,
        'issue': None,
        'aadhar': None,
        'appointment_time': None,
        'appointment_date': None,
        'appointment_day': None,
        'lang': prev_lang
    }

def set_chatbot_state(new_state):
    """Set chatbot state from external source (e.g., server session)"""
    global state
    state = new_state.copy() if new_state else state

def get_chatbot_state():
    """Get current chatbot state"""
    return state.copy()

def set_last_booking(record):
    global last_booking_record
    last_booking_record = record.copy() if record else None

def get_last_booking_record():
    return last_booking_record.copy() if last_booking_record else None

def clear_last_booking_record():
    global last_booking_record
    last_booking_record = None

def detect_language(text):
    """Detect language from text"""
    for char in text:
        if '\u0C00' <= char <= '\u0C7F':
            return 'telugu'
        elif '\u0900' <= char <= '\u097F':
            return 'hindi'
    return 'english'

def transliterate_name_to_english(name):
    """Simple transliteration for common Telugu/Hindi names to English for database storage"""
    # Telugu to English mappings for common names
    telugu_to_english = {
        'రమేష్': 'Ramesh', 'రామ': 'Ram', 'కృష్ణ': 'Krishna', 'రాజ': 'Raj',
        'వెంకట్': 'Venkat', 'సునీల్': 'Sunil', 'అనిల్': 'Anil', 'విజయ్': 'Vijay',
        'రవి': 'Ravi', 'మహేష్': 'Mahesh', 'సురేష్': 'Suresh', 'గణేష్': 'Ganesh',
        'నాగేష్': 'Nagesh', 'దినేష్': 'Dinesh', 'ఉమేష్': 'Umesh', 'నితీష్': 'Nitish',
        'అశ్వేనీ': 'Ashwini', 'లక్ష్మీ': 'Lakshmi', 'పార్వతీ': 'Parvati', 'రాధా': 'Radha',
        'సీతా': 'Sita', 'గీతా': 'Gita', 'నీతా': 'Nita', 'సునీతా': 'Sunita'
    }
    
    # Hindi to English mappings
    hindi_to_english = {
        'रमेश': 'Ramesh', 'राम': 'Ram', 'कृष्ण': 'Krishna', 'राज': 'Raj',
        'सुनील': 'Sunil', 'अनिल': 'Anil', 'विजय': 'Vijay', 'रवि': 'Ravi',
        'महेश': 'Mahesh', 'सुरेश': 'Suresh', 'गणेश': 'Ganesh'
    }
    
    # Check if name is in our mapping
    if name in telugu_to_english:
        return telugu_to_english[name]
    elif name in hindi_to_english:
        return hindi_to_english[name]
    else:
        # For unmapped names, return as-is or try basic transliteration
        # For now, return the original name
        return name

def find_doctor(text):
    """Find doctor from user input - supports both English and Telugu keywords.
    Checks longer/more specific keywords first to avoid false matches."""
    text_low = text.lower()

    # Build a flat list of (keyword, doctor_id) sorted by keyword length DESC
    # so specific phrases like 'chest pain' match before generic 'pain'
    all_keywords = []
    for doctor_id, doctor_info in DOCTORS.items():
        for keyword in doctor_info['keywords']:
            all_keywords.append((keyword, doctor_id))
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    for keyword, doctor_id in all_keywords:
        if keyword.lower() in text_low or keyword in text:
            return doctor_id
    return None

def extract_time(text):
    """Extract time from text like '6pm', '6:00 PM', '6 pm', '6.00 pm', etc"""
    text_clean = text.lower()
    # Remove periods from p.m. and a.m. to normalize
    text_clean = text_clean.replace('p.m.', 'pm').replace('a.m.', 'am').replace('p.m', 'pm').replace('a.m', 'am')
    text_clean = text_clean.replace('p m', 'pm').replace('a m', 'am')
    
    # Try to match: digits(:digits) followed by am/pm
    match = re.search(r'(\d{1,2}):?(\d{0,2})\s*([ap]m)', text_clean)
    if match:
        h = match.group(1)
        m = match.group(2) or '00'
        p = match.group(3).upper()
        return f"{h}:{m} {p}"
    return None

def extract_day(text):
    """Extract day name from text like 'tuesday', 'monday', etc"""
    text_lower = text.lower()
    
    # Day names mapping
    day_names = {
        'monday': 'Monday', 'mon': 'Monday',
        'tuesday': 'Tuesday', 'tue': 'Tuesday', 'tues': 'Tuesday',
        'wednesday': 'Wednesday', 'wed': 'Wednesday',
        'thursday': 'Thursday', 'thu': 'Thursday', 'thurs': 'Thursday',
        'friday': 'Friday', 'fri': 'Friday',
        'saturday': 'Saturday', 'sat': 'Saturday',
        'sunday': 'Sunday', 'sun': 'Sunday'
    }
    
    # Check for day names
    for day_key, day_name in day_names.items():
        if day_key in text_lower:
            return day_name
    
    return None

def extract_day_and_time(text):
    """Extract day name and time from text like 'tuesday 6pm' or 'book monday 5:30 PM'"""
    text_lower = text.lower()
    
    # Day names mapping
    day_names = {
        'monday': 'Monday', 'mon': 'Monday',
        'tuesday': 'Tuesday', 'tue': 'Tuesday', 'tues': 'Tuesday',
        'wednesday': 'Wednesday', 'wed': 'Wednesday',
        'thursday': 'Thursday', 'thu': 'Thursday', 'thurs': 'Thursday',
        'friday': 'Friday', 'fri': 'Friday',
        'saturday': 'Saturday', 'sat': 'Saturday',
        'sunday': 'Sunday', 'sun': 'Sunday'
    }
    
    # Extract day
    found_day = None
    for day_key, day_name in day_names.items():
        if day_key in text_lower:
            found_day = day_name
            break
    
    # Extract time
    time_slot = extract_time(text)
    
    return found_day, time_slot

def time_to_24h(time_str):
    """Convert '6:00 PM' to 18.0 (24-hour format)"""
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        period = match.group(3)
        
        if period == 'PM' and h != 12:
            h += 12
        elif period == 'AM' and h == 12:
            h = 0
        
        return h + (m / 60)
    return None

def is_time_available(time_str, doctor_id):
    """Check if time is within doctor's available hours"""
    if not time_str or not doctor_id:
        return False
    
    doctor = DOCTORS.get(doctor_id)
    if not doctor:
        return False
    
    time_24h = time_to_24h(time_str)
    if time_24h is None:
        return False
    
    for start, end in doctor['hours']:
        if start <= time_24h <= end:
            return True
    return False

def extract_appointment_date(text):
    """Extract appointment date from patient input.
    Understands: today, tomorrow, day after tomorrow, weekday names (English).
    Returns (date_str 'YYYY-MM-DD', day_name 'Monday', display 'Monday, 09 March 2026')
    or (None, None, None) if no date found.
    """
    text_lower = text.lower()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if 'day after tomorrow' in text_lower:
        d = today + timedelta(days=2)
    elif 'tomorrow' in text_lower or 'tmrw' in text_lower or 'tmr' in text_lower or 'రేపు' in text or 'kal' in text_lower or 'కల' in text_lower or 'कल' in text:
        d = today + timedelta(days=1)
    elif 'today' in text_lower or 'ఈ రోజు' in text or 'ఇవాళ' in text or 'आज' in text or 'आजा' in text:
        d = today
    else:
        # Try full/abbreviated weekday names - English + Hindi
        day_map = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tues': 1, 'tue': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thurs': 3, 'thu': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6,
            # Hindi day names
            'सोमवार': 0, 'सूमवार': 0,
            'मंगलवार': 1, 'मंगल': 1,
            'बुधवार': 2, 'बुध': 2,
            'गुरुवार': 3, 'गुरु': 3, 'बृहस्पति': 3,
            'शुक्रवार': 4, 'शुक्र': 4,
            'शनिवार': 5, 'शनि': 5,
            'रविवार': 6, 'रवि': 6,
        }
        found_day_num = None
        for day_key, day_num in day_map.items():
            if re.search(r'\b' + day_key + r'\b', text_lower):
                found_day_num = day_num
                break
        if found_day_num is None:
            return None, None, None
        today_weekday = today.weekday()
        days_ahead = found_day_num - today_weekday
        if days_ahead <= 0:
            days_ahead += 7
        d = today + timedelta(days=days_ahead)

    date_str = d.strftime('%Y-%m-%d')
    day_name = d.strftime('%A')
    display = d.strftime('%A, %d %B %Y')
    return date_str, day_name, display

def is_day_available_for_doctor(date_str, doctor_id):
    """Return True if the doctor works on the weekday of the given date."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        weekday = d.weekday()  # 0=Monday, 6=Sunday
        doctor = DOCTORS.get(doctor_id)
        if not doctor or 'days' not in doctor:
            return True
        return weekday in doctor['days']
    except Exception:
        return True

def format_date_display(date_str):
    """Format '2026-03-09' → 'Monday, 09 March 2026'"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.strftime('%A, %d %B %Y')
    except Exception:
        return date_str

def extract_number(text, min_val=None, max_val=None):
    """Extract number from text"""
    # Check if user is referencing previous phone number
    if any(w in text.lower() for w in ['same', 'above', 'previous', 'earlier', 'same as before']):
        # Return a special marker to use previous phone
        return -1  # Marker for "use previous"
    
    match = re.search(r'\d+', text)
    if match:
        num = int(match.group(0))
        if min_val and num < min_val:
            return None
        if max_val and num > max_val:
            return None
        return num
    return None

def extract_word(text):
    """Extract a name/word from text - handles Telugu/Hindi/English"""
    # Words to skip - English only
    skip_words_en = {'can', 'i', 'the', 'a', 'at', 'to', 'for', 'is', 'ok', 'book', 
                     'appointment', 'yes', 'no', 'sure', 'my', 'name', 'please',
                     'tell', 'me', 'your', 'what', 'how', 'when', 'where', 'which',
                     'am', 'pm', 'do', 'you', 'will', 'would', 'should', 'could', 'or'}
    
    # Telugu words to skip
    skip_words_te = {'నా', 'పేరు', 'మీ', 'నేను', 'అవును', 'లేదు', 'ఓకే', 'దయచేసి', 'చెప్పండి'}
    
    # Hindi words to skip
    skip_words_hi = {'मेरा', 'नाम', 'आप', 'मैं', 'हाँ', 'नहीं', 'ठीक', 'कृपया', 'बताएं'}
    
    words = text.split()
    for word in words:
        # Clean punctuation
        clean = word.replace('?', '').replace(',', '').replace('.', '').replace('!', '')
        clean_lower = clean.lower()
        
        # Skip if too short
        if len(clean) < 2:
            continue
            
        # Skip if it's a number
        if clean.isdigit():
            continue
            
        # Skip if looks like time (has colon)
        if ':' in clean:
            continue
        
        # Skip common words based on script
        if clean_lower in skip_words_en or clean in skip_words_te or clean in skip_words_hi:
            continue
        
        # Found a valid name!
        return clean
    
    return None

def has_booking_intent(text):
    """Check if user wants to book"""
    text_lower = text.lower()
    
    # English booking keywords
    english_keywords = ['book', 'appointment', 'register', 'can i', 'want to', 'want', 'schedule']
    
    # Telugu booking keywords
    telugu_keywords = ['బుక్', 'బుక', 'చేద్దాం', 'చేయాలి', 'నిర్ధారించండి', 'రిజిస్టర్', 'పదవీ', 'కావాలి', 'అందాలి', 'అపాయింట్‌మెంట్']
    
    # Hindi booking keywords
    hindi_keywords = ['बुक', 'नियुक्ति', 'चाहता', 'चाहती', 'करना', 'रजिस्टर',
                     'अपोइंटमेंट', 'अपॉइंटमेंट', 'दिखाना', 'दिखाना है', 'दिखाना होगा',
                     'डॉक्टर से मिलना', 'मिलना है', 'इलाज', 'इलाज कराना']
    
    # Check English
    if any(w in text_lower for w in english_keywords):
        return True
    
    # Check Telugu
    if any(w in text for w in telugu_keywords):
        return True
    
    # Check Hindi
    if any(w in text for w in hindi_keywords):
        return True
    
    return False

def get_response_by_key(key, lang='english'):
    """Get response in specific language"""
    if lang == 'telugu':
        return TELUGU_RESPONSES.get(key, TELUGU_RESPONSES.get('default', ''))
    elif lang == 'hindi':
        return HINDI_RESPONSES.get(key, HINDI_RESPONSES.get('default', ''))
    else:  # english
        return 'Tell me your symptom or what you need help with. I can help you book appointments with our doctors.'

def respond(user_input, lang='english'):
    """Main chatbot logic with language support"""
    # Persist language: if user sends non-numeric content, update stored lang
    # (numbers/phone/aadhar keep the previous language)
    detected = detect_language(user_input)
    if detected != 'english':
        lang = detected
        state['lang'] = lang
    elif state.get('lang', 'english') != 'english' and not re.search(r'^[\d\s:APMapm]+$', user_input.strip()):
        # Only override back to english if pure English text, not numbers/time
        lang = state.get('lang', 'english')
    else:
        lang = state.get('lang', lang)

    text_low = user_input.lower()
    doctor = find_doctor(user_input)
    time_slot = extract_time(user_input)
    is_booking = has_booking_intent(user_input)
    
    # ---- Telugu greetings / farewells ----
    telugu_bye = ['సెలవు', 'బై', 'వెళ్తున్నాను', 'థాంక్యూ']
    telugu_greet = ['నమస్కారం', 'హలో', 'హాయ్', 'నమస్తే']
    telugu_thanks = ['ధన్యవాదాలు', 'థాంక్స్', 'థాంక్యూ']
    hindi_bye = ['अलविदा', 'बाय', 'धन्यवाद', 'शुक्रिया']
    hindi_greet = ['नमस्ते', 'नमस्कार', 'हेलो', 'हाय']
    hindi_thanks = ['धन्यवाद', 'शुक्रिया', 'थैंक्यू']

    # Handle casual greetings/responses with friendly tone
    # First check for conversation ending phrases (more specific)
    if text_low in ['no thanks', 'no thank you', 'thats all', 'that\'s all', 'bye', 'goodbye', 'see you later', 'see you'] or \
       any(phrase in text_low for phrase in ['no thanks', 'no thank you', 'thats all', 'that\'s all', 'bye', 'goodbye', 'see you']) or \
       any(w in user_input for w in telugu_bye) or any(w in user_input for w in hindi_bye):
        if lang == 'telugu':
            return f"సెలవు! {HOSPITAL_NAME_TE}కు వచ్చినందుకు ధన్యవాదాలు. మీ ఆరోగ్యం బాగుండాలి! 😊 ఎప్పుడైనా సహాయం కోసం తిరిగి రండి."
        elif lang == 'hindi':
            return f"अलविदा! {HOSPITAL_NAME_HI} आने के लिए धन्यवाद। स्वस्थ रहें! 😊 जब भी जरूरत हो, हम यहाँ हैं।"
        elif any(phrase in text_low for phrase in ['bye', 'goodbye', 'see you']):
            return f"Goodbye! Thank you for visiting {HOSPITAL_NAME}. Take care and stay healthy! 😊 We're here whenever you need us."
        else:
            return f"Perfect! Thank you for using {HOSPITAL_NAME} services. Have a wonderful day and take care! 😊 Feel free to contact us anytime you need medical assistance."

    # Telugu thanks
    elif any(w in user_input for w in telugu_thanks) and lang == 'telugu':
        return "మీకు స్వాగతం! సహాయపడటం నాకు సంతోషం. మరింత సహాయం కావాలంటే చెప్పండి. 😊"

    # Hindi thanks
    elif any(w in user_input for w in hindi_thanks) and lang == 'hindi':
        return "आपका स्वागत है! मदद करना मुझे खुशी है। कोई और सहायता चाहिए तो बताएं। 😊"

    # Telugu greetings
    elif any(w in user_input for w in telugu_greet) or (lang == 'telugu' and text_low in ['hi', 'hello', 'hey']):
        hour = datetime.now().hour
        if hour < 12:
            return f"శుభోదయం! 🌅 {HOSPITAL_NAME_TE}కు స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?"
        elif hour < 17:
            return f"శుభ మధ్యాహ్నం! 🌤️ {HOSPITAL_NAME_TE}కు స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?"
        else:
            return f"శుభ సాయంత్రం! 🌙 {HOSPITAL_NAME_TE}కు స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?"

    # Hindi greetings
    elif any(w in user_input for w in hindi_greet) or (lang == 'hindi' and text_low in ['hi', 'hello', 'hey']):
        hour = datetime.now().hour
        if hour < 12:
            return f"सुप्रभात! 🌅 {HOSPITAL_NAME_HI} में आपका स्वागत है। मैं आपकी कैसे मदद कर सकता हूँ?"
        elif hour < 17:
            return f"नमस्ते! 🌤️ {HOSPITAL_NAME_HI} में आपका स्वागत है। मैं आपकी कैसे मदद कर सकता हूँ?"
        else:
            return f"शुभ संध्या! 🌙 {HOSPITAL_NAME_HI} में आपका स्वागत है। मैं आपकी कैसे मदद कर सकता हूँ?"
    
    # Then handle other casual responses
    elif text_low in ['thanks', 'thank you', 'ok', 'okay', 'sure', 'yes', 'no', 'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
                    'థాంక్యూ', 'ఓకే', 'అవును', 'లేదు', 'హలో'] or \
       any(word in text_low for word in ['how are you', 'how r you', 'whats up', 'sup', 'hey there', 'hello there', 'hi buddy', 'hello buddy', 'hey buddy', 'whats going on', 'what\'s going on']) or \
       any(text_low.startswith(word) for word in ['hi ', 'hello ', 'hey ', 'good morning', 'good afternoon', 'good evening']):
        if text_low in ['thanks', 'thank you', 'థాంక్యూ']:
            return "You're very welcome! I'm always happy to help. Is there anything else you need assistance with? 😊"
        elif text_low in ['ok', 'okay', 'sure', 'ఓకే', 'అవును']:
            return "Great! I'm here to help. What would you like to know about? 😊"
        elif text_low in ['good morning', 'morning'] or text_low.startswith('good morning'):
            return "Good morning! ☀️ Hope you're having a wonderful day! How may I assist you today?"
        elif text_low in ['good afternoon', 'afternoon'] or text_low.startswith('good afternoon'):
            return "Good afternoon! 🌤️ How may I help you today?"
        elif text_low in ['good evening', 'evening'] or text_low.startswith('good evening'):
            return "Good evening! 🌙 How can I assist you this evening?"
        elif 'how are you' in text_low or 'how r you' in text_low:
            return "I'm doing great, thank you for asking! 😊 I'm here to help you. What brings you to Star Hospital today? Do you need a doctor's appointment?"
        elif 'whats going on' in text_low or "what's going on" in text_low or 'whats up' in text_low or 'sup' in text_low:
            return "I'm here to help you with Star Hospital services! 😊 Are you looking to book an appointment with a doctor, get information about our services, or do you have a specific health concern I can assist with?"
        else:
            return WELCOME_MESSAGES.get('english', f"Hello! Welcome to {HOSPITAL_NAME}. 🏥 I'm your AI assistant here to help you book appointments and answer health questions. How can I assist you today! 😊")
    
    # If not in booking mode
    if not state['booking_active']:
        
        # Special case: Just "book" or "appointment" when doctor already selected
        if (is_booking or text_low == 'book') and state['doctor_selected'] and not state['name']:
            # User wants to proceed with already-selected doctor
            state['booking_active'] = True
            doc = DOCTORS[state['doctor_selected']]
            timings = doc['timings_te'] if lang == 'telugu' else doc['timings']
            if state['appointment_time'] and state['appointment_date']:
                # Already have both, ask for name
                disp = format_date_display(state['appointment_date'])
                return f"Perfect! Let's confirm your booking with {doc['name']} on {disp} at {state['appointment_time']}.\n\nPlease tell me your full name:"
            else:
                # Ask for date and time
                return f"Let's book with {doc['name']} ({doc['specialty']}).\n\nAvailable: {timings}\n\nWhat date and time works for you? (e.g., Tomorrow 12:00 PM, Monday 6:00 PM)"
        
        # Special case: If user just provides a time slot when we have a doctor selected from previous message
        if time_slot and state['doctor_selected'] and not state['name']:
            # User is continuing the booking conversation with a time
            state['booking_active'] = True
            if not is_time_available(time_slot, state['doctor_selected']):
                doc = DOCTORS[state['doctor_selected']]
                timings = doc['timings_te'] if lang == 'telugu' else doc['timings']
                return f"Sorry, {time_slot} is not available.\n\nAvailable: {timings}\n\nWhat time works for you?"
            state['appointment_time'] = time_slot
            # Also capture date if mentioned in the same message
            _ds, _dn, _dd = extract_appointment_date(user_input)
            if _ds:
                if not is_day_available_for_doctor(_ds, state['doctor_selected']):
                    doc_inner = DOCTORS[state['doctor_selected']]
                    timings_inner = doc_inner['timings_te'] if lang == 'telugu' else doc_inner['timings']
                    return f"Time {state['appointment_time']} noted. However, {doc_inner['name']} is not available on {_dn}.\n\nAvailable: {timings_inner}\n\nPlease choose a different day:"
                state['appointment_date'] = _ds
                state['appointment_day'] = _dn
            doc = DOCTORS[state['doctor_selected']]
            if state['appointment_date']:
                disp = format_date_display(state['appointment_date'])
                return f"Perfect! {disp} at {state['appointment_time']} confirmed.\n\nPlease tell me your full name:"
            else:
                return f"Time {state['appointment_time']} noted.\n\nWhat date? (e.g., Today, Tomorrow, Monday)"
        
        # Case 1: User mentions symptom + wants to book + gives time
        if doctor and is_booking and time_slot:
            # VALIDATE TIME
            if not is_time_available(time_slot, doctor):
                doc = DOCTORS[doctor]
                timings = doc['timings_te'] if lang == 'telugu' else doc['timings']
                return f"Sorry, {time_slot} is not available.\n\nAvailable: {timings}\n\nWhat time works for you?"
            
            state['booking_active'] = True
            state['doctor_selected'] = doctor
            state['appointment_time'] = time_slot
            # Also capture date if mentioned in the same message
            _ds, _dn, _dd = extract_appointment_date(user_input)
            if _ds:
                if not is_day_available_for_doctor(_ds, doctor):
                    doc = DOCTORS[doctor]
                    timings_inner = doc['timings_te'] if lang == 'telugu' else doc['timings']
                    return f"Time {time_slot} noted. However, {doc['name']} is not available on {_dn}.\n\nAvailable: {timings_inner}\n\nWhat date works for you? (e.g., Tomorrow, Monday)"
                state['appointment_date'] = _ds
                state['appointment_day'] = _dn
            doc = DOCTORS[doctor]
            if state['appointment_date']:
                disp = format_date_display(state['appointment_date'])
                return f"Great! Booking {doc['name']} ({doc['specialty']}) on {disp} at {time_slot}.\n\nPlease tell me your full name:"
            else:
                return f"Great! Let's book with {doc['name']} ({doc['specialty']}) at {state['appointment_time']}.\n\nWhat date? (e.g., Today, Tomorrow, Monday)"
        
        # Case 2: User mentions symptom + wants to book (no time)
        elif doctor and is_booking and not time_slot:
            state['booking_active'] = True
            state['doctor_selected'] = doctor
            doc = DOCTORS[doctor]
            timings = doc['timings_te'] if lang == 'telugu' else doc['timings']
            if lang == 'telugu':
                return f"మీకు {doc['name']} ({doc['specialty']}) తో అపాయింట్‌మెంట్ బుక్ చేస్తాను.\n\nఉపలబ్ధ: {timings}\n\nఏ తేదీ మరియు సమయం? (ఉదా: రేపు 12:00 PM, సోమవారం 6:00 PM)"
            elif lang == 'hindi':
                return f"मैं {doc['name']} ({doc['specialty']}) के साथ अपॉइंटमेंट बुक करता हूँ।\n\nउपलब्ध: {timings}\n\nकौन सी तारीख और समय? (उदा: कल 12:00 PM, सोमवार 6:00 PM)"
            else:
                return f"Let's book with {doc['name']} ({doc['specialty']}).\n\nAvailable: {timings}\n\nWhat date and time works for you? (e.g., Tomorrow 12:00 PM, Monday 6:00 PM)"
        
        # Case 3: User asks about doctor/symptom (no booking intent - but remember the doctor)
        elif doctor and not is_booking:
            state['doctor_selected'] = doctor  # Remember the doctor for next message
            doc = DOCTORS[doctor]
            if lang == 'telugu':
                timings = doc.get('timings_te', doc['timings'])
                return f"నేను {doc['name']} ({doc['specialty']})ని సిఫారసు చేస్తున్నాను.\n\nఉపలబ్ధ: {timings}\n\n'బుక్' చెప్పండి లేదా మీకు సరిపడిన సమయం చెప్పండి."
            elif lang == 'hindi':
                timings = doc.get('timings_hi', doc['timings'])
                return f"मैं {doc['name']} ({doc['specialty']}) की सिफारिश करता हूँ।\n\nउपलब्ध: {timings}\n\n'बुक' कहें या अपना पसंदीदा समय बताएं।"
            else:
                timings = doc['timings']
                return f"I recommend {doc['name']} ({doc['specialty']}).\n\nAvailable: {timings}\n\nSay 'Book' or just tell me your preferred time to book an appointment."
        
        # Case 3.5: User wants to book but hasn't mentioned a specific doctor/symptom yet
        elif is_booking and not doctor:
            # Ask which doctor or what's the issue
            if lang == 'telugu':
                return "మీ సమస్య ఏమిటో చెప్పండి లేదా ఎటువంటి డాక్టర్ అవసరం? (ఉదాహరణ: జ్వరం, పెయిన్, సర్దీ)"
            elif lang == 'hindi':
                return "अपनी समस्या बताएं या किस डॉक्टर की जरूरत है? (उदाहरण: बुखार, दर्द, सर्दी)"
            else:
                return "Tell me what the issue is or which doctor you need. (Example: Fever, Pain, Cold)"

        
        # Case 4: User asks about X-Ray
        elif 'xray' in text_low or 'x-ray' in text_low or 'x ray' in text_low or 'ఎక్స్ రే' in text_low:
            return "X-Ray Service:\nAvailable: 9:00 AM - 7:00 PM\nLast registration: 6:30 PM\n\nClick 'Register OPD' to book."
        
        # Case 5: User asks about Lab
        elif 'lab' in text_low or 'blood' in text_low or 'test' in text_low or 'బ్లడ్' in text_low:
            return "Lab Services:\nAvailable: 8:00 AM - 6:00 PM\n\nClick 'Register OPD' to book."
        
        # Case 6: Default response
        else:
            if lang == 'telugu':
                return "మీ లక్షణం చెప్పండి లేదా సహాయం కోసం చెప్పండి. నేను డాక్టర్‌ల కోసం ఆపాయింట్‌మెంట్‌లను బుక్ చేయడానికి సహాయం చేయగలను."
            elif lang == 'hindi':
                return "अपने लक्षण बताएं या मदद मांगें। मैं डॉक्टरों के साथ नियुक्ति बुक करने में मदद कर सकता हूँ।"
            else:
                return "Tell me your symptom or what you need help with. I can help you book appointments with our doctors."
    
    # If in booking mode - collect details step by step
    if state['booking_active']:
        doc = DOCTORS[state['doctor_selected']]
        
        # Inside booking mode - show language-appropriate timings
        if not state['appointment_time'] or not state['appointment_date']:
            time_slot = extract_time(user_input)
            date_str, day_name, date_display = extract_appointment_date(user_input)
            if lang == 'telugu':
                timings = doc.get('timings_te', doc['timings'])
            elif lang == 'hindi':
                timings = doc.get('timings_hi', doc['timings'])
            else:
                timings = doc['timings']

            # --- Validate and store time ---
            if time_slot and not state['appointment_time']:
                if not is_time_available(time_slot, state['doctor_selected']):
                    if lang == 'telugu':
                        return f"క్షమించండి, {time_slot} అందుబాటులో లేదు.\n\nఉపలబ్ధ: {timings}\n\nవేరే సమయం చెప్పండి:"
                    elif lang == 'hindi':
                        return f"क्षमा करें, {time_slot} उपलब्ध नहीं है।\n\nउपलब्ध: {timings}\n\nकृपया अलग समय चुनें:"
                    else:
                        return f"Sorry, {time_slot} is outside {doc['name']}'s hours.\n\nAvailable: {timings}\n\nPlease choose a different time:"
                state['appointment_time'] = time_slot

            # --- Validate and store date ---
            if date_str and not state['appointment_date']:
                if not is_day_available_for_doctor(date_str, state['doctor_selected']):
                    if lang == 'telugu':
                        return f"క్షమించండి, {doc['name']} {day_name}న అందుబాటులో లేరు.\n\nఉపలబ్ధ: {timings}\n\nవేరే రోజు చెప్పండి:"
                    elif lang == 'hindi':
                        return f"क्षमा करें, {doc['name']} {day_name} को उपलब्ध नहीं हैं।\n\nउपलब्ध: {timings}\n\nकृपया अलग दिन चुनें:"
                    else:
                        return f"Sorry, {doc['name']} is not available on {day_name}.\n\nAvailable: {timings}\n\nPlease choose a different day:"
                state['appointment_date'] = date_str
                state['appointment_day'] = day_name

            # --- Both collected → proceed to name ---
            if state['appointment_time'] and state['appointment_date']:
                disp = format_date_display(state['appointment_date'])
                if lang == 'telugu':
                    return f"సరిగ్గా! {disp}, సమయం {state['appointment_time']}.\n\nదయచేసి మీ పూర్తి పేరు చెప్పండి (కనీసం 3 అక్షరాలు):"
                elif lang == 'hindi':
                    return f"बढ़िया! {disp} को {state['appointment_time']} निश्चित किया गया।\n\nकृपया अपना पूरा नाम बताएं (कम से कम 3 अक्षर):"
                else:
                    return f"Perfect! Appointment set for {disp} at {state['appointment_time']}.\n\nNow, please tell me your full name (at least 3 characters):"

            # --- Time set, date missing → ask for date ---
            if state['appointment_time'] and not state['appointment_date']:
                if lang == 'telugu':
                    return f"సమయం {state['appointment_time']} నమోదు చేయబడింది.\n\nఏ తేదీన రావాలి? (ఉదా: 'రేపు', 'సోమవారం', 'ఈ రోజు')"
                elif lang == 'hindi':
                    return f"समय {state['appointment_time']} दर्ज किया गया।\n\nकिस तारीख को आना है? (उदा: कल, सोमवार, आज)"
                else:
                    return f"Time noted: {state['appointment_time']}.\n\nWhat date would you like? (e.g., Today, Tomorrow, Monday)"

            # --- Date set, time missing → ask for time ---
            if state['appointment_date'] and not state['appointment_time']:
                disp = format_date_display(state['appointment_date'])
                if lang == 'telugu':
                    return f"తేదీ {disp} నమోదు చేయబడింది.\n\nఏ సమయం? (ఉదా: 12:00 PM)\n\nఉపలబ్ధ: {timings}"
                elif lang == 'hindi':
                    return f"तारीख {disp} दर्ज की गई।\n\nकौन सा समय? (उदा: 12:00 PM)\n\nउपलब्ध: {timings}"
                else:
                    return f"Date noted: {disp}.\n\nWhat time works for you? (e.g., 12:00 PM)\n\nAvailable: {timings}"

            # --- Neither set → ask for both together ---
            if lang == 'telugu':
                return f"ఏ తేదీ మరియు సమయం? (ఉదా: 'రేపు 12:00 PM', 'సోమవారం 6:00 PM')\n\nఉపలబ్ధ: {timings}"
            elif lang == 'hindi':
                return f"कौन सी तारीख और समय? (उदा: कल दोपहर 12 बजे, सोमवार 6:00 PM)\n\nउपलब्ध: {timings}"
            else:
                return f"What date and time works for you?\n\nAvailable: {timings}\n\n(e.g., Tomorrow 12:00 PM, Monday 6:00 PM)"

        # Step 1: Collect Name
        if not state['name']:
            name = extract_word(user_input)
            if name and len(name) > 1:  # More lenient for Telugu
                # Transliterate Telugu/Hindi names to English for database storage
                english_name = transliterate_name_to_english(name)
                state['name'] = english_name
                # But show in original language for conversation
                display_name = name if lang in ['telugu', 'hindi'] else english_name
                if lang == 'telugu':
                    return f"మీకు సంతోషించాను, {display_name}!\n\nమీ వయస్సు? (సంఖ్య చెప్పండి)"
                elif lang == 'hindi':
                    return f"आपसे मिलकर खुशी हुई, {display_name}!\n\nआपकी आयु? (संख्या बताएं)"
                else:
                    return f"Nice to meet you, {english_name}!\n\nWhat's your age? (Please enter as a number)"
            else:
                if lang == 'telugu':
                    return "దయచేసి మీ పూర్తి పేరు చెప్పండి (కనీసం 2 అక్షరాలు):"
                elif lang == 'hindi':
                    return "कृपया अपना पूरा नाम बताएं (कम से कम 2 अक्षर):"
                else:
                    return "Please tell me your full name (at least 2 characters):"
        
        # Step 2: Collect Age
        elif not state['age']:
            age = extract_number(user_input, min_val=1, max_val=150)
            if age:
                state['age'] = age
                if lang == 'telugu':
                    return f"మీకు {state['age']} సంవత్సరాల వయస్సు ఉంది.\n\nదయచేసి 10-అంకెల ఫోన్ నంబర్ చెప్పండి:"
                elif lang == 'hindi':
                    return f"आपकी आयु {state['age']} वर्ष है।\n\nकृपया 10-अंकीय फोन नंबर बताएं:"
                else:
                    return f"Good, you are {state['age']} years old.\n\nTell me your 10-digit phone number:"
            else:
                if lang == 'telugu':
                    return "దయచేసి సంఖ్య ఎంటర్ చేయండి (ఉదా: 35):"
                elif lang == 'hindi':
                    return "कृपया संख्या दर्ज करें (उदा: 35):"
                else:
                    return "Please enter your age as a number (e.g., 35):"
        
        # Step 3: Collect Phone
        elif not state['phone']:
            phone = extract_number(user_input)
            if phone == -1:
                if lang == 'telugu':
                    return "దయచేసి 10-అంకెల ఫోన్ నంబర్ చెప్పండి (ఉదా: 9876543210):"
                elif lang == 'hindi':
                    return "कृपया 10-अंकीय फोन नंबर बताएं (उदा: 9876543210):"
                else:
                    return "Please enter your 10-digit phone number (e.g., 9876543210):"
            elif phone and len(str(phone)) == 10:
                state['phone'] = str(phone)
                if lang == 'telugu':
                    return f"ఫోన్ నంబర్ {state['phone']} నమోదు చేయబడింది.\n\n12-అంకెల ఆధార్ సంఖ్య చెప్పండి:"
                elif lang == 'hindi':
                    return f"फोन नंबर {state['phone']} दर्ज किया गया।\n\n12-अंकीय आधार संख्या बताएं:"
                else:
                    return f"Phone number {state['phone']} noted.\n\nTell me your 12-digit Aadhar number:"
            else:
                if lang == 'telugu':
                    return "దయచేసి చెల్లుబాటుయોग్యమైన 10-అంకెల ఫోన్ నంబర్ చెప్పండి:"
                elif lang == 'hindi':
                    return "कृपया वैध 10-अंकीय फोन नंबर बताएं:"
                else:
                    return "Please enter a valid 10-digit phone number (e.g., 9876543210):"
        
        # Step 4: Collect Aadhar
        elif not state['aadhar']:
            aadhar = extract_number(user_input)
            if aadhar and len(str(aadhar)) == 12:
                state['aadhar'] = str(aadhar)
                if lang == 'telugu':
                    return f"ఆధార్ సంఖ్య {state['aadhar']} నమోదు చేయబడింది.\n\nమీ ఆరోగ్య సమస్య ఏమిటి?"
                elif lang == 'hindi':
                    return f"आधार संख्या {state['aadhar']} दर्ज की गई।\n\nआपकी स्वास्थ्य समस्या क्या है?"
                else:
                    return f"Aadhar number {state['aadhar']} noted.\n\nWhat is your health issue or complaint?"
            else:
                if lang == 'telugu':
                    return "దయచేసి చెల్లుబాటుయోग్యమైన 12-అంకెల ఆధార్ సంఖ్య చెప్పండి:"
                elif lang == 'hindi':
                    return "कृपया वैध 12-अंकीय आधार संख्या बताएं:"
                else:
                    return "Please enter a valid 12-digit Aadhar number:"
        
        # Step 5: Collect Issue
        elif not state['issue']:
            issue = user_input.strip()[:60]
            if len(issue) > 2:
                state['issue'] = issue
                
                # If time not given yet, ask for it
                if not state['appointment_time'] or not state['appointment_date']:
                    if lang == 'telugu':
                        return f"సరే. మీ సమస్య: {state['issue']}\n\nఉపలబ్ధ: {doc['timings']}\n\nఏ తేదీ మరియు సమయం? (ఉదా: రేపు 12:00 PM, సోమవారం 6:00 PM)"
                    elif lang == 'hindi':
                        return f"ठीक है। आपकी समस्या: {state['issue']}\n\nउपलब्ध: {doc['timings']}\n\nकौन सी तारीख और समय? (उदा: कल 12:00 PM, सोमवार 6:00 PM)"
                    else:
                        return f"Got it. Your issue: {state['issue']}\n\nAvailable: {doc['timings']}\n\nWhat date and time works for you? (e.g., Tomorrow 12:00 PM, Monday 6:00 PM)"

                else:
                    return confirm_booking(lang)
            else:
                if lang == 'telugu':
                    return "దయచేసి మీ ఆరోగ్య సమస్య వివరించండి:"
                elif lang == 'hindi':
                    return "कृपया अपनी स्वास्थ्य समस्या बताएं:"
                else:
                    return "Please describe your health issue:"
        
        # Step 6: Collect Time and Date (if not already set)
        elif not state['appointment_time'] or not state['appointment_date']:
            time_slot = extract_time(user_input)
            date_str, day_name, _dd = extract_appointment_date(user_input)
            if time_slot and not state['appointment_time']:
                if not is_time_available(time_slot, state['doctor_selected']):
                    if lang == 'telugu':
                        return f"క్షమించండి, {time_slot} అందుబాటులో లేదు.\n\nఉపలబ్ధ: {doc['timings']}\n\nవేరే సమయం చెప్పండి:"
                    elif lang == 'hindi':
                        return f"क्षमा करें, {time_slot} उपलब्ध नहीं है।\n\nउपलब्ध: {doc['timings']}\n\nकृपया अलग समय चुनें:"
                    else:
                        return f"Sorry, {time_slot} is not available.\n\nAvailable: {doc['timings']}\n\nPlease choose a time within these hours:"
                state['appointment_time'] = time_slot
            if date_str and not state['appointment_date']:
                if is_day_available_for_doctor(date_str, state['doctor_selected']):
                    state['appointment_date'] = date_str
                    state['appointment_day'] = day_name
            if state['appointment_time'] and state['appointment_date']:
                return confirm_booking(lang)
            elif state['appointment_time'] and not state['appointment_date']:
                if lang == 'telugu':
                    return f"సమయం నమోదు: {state['appointment_time']}. ఏ తేదీ? (ఉదా: ఈ రోజు, రేపు, సోమవారం)"
                elif lang == 'hindi':
                    return f"समय दर्ज: {state['appointment_time']}. कौन सी तारीख? (उदा: आज, कल, सोमवार)"
                else:
                    return f"Time noted: {state['appointment_time']}. What date? (e.g., Today, Tomorrow, Monday)"
            elif state['appointment_date'] and not state['appointment_time']:
                if lang == 'telugu':
                    return f"తేదీ నమోదు: {format_date_display(state['appointment_date'])}. ఏ సమయం? (ఉదా: 6:00 PM)\n\nఉపలబ్ధ: {doc['timings']}"
                elif lang == 'hindi':
                    return f"तारीख दर्ज: {format_date_display(state['appointment_date'])}. कौन सा समय? (उदा: 6:00 PM)\n\nउपलब्ध: {doc['timings']}"
                else:
                    return f"Date noted: {format_date_display(state['appointment_date'])}. What time? (e.g., 6:00 PM)\n\nAvailable: {doc['timings']}"
            else:
                if lang == 'telugu':
                    return f"ఉపలబ్ధ: {doc['timings']}\n\nఏ తేదీ మరియు సమయం? (ఉదా: రేపు 6:00 PM):"
                elif lang == 'hindi':
                    return f"उपलब्ध: {doc['timings']}\n\nकौन सी तारीख और समय? (उदा: कल 6:00 PM):"
                else:
                    return f"Available: {doc['timings']}\n\nWhat date and time? (e.g., Tomorrow 6:00 PM):"

def confirm_booking(lang='english'):
    """Confirm and save booking"""
    doc = DOCTORS[state['doctor_selected']]
    appt_date = state.get('appointment_date') or datetime.now().strftime('%Y-%m-%d')
    appt_day  = state.get('appointment_day')  or datetime.strptime(appt_date, '%Y-%m-%d').strftime('%A')
    date_display = format_date_display(appt_date)  # e.g. 'Monday, 09 March 2026'

    booking_record = {
        'name': state['name'],
        'age': state['age'],
        'phone': state['phone'],
        'aadhar': state['aadhar'],
        'issue': state['issue'],
        'doctor': doc['name'],
        'doctor_id': state['doctor_selected'],
        'appointment_time': state['appointment_time'],
        'appointment_date': appt_date,
        'appointment_day': appt_day,
        'status': 'confirmed',
        'date': appt_date,
        'created_at': datetime.now().isoformat()
    }
    set_last_booking(booking_record)
    
    # Save to PostgreSQL (non-blocking)
    import threading
    def _save_to_db(record):
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import db as hospital_db
            if hospital_db.test_connection():
                hospital_db.save_registration(record)
                print(f"✓ Appointment saved to PostgreSQL: {record['name']}")
        except Exception as e:
            print(f"⚠ DB save error: {e}")
    threading.Thread(target=_save_to_db, args=(dict(booking_record),), daemon=True).start()
    
    if lang == 'telugu':
        msg = f"""అపాయింట్‌మెంట్ నిర్ధారించబడింది! ✅

రోగి పేరు: {state['name']}
వయస్సు: {state['age']} సంవత్సరాలు
ఫోన్: {state['phone']}
ఆధార్: {state['aadhar']}
ఆరోగ్య సమస్య: {state['issue']}

డాక్టర్: {doc['name']} ({doc['specialty']})
తేదీ: {date_display}
సమయం: {state['appointment_time']}

మీ అపాయింట్‌మెంట్ నిర్ధారించబడింది! నిర్ణీత సమయానికి 10 నిమిషాల ముందు రావాలని కోరుతున్నాం. ధన్యవాదాలు!"""
    elif lang == 'hindi':
        msg = f"""नियुक्ति की पुष्टि! ✅

रोगी का नाम: {state['name']}
आयु: {state['age']} वर्ष
फोन: {state['phone']}
आधार: {state['aadhar']}
स्वास्थ्य समस्या: {state['issue']}

डॉक्टर: {doc['name']} ({doc['specialty']})
तारीख: {date_display}
समय: {state['appointment_time']}

आपकी नियुक्ति पुष्टि हो गई है! कृपया निर्धारित समय से 10 मिनट पहले आएं। धन्यवाद!"""
    else:
        msg = f"""APPOINTMENT CONFIRMED! ✅

Patient Name: {state['name']}
Age: {state['age']} years
Phone: {state['phone']}
Aadhar: {state['aadhar']}
Health Issue: {state['issue']}

Doctor: {doc['name']} ({doc['specialty']})
Appointment Date: {date_display}
Appointment Time: {state['appointment_time']}

Your appointment is confirmed! Please arrive 10 minutes before your scheduled time. Thank you!"""
    
    reset_state()
    return msg

def generate_chatbot_response(user_input):
    """Main function called by server"""
    # Detect from input; respond() will reconcile with persisted state['lang']
    language = detect_language(user_input)
    response = respond(user_input, language)
    
    # Ensure response is never None
    if response is None:
        if state.get('lang') == 'telugu':
            response = "క్షమించండి, నాకు అర్థం కాలేదు. దయచేసి మళ్ళీ చెప్పండి."
        elif state.get('lang') == 'hindi':
            response = "क्षमा करें, मुझे समझ नहीं आया। कृपया दोबारा बताएं।"
        else:
            response = "I'm sorry, I didn't quite understand that. Could you please rephrase?"
    
    # Return the persisted language so caller knows current lang
    return response, state.get('lang', language)

if __name__ == "__main__":
    print("Hospital Chatbot - Interactive Mode")
    print("Type 'exit' to quit\n")
    
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response, lang = generate_chatbot_response(user_input)
        print(f"\nAssistant: {response}\n")
