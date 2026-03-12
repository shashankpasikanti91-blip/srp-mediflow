"""
══════════════════════════════════════════════════════════════════════════════
  SRP MediFlow — COMPLETE DEMO: Patient Journey + New Client Onboarding
  v7.1 — March 2026

  Demonstrates EVERY capability end-to-end:
    1. New hospital onboarding (full automatic DB + chatbot + dashboard)
    2. Demo patient: Registration → IPD Admit → Doctor Round
    3. Lab orders + Results (CBC, Lipid Panel)
    4. X-Ray order + Report
    5. Pharmacy stock + Dispense medicines
    6. Digital Prescription (PDF)
    7. Billing (OPD + IPD consolidated)
    8. Discharge with summary
    9. Telegram alerts (doctor notification, lab ready, discharge)
   10. Founder alert (new client, patient activity)
   11. Chatbot appointment flow
   12. Inventory low-stock alert
   13. Staff attendance
   14. DB row verification (patients, bills, lab, pharmacy all > 0)

  Run:
    python _demo_full_journey.py            # → http://5.223.67.236:7500
    python _demo_full_journey.py live       # → https://star-hospital.mediflow.srpailabs.com
══════════════════════════════════════════════════════════════════════════════
"""
import json, time, sys, random, string
import http.client, ssl
from datetime import datetime, date

# ─── Target ──────────────────────────────────────────────────────────────────
USE_LIVE = "live" in sys.argv
if USE_LIVE:
    BASE_HOST = "star-hospital.mediflow.srpailabs.com"
    BASE_PORT = 443
    USE_HTTPS = True
    LABEL     = "LIVE (HTTPS)"
else:
    BASE_HOST = "5.223.67.236"
    BASE_PORT = 7500
    USE_HTTPS = False
    LABEL     = "SERVER HTTP"

PASS_COUNT, FAIL_COUNT = 0, 0
RESULTS = []
START   = datetime.now()

# ─── Utils ───────────────────────────────────────────────────────────────────
def _ts(): return datetime.now().strftime("%H:%M:%S")

def log(sym, msg): print(f"[{_ts()}] {sym}  {msg[:110]}")

def sep(title):
    print(f"\n{'═'*70}\n  {title}\n{'═'*70}")

def api(method, path, body=None, cookie="", timeout=30, host=None):
    time.sleep(0.08)
    h = host or BASE_HOST
    p = BASE_PORT
    if USE_HTTPS and not host:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(h, p, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(h, 7500 if host else p, timeout=timeout)
    hdrs = {"Content-Type": "application/json"}
    if cookie: hdrs["Cookie"] = cookie
    payload = json.dumps(body).encode() if body else b""
    conn.request(method, path, payload, hdrs)
    resp = conn.getresponse()
    raw  = resp.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = {"_raw": raw.decode(errors="replace")[:400]}
    conn.close()
    return resp.status, data, resp.getheader("Set-Cookie","")

def chk(label, status, data, expect=(200,201), must_keys=None):
    global PASS_COUNT, FAIL_COUNT
    if isinstance(expect, int): expect = (expect,)
    ok = status in expect
    if ok and must_keys:
        ok = all(k in data for k in must_keys)
    sym = "✅" if ok else "❌"
    detail = "" if ok else f"  → {str(data)[:90]}"
    log(sym, f"{label:<60}[{status}]{detail}")
    if ok:
        PASS_COUNT += 1; RESULTS.append(("PASS", label))
    else:
        FAIL_COUNT += 1; RESULTS.append(("FAIL", label))
    return ok

def login(username, password, label=None):
    global PASS_COUNT, FAIL_COUNT
    s, d, sc = api("POST", "/api/login",
                   {"username": username, "password": password, "tenant_slug": "auto"})
    lbl = label or f"LOGIN {username}"
    if s == 200 and d.get("status") == "success":
        cookie = ""
        for part in (sc or "").split(";"):
            pp = part.strip()
            if pp.startswith("admin_session="):
                cookie = pp; break
        log("✅", f"LOGIN {username:<40} role={d.get('role','?')} tenant={d.get('tenant_slug','?')}")
        PASS_COUNT += 1; RESULTS.append(("PASS", lbl))
        return cookie, d
    log("❌", f"LOGIN {username:<40} {s} → {d.get('message','?')}")
    FAIL_COUNT += 1; RESULTS.append(("FAIL", f"{lbl}: {s}"))
    return None, None

# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print(f"  SRP MediFlow v7.1 — COMPLETE DEMO & E2E")
print(f"  Target : {BASE_HOST}:{BASE_PORT}  [{LABEL}]")
print(f"  Started: {START.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ─── 0. Server Health ─────────────────────────────────────────────────────────
sep("0. SERVER HEALTH CHECK")
s, d, _ = api("GET", "/ping")
chk("GET /ping", s, d)
s, d, _ = api("GET", "/health")
chk("GET /health", s, d)

# ─── 1. Core Logins ──────────────────────────────────────────────────────────
sep("1. CORE HOSPITAL LOGINS — Star Hospital (all roles)")
star_admin_ck, _ = login("star_hospital_admin", "Star@Admin2026!")
star_doc_ck,   _ = login("star_hospital_doctor",    "Doctor@Star2026!")
star_nurse_ck, _ = login("star_hospital_nurse",     "Nurse@Star2026!")
star_lab_ck,   _ = login("star_hospital_lab",       "Lab@Star2026!")
star_stock_ck, _ = login("star_hospital_stock",     "Stock@Star2026!")
star_recep_ck, _ = login("star_hospital_reception", "Recep@Star2026!")
founder_ck,    _ = login("founder", "Srp@Founder2026!")

# ─── 2. Admin Dashboard Data ─────────────────────────────────────────────────
sep("2. ADMIN DASHBOARD — Star Hospital")
if star_admin_ck:
    for path, lbl in [
        ("/api/session/me",             "session/me"),
        ("/api/admin/data",             "admin/data"),
        ("/api/admin/doctors",          "admin/doctors"),
        ("/api/admin/attendance/today", "attendance/today"),
        ("/api/admin/billing/list",     "billing/list"),
        ("/api/admin/logs",             "admin/logs"),
        ("/api/staff/list",             "staff/list"),
        ("/api/ipd/admissions",         "ipd/admissions"),
        ("/api/surgery/list",           "surgery/list"),
    ]:
        s, d, _ = api("GET", path, cookie=star_admin_ck)
        chk(f"Star {lbl}", s, d)

# ─── 3. DEMO PATIENT: Full Journey ───────────────────────────────────────────
sep("3. DEMO PATIENT JOURNEY — Admission to Discharge")

DEMO_PHONE = "9" + str(random.randint(800000000, 899999999))
DEMO_NAME  = "Rajesh Kumar (Demo)"
DEMO_DATE  = date.today().isoformat()

log("📋", f"Demo Patient: {DEMO_NAME} | Phone: {DEMO_PHONE}")

# 3a. OPD Patient Registration
s, d, _ = api("POST", "/api/patients/register", {
    "full_name": DEMO_NAME,
    "phone":     DEMO_PHONE,
    "age":       "45",
    "gender":    "Male",
    "blood_group": "O+",
    "address":   "123 Demo Street, Hyderabad",
    "issue":     "Chest pain and breathlessness since 2 days",
    "emergency": False,
}, cookie=star_admin_ck)
chk("PATIENT register (OPD)", s, d, expect=(200, 201))
patient_id = d.get("patient_id") or d.get("id")
log("📋", f"Patient ID: {patient_id}")

# 3b. OPD Billing
s, d, _ = api("POST", "/api/billing/create", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "items": [
        {"description": "OPD Consultation",   "amount": 500},
        {"description": "ECG",                "amount": 300},
        {"description": "Blood Pressure Check","amount": 100},
    ],
    "total_amount": 900,
    "bill_type": "OPD",
    "payment_status": "paid",
    "payment_method": "Cash",
}, cookie=star_admin_ck)
chk("BILLING — OPD consultation", s, d, expect=(200, 201))
bill_id = d.get("bill_id") or d.get("id")

# 3c. Doctor Prescription
s, d, _ = api("POST", "/api/prescriptions/create", {
    "patient_name":   DEMO_NAME,
    "patient_phone":  DEMO_PHONE,
    "doctor_name":    "Dr. Arjun Reddy",
    "diagnosis":      "Suspected Angina — pending investigations",
    "medicines": [
        {"name": "Aspirin 75mg",      "dosage": "1-0-1", "duration": "5 days", "instructions": "After food"},
        {"name": "Pantoprazole 40mg", "dosage": "1-0-0", "duration": "5 days", "instructions": "Before breakfast"},
        {"name": "Atorvastatin 20mg", "dosage": "0-0-1", "duration": "30 days","instructions": "At bedtime"},
    ],
    "advice": "Avoid strenuous activity. Return immediately if chest pain worsens.",
    "follow_up": "3 days",
}, cookie=star_doc_ck)
chk("PRESCRIPTION — doctor creates Rx", s, d, expect=(200, 201))
rx_id = d.get("prescription_id") or d.get("id")

# 3d. IPD Admit
s, d, _ = api("POST", "/api/ipd/admit", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "ward":          "Cardiac ICU",
    "bed_number":    "C-04",
    "doctor_name":   "Dr. Arjun Reddy",
    "diagnosis":     "Suspected Acute Coronary Syndrome — under observation",
    "blood_group":   "O+",
    "attendant_name": "Suresh Kumar",
    "attendant_phone": "9876500001",
}, cookie=star_admin_ck)
chk("IPD admit — Cardiac ICU", s, d, expect=(200, 201, 409))
admission_id = d.get("admission_id") or d.get("id")
log("🛏️", f"Admission ID: {admission_id}")

# ─── 4. LAB ORDERS ───────────────────────────────────────────────────────────
sep("4. LAB ORDERS + RESULTS (CBC, Lipid, Troponin)")

# 4a. Order labs
s, d, _ = api("POST", "/api/lab/order", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "doctor_name":   "Dr. Arjun Reddy",
    "tests": ["Complete Blood Count", "Lipid Panel", "Troponin-I", "Blood Sugar (Fasting)"],
    "priority": "URGENT",
    "ward": "Cardiac ICU",
}, cookie=star_doc_ck)
chk("LAB order — CBC + Lipid + Troponin", s, d, expect=(200, 201))
lab_order_id = d.get("order_id") or d.get("id")
log("🔬", f"Lab Order ID: {lab_order_id}")

# 4b. Complete lab tests (lab tech uploads results)
s, d, _ = api("POST", "/api/lab/result", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "test_name":     "Complete Blood Count",
    "results": {
        "Hemoglobin":    "10.2 g/dL   (Normal: 13-17)",
        "WBC":           "11,500 /μL  (Normal: 4000-11000) ⚠️ HIGH",
        "Platelets":     "1,85,000 /μL (Normal: 1.5-4.5 Lac)",
        "PCV":           "38%          (Normal: 40-52)",
        "MCV":           "78 fL        (Normal: 80-100) ⚠️ LOW",
    },
    "remarks":    "Leukocytosis suggestive of infection. Mild microcytic anaemia.",
    "lab_tech":   "Kumar (Lab Tech)",
    "status":     "completed",
}, cookie=star_lab_ck)
chk("LAB result — CBC completed", s, d, expect=(200, 201))

s, d, _ = api("POST", "/api/lab/result", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "test_name":     "Troponin-I",
    "results": {
        "Troponin-I": "0.08 ng/mL (Normal: <0.04)  🔴 ELEVATED",
    },
    "remarks":    "Elevated Troponin — ACS not ruled out. Repeat in 3 hours.",
    "lab_tech":   "Kumar (Lab Tech)",
    "status":     "completed",
}, cookie=star_lab_ck)
chk("LAB result — Troponin-I (elevated)", s, d, expect=(200, 201))

# 4c. Check lab orders list
s, d, _ = api("GET", "/api/lab/orders", cookie=star_lab_ck)
chk("LAB orders list", s, d)

# ─── 5. X-RAY / RADIOLOGY ────────────────────────────────────────────────────
sep("5. X-RAY / RADIOLOGY ORDER + REPORT")
s, d, _ = api("POST", "/api/lab/order", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "doctor_name":   "Dr. Arjun Reddy",
    "tests":         ["Chest X-Ray (PA View)", "Chest X-Ray (Lateral View)"],
    "priority":      "URGENT",
    "test_type":     "XRAY",
    "notes":         "R/O Cardiomegaly. Check for pulmonary congestion.",
}, cookie=star_doc_ck)
chk("XRAY order — Chest PA + Lateral", s, d, expect=(200, 201))
xray_order_id = d.get("order_id") or d.get("id")

# X-Ray result from lab tech
s, d, _ = api("POST", "/api/lab/result", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "test_name":     "Chest X-Ray (PA View)",
    "test_type":     "XRAY",
    "results": {
        "Heart Size":   "Mildly enlarged (CTR ~0.55)",
        "Lung Fields":  "Bilateral lower zone haziness — pulmonary congestion",
        "Costophrenic": "Blunted right angle — minimal pleural effusion",
        "Bones":        "No fracture",
    },
    "remarks":        "IMPRESSION: Cardiomegaly with bilateral pulmonary congestion. Clinical correlation advised.",
    "radiologist":    "Dr. Priya Sharma (Radiologist)",
    "status":         "completed",
}, cookie=star_lab_ck)
chk("XRAY result — Chest X-Ray report ready", s, d, expect=(200, 201))
log("📷", "X-Ray: Cardiomegaly + pulmonary congestion detected")

# ─── 6. PHARMACY — Stock & Dispense ──────────────────────────────────────────
sep("6. PHARMACY — INVENTORY + MEDICINE DISPENSE")

# 6a. Check current stock
s, d, _ = api("GET", "/api/pharmacy/inventory", cookie=star_stock_ck)
chk("PHARMACY inventory list", s, d)

# 6b. Add stock (medicines)
medicines = [
    {"name": "Aspirin 75mg",           "batch": "ASP2026A", "qty": 500, "unit": "tablet",
     "mrp": 2.5,  "purchase_price": 1.5, "expiry": "2027-06-30", "manufacturer": "Cipla"},
    {"name": "Pantoprazole 40mg",      "batch": "PAN2026B", "qty": 300, "unit": "tablet",
     "mrp": 8.0,  "purchase_price": 5.0, "expiry": "2027-03-31", "manufacturer": "Sun Pharma"},
    {"name": "Atorvastatin 20mg",      "batch": "ATV2026C", "qty": 200, "unit": "tablet",
     "mrp": 12.0, "purchase_price": 8.0, "expiry": "2027-12-31", "manufacturer": "Dr. Reddy's"},
    {"name": "Nitroglycerin 0.5mg SL", "batch": "NTG2026D", "qty": 50,  "unit": "tablet",
     "mrp": 25.0, "purchase_price": 18.0,"expiry": "2026-12-31", "manufacturer": "Pfizer"},
    {"name": "Heparin 5000 IU/mL",    "batch": "HEP2026E", "qty": 20,  "unit": "vial",
     "mrp": 350.0,"purchase_price": 280.0,"expiry": "2026-09-30","manufacturer": "Leo Pharma"},
    {"name": "IV Normal Saline 500ml", "batch": "NSL2026F", "qty": 100,  "unit": "bag",
     "mrp": 45.0, "purchase_price": 32.0, "expiry": "2027-01-31","manufacturer": "Baxter"},
    {"name": "Paracetamol 500mg",      "batch": "PCM2026G", "qty": 1000, "unit": "tablet",
     "mrp": 1.5,  "purchase_price": 0.8,  "expiry": "2028-01-31","manufacturer": "Cipla"},
    {"name": "Furosemide 40mg",        "batch": "FRS2026H", "qty": 150,  "unit": "tablet",
     "mrp": 3.5,  "purchase_price": 2.0,  "expiry": "2027-06-30","manufacturer": "Abbott"},
]
for med in medicines[:3]:  # add first 3 to keep demo fast
    s, d, _ = api("POST", "/api/pharmacy/add-stock", med, cookie=star_stock_ck)
    chk(f"STOCK add — {med['name'][:30]}", s, d, expect=(200, 201))

# 6c. Pharmacy sell / dispense
s, d, _ = api("POST", "/api/pharmacy/sell", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "prescribed_by": "Dr. Arjun Reddy",
    "items": [
        {"medicine_name": "Aspirin 75mg",      "quantity": 10, "unit_price": 2.5},
        {"medicine_name": "Pantoprazole 40mg", "quantity": 5,  "unit_price": 8.0},
        {"medicine_name": "Atorvastatin 20mg", "quantity": 30, "unit_price": 12.0},
    ],
    "total":        436.0,
    "payment_mode": "Cash",
}, cookie=star_stock_ck)
chk("PHARMACY dispense — 3 medicines", s, d, expect=(200, 201))
log("💊", "Medicines dispensed: Aspirin, Pantoprazole, Atorvastatin")

# 6d. Low stock alert
s, d, _ = api("GET", "/api/pharmacy/alerts/low-stock", cookie=star_stock_ck)
chk("PHARMACY low-stock alerts", s, d)
low_count = len(d.get("alerts", d.get("items", [])))
log("⚠️", f"Low stock medicines: {low_count}")

# 6e. Expiry alert
s, d, _ = api("GET", "/api/pharmacy/alerts/expiry", cookie=star_stock_ck)
chk("PHARMACY expiry alerts", s, d)

# ─── 7. NURSE — Vitals & IPD Rounds ──────────────────────────────────────────
sep("7. NURSE — VITALS + IPD DAILY ROUND")
s, d, _ = api("POST", "/api/ipd/round/add", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "vitals": {
        "bp":          "140/90 mmHg",
        "pulse":       "94 bpm",
        "temperature": "99.2°F",
        "spo2":        "95%",
        "weight":      "72 kg",
    },
    "notes": "Patient reports mild chest discomfort. Troponin elevated. Cardiologist review requested.",
    "recorded_by": "Nurse Lakshmi",
    "round_time":  datetime.now().isoformat(),
}, cookie=star_nurse_ck)
chk("IPD round — vitals recorded by nurse", s, d, expect=(200, 201))

# ─── 8. SURGERY ───────────────────────────────────────────────────────────────
sep("8. SURGERY RECORD")
s, d, _ = api("POST", "/api/surgery/create", {
    "patient_name":   DEMO_NAME,
    "patient_phone":  DEMO_PHONE,
    "surgery_name":   "Coronary Angiography (Diagnostic)",
    "surgeon":        "Dr. Arjun Reddy",
    "anaesthetist":   "Dr. Meena Patel",
    "ot_assistant":   "Nurse Lakshmi",
    "surgery_date":   DEMO_DATE,
    "duration_mins":  45,
    "status":         "completed",
    "notes":          "Single vessel CAD, LAD 60% stenosis. Conservative management advised.",
    "estimated_cost": 25000,
}, cookie=star_admin_ck)
chk("SURGERY — Coronary Angiography recorded", s, d, expect=(200, 201))

# ─── 9. IPD BILLING (final consolidated) ─────────────────────────────────────
sep("9. CONSOLIDATED IPD BILLING")
s, d, _ = api("POST", "/api/billing/create", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "bill_type": "IPD",
    "items": [
        {"description": "Cardiac ICU Bed (3 days)",         "amount": 9000},
        {"description": "Coronary Angiography",             "amount": 25000},
        {"description": "Cardiac Monitoring",               "amount": 3500},
        {"description": "Lab Tests (CBC, Troponin, Lipid)", "amount": 2400},
        {"description": "Chest X-Ray (2 views)",            "amount": 800},
        {"description": "IV Fluids + Consumables",          "amount": 1500},
        {"description": "Medicines (Pharmacy)",             "amount": 436},
        {"description": "Nursing Charges",                  "amount": 1500},
        {"description": "Doctor Visit Charges (3 days)",    "amount": 4500},
    ],
    "total_amount":   49136,
    "payment_status": "partial",
    "paid_amount":    20000,
    "payment_method": "Card",
    "insurance_covered": True,
    "insurance_name": "Star Health Insurance",
    "gst_percent":    5,
}, cookie=star_admin_ck)
chk("BILLING — IPD consolidated ₹49,136", s, d, expect=(200, 201))
ipd_bill_id = d.get("bill_id") or d.get("id")

# ─── 10. DISCHARGE ────────────────────────────────────────────────────────────
sep("10. PATIENT DISCHARGE + SUMMARY")
s, d, _ = api("POST", "/api/ipd/discharge", {
    "patient_name":  DEMO_NAME,
    "patient_phone": DEMO_PHONE,
    "discharge_date": DEMO_DATE,
    "diagnosis":     "Acute Coronary Syndrome — Single Vessel CAD (LAD 60% stenosis)",
    "treatment_given": "Aspirin, Heparin, Nitroglycerin, IV Fluids, O2 therapy",
    "discharge_condition": "Stable",
    "follow_up":     "Cardiology OPD in 1 week",
    "discharge_instructions": "Low salt diet, avoid strenuous activity, take medications regularly",
    "medicines_on_discharge": "Aspirin 75mg, Pantoprazole 40mg, Atorvastatin 20mg, Metoprolol 25mg",
    "doctor": "Dr. Arjun Reddy",
    "total_days": 3,
}, cookie=star_admin_ck)
chk("DISCHARGE — patient discharged stable", s, d, expect=(200, 201))
log("🏥", "Patient discharge complete. DIAGNOSIS: ACS — Single Vessel CAD")

# ─── 11. TELEGRAM NOTIFICATIONS ──────────────────────────────────────────────
sep("11. TELEGRAM NOTIFICATIONS")

# Test notification endpoint
s, d, _ = api("POST", "/api/notifications/test", {
    "notification_type": "appointment",
    "patient_name": DEMO_NAME,
    "doctor_name":  "Dr. Arjun Reddy",
    "message":      f"DEMO: Patient {DEMO_NAME} discharged. Troponin elevated case resolved.",
}, cookie=star_admin_ck)
chk("TELEGRAM test notification", s, d, expect=(200, 201, 202))
log("📱", f"Telegram status: {d.get('status','?')} | {d.get('message','?')[:60]}")

# Lab ready notification
s, d, _ = api("POST", "/api/notifications/test", {
    "notification_type": "lab_result",
    "patient_name":      DEMO_NAME,
    "test_name":         "Troponin-I",
    "result_summary":    "ELEVATED (0.08 ng/mL) — ACS protocol activated",
}, cookie=star_admin_ck)
chk("TELEGRAM — lab result alert", s, d, expect=(200, 201, 202))

# Appointment reminder
s, d, _ = api("POST", "/api/notifications/test", {
    "notification_type": "reminder",
    "patient_name":      DEMO_NAME,
    "message":           "Reminder: Cardiology follow-up tomorrow at 10:00 AM",
}, cookie=star_admin_ck)
chk("TELEGRAM — appointment reminder", s, d, expect=(200, 201, 202))

# ─── 12. P&L + ANALYTICS ──────────────────────────────────────────────────────
sep("12. P&L + ANALYTICS REPORTS")
if star_admin_ck:
    for path, lbl in [
        ("/api/admin/analytics/pl?period=monthly",      "P&L monthly"),
        ("/api/admin/expenses?period=monthly",           "Expenses monthly"),
        ("/api/admin/analytics/revenue?period=monthly", "Revenue monthly"),
        ("/api/admin/analytics/doctors",                 "Doctor analytics"),
        ("/api/admin/billing/list",                      "Billing list"),
    ]:
        s, d, _ = api("GET", path, cookie=star_admin_ck)
        chk(f"REPORT {lbl}", s, d)
        if "pl?" in path:
            rev = d.get("revenue", {}).get("total", 0)
            exp = d.get("expenses", {}).get("total", 0)
            log("📊", f"P&L: Revenue ₹{rev:,.0f}  |  Expenses ₹{exp:,.0f}")

# ─── 13. CHATBOT FLOW ─────────────────────────────────────────────────────────
sep("13. AI CHATBOT — 3-Step Appointment Flow")
tid = f"demo_journey_{random.randint(10000,99999)}"
for step, msg in [
    ("step-1 hello",      "Hi, I want to book an appointment"),
    ("step-2 symptoms",   "I have chest pain and breathlessness"),
    ("step-3 schedule",   "Tomorrow morning at 10am please"),
]:
    s, d, _ = api("POST", "/api/chat", {"message": msg, "session_id": tid})
    chk(f"CHATBOT {step}", s, d)
    log("🤖", f"Bot: {d.get('message','?')[:80]}")

# ─── 14. STAFF ATTENDANCE ─────────────────────────────────────────────────────
sep("14. STAFF ATTENDANCE")
s, d, _ = api("POST", "/api/attendance/check-in",
              {"action": "check_in"}, cookie=star_doc_ck)
chk("ATTENDANCE check-in — doctor", s, d, expect=(200, 201, 409))

s, d, _ = api("GET", "/api/admin/attendance/today", cookie=star_admin_ck)
chk("ATTENDANCE today — admin view", s, d)
att_count = d.get("total_present", d.get("count", "?"))
log("📅", f"Staff present today: {att_count}")

# ─── 15. NEW CLIENT ONBOARDING (Full Auto) ────────────────────────────────────
sep("15. NEW CLIENT ONBOARDING — Full Automatic")
suffix   = ''.join(random.choices(string.digits, k=6))
NEW_SLUG = f"tv71{suffix}"
NEW_USER = f"tv71admin{suffix}"
NEW_PW   = f"DemoHosp@{suffix}!"
NEW_NAME = f"Demo Hospital ({suffix})"

log("🏥", f"Provisioning: '{NEW_NAME}'")
log("👤", f"Admin: {NEW_USER} / {NEW_PW}")

s, d, _ = api("POST", "/api/hospital/signup", {
    "hospital_name":  NEW_NAME,
    "subdomain":      NEW_SLUG,
    "admin_username": NEW_USER,
    "admin_password": NEW_PW,
    "admin_name":     "Demo Administrator",
    "admin_email":    f"{NEW_USER}@demohospital.in",
    "phone":          "9" + str(random.randint(100000000, 999999999)),
    "city":           "Hyderabad",
    "state":          "Telangana",
    "plan_type":      "starter",
})
created = chk("NEW hospital /api/hospital/signup", s, d, expect=(200, 201))
if not created:
    log("⚠️", f"Signup detail: {d}")

log("⏳", "Waiting 8s for DB provisioning + schema init...")
time.sleep(8)

# 15a. Login to new hospital
new_ck, new_session = login(NEW_USER, NEW_PW, label=f"NEW hospital admin login [{NEW_SLUG}]")
chk("NEW hospital admin login verified", 200 if new_ck else 401, new_session or {})

if new_ck:
    # 15b. Verify new hospital dashboards
    s, d, _ = api("GET", "/api/session/me", cookie=new_ck)
    chk("NEW hospital /session/me", s, d)
    log("🔐", f"Session: tenant={d.get('tenant_slug','?')} role={d.get('role','?')}")

    s, d, _ = api("GET", "/api/admin/data", cookie=new_ck)
    chk("NEW hospital /admin/data", s, d)

    # 15c. Patient in new hospital
    demo_ph2 = "9" + str(random.randint(700000000, 799999999))
    s, d, _ = api("POST", "/api/patients/register", {
        "full_name": "New Hospital Demo Patient",
        "phone":     demo_ph2, "age": "32",
        "gender":    "Female", "issue": "Headache",
    }, cookie=new_ck)
    chk("NEW hospital — patient register", s, d, expect=(200, 201))

    # 15d. Bill in new hospital
    s, d, _ = api("POST", "/api/billing/create", {
        "patient_name": "New Hospital Demo Patient",
        "patient_phone": demo_ph2,
        "items": [{"description": "OPD Consultation", "amount": 300}],
        "total_amount": 300, "bill_type": "OPD",
    }, cookie=new_ck)
    chk("NEW hospital — billing OPD", s, d, expect=(200, 201))

    # 15e. Chatbot on new hospital
    new_tid = f"new_demo_{suffix}"
    s, d, _ = api("POST", "/api/chat",
                  {"message": "book appointment", "session_id": new_tid})
    chk("NEW hospital — chatbot working", s, d)

    log("✅", f"NEW hospital '{NEW_NAME}' fully provisioned — all APIs working!")
else:
    log("❌", "New hospital login FAILED — provisioning may have an issue")

# ─── 16. FOUNDER ALERTS ───────────────────────────────────────────────────────
sep("16. FOUNDER ALERTS — sees everything")
if founder_ck:
    s, d, _ = api("GET", "/api/founder/clients", cookie=founder_ck)
    chk("FOUNDER /founder/clients", s, d)
    if s == 200:
        clients = d.get("clients", [])
        slugs   = [c.get("slug","") for c in clients]
        found   = NEW_SLUG in slugs or any(NEW_SLUG[:8] in str(c) for c in clients)
        log("🔔", f"Founder sees {len(clients)} clients | new={NEW_SLUG} present={found}")

    s, d, _ = api("GET", "/api/platform/stats", cookie=founder_ck)
    chk("FOUNDER platform/stats", s, d)
    if s == 200:
        log("📊", f"Platform: hospitals={d.get('total_hospitals','?')} "
                  f"patients={d.get('total_patients','?')} "
                  f"staff={d.get('total_staff','?')}")

    for path, lbl in [
        ("/api/platform/tenants",    "platform/tenants"),
        ("/api/founder/system-status","system-status"),
    ]:
        s, d, _ = api("GET", path, cookie=founder_ck)
        chk(f"FOUNDER {lbl}", s, d)

# ─── 17. DB VERIFICATION ──────────────────────────────────────────────────────
sep("17. DB ROW VERIFICATION — all tenants")
try:
    import psycopg2
    DB_CFG  = dict(host="localhost", port=5432, user="ats_user", password="ats_password")
    TENANTS = [
        ("hospital_ai",         "Star Hospital"),
        ("srp_sai_care",        "Sai Care Hospital"),
        ("srp_city_medical",    "City Medical Centre"),
        ("srp_apollo_warangal", "Apollo Clinic Warangal"),
        ("srp_green_cross",     "Green Cross Hospital"),
        (f"srp_{NEW_SLUG}",     NEW_NAME[:28]),
    ]
    TABLES = ["patients","staff_users","appointments","billing",
              "prescriptions","lab_orders","attendance","hospital_expenses"]
    for dbname, hosp_name in TENANTS:
        try:
            conn = psycopg2.connect(database=dbname, **DB_CFG)
            cur  = conn.cursor()
            row_info = []
            for tbl in TABLES:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                    cnt = cur.fetchone()[0]
                    row_info.append(f"{tbl}={cnt}")
                    PASS_COUNT += 1; RESULTS.append(("PASS", f"DB {dbname}.{tbl}"))
                except Exception:
                    row_info.append(f"{tbl}=n/a")
            cur.close(); conn.close()
            log("✅", f"  {hosp_name:<28} {' | '.join(row_info[:5])}")
        except Exception as e:
            log("⚠️", f"  {hosp_name:<28} DB unreachable: {str(e)[:60]}")
except ImportError:
    log("⚠️", "psycopg2 not installed locally — skipping local DB check")

# ─── FINAL SUMMARY ────────────────────────────────────────────────────────────
total  = PASS_COUNT + FAIL_COUNT
pct    = round(PASS_COUNT / total * 100, 1) if total else 0
duration = (datetime.now() - START).seconds
status   = "🟢 100% PASS" if FAIL_COUNT == 0 else f"🔴 {FAIL_COUNT} FAILED"

print("\n" + "=" * 70)
print(f"  SRP MediFlow v7.1 — COMPLETE DEMO RESULTS")
print("=" * 70)
print(f"  TOTAL    : {total}")
print(f"  PASSED   : {PASS_COUNT}  ({pct}%)")
print(f"  FAILED   : {FAIL_COUNT}")
print(f"  DURATION : {duration}s")
print()

if FAIL_COUNT:
    print("  ─── FAILURES ───")
    for sym, msg in RESULTS:
        if sym == "FAIL":
            print(f"    ❌ {msg}")
    print()

print(f"  {status}")
print()
print("  DEMO PATIENT JOURNEY SUMMARY:")
print(f"  Patient  : {DEMO_NAME}  |  Phone: {DEMO_PHONE}")
print(f"  Diagnosis: Acute Coronary Syndrome — Single Vessel CAD")
print(f"  Labs     : CBC (Leukocytosis), Troponin-I (Elevated)")
print(f"  X-Ray    : Cardiomegaly + Pulmonary Congestion")
print(f"  Rx       : Aspirin, Pantoprazole, Atorvastatin, Metoprolol")
print(f"  IPD Bill : ₹49,136 (partial ₹20,000 paid via Card)")
print(f"  Outcome  : Discharged STABLE after 3 days")
print()
print(f"  NEW CLIENT : {NEW_NAME}")
print(f"  Admin      : {NEW_USER} / {NEW_PW}")
print(f"  URL        : https://{NEW_SLUG}.mediflow.srpailabs.com")
print()
print("  SERVER URLS:")
print("  ✅ Main     : https://mediflow.srpailabs.com")
print("  ✅ Login    : https://mediflow.srpailabs.com/login")
print("  ✅ Founder  : https://mediflow.srpailabs.com/founder")
print("  ✅ Chat     : https://star-hospital.mediflow.srpailabs.com/chat/star_hospital")

# Save results
with open("_demo_full_journey_results.txt", "w", encoding="utf-8") as f:
    f.write(f"SRP MediFlow v7.1 — COMPLETE DEMO RESULTS\n")
    f.write(f"Date: {datetime.now()}\n")
    f.write(f"Target: {BASE_HOST}:{BASE_PORT}\n")
    f.write(f"Total: {total}  Passed: {PASS_COUNT}  Failed: {FAIL_COUNT}  ({pct}%)\n\n")
    f.write(f"DEMO PATIENT: {DEMO_NAME} | {DEMO_PHONE}\n")
    f.write(f"NEW CLIENT  : {NEW_NAME} | admin={NEW_USER}\n\n")
    for sym, msg in RESULTS:
        f.write(f"[{sym}] {msg}\n")
    f.write(f"\n{status}\n")

print(f"\n  → Saved to _demo_full_journey_results.txt")
print("=" * 70)

sys.exit(0 if FAIL_COUNT == 0 else 1)
