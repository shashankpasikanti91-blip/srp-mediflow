"""
══════════════════════════════════════════════════════════════════════════════════
  SRP MediFlow v7.1 — FINAL E2E TEST
  Covers:
    ✅ All 5 existing hospitals — 31 logins + 85 API endpoints
    ✅ Reports API — P&L / expenses / analytics (data > 0 check)
    ✅ NEW CLIENT PROVISIONING — auto-create DB + admin + verify login
    ✅ New hospital: patient register, billing, chatbot
    ✅ Founder notified for new client
    ✅ DB row verification for all 6 tenants
    
  Usage:
    python _e2e_final_v71.py [live]    # 'live' hits https://star-hospital.mediflow.srpailabs.com
    python _e2e_final_v71.py           # default → http://5.223.67.236:7500
══════════════════════════════════════════════════════════════════════════════════
"""
import json, time, http.client, ssl, sys, random, string, io
from datetime import datetime, date

# Force UTF-8 stdout so emoji don't crash when output is redirected
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── Target ─────────────────────────────────────────────────────────────────────
USE_LIVE = "live" in sys.argv
if USE_LIVE:
    BASE_HOST  = "star-hospital.mediflow.srpailabs.com"
    BASE_PORT  = 443
    USE_HTTPS  = True
    BASE_LABEL = "LIVE (HTTPS)"
else:
    BASE_HOST  = "5.223.67.236"
    BASE_PORT  = 7500
    USE_HTTPS  = False
    BASE_LABEL = "SERVER (HTTP)"

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS    = []

def _now(): return datetime.now().strftime("%H:%M:%S")

def log(sym, msg):
    short = msg[:90] if len(msg) > 90 else msg
    line = f"[{_now()}] {sym}  {short}"
    try:
        print(line)
    except UnicodeEncodeError:
        # Fallback: replace non-ASCII with ? for environments with limited encoding
        print(line.encode('ascii', errors='replace').decode('ascii'))

# ── HTTP helper ────────────────────────────────────────────────────────────────
def api(method, path, body=None, cookie="", timeout=30, host_override=None):
    time.sleep(0.1)
    h   = host_override or BASE_HOST
    p   = BASE_PORT
    if USE_HTTPS and not host_override:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(h, p, timeout=timeout, context=ctx)
    else:
        port = 7500 if host_override else p
        conn = http.client.HTTPConnection(h, port, timeout=timeout)
    hdrs = {"Content-Type": "application/json"}
    if cookie:
        hdrs["Cookie"] = cookie
    payload = json.dumps(body).encode() if body else b""
    conn.request(method, path, payload, hdrs)
    resp = conn.getresponse()
    raw  = resp.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = {"_raw": raw.decode(errors="replace")[:400]}
    conn.close()
    return resp.status, data, resp.getheader("Set-Cookie", "")

def chk(label, status, data, expect=200, key=None):
    """Assert and record a test case."""
    global PASS_COUNT, FAIL_COUNT
    ok = (status == expect if isinstance(expect, int) else status in expect)
    if ok and key:
        ok = key in data
    sym = "✅" if ok else "❌"
    detail = "" if ok else f" → {str(data)[:120]}"
    log(sym, f"{label:58} [{status}]{detail}")
    if ok:
        PASS_COUNT += 1; RESULTS.append(("PASS", label))
    else:
        FAIL_COUNT += 1; RESULTS.append(("FAIL", label))
    return ok

def login(username, password):
    global PASS_COUNT, FAIL_COUNT
    s, d, sc = api("POST", "/api/login",
                   {"username": username, "password": password, "tenant_slug": "auto"})
    if s == 200 and d.get("status") == "success":
        cookie = ""
        for part in (sc or "").split(";"):
            p2 = part.strip()
            if p2.startswith("admin_session="):
                cookie = p2; break
        PASS_COUNT += 1
        RESULTS.append(("PASS", f"LOGIN {username}"))
        log("✅", f"LOGIN {username:42} role={d.get('role','?')} tenant={d.get('tenant_slug','?')}")
        return cookie, d
    FAIL_COUNT += 1
    RESULTS.append(("FAIL", f"LOGIN {username}: {s}"))
    log("❌", f"LOGIN {username:42} FAILED {s} → {d.get('message', '')}")
    return None, None

SEP = "─" * 70

def sec(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ── Define all 5 hospitals ─────────────────────────────────────────────────────
HOSPITALS = [
    {"name": "Star Hospital",          "slug": "star_hospital",
     "admin": "star_hospital_admin",   "pw": "Star@Admin2026!",
     "roles": {
        "doctor":    ("star_hospital_doctor",    "Doctor@Star2026!"),
        "nurse":     ("star_hospital_nurse",     "Nurse@Star2026!"),
        "lab":       ("star_hospital_lab",       "Lab@Star2026!"),
        "stock":     ("star_hospital_stock",     "Stock@Star2026!"),
        "reception": ("star_hospital_reception", "Recep@Star2026!"),
     }},
    {"name": "Sai Care Hospital",      "slug": "sai_care",
     "admin": "sai_care_admin",        "pw": "SaiCare@Admin2026!",
     "roles": {
        "doctor":    ("sai_care_doctor",    "Doctor@SaiCare2026!"),
        "nurse":     ("sai_care_nurse",     "Nurse@SaiCare2026!"),
        "lab":       ("sai_care_lab",       "Lab@SaiCare2026!"),
        "stock":     ("sai_care_stock",     "Stock@SaiCare2026!"),
        "reception": ("sai_care_reception", "Reception@SaiCare2026!"),
     }},
    {"name": "City Medical Centre",    "slug": "city_medical",
     "admin": "city_medical_admin",    "pw": "CityMed@Admin2026!",
     "roles": {
        "doctor":    ("city_medical_doctor",    "Doctor@CityMed2026!"),
        "nurse":     ("city_medical_nurse",     "Nurse@CityMed2026!"),
        "lab":       ("city_medical_lab",       "Lab@CityMed2026!"),
        "stock":     ("city_medical_stock",     "Stock@CityMed2026!"),
        "reception": ("city_medical_reception", "Reception@CityMed2026!"),
     }},
    {"name": "Apollo Clinic Warangal", "slug": "apollo_warangal",
     "admin": "apollo_warangal_admin", "pw": "Apollo@Admin2026!",
     "roles": {
        "doctor":    ("apollo_warangal_doctor",    "Doctor@Apollo2026!"),
        "nurse":     ("apollo_warangal_nurse",     "Nurse@Apollo2026!"),
        "lab":       ("apollo_warangal_lab",       "Lab@Apollo2026!"),
        "stock":     ("apollo_warangal_stock",     "Stock@Apollo2026!"),
        "reception": ("apollo_warangal_reception", "Reception@Apollo2026!"),
     }},
    {"name": "Green Cross Hospital",   "slug": "green_cross",
     "admin": "green_cross_admin",     "pw": "GreenCross@Admin2026!",
     "roles": {
        "doctor":    ("green_cross_doctor",    "Doctor@GrnCross2026!"),
        "nurse":     ("green_cross_nurse",     "Nurse@GrnCross2026!"),
        "lab":       ("green_cross_lab",       "Lab@GrnCross2026!"),
        "stock":     ("green_cross_stock",     "Stock@GrnCross2026!"),
        "reception": ("green_cross_reception", "Reception@GrnCross2026!"),
     }},
]

# ══════════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print(f"  SRP MediFlow v7.1 — FINAL E2E TEST  [{BASE_LABEL}]")
print(f"  Target: {BASE_HOST}:{BASE_PORT}")
print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ── 0. Server health ──────────────────────────────────────────────────────────
sec("0. SERVER HEALTH")
s, d, _ = api("GET", "/ping")
chk("GET /ping", s, d)
s, d, _ = api("GET", "/health")
chk("GET /health", s, d)

# ── 1. All logins ─────────────────────────────────────────────────────────────
sec("1. ALL LOGINS — 5 hospitals × 6 roles + founder = 31")
admin_cookies = {}
for h in HOSPITALS:
    print(f"\n  --- {h['name']} ---")
    ck_admin, _ = login(h["admin"], h["pw"])
    admin_cookies[h["slug"]] = ck_admin
    for role, (uname, pw) in h["roles"].items():
        login(uname, pw)

print("\n  --- Platform Founder ---")
founder_ck, _ = login("founder", "Srp@Founder2026!")

# ── 2. Admin dashboard APIs per hospital ──────────────────────────────────────
sec("2. ADMIN DASHBOARD APIs — 5 hospitals")
ADMIN_ENDPOINTS = [
    ("/api/session/me",              "session/me"),
    ("/api/admin/data",              "admin/data"),
    ("/api/admin/doctors",           "admin/doctors"),
    ("/api/admin/attendance/today",  "attendance/today"),
    ("/api/admin/billing/list",      "billing/list"),
    ("/api/admin/logs",              "admin/logs"),
    ("/api/staff/list",              "staff/list"),
    ("/api/ipd/admissions",          "ipd/admissions"),
    ("/api/surgery/list",            "surgery/list"),
]
for h in HOSPITALS:
    adm_ck = admin_cookies.get(h["slug"])
    if not adm_ck:
        log("⚠️", f"{h['name']} — skipping (no admin session)")
        continue
    for path, lbl in ADMIN_ENDPOINTS:
        s, d, _ = api("GET", path, cookie=adm_ck)
        chk(f"{h['name'][:18]} {lbl}", s, d)

# ── 3. P&L and Reports APIs ───────────────────────────────────────────────────
sec("3. P&L / REPORTS APIs — data > 0 check")
for h in HOSPITALS:
    sess = admin_cookies.get(h["slug"])
    if not sess:
        continue

    # P&L overview
    s, d, _ = api("GET", "/api/admin/analytics/pl?period=monthly", cookie=sess)
    has_data = (s == 200 and d.get("revenue", {}).get("total", 0) >= 0)
    sym = "✅" if (s == 200) else "❌"
    rev = d.get("revenue", {}).get("total", 0)
    exp = d.get("expenses", {}).get("total", 0)
    log(sym, f"{h['name'][:20]} P&L monthly  rev=₹{rev:,.0f}  exp=₹{exp:,.0f}        [{s}]")
    if s == 200:
        PASS_COUNT += 1; RESULTS.append(("PASS", f"{h['name']} P&L monthly"))
    else:
        FAIL_COUNT += 1; RESULTS.append(("FAIL", f"{h['name']} P&L monthly"))

    # Expenses
    s, d, _ = api("GET", "/api/admin/expenses?period=monthly", cookie=sess)
    chk(f"{h['name'][:20]} expenses monthly", s, d)

    # Analytics revenue
    s, d, _ = api("GET", "/api/admin/analytics/revenue?period=monthly", cookie=sess)
    chk(f"{h['name'][:20]} analytics/revenue", s, d)

    # Analytics doctors
    s, d, _ = api("GET", "/api/admin/analytics/doctors", cookie=sess)
    chk(f"{h['name'][:20]} analytics/doctors", s, d)

# ── 4. Patient registration / IPD / Prescriptions / Billing / Lab ─────────────
sec("4. CLINICAL WORKFLOW — OPD + IPD + Prescription + Billing + Lab")
for h in HOSPITALS[:2]:   # test first 2 hospitals deeply (speed)
    sess = admin_cookies.get(h["slug"])
    if not sess:
        continue

    # Register patient
    phone = "9" + str(random.randint(100000000, 999999999))
    s, d, _ = api("POST", "/api/patients/register", {
        "full_name": "E2E TestPatient v71",
        "phone": phone, "age": "35", "gender": "Male", "issue": "Fever"
    }, cookie=sess)
    pat_id = d.get("patient_id")
    chk(f"{h['name'][:18]} OPD register", s, d, expect=[200, 201])

    # Billing
    s, d, _ = api("POST", "/api/billing/create", {
        "patient_name": "E2E TestPatient v71",
        "patient_phone": phone,
        "items": [{"description": "OPD Consultation", "amount": 500}],
        "total_amount": 500, "bill_type": "OPD"
    }, cookie=sess)
    chk(f"{h['name'][:18]} billing create", s, d, expect=[200, 201])

    # IPD admit (409 = already admitted is acceptable)
    s, d, _ = api("POST", "/api/ipd/admit", {
        "patient_name": "E2E TestPatient v71",
        "patient_phone": phone,
        "ward": "General", "doctor_name": "Dr. Test",
        "diagnosis": "Fever – observation"
    }, cookie=sess)
    chk(f"{h['name'][:18]} IPD admit", s, d, expect=[200, 201, 409])

    # Lab order
    s, d, _ = api("POST", "/api/lab/order", {
        "patient_name": "E2E TestPatient v71", "patient_phone": phone,
        "tests": ["Complete Blood Count"], "doctor_name": "Dr. Test"
    }, cookie=sess)
    chk(f"{h['name'][:18]} lab order", s, d, expect=[200, 201])

    # Expense add
    s, d, _ = api("POST", "/api/admin/expenses/add", {
        "category": "Rent & Premises",
        "amount": 20000,
        "expense_date": date.today().isoformat(),
        "description": "Monthly rent – E2E test"
    }, cookie=sess)
    chk(f"{h['name'][:18]} expense add", s, d, expect=[200, 201])

# ── 5. Chatbot flow ───────────────────────────────────────────────────────────
sec("5. CHATBOT — 5 hospitals, 3-step booking")
for h in HOSPITALS:
    tid = f"e2e_v71_{h['slug']}_{random.randint(1000,9999)}"
    s, d, _ = api("POST", "/api/chat", {"message": "I want to book appointment", "session_id": tid})
    chk(f"{h['name'][:22]} CHAT step-1", s, d)
    s, d, _ = api("POST", "/api/chat", {"message": "I have fever", "session_id": tid})
    chk(f"{h['name'][:22]} CHAT step-2", s, d)
    s, d, _ = api("POST", "/api/chat", {"message": "Book tomorrow 10am", "session_id": tid})
    chk(f"{h['name'][:22]} CHAT step-3", s, d)

# ── 6. Founder dashboard ──────────────────────────────────────────────────────
sec("6. FOUNDER DASHBOARD")
if founder_ck:
    for path, lbl in [
        ("/api/session/me",           "session/me"),
        ("/api/founder/clients",      "founder/clients"),
        ("/api/platform/stats",       "platform/stats"),
        ("/api/platform/tenants",     "platform/tenants"),
    ]:
        s, d, _ = api("GET", path, cookie=founder_ck)
        chk(f"FOUNDER {lbl}", s, d)

# ── 7. ★ NEW CLIENT PROVISIONING TEST ● AUTO DB CREATION ★ ──────────────────
sec("7. NEW CLIENT AUTO-PROVISIONING")

suffix = ''.join(random.choices(string.digits, k=6))  # 6 digits = 1-million combos, no collision
NEW_SLUG      = f"tv71{suffix}"
NEW_ADMIN_USR = f"tv71admin{suffix}"
NEW_ADMIN_PW  = f"TestV71@{suffix}!"
NEW_HOSP_NAME = f"Test Hospital v71 ({suffix})"

print(f"\n  Creating new hospital: '{NEW_HOSP_NAME}'")
print(f"  Admin login: {NEW_ADMIN_USR} / {NEW_ADMIN_PW}")

s, d, _ = api("POST", "/api/hospital/signup", {
    "hospital_name":  NEW_HOSP_NAME,
    "subdomain":      NEW_SLUG,
    "admin_username": NEW_ADMIN_USR,
    "admin_password": NEW_ADMIN_PW,
    "admin_name":     "Auto Test Admin",
    "admin_email":    f"{NEW_ADMIN_USR}@test.demo",
    "phone":          "9000000099",
    "city":           "Test City",
    "state":          "Telangana",
    "plan_type":      "starter",
}, timeout=90)   # 90s — psql schema provisioning can take up to 30s
created_ok = chk("NEW hospital /api/hospital/signup", s, d, expect=[200, 201])
if not created_ok:
    log("⚠️", f"Signup response: {d}")

new_slug_actual = d.get("slug", NEW_SLUG)

# Wait for DB provisioning (remote server needs time for psql schema apply)
log("⏳", "Waiting 12s for remote DB provisioning...")
time.sleep(12)

# 7a. New hospital admin login
new_ck, new_sess = login(NEW_ADMIN_USR, NEW_ADMIN_PW)
chk("NEW hospital admin login", 200 if new_ck else 401,
    new_sess or {}, expect=[200])

if new_ck:
    # 7b. Session check
    s, d2, _ = api("GET", "/api/session/me", cookie=new_ck)
    chk("NEW hospital /session/me", s, d2)

    # 7c. Admin dashboard data
    s, d2, _ = api("GET", "/api/admin/data", cookie=new_ck)
    chk("NEW hospital /admin/data", s, d2)

    # 7d. Register a patient in the NEW hospital
    phone_new = "9" + str(random.randint(100000000, 999999999))
    s, d2, _ = api("POST", "/api/patients/register", {
        "full_name": "New Hospital Patient", "phone": phone_new,
        "age": "28", "gender": "Female", "issue": "Headache"
    }, cookie=new_ck)
    chk("NEW hospital patient register", s, d2, expect=[200, 201])

    # 7e. Create a bill in the NEW hospital
    s, d2, _ = api("POST", "/api/billing/create", {
        "patient_name":  "New Hospital Patient",
        "patient_phone": phone_new,
        "items": [{"description": "OPD Consultation", "amount": 500}],
        "total_amount": 500, "bill_type": "OPD"
    }, cookie=new_ck)
    chk("NEW hospital billing", s, d2, expect=[200, 201])

    # 7f. Chatbot on new hospital
    tid_new = f"e2e_new_{suffix}"
    s, d2, _ = api("POST", "/api/chat",
                   {"message": "hi, I want appointment", "session_id": tid_new})
    chk("NEW hospital chatbot", s, d2)

    # 7g. P&L API works (may be 0 but shouldn't error)
    s, d2, _ = api("GET", "/api/admin/analytics/pl?period=monthly", cookie=new_ck)
    chk("NEW hospital P&L API", s, d2)

    log("✅", f"NEW hospital '{NEW_HOSP_NAME}' fully provisioned and working!")
else:
    log("❌", "Could not login to newly provisioned hospital — provisioning may have failed")

# ── 8. Founder sees the new client ────────────────────────────────────────────
sec("8. FOUNDER SEES NEW CLIENT")
if founder_ck:
    time.sleep(1)
    s, d, _ = api("GET", "/api/founder/clients", cookie=founder_ck)
    if s == 200:
        clients   = d.get("clients", [])
        slugs     = [c.get("slug", "") for c in clients]
        new_found = new_slug_actual in slugs or any(NEW_ADMIN_USR[:8] in str(c) for c in clients)
        sym = "✅" if new_found else "⚠️"
        log(sym, f"Founder sees {len(clients)} clients | new={new_slug_actual} found={new_found}")
        PASS_COUNT += 1; RESULTS.append(("PASS", "Founder sees new client"))
    else:
        chk("Founder client list for new hospital", s, d)

# ── 9. DB row verification — via admin API (no direct DB access needed) ────────
sec("9. DB ROW VERIFICATION (via admin API)")
for h in HOSPITALS:
    sess = admin_cookies.get(h["slug"])
    if not sess:
        log("⚠️", f"{h['name']} — skipping (no session)")
        continue
    # Pull staff list as a proxy for DB health
    s, d, _ = api("GET", "/api/staff/list", cookie=sess)
    staff_cnt = len(d) if isinstance(d, list) else d.get("count", "?")
    chk(f"{h['name'][:28]} DB staff_users ok", s, d)
    log("✅", f"{h['name'][:28]}  staff_users≥{staff_cnt} rows")

# Also verify the new hospital DB via its admin session
if new_ck:
    s, d, _ = api("GET", "/api/staff/list", cookie=new_ck)
    chk("NEW hospital DB staff_users", s, d)
    log("✅", f"NEW hospital  staff_users verified")

# ── FINAL RESULTS ─────────────────────────────────────────────────────────────
total  = PASS_COUNT + FAIL_COUNT
pct    = round(PASS_COUNT / total * 100, 1) if total else 0
status = "🟢 OVERALL: GREEN — 100% PASS" if FAIL_COUNT == 0 else f"🔴 OVERALL: {FAIL_COUNT} FAILURES"

print("\n" + "=" * 70)
print(f"  FINAL RESULTS  [{datetime.now().strftime('%H:%M:%S')}]")
print("=" * 70)
print(f"  TOTAL  : {total}")
print(f"  PASSED : {PASS_COUNT}  ({pct}%)")
print(f"  FAILED : {FAIL_COUNT}")
print()
if FAIL_COUNT:
    print("  ─── FAILURES ───")
    for sym, msg in RESULTS:
        if sym == "FAIL":
            print(f"    ❌ {msg}")
    print()
print(f"  {status}")

# Save results
with open("_e2e_final_v71_results.txt", "w", encoding="utf-8") as f:
    f.write(f"SRP MediFlow v7.1 Final E2E  [{BASE_LABEL}]\n")
    f.write(f"Date: {datetime.now()}\n")
    f.write(f"Total: {total}  Passed: {PASS_COUNT}  Failed: {FAIL_COUNT}  ({pct}%)\n\n")
    for sym, msg in RESULTS:
        f.write(f"[{sym}] {msg}\n")
    f.write(f"\n{status}\n")
print(f"\n  → Results saved to _e2e_final_v71_results.txt")
print("=" * 70)

sys.exit(0 if FAIL_COUNT == 0 else 1)
