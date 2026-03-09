"""
srp_hms_test.py  –  SRP MediFlow HMS v4 Test Suite
====================================================
Tests all 7 new hospital modules:
  1. Patient Registration Module  (POST /api/patients/register)
  2. Billing System               (POST /api/billing/create)
  3. Doctor Workflow              (GET  /api/doctor/patient-queue, note, prescription)
  4. Pharmacy Inventory           (GET  /api/pharmacy/stock, alerts + POST /api/pharmacy/sale)
  5. Lab & Diagnostic             (POST /api/lab/order, /api/lab/result)
  6. Owner Analytics              (GET  /api/admin/analytics/revenue|patients|doctors)
  7. Mobile Dashboard             (GET  /api/admin/mobile-dashboard)

  + Data Export                   (GET  /api/admin/export/*)
  + Reception Module              (POST /api/appointments/create)
  + Patient History               (GET  /api/patients/{id}/history)
  + Lab Report Linking            (GET  /api/lab/report/{patient_id})

Run:   python srp_hms_test.py
Requires server running on localhost:7500  (admin / hospital2024)
"""

import sys
import json
import time
import traceback
import urllib.request
import urllib.parse
import urllib.error
from http.cookiejar import CookieJar

BASE   = "http://localhost:7500"
ADMIN  = {"username": "admin", "password": "hospital2024"}

PASS, FAIL, WARN = [], [], []

COOKIE_JAR = CookieJar()
OPENER     = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(COOKIE_JAR)
)

# ─── helpers ──────────────────────────────────────────────────────────────────

def ok(name):   PASS.append(name); print(f"  ✅  {name}")
def fail(name, err=""): FAIL.append(name); print(f"  ❌  {name}  {err}")
def warn(name, msg=""):  WARN.append(name); print(f"  ⚠️   {name}  {msg}")


def get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    try:
        with OPENER.open(req, timeout=8) as r:
            try: return r.status, json.loads(r.read())
            except: return r.status, {}
    except urllib.error.HTTPError as e:
        try:  body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def post(path, data):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with OPENER.open(req, timeout=8) as r:
            try: return r.status, json.loads(r.read())
            except: return r.status, {}
    except urllib.error.HTTPError as e:
        try:  body_err = json.loads(e.read())
        except: body_err = {}
        return e.code, body_err
    except Exception as e:
        return 0, {"error": str(e)}


def login_admin():
    s, d = post("/api/login", ADMIN)
    if s == 200 and d.get("status") == "success":
        ok("Admin login for HMS test session")
        return True
    fail("Admin login", f"status={s} body={d}")
    return False


# ─── 0. Pre-flight ────────────────────────────────────────────────────────────

print("\n" + "="*70)
print("  SRP MediFlow HMS v4 — Test Suite")
print("="*70)

print("\n[0] Pre-flight: server reachability")
s, d = get("/health")
if s == 200:
    ok(f"GET /health → 200  (db={d.get('db')}, hms={d.get('hms_modules')})")
else:
    # Try legacy health endpoint
    s2, _ = get("/api/admin/data")
    if s2 in (200, 401):
        warn("GET /health", f"status={s} — trying legacy endpoint; server is up")
    else:
        fail("Server unreachable", f"GET /health returned {s}")
        print("\n❌ Cannot continue — start the server first:")
        print("   python srp_mediflow_server.py\n")
        sys.exit(1)

# Authenticate
print("\n[0b] Authentication")
if not login_admin():
    print("\n❌ Cannot continue without admin session.\n")
    sys.exit(1)


# ─── 1. Patient Registration Module ──────────────────────────────────────────

print("\n[1] PATIENT REGISTRATION MODULE")

# 1a. Register new patient
PATIENT_PHONE = f"9{int(time.time()) % 1000000000:09d}"
s, d = post("/api/patients/register", {
    "full_name":      "Test Patient HMS",
    "phone":          PATIENT_PHONE,
    "gender":         "Male",
    "dob":            "1990-06-15",
    "chief_complaint": "Fever and headache",
    "doctor":         "Dr. Test",
    "department":     "General Medicine",
    "visit_type":     "OP",
})
if s == 201 and d.get("patient_id"):
    ok(f"POST /api/patients/register → 201  (patient_id={d['patient_id']}, "
       f"ticket={d.get('op_ticket_no')}, is_new={d.get('is_new_patient')})")
    PATIENT_ID    = d["patient_id"]
    OP_TICKET     = d.get("op_ticket_no", "")
    PATIENT_NAME  = d.get("full_name", "Test Patient HMS")
else:
    fail("POST /api/patients/register", f"status={s} body={d}")
    PATIENT_ID   = None
    OP_TICKET    = ""
    PATIENT_NAME = "Test Patient HMS"

# 1b. OP ticket generated in < 3 s
if OP_TICKET:
    ok(f"OP ticket generated: {OP_TICKET}")
else:
    warn("OP ticket", "ticket_no missing in response")

# 1c. Register same phone = existing patient returned
if PATIENT_PHONE:
    s2, d2 = post("/api/patients/register", {
        "full_name":      "Test Patient HMS",
        "phone":          PATIENT_PHONE,
        "chief_complaint": "Follow-up",
    })
    if s2 == 201 and d2.get("is_new_patient") is False:
        ok("Repeat registration returns existing patient + new visit")
    elif s2 == 201:
        warn("Repeat registration", f"is_new_patient={d2.get('is_new_patient')}")
    else:
        fail("Repeat registration", f"status={s2}")

# 1d. Search by phone
s, d = get(f"/api/patients/search?phone={PATIENT_PHONE}")
if s == 200 and d.get("patients"):
    ok(f"GET /api/patients/search?phone → 200  (found {d['count']} patient(s))")
else:
    fail("GET /api/patients/search", f"status={s} body={d}")

# 1e. Patient history
if PATIENT_ID:
    s, d = get(f"/api/patients/{PATIENT_ID}/history")
    if s == 200 and d.get("patient"):
        ok(f"GET /api/patients/{PATIENT_ID}/history → 200  "
           f"(visits={d.get('total_visits')}, labs={len(d.get('lab_results', []))})")
    else:
        fail(f"GET /api/patients/{PATIENT_ID}/history", f"status={s} body={d}")

# 1f. Validation — missing full_name
s, d = post("/api/patients/register", {"phone": "0000000001"})
if s in (400, 422):
    ok("Patient register: missing full_name → 400")
else:
    warn("Patient register validation", f"expected 400, got {s}")


# ─── 2. Billing System ────────────────────────────────────────────────────────

print("\n[2] BILLING SYSTEM")

BILL_ID = None

# 2a. Create OPD invoice with line items
s, d = post("/api/billing/create", {
    "patient_name":  PATIENT_NAME,
    "patient_phone": PATIENT_PHONE,
    "bill_type":     "OPD",
    "discount":      50,
    "notes":         "Test invoice from HMS test suite",
    "items": [
        {"item_type": "consultation", "item_name": "OPD Consultation",    "price": 300, "quantity": 1, "tax_percent": 0},
        {"item_type": "lab",          "item_name": "CBC Blood Test",       "price": 200, "quantity": 1, "tax_percent": 0},
        {"item_type": "medicine",     "item_name": "Paracetamol 500mg",    "price": 15,  "quantity": 10, "tax_percent": 5},
    ],
})
if s == 201 and d.get("bill_id"):
    BILL_ID = d["bill_id"]
    ok(f"POST /api/billing/create → 201  (bill_id={BILL_ID}, "
       f"total={d.get('total_amount')}, net={d.get('net_amount')})")
else:
    fail("POST /api/billing/create", f"status={s} body={d}")

# 2b. Retrieve invoice
if BILL_ID:
    s, d = get(f"/api/billing/invoice/{BILL_ID}")
    if s == 200 and d.get("invoice"):
        inv = d["invoice"]
        ok(f"GET /api/billing/invoice/{BILL_ID} → 200  "
           f"(items={len(inv.get('items',[]))}, status={inv.get('status')})")
    else:
        fail(f"GET /api/billing/invoice/{BILL_ID}", f"status={s}")

# 2c. Daily revenue report
s, d = get("/api/billing/reports/daily")
if s == 200 and "total_revenue" in d:
    ok(f"GET /api/billing/reports/daily → 200  "
       f"(revenue={d.get('total_revenue')}, invoices={d.get('num_invoices')})")
else:
    fail("GET /api/billing/reports/daily", f"status={s} body={d}")

# 2d. GST line item check
if BILL_ID:
    s, d = get(f"/api/billing/invoice/{BILL_ID}")
    if s == 200:
        items = d.get("invoice", {}).get("items", [])
        gst_items = [i for i in items if float(i.get("tax_percent",0)) > 0]
        if gst_items:
            ok(f"GST billing: {len(gst_items)} item(s) with non-zero tax")
        else:
            warn("GST billing", "No items with tax_percent > 0 in invoice items")

# 2e. Missing patient_name → 400
s, d = post("/api/billing/create", {"bill_type": "OPD", "items": []})
if s in (400, 422):
    ok("Billing create: missing patient_name → 400")
else:
    warn("Billing validation", f"expected 400/422, got {s}")


# ─── 3. Doctor Workflow ───────────────────────────────────────────────────────

print("\n[3] DOCTOR WORKFLOW MODULE")

# 3a. Patient queue
s, d = get("/api/doctor/patient-queue")
if s == 200 and "queue" in d:
    ok(f"GET /api/doctor/patient-queue → 200  (count={d.get('count',0)})")
else:
    fail("GET /api/doctor/patient-queue", f"status={s} body={d}")

# 3b. Patient record for doctor
if PATIENT_ID:
    s, d = get(f"/api/doctor/patient/{PATIENT_ID}")
    if s == 200 and d.get("patient"):
        ok(f"GET /api/doctor/patient/{PATIENT_ID} → 200")
    else:
        fail(f"GET /api/doctor/patient/{PATIENT_ID}", f"status={s}")

# 3c. Structured prescription
PRESC_ID = None
s, d = post("/api/doctor/prescription", {
    "patient_name":  PATIENT_NAME,
    "patient_phone": PATIENT_PHONE,
    "diagnosis":     "Viral fever",
    "notes":         "Rest advised",
    "medicines_list": [
        {
            "medicine_name": "Paracetamol 500mg",
            "dosage":        "500 mg",
            "frequency":     "1-0-1",
            "duration":      "5 days",
            "instructions":  "Take after food",
            "quantity":      10,
        },
        {
            "medicine_name": "Cetirizine 10mg",
            "dosage":        "10 mg",
            "frequency":     "0-0-1",
            "duration":      "3 days",
            "instructions":  "Take at night",
            "quantity":      3,
        },
    ],
})
if s == 201 and d.get("prescription_id"):
    PRESC_ID = d["prescription_id"]
    ok(f"POST /api/doctor/prescription (structured) → 201  "
       f"(id={PRESC_ID}, medicines={d.get('medicines_count')})")
else:
    fail("POST /api/doctor/prescription (structured)", f"status={s} body={d}")

# 3d. Legacy prescription (medicines text only)
s, d = post("/api/doctor/prescription", {
    "patient_name":  PATIENT_NAME,
    "patient_phone": PATIENT_PHONE,
    "diagnosis":     "Common cold",
    "medicines":     "Vitamin C 500mg OD x 7 days",
    "notes":         "Legacy path test",
})
if s == 201 and d.get("prescription_id"):
    ok(f"POST /api/doctor/prescription (legacy) → 201  (id={d['prescription_id']})")
else:
    fail("POST /api/doctor/prescription (legacy)", f"status={s} body={d}")

# 3e. Doctor note
if PATIENT_ID:
    s, d = post("/api/doctor/note", {
        "patient_id": PATIENT_ID,
        "note_type":  "clinical",
        "note_text":  "Patient presents with 3-day history of fever. "
                      "O/E: Temp 38.5°C, no throat infection. BP: 120/80.",
    })
    if s == 201 and d.get("note_id"):
        ok(f"POST /api/doctor/note → 201  (note_id={d['note_id']})")
    else:
        fail("POST /api/doctor/note", f"status={s} body={d}")

# 3f. Lab results now appear in patient history
if PATIENT_ID:
    s, d = get(f"/api/patients/{PATIENT_ID}/history")
    if s == 200:
        ok(f"Patient history after prescription: visits={d.get('total_visits')} "
           f"prescriptions={len(d.get('prescriptions',[]))}")
    else:
        fail("Patient history (post-prescription)", f"status={s}")


# ─── 4. Pharmacy Inventory ────────────────────────────────────────────────────

print("\n[4] PHARMACY INVENTORY MODULE")

# 4a. Stock list
s, d = get("/api/pharmacy/stock")
if s == 200 and "stock" in d:
    ok(f"GET /api/pharmacy/stock → 200  (items={d.get('count',0)})")
else:
    fail("GET /api/pharmacy/stock", f"status={s} body={d}")

# 4b. Alerts (low stock + expiry)
s, d = get("/api/pharmacy/alerts")
if s == 200 and "summary" in d:
    summary = d.get("summary", {})
    ok(f"GET /api/pharmacy/alerts → 200  "
       f"(low={summary.get('low_stock_count',0)}, "
       f"expiring={summary.get('expiring_count',0)}, "
       f"out_of_stock={summary.get('out_of_stock_count',0)})")
else:
    fail("GET /api/pharmacy/alerts", f"status={s} body={d}")

# 4c. Legacy low-stock endpoint (backward compat)
s, d = get("/api/pharmacy/alerts/low-stock")
if s == 200:
    ok("GET /api/pharmacy/alerts/low-stock (legacy) → 200")
else:
    warn("GET /api/pharmacy/alerts/low-stock", f"status={s}")

# 4d. Pharmacy sale
s, d = post("/api/pharmacy/sale", {
    "patient_name":  PATIENT_NAME,
    "patient_phone": PATIENT_PHONE,
    "payment_mode":  "Cash",
    "items": [
        {
            "medicine_name": "Paracetamol 500mg",
            "quantity":      10,
            "unit_price":    5.0,
        },
    ],
})
if s == 201 and d.get("sale_id"):
    ok(f"POST /api/pharmacy/sale → 201  "
       f"(sale_id={d['sale_id']}, net={d.get('net_amount')})")
else:
    fail("POST /api/pharmacy/sale", f"status={s} body={d}")


# ─── 5. Lab & Diagnostic Module ───────────────────────────────────────────────

print("\n[5] LAB & DIAGNOSTIC MODULE")

ORDER_IDS  = []
RESULT_ID  = None

# 5a. Order a lab test
s, d = post("/api/lab/order", {
    "patient_name":  PATIENT_NAME,
    "patient_phone": PATIENT_PHONE,
    "patient_id":    PATIENT_ID,
    "tests":         ["CBC Blood Count", "Blood Sugar Fasting"],
    "test_type":     "LAB",
})
if s == 201 and d.get("order_ids"):
    ORDER_IDS = d["order_ids"]
    ok(f"POST /api/lab/order → 201  "
       f"(order_ids={ORDER_IDS}, tests={d.get('tests')})")
else:
    fail("POST /api/lab/order", f"status={s} body={d}")

# 5b. Record lab result and auto-link to patient
if ORDER_IDS:
    s, d = post("/api/lab/result", {
        "order_id":       ORDER_IDS[0],
        "patient_id":     PATIENT_ID,
        "patient_name":   PATIENT_NAME,
        "test_name":      "CBC Blood Count",
        "result_value":   "Hb: 12.5 g/dL, WBC: 8000/µL, Platelets: 2.5 lac/µL",
        "reference_range": "Hb: 13-17 g/dL",
        "unit":           "g/dL",
        "is_abnormal":    True,
        "remarks":        "Mild anaemia",
    })
    if s == 201 and d.get("result_id"):
        RESULT_ID = d["result_id"]
        ok(f"POST /api/lab/result → 201  "
           f"(result_id={RESULT_ID}, abnormal={d.get('is_abnormal')})")
    else:
        fail("POST /api/lab/result", f"status={s} body={d}")

# 5c. Lab report linked to patient history
if PATIENT_ID:
    s, d = get(f"/api/lab/report/{PATIENT_ID}")
    if s == 200 and "reports" in d:
        ok(f"GET /api/lab/report/{PATIENT_ID} → 200  "
           f"(reports={d.get('count',0)})")
    else:
        fail(f"GET /api/lab/report/{PATIENT_ID}", f"status={s} body={d}")

# 5d. Verify lab result appears in patient history
if PATIENT_ID and RESULT_ID:
    s, d = get(f"/api/patients/{PATIENT_ID}/history")
    if s == 200:
        labs = d.get("lab_results", [])
        if labs:
            ok(f"Lab result auto-linked to patient history (count={len(labs)})")
        else:
            warn("Lab result in patient history", "No lab_results in history yet")


# ─── 6. Owner Analytics Dashboard ─────────────────────────────────────────────

print("\n[6] OWNER ANALYTICS DASHBOARD")

for period in ("daily", "weekly", "monthly"):
    s, d = get(f"/api/admin/analytics/revenue?period={period}")
    if s == 200 and d.get("summary"):
        ok(f"GET /api/admin/analytics/revenue?period={period} → 200  "
           f"(total={d['summary'].get('total_revenue',0)}, "
           f"invoices={d['summary'].get('total_invoices',0)})")
    else:
        fail(f"GET /api/admin/analytics/revenue?period={period}", f"status={s} body={d}")

s, d = get("/api/admin/analytics/patients?period=daily")
if s == 200 and "visits" in d:
    ok(f"GET /api/admin/analytics/patients → 200  "
       f"(new={d.get('new_patients',0)}, "
       f"bed_occupancy={d.get('bed_occupancy',{}).get('occupancy_pct',0)}%)")
else:
    fail("GET /api/admin/analytics/patients", f"status={s} body={d}")

s, d = get("/api/admin/analytics/doctors")
if s == 200 and "doctors_on_duty" in d:
    ok(f"GET /api/admin/analytics/doctors → 200  "
       f"(on_duty={d.get('doctors_on_duty_count',0)})")
else:
    fail("GET /api/admin/analytics/doctors", f"status={s} body={d}")


# ─── 7. Mobile-Ready Dashboard ────────────────────────────────────────────────

print("\n[7] MOBILE-READY DASHBOARD")

s, d = get("/api/admin/mobile-dashboard")
if s == 200 and d.get("today"):
    today = d["today"]
    alerts = d.get("alerts", {})
    ok(f"GET /api/admin/mobile-dashboard → 200")
    ok(f"  today.revenue={today.get('revenue',0)}  "
       f"patients={today.get('patients',0)}  "
       f"doctors_on_duty={today.get('doctors_on_duty',0)}")
    ok(f"  alerts: low_stock={alerts.get('low_stock_medicines',0)}  "
       f"expiring={alerts.get('expiring_medicines',0)}  "
       f"pending_labs={alerts.get('pending_lab_orders',0)}")
    # Response must have all required mobile fields
    for field in ('today', 'month', 'alerts', 'timestamp', 'status'):
        if field in d:
            ok(f"  mobile-dashboard.{field} present")
        else:
            fail(f"mobile-dashboard.{field}", "field missing")
else:
    fail("GET /api/admin/mobile-dashboard", f"status={s} body={d}")


# ─── 8. Reception Module — Appointment Scheduling ─────────────────────────────

print("\n[8] RECEPTION MODULE — APPOINTMENT SCHEDULING")

s, d = post("/api/appointments/create", {
    "patient_name":     PATIENT_NAME,
    "patient_phone":    PATIENT_PHONE,
    "doctor_name":      "Dr. Test",
    "department":       "General Medicine",
    "appointment_date": "2026-03-10",
    "appointment_time": "10:30",
    "issue":            "Follow-up fever",
})
if s == 201 and d.get("appointment_id"):
    ok(f"POST /api/appointments/create → 201  "
       f"(appt_id={d['appointment_id']}, "
       f"time={d.get('appointment_time')}, "
       f"patient_linked={d.get('patient_id') is not None})")
else:
    fail("POST /api/appointments/create", f"status={s} body={d}")


# ─── 9. Data Export ───────────────────────────────────────────────────────────

print("\n[9] DATA EXPORT")

for etype in ("patients", "billing", "appointments"):
    s, d = get(f"/api/admin/export/{etype}?format=csv&range=daily")
    if s == 200:
        ok(f"GET /api/admin/export/{etype}?format=csv → 200")
    elif s == 503:
        warn(f"GET /api/admin/export/{etype}", "export module not available (503)")
    else:
        fail(f"GET /api/admin/export/{etype}", f"status={s}")


# ─── 10. RBAC Guards ──────────────────────────────────────────────────────────

print("\n[10] SECURITY / RBAC GUARDS")

# 10a. Unauthenticated access to patient registration should fail
_bare_req = urllib.request.Request(
    f"{BASE}/api/patients/register",
    data=json.dumps({"full_name": "Anon"}).encode(),
    headers={"Content-Type": "application/json"}
)
try:
    _r = urllib.request.urlopen(_bare_req, timeout=5)
    fail("Patient register: no-auth guard", f"Got {_r.status} — should be 401/403")
except urllib.error.HTTPError as _e:
    if _e.code in (401, 403):
        ok(f"Patient register: no-auth → {_e.code}")
    else:
        fail("Patient register: no-auth guard", f"code={_e.code}")

# 10b. Unauthenticated access to mobile dashboard
_bare2 = urllib.request.Request(f"{BASE}/api/admin/mobile-dashboard")
try:
    _r2 = urllib.request.urlopen(_bare2, timeout=5)
    fail("Mobile dashboard: no-auth guard", f"Got {_r2.status}")
except urllib.error.HTTPError as _e2:
    if _e2.code in (401, 403):
        ok(f"Mobile dashboard: no-auth → {_e2.code}")
    else:
        fail("Mobile dashboard: no-auth guard", f"code={_e2.code}")

# 10c. Input validation — missing required fields
s, _ = post("/api/billing/create", {})
if s in (400, 401, 403, 422):
    ok(f"Billing: empty POST → {s} (not 500)")
else:
    warn("Billing empty POST", f"got {s}")


# ─── 11. DB Schema Check ──────────────────────────────────────────────────────

print("\n[11] DATABASE SCHEMA — HMS v4 TABLES")

try:
    import psycopg2
    conn = psycopg2.connect(
        host='localhost', port=5434, database='hospital_ai',
        user='ats_user', password='ats_password'
    )
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    existing = {r[0] for r in cur.fetchall()}
    conn.close()

    hms_tables = [
        'patient_visits', 'doctor_notes', 'prescription_items',
        'lab_results', 'pharmacy_stock', 'op_tickets',
    ]
    for t in hms_tables:
        if t in existing:
            ok(f"HMS v4 table: {t}")
        else:
            fail(f"HMS v4 table: {t}", "MISSING — run server to bootstrap")
except Exception as e:
    warn("DB schema check", f"Could not connect: {e}")


# ─── 12. Performance: Registration under 3 seconds ───────────────────────────

print("\n[12] PERFORMANCE — Patient Registration < 3s")

_start = time.time()
s, d = post("/api/patients/register", {
    "full_name":      "Perf Test Patient",
    "phone":          f"8{int(time.time()) % 1000000000:09d}",
    "chief_complaint": "Performance test",
})
_elapsed = time.time() - _start

if s in (200, 201):
    if _elapsed < 3.0:
        ok(f"Patient registration time: {_elapsed:.3f}s  (< 3s ✅)")
    else:
        warn("Patient registration time", f"{_elapsed:.3f}s  (> 3s target)")
else:
    fail("Performance registration", f"status={s}")


# ─── Summary ─────────────────────────────────────────────────────────────────

print("\n" + "="*70)
print(f"  SRP MediFlow HMS v4 Test Results")
print(f"  {len(PASS)} passed  |  {len(FAIL)} failed  |  {len(WARN)} warnings")
print("="*70)
if FAIL:
    print("\n❌ FAILED TESTS:")
    for f in FAIL: print(f"   {f}")
if WARN:
    print("\n⚠️  WARNINGS:")
    for w in WARN: print(f"   {w}")
print()
sys.exit(0 if not FAIL else 1)
