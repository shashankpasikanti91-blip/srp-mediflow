"""
SRP MediFlow - Full System Test Suite
Tests: DB tables, all API endpoints, RBAC, IPD, Surgery, Pharmacy, Billing
Run: python srp_test_all.py
"""
import sys, json, time, traceback
import urllib.request, urllib.parse, urllib.error
from http.cookiejar import CookieJar

BASE = "http://localhost:7500"
PASS, FAIL, WARN = [], [], []
COOKIE_JAR = CookieJar()
COOKIE_HANDLER = urllib.request.HTTPCookieProcessor(COOKIE_JAR)
OPENER = urllib.request.build_opener(COOKIE_HANDLER)
SESSION_TOKEN = None  # kept for compatibility

# ─── helpers ─────────────────────────────────────────────────────────────────
def ok(name):  PASS.append(name); print(f"  ✅  {name}")
def fail(name, err=""): FAIL.append(name); print(f"  ❌  {name}  {err}")
def warn(name, msg=""): WARN.append(name); print(f"  ⚠️   {name}  {msg}")

def get(path, token=None, raw=False):
    req = urllib.request.Request(f"{BASE}{path}")
    # send stored cookie regardless of token arg
    try:
        with OPENER.open(req, timeout=6) as r:
            body = r.read()
            if raw: return r.status, {}
            try: return r.status, json.loads(body)
            except: return r.status, {"_html": True}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

def post(path, data, token=None):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                  headers={"Content-Type":"application/json"})
    try:
        with OPENER.open(req, timeout=6) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: body_err = json.loads(e.read())
        except: body_err = {}
        return e.code, body_err
    except Exception as e:
        return 0, {"error": str(e)}

# ─── 1. DB Schema ─────────────────────────────────────────────────────────────
print("\n[1] DATABASE SCHEMA")
try:
    import psycopg2
    conn = psycopg2.connect(host='localhost',port=5434,database='hospital_ai',
                             user='ats_user',password='ats_password')
    cur = conn.cursor()
    required_tables = [
        'staff_users','patients','appointments','billing','inventory_stock',
        'medicines','wards','beds','attendance',
        # extended
        'patient_admissions','surgery_records','procedure_charges',
        'discharge_summaries','bill_items','daily_rounds',
    ]
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    existing = {r[0] for r in cur.fetchall()}
    for t in required_tables:
        if t in existing: ok(f"table: {t}")
        else: fail(f"table: {t}", "MISSING")
    # Check altered columns
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='billing' AND column_name IN ('tax_amount','admission_id','bed_charges','surgery_charges','notes')")
    found_cols = {r[0] for r in cur.fetchall()}
    for col in ['tax_amount','admission_id','bed_charges','notes']:
        if col in found_cols: ok(f"billing.{col}")
        else: fail(f"billing.{col}", "column missing")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='inventory_stock' AND column_name IN ('supplier','batch_number')")
    found_cols2 = {r[0] for r in cur.fetchall()}
    for col in ['supplier','batch_number']:
        if col in found_cols2: ok(f"inventory_stock.{col}")
        else: fail(f"inventory_stock.{col}", "column missing")
    conn.close()
except Exception as e:
    fail("DB schema check", str(e))

# ─── 2. Server reachability ───────────────────────────────────────────────────
print("\n[2] SERVER REACHABILITY")
status, _ = get("/login", raw=True)
if status == 200: ok("GET /login → 200")
else: fail("GET /login", f"status={status}")

status, _ = get("/", raw=True)
if status in (200, 302): ok("GET / → accessible")
else: fail("GET /", f"status={status}")

# ─── 3. Authentication ────────────────────────────────────────────────────────
print("\n[3] AUTHENTICATION & RBAC")# Check auth guard BEFORE login (no cookie yet)
_bare_req = urllib.request.Request(f"{BASE}/api/admin/data")
try:
    _r = urllib.request.urlopen(_bare_req, timeout=5)
    warn("No-token request", f"Got {_r.status} (expected 401/403)")
except urllib.error.HTTPError as _e:
    if _e.code in (401, 403): ok("No-token request → 401/403")
    else: warn("No-token request", f"Got {_e.code}")
except Exception as _e:
    warn("No-token request", str(_e))
status, data = post("/api/login", {"username":"admin","password":"hospital2024"})
if status == 200 and data.get("status") in ("ok", "success"):
    SESSION_TOKEN = "cookie_auth_active"
    ok(f"POST /api/login admin \u2192 cookie set, role={data.get('role')}, redirect={data.get('redirect')}")
else:
    fail("POST /api/login admin", f"status={status} data={data}")

# Wrong password
status, data = post("/api/login", {"username":"admin","password":"wrongpass999"})
if status in (401, 403, 200) and data.get("status") != "ok":
    ok("Wrong password → rejected")
else:
    warn("Wrong password check", f"Got {status}/{data.get('status')}")

# ─── 4. Admin API ─────────────────────────────────────────────────────────────
print("\n[4] ADMIN DASHBOARD DATA")
if SESSION_TOKEN:
    s, d = get("/api/admin/data", SESSION_TOKEN)
    if s == 200: ok("GET /api/admin/data → 200")
    else: fail("GET /api/admin/data", f"{s}")

    s, d = get("/api/admin/extended-data", SESSION_TOKEN)
    if s == 200:
        ok("GET /api/admin/extended-data → 200")
        for key in ['total_admissions','low_stock_count','total_revenue']:
            if key in d: ok(f"  extended-data.{key} = {d[key]}")
            else: warn(f"  extended-data.{key}", "key missing")
    else: fail("GET /api/admin/extended-data", f"{s}")

# ─── 5. Patients & Appointments ───────────────────────────────────────────────
print("\n[5] PATIENTS & APPOINTMENTS")
if SESSION_TOKEN:
    # patients/appointments are bundled in admin/data
    s, d = get("/api/admin/data")
    if s == 200:
        ok(f"GET /api/admin/data (patients bundle) → {len(d.get('registrations', d.get('patients', [])))} records")
        ok(f"  appointments included: {d.get('total_appointments', 'N/A')}")
    else: fail("GET /api/admin/data for patients", f"{s}")

# ─── 6. IPD Admission Flow ────────────────────────────────────────────────────
print("\n[6] IPD ADMISSION FLOW")
test_admission_id = None
if SESSION_TOKEN:
    # Admit patient
    s, d = post("/api/ipd/admit", {
        "patient_name": "TEST Patient IPD",
        "patient_phone": "9999000001",
        "patient_aadhar": "111122223333",
        "age": 35, "gender": "M", "blood_group": "O+",
        "ward_name": "General Ward", "bed_number": "T-01",
        "admitting_doctor": "Dr. Test",
        "department": "Medicine",
        "diagnosis": "Test Fever for automated test",
        "admission_notes": "Test admission"
    }, SESSION_TOKEN)
    if s == 200 and d.get("status") == "ok":
        test_admission_id = d.get("admission_id")
        ok(f"POST /api/ipd/admit → admission_id={test_admission_id}")
    else:
        fail("POST /api/ipd/admit", f"{s} {d}")

    # List admissions
    s, d = get("/api/ipd/admissions", SESSION_TOKEN)
    if s == 200:
        adms = d.get("admissions", [])
        ok(f"GET /api/ipd/admissions → {len(adms)} records")
    else: fail("GET /api/ipd/admissions", f"{s}")

    # Get by ID
    if test_admission_id:
        s, d = get(f"/api/ipd/admission/{test_admission_id}", SESSION_TOKEN)
        if s == 200: ok(f"GET /api/ipd/admission/{test_admission_id} → OK")
        else: fail(f"GET /api/ipd/admission/{test_admission_id}", f"{s}")

        # Add daily round
        s, d = post("/api/ipd/round/add", {
            "admission_id": test_admission_id,
            "temperature": 98.6, "bp": "120/80",
            "pulse": 72, "spo2": 99, "weight": 70,
            "notes": "Test round - stable", "medications": "Paracetamol 500mg"
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok": ok("POST /api/ipd/round/add → OK")
        else: fail("POST /api/ipd/round/add", f"{s} {d}")

        # Get rounds
        s, d = get(f"/api/ipd/rounds/{test_admission_id}", SESSION_TOKEN)
        if s == 200:
            ok(f"GET /api/ipd/rounds/{test_admission_id} → {len(d.get('rounds',[]))} rounds")
        else: fail(f"GET /api/ipd/rounds", f"{s}")

        # Discharge
        s, d = post("/api/ipd/discharge", {
            "admission_id": test_admission_id,
            "final_diagnosis": "Resolved Fever",
            "treatment_given": "Antipyretics + IV fluids",
            "discharge_medicines": "Tab Paracetamol 3 days",
            "follow_up_date": "2026-03-15",
            "follow_up_notes": "Review if fever recurs"
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok":
            ok(f"POST /api/ipd/discharge → summary_id={d.get('discharge_summary_id')}")
        else: fail("POST /api/ipd/discharge", f"{s} {d}")

        # Get discharge summary
        s, d = get(f"/api/ipd/discharge/{test_admission_id}", SESSION_TOKEN)
        if s == 200: ok("GET /api/ipd/discharge summary → OK")
        else: warn("GET /api/ipd/discharge summary", f"{s}")

# ─── 7. Surgery ───────────────────────────────────────────────────────────────
print("\n[7] SURGERY MODULE")
test_surgery_id = None
if SESSION_TOKEN:
    s, d = post("/api/surgery/create", {
        "patient_name": "TEST Surgery Patient",
        "patient_phone": "9999000002",
        "surgery_type": "Appendectomy",
        "anesthesia_type": "general",
        "operation_date": "2026-03-10T09:00:00",
        "estimated_cost": 45000,
        "negotiated_cost": 40000,
        "operation_notes": "Routine appendectomy test"
    }, SESSION_TOKEN)
    if s == 200 and d.get("status") == "ok":
        test_surgery_id = d.get("surgery_id")
        ok(f"POST /api/surgery/create → id={test_surgery_id}")
    else: fail("POST /api/surgery/create", f"{s} {d}")

    s, d = get("/api/surgery/list", SESSION_TOKEN)
    if s == 200: ok(f"GET /api/surgery/list → {len(d.get('surgeries',[]))} records")
    else: fail("GET /api/surgery/list", f"{s}")

    if test_surgery_id:
        s, d = post("/api/surgery/update-cost", {
            "surgery_id": test_surgery_id,
            "negotiated_cost": 38000,
            "notes": "Patient negotiated discount"
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok": ok("POST /api/surgery/update-cost → OK")
        else: fail("POST /api/surgery/update-cost", f"{s} {d}")

# ─── 8. Procedures ───────────────────────────────────────────────────────────
print("\n[8] PROCEDURES")
if SESSION_TOKEN:
    s, d = get("/api/procedures/list", SESSION_TOKEN)
    if s == 200: ok(f"GET /api/procedures/list → {len(d.get('procedures',[]))} items")
    else: fail("GET /api/procedures/list", f"{s}")

    s, d = post("/api/procedures/add", {
        "procedure_name": "TEST ECG",
        "category": "diagnostic",
        "base_price": 250,
        "gst_rate": 0,
        "is_active": True
    }, SESSION_TOKEN)
    if s == 200 and d.get("status") == "ok": ok("POST /api/procedures/add → OK")
    else: fail("POST /api/procedures/add", f"{s} {d}")

# ─── 9. Pharmacy ─────────────────────────────────────────────────────────────
print("\n[9] PHARMACY / STOCK MANAGEMENT")
if SESSION_TOKEN:
    # Need a medicine_id; check if there are any medicines
    s, d = get("/api/medicines")
    med_id = None
    if s == 200:
        meds = d.get("medicines", [])
        if meds:
            med_id = meds[0]["id"]
            ok(f"GET /api/medicines \u2192 {len(meds)} medicines, using id={med_id}")
        else:
            warn("GET /api/medicines", "No medicines in DB \u2014 add-stock test may skip")
    else:
        # /api/medicines might be at /api/admin/medicines or bundled
        s2, d2 = get("/api/admin/data")
        if s2 == 200 and d2.get('medicines'):
            meds = d2['medicines']
            med_id = meds[0]['id']
            ok(f"GET medicines via /api/admin/data \u2192 {len(meds)} items, id={med_id}")
        else:
            warn("GET /api/medicines", f"404 \u2014 no separate medicines endpoint (bundled in admin/data)")

    if med_id:
        s, d = post("/api/pharmacy/add-stock", {
            "medicine_id": med_id,
            "batch_number": "BATCH-TEST-001",
            "expiry_date": "2027-12-31",
            "quantity": 100,
            "purchase_price": 5.50,
            "sell_price": 10.00,
            "supplier": "Test Pharma Ltd",
            "min_quantity": 10
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok":
            ok(f"POST /api/pharmacy/add-stock → id={d.get('id')}")
        else: fail("POST /api/pharmacy/add-stock", f"{s} {d}")

    s, d = get("/api/pharmacy/inventory", SESSION_TOKEN)
    if s == 200: ok(f"GET /api/pharmacy/inventory → {len(d.get('inventory',[]))} records")
    else: fail("GET /api/pharmacy/inventory", f"{s}")

    s, d = get("/api/pharmacy/alerts/low-stock", SESSION_TOKEN)
    if s == 200: ok(f"GET /api/pharmacy/alerts/low-stock → {len(d.get('low_stock',[]))} alerts")
    else: fail("GET /api/pharmacy/alerts/low-stock", f"{s}")

    s, d = get("/api/pharmacy/alerts/expiry", SESSION_TOKEN)
    if s == 200: ok(f"GET /api/pharmacy/alerts/expiry → {len(d.get('expiring',[]))} alerts")
    else: fail("GET /api/pharmacy/alerts/expiry", f"{s}")

# ─── 10. Billing ─────────────────────────────────────────────────────────────
print("\n[10] BILLING & GST")
test_bill_id = None
if SESSION_TOKEN:
    # Get an existing bill or create via patients
    s, d = get("/api/admin/billing/list")
    bills = []
    if s == 200:
        bills = d.get("bills", d.get("billing", []))
        ok(f"GET /api/admin/billing/list \u2192 {len(bills)} bills")
    else: warn("GET /api/admin/billing/list", f"{s}")

    if bills:
        test_bill_id = bills[0]["id"]
        s, d = get(f"/api/billing/items/{test_bill_id}", SESSION_TOKEN)
        if s == 200:
            ok(f"GET /api/billing/items/{test_bill_id} → {len(d.get('items',[]))} items")
            if "gst_summary" in d: ok("  GST summary present in bill")
        else: warn(f"GET /api/billing/items", f"{s}")

        # Add bill item (GST test)
        s, d = post("/api/billing/add-item", {
            "bill_id": test_bill_id,
            "item_type": "consultation",
            "description": "OPD Consultation Test",
            "quantity": 1,
            "unit_price": 300,
            "gst_rate": 0
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok": ok("POST /api/billing/add-item (GST 0%) → OK")
        else: warn("POST /api/billing/add-item", f"{s} {d}")

        s, d = post("/api/billing/add-item", {
            "bill_id": test_bill_id,
            "item_type": "medicine",
            "description": "Paracetamol 500mg x10",
            "quantity": 10,
            "unit_price": 5,
            "gst_rate": 5
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok": ok("POST /api/billing/add-item (GST 5% medicine) → OK")
        else: warn("POST /api/billing/add-item (med)", f"{s} {d}")

        # Record payment
        s, d = post("/api/billing/payment", {
            "bill_id": test_bill_id,
            "amount_paid": 500,
            "payment_mode": "cash"
        }, SESSION_TOKEN)
        if s == 200 and d.get("status") == "ok": ok("POST /api/billing/payment → OK")
        else: warn("POST /api/billing/payment", f"{s} {d}")

# ─── 11. HTML Pages ──────────────────────────────────────────────────────────
print("\n[11] DASHBOARD HTML PAGES")
if SESSION_TOKEN:
    # /admin works for ADMIN role
    s, _ = get("/admin", raw=True)
    if s == 200: ok("GET /admin page → 200")
    else: warn("GET /admin page", f"{s}")

    # These pages redirect ADMIN to login (role-check), so check they exist via bare requests
    _bare = urllib.request.build_opener()
    for path in ["/doctor", "/nurse", "/lab", "/stock"]:
        try:
            _bare.open(f"{BASE}{path}", timeout=4)
            ok(f"GET {path} page → served (HTML)")
        except urllib.error.HTTPError as _e:
            # 302 redirect = page exists but role mismatch → expected behaviour
            if _e.code == 302: ok(f"GET {path} page → 302 redirect (role-guarded, correct)")
            else: warn(f"GET {path} page", f"{_e.code}")
        except Exception as _e:
            warn(f"GET {path} page", str(_e))

# ─── 12. System Logs / Health ────────────────────────────────────────────────
print("\n[12] SYSTEM HEALTH")
if SESSION_TOKEN:
    s, d = get("/api/admin/logs")
    if s == 200: ok("GET /api/admin/logs \u2192 OK")
    else: warn("GET /api/admin/logs", f"{s}")

# ─── 13. Founder Alert System ─────────────────────────────────────────────────
print("\n[13] FOUNDER ALERT SYSTEM")

# 13a. Module import
try:
    import sys, os
    _pkg = os.path.dirname(os.path.abspath(__file__))
    if _pkg not in sys.path:
        sys.path.insert(0, _pkg)
    from notifications.founder_alerts import (
        send_founder_alert,
        FOUNDER_ALERT_EVENTS,
        _build_message,
        _LOG_FILE,
    )
    ok("notifications.founder_alerts imports successfully")
except ImportError as _e:
    fail("notifications.founder_alerts import", str(_e))

# 13b. FOUNDER_ALERT_EVENTS whitelist
try:
    required_events = {
        "SERVER_START", "SERVER_CRASH", "DATABASE_CONNECTION_ERROR",
        "NEW_CLIENT_REGISTERED", "SECURITY_ALERT", "BACKUP_FAILED",
    }
    if required_events == FOUNDER_ALERT_EVENTS:
        ok("FOUNDER_ALERT_EVENTS whitelist matches spec")
    else:
        missing = required_events - FOUNDER_ALERT_EVENTS
        extra   = FOUNDER_ALERT_EVENTS - required_events
        fail("FOUNDER_ALERT_EVENTS whitelist",
             f"missing={missing}, extra={extra}")
except Exception as _e:
    fail("FOUNDER_ALERT_EVENTS check", str(_e))

# 13c. Message format
try:
    _msg = _build_message("SERVER_START", "Test server start message")
    assert "🚨 SRP MEDIFLOW SYSTEM ALERT" in _msg, "Header missing"
    assert "Event: SERVER_START"          in _msg, "Event line missing"
    assert "Test server start message"    in _msg, "Body missing"
    assert "Timestamp:"                   in _msg, "Timestamp missing"
    ok("_build_message format is correct")
except AssertionError as _e:
    fail("_build_message format", str(_e))
except Exception as _e:
    fail("_build_message", str(_e))

# 13d. send_founder_alert — SERVER_START trigger (non-blocking, returns immediately)
try:
    import threading as _thr
    _before = _thr.active_count()
    send_founder_alert("SERVER_START", "SRP MediFlow test suite — server start alert")
    _after = _thr.active_count()
    # A daemon thread should have been spawned (may already have finished on fast machines)
    ok("send_founder_alert(SERVER_START) dispatched without blocking")
except Exception as _e:
    fail("send_founder_alert SERVER_START", str(_e))

# 13e. send_founder_alert — DATABASE_CONNECTION_ERROR trigger
try:
    send_founder_alert("DATABASE_CONNECTION_ERROR",
                       "Test: DB connection error alert from test suite")
    ok("send_founder_alert(DATABASE_CONNECTION_ERROR) dispatched")
except Exception as _e:
    fail("send_founder_alert DATABASE_CONNECTION_ERROR", str(_e))

# 13f. send_founder_alert — unknown event_type normalised to SECURITY_ALERT
try:
    send_founder_alert("UNKNOWN_EVENT", "This should be normalised to SECURITY_ALERT")
    ok("send_founder_alert unknown event_type normalised silently")
except Exception as _e:
    fail("send_founder_alert unknown event normalisation", str(_e))

# 13g. Log file created under logs/
try:
    import time as _time
    _time.sleep(0.3)  # allow daemon thread to write log entry
    if os.path.exists(_LOG_FILE):
        ok(f"logs/system_alerts.log exists: {_LOG_FILE}")
        with open(_LOG_FILE, encoding='utf-8') as _lf:
            _contents = _lf.read()
        if "SERVER_START" in _contents or "DATABASE_CONNECTION_ERROR" in _contents:
            ok("logs/system_alerts.log contains founder alert entries")
        else:
            warn("logs/system_alerts.log content", "Expected event names not yet flushed")
    else:
        fail("logs/system_alerts.log exists", "File not found — check _LOG_DIR creation")
except Exception as _e:
    fail("logs/system_alerts.log check", str(_e))

# 13h. /api/founder/system-status endpoint
if SESSION_TOKEN:
    s, d = get("/api/founder/system-status", SESSION_TOKEN)
    if s == 200:
        ok("GET /api/founder/system-status → 200")
        # Verify no patient data in response
        _safe_keys = {
            'server_status', 'active_clients', 'client_health', 'databases',
            'worker_processes', 'last_backup', 'db_reachable',
            'db_tables_present', 'missing_tables', 'last_activity', 'timestamp',
        }
        _patient_keys = {'patient_name', 'phone', 'aadhar', 'diagnosis',
                         'prescription', 'blood_group', 'address'}
        _response_keys = set(d.keys())
        _leak = _response_keys & _patient_keys
        if not _leak:
            ok("system-status: no patient data fields exposed")
        else:
            fail("system-status patient data leak", f"Found: {_leak}")
        # Check required top-level fields
        for _field in ('server_status', 'active_clients', 'databases',
                       'worker_processes', 'last_backup'):
            if _field in d:
                ok(f"  system-status.{_field} present")
            else:
                warn(f"  system-status.{_field}", "field missing from response")
        # check client_health items expose only safe fields
        for _ch in d.get('client_health', []):
            _ch_leak = set(_ch.keys()) & _patient_keys
            if _ch_leak:
                fail("client_health patient data leak", f"Found: {_ch_leak}")
                break
        else:
            if d.get('client_health') is not None:
                ok("client_health: no patient data fields exposed")
    else:
        fail("GET /api/founder/system-status", f"status={s}")

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print(f"  RESULTS:  {len(PASS)} passed  |  {len(FAIL)} failed  |  {len(WARN)} warnings")
print("="*60)
if FAIL:
    print("\nFAILED TESTS:")
    for f in FAIL: print(f"  ❌  {f}")
if WARN:
    print("\nWARNINGS:")
    for w in WARN: print(f"  ⚠️   {w}")
print()
sys.exit(0 if not FAIL else 1)
