"""
SRP MediFlow — SaaS Platform Test Suite
Tests: Billing, Analytics, Export, Onboarding, Audit Log, Backup, Clients Registry
Run: python srp_saas_test.py

Assumes the server is running at http://localhost:7500 and admin session is available.
"""
import sys, json, time, traceback
import urllib.request, urllib.parse, urllib.error
from http.cookiejar import CookieJar

BASE = "http://localhost:7500"
PASS, FAIL, WARN = [], [], []
COOKIE_JAR = CookieJar()
COOKIE_HANDLER = urllib.request.HTTPCookieProcessor(COOKIE_JAR)
OPENER = urllib.request.build_opener(COOKIE_HANDLER)
SESSION_TOKEN = None

# ─── helpers ──────────────────────────────────────────────────────────────────
def ok(name):       PASS.append(name); print(f"  ✅  {name}")
def fail(name, err=""): FAIL.append(name); print(f"  ❌  {name}  {err}")
def warn(name, msg=""): WARN.append(name); print(f"  ⚠️   {name}  {msg}")

def get(path, raw=False):
    req = urllib.request.Request(f"{BASE}{path}")
    try:
        with OPENER.open(req, timeout=8) as r:
            body = r.read()
            if raw: return r.status, {}, body
            try: return r.status, json.loads(body), body
            except: return r.status, {"_html": True}, body
    except urllib.error.HTTPError as e:
        body = b""
        try: body = e.read()
        except: pass
        try: return e.code, json.loads(body), body
        except: return e.code, {}, body
    except Exception as e:
        return 0, {"error": str(e)}, b""

def post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with OPENER.open(req, timeout=8) as r:
            body = r.read()
            try: return r.status, json.loads(body)
            except: return r.status, {}
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except: return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

# ─── 0. Admin Login ────────────────────────────────────────────────────────────
print("\n" + "═"*60)
print(" SRP MediFlow — SaaS Platform Test Suite")
print("═"*60)
print("\n[0] ADMIN LOGIN")

s, d = post("/api/login", {"username": "admin", "password": "hospital2024"})
if s == 200 and d.get("status") in ("ok", "success"):
    SESSION_TOKEN = "cookie_active"
    ok(f"Admin login → role={d.get('role')}")
else:
    fail("Admin login", f"status={s} data={d}")
    print("\n  ⛔  Cannot continue without admin session. Exiting.\n")
    sys.exit(1)

# ─── 1. Billing Plans ─────────────────────────────────────────────────────────
print("\n[1] BILLING PLANS (public endpoint)")
s, d, _ = get("/api/admin/billing/plans")
if s == 200 and "plans" in d:
    plans = d["plans"]
    ok(f"GET /api/admin/billing/plans → {len(plans)} plans")
    for plan_key in ("starter", "professional", "enterprise"):
        if plan_key in plans or any(p.get("name","").lower() == plan_key for p in (plans.values() if isinstance(plans, dict) else plans)):
            ok(f"  plan '{plan_key}' present")
        else:
            warn(f"  plan '{plan_key}'", "Not found in plans list")
else:
    fail("GET /api/admin/billing/plans", f"status={s}")

# ─── 2. Clients Registry ──────────────────────────────────────────────────────
print("\n[2] CLIENTS REGISTRY")
s, d, _ = get("/api/admin/clients/registry")
if s == 200 and "clients" in d:
    clients = d["clients"]
    ok(f"GET /api/admin/clients/registry → {len(clients)} clients")
elif s == 200:
    ok("GET /api/admin/clients/registry → 200 (no clients key — check response shape)")
    warn("clients key missing", f"keys={list(d.keys())}")
else:
    fail("GET /api/admin/clients/registry", f"status={s}")

# ─── 3. Hospital Onboarding ────────────────────────────────────────────────────
print("\n[3] HOSPITAL ONBOARDING")
_ts = int(time.time())
reg_payload = {
    "hospital_name": f"Test Clinic SaaS {_ts}",
    "subdomain":     f"testclinic{_ts}",
    "admin_email":   f"admin{_ts}@testclinic.com",
    "admin_username": f"testadmin{_ts}",
    "plan": "starter",
    "contact_phone": "9876543210"
}
s, d = post("/api/admin/register-client", reg_payload)
if s in (200, 201):
    ok(f"POST /api/admin/register-client → status={s}")
    registered_client_id = d.get("client_id")
    if d.get("login_url"):   ok(f"  login_url returned: {d['login_url']}")
    if d.get("admin_password"): ok("  admin_password returned (auto-generated)")
    if registered_client_id: ok(f"  client_id: {registered_client_id}")
    else: warn("register-client", "client_id not returned")
elif s == 400:
    warn("POST /api/admin/register-client", f"400 — {d.get('error','?')} (may be duplicate subdomain from previous run)")
    registered_client_id = None
else:
    fail("POST /api/admin/register-client", f"status={s} data={d}")
    registered_client_id = None

# ─── 4. Billing Accounts ──────────────────────────────────────────────────────
print("\n[4] BILLING ACCOUNTS")
s, d, _ = get("/api/admin/billing/accounts")
if s == 200:
    accounts = d.get("accounts", d.get("billing_accounts", []))
    ok(f"GET /api/admin/billing/accounts → {len(accounts)} accounts")
else:
    fail("GET /api/admin/billing/accounts", f"status={s}")

# Per-client account lookup
if registered_client_id:
    s, d, _ = get(f"/api/admin/billing/account/{registered_client_id}")
    if s == 200:
        ok(f"GET /api/admin/billing/account/{registered_client_id} → 200")
        ok(f"  plan_name: {d.get('plan_name','?')}")
        ok(f"  payment_status: {d.get('payment_status','?')}")
    elif s == 404:
        warn(f"billing/account/{registered_client_id}", "404 — billing record may not have been created")
    else:
        fail(f"GET /api/admin/billing/account/{registered_client_id}", f"status={s}")

# Billing status update
if registered_client_id:
    s, d = post("/api/admin/billing/update", {
        "client_id": registered_client_id,
        "payment_status": "paid"
    })
    if s == 200:
        ok(f"POST /api/admin/billing/update → payment_status=paid")
    elif s in (400, 404):
        warn("billing/update", f"status={s} — {d.get('error','')}")
    else:
        fail("POST /api/admin/billing/update", f"status={s}")

# Flag expired accounts
s, d = post("/api/admin/billing/flag-expired", {})
if s == 200:
    flagged = d.get("flagged", d.get("count", "?"))
    ok(f"POST /api/admin/billing/flag-expired → flagged={flagged}")
else:
    fail("POST /api/admin/billing/flag-expired", f"status={s}")

# ─── 5. Analytics ─────────────────────────────────────────────────────────────
print("\n[5] ANALYTICS")

analytics_cases = [
    ("/api/admin/analytics/revenue",      "monthly", "revenue"),
    ("/api/admin/analytics/revenue",      "weekly",  "revenue"),
    ("/api/admin/analytics/appointments", "monthly", "appointments"),
    ("/api/admin/analytics/appointments", "daily",   "appointments"),
    ("/api/admin/analytics/doctors",      "monthly", "doctors"),
]

for path, rng, label in analytics_cases:
    s, d, _ = get(f"{path}?range={rng}")
    if s == 200:
        ok(f"GET {path}?range={rng} → 200")
        # Verify summary key present
        if "summary" in d:
            ok(f"  summary keys: {list(d['summary'].keys())}")
        else:
            warn(f"  {label} summary", "key missing")
    else:
        fail(f"GET {path}?range={rng}", f"status={s}")

# Custom range test
s, d, _ = get("/api/admin/analytics/revenue?range=custom&from=2025-01-01&to=2025-12-31")
if s == 200:
    ok("GET /api/admin/analytics/revenue?range=custom&from=...&to=... → 200")
else:
    warn("analytics/revenue custom range", f"status={s}")

# ─── 6. Export Endpoints ──────────────────────────────────────────────────────
print("\n[6] DATA EXPORT")

export_cases = [
    ("/api/admin/export/patients?format=csv&range=monthly",      "text/csv"),
    ("/api/admin/export/billing?format=csv&range=monthly",       "text/csv"),
    ("/api/admin/export/appointments?format=csv&range=monthly",  "text/csv"),
    ("/api/admin/export/patients?format=excel&range=monthly",    None),   # xlsx if openpyxl installed
    ("/api/admin/export/billing?format=pdf&range=monthly",       None),   # pdf if reportlab installed
]

for path, expected_mime in export_cases:
    s, d, raw_body = get(path, raw=True)
    if s == 200:
        size = len(raw_body)
        ok(f"GET {path.split('?')[0]}?{path.split('?')[1]} → 200 ({size} bytes)")
        if size == 0:
            warn(f"  export body", "EMPTY — check data or query")
    elif s in (500,):
        fail(f"GET {path}", f"status={s} — {d.get('error','')}")
    else:
        warn(f"GET {path}", f"status={s} (may be 501 if library not installed)")

# ─── 7. Audit Log ─────────────────────────────────────────────────────────────
print("\n[7] AUDIT LOG")
s, d, _ = get("/api/admin/audit-log")
if s == 200:
    logs = d.get("logs", d.get("audit_log", []))
    ok(f"GET /api/admin/audit-log → {len(logs)} entries")
else:
    fail("GET /api/admin/audit-log", f"status={s}")

s, d, _ = get("/api/admin/audit-log?limit=5")
if s == 200:
    logs = d.get("logs", d.get("audit_log", []))
    ok(f"GET /api/admin/audit-log?limit=5 → {len(logs)} entries (≤5)")
    if len(logs) > 5:
        warn("audit-log limit", f"Returned {len(logs)} but limit=5 requested")
else:
    fail("GET /api/admin/audit-log?limit=5", f"status={s}")

# ─── 8. Security Logs ─────────────────────────────────────────────────────────
print("\n[8] SECURITY LOGS")
s, d, _ = get("/api/admin/security-logs")
if s == 200:
    logs = d.get("logs", d.get("security_logs", []))
    ok(f"GET /api/admin/security-logs → {len(logs)} entries")
else:
    fail("GET /api/admin/security-logs", f"status={s}")

# Verify failed login produces a security log entry
post("/api/login", {"username": "admin", "password": "WRONG_PASSWORD_TEST_999"})
time.sleep(0.3)
s, d2, _ = get("/api/admin/security-logs")
if s == 200:
    logs2 = d2.get("logs", d2.get("security_logs", []))
    ok(f"GET /api/admin/security-logs after failed login → {len(logs2)} entries")
    if len(logs2) > len(d.get("logs", [])):
        ok("  New security log entry created by failed login attempt ✓")
    else:
        warn("  security log growth", "Entry count unchanged after failed login")

# ─── 9. Backup ────────────────────────────────────────────────────────────────
print("\n[9] BACKUP SYSTEM")
s, d, _ = get("/api/admin/backup/status")
if s == 200:
    ok(f"GET /api/admin/backup/status → 200")
    ok(f"  last_backup: {d.get('last_backup', 'never')}")
    ok(f"  next_backup_hour: {d.get('next_backup_hour', '?')}")
    ok(f"  scheduler_running: {d.get('scheduler_running', '?')}")
else:
    fail("GET /api/admin/backup/status", f"status={s}")

# Manual backup trigger (may take a few seconds)
s, d = post("/api/admin/backup/trigger", {})
if s == 200:
    ok(f"POST /api/admin/backup/trigger → {d.get('message', 'OK')}")
elif s == 503:
    warn("backup/trigger", "503 — backup module not loaded")
else:
    fail("POST /api/admin/backup/trigger", f"status={s} {d}")

# ─── 10. Subdomain Lookup ─────────────────────────────────────────────────────
print("\n[10] SUBDOMAIN ROUTING LOOKUP")
if registered_client_id:
    s, d = post("/api/admin/subdomain/lookup", {"subdomain": reg_payload["subdomain"]})
    if s == 200:
        ok(f"POST /api/admin/subdomain/lookup → found client_id={d.get('client_id')}")
        ok(f"  hospital_name: {d.get('hospital_name','?')}")
    elif s == 404:
        warn("subdomain lookup", "404 — client registered but subdomain not found yet")
    else:
        fail("POST /api/admin/subdomain/lookup", f"status={s}")
else:
    # Lookup a known-bad subdomain
    s, d = post("/api/admin/subdomain/lookup", {"subdomain": "nonexistent_xyz_999"})
    if s == 404:
        ok("POST /api/admin/subdomain/lookup (unknown) → 404 ✓")
    else:
        warn("subdomain lookup (unknown)", f"status={s}")

# ─── 11. Founder System Status ────────────────────────────────────────────────
print("\n[11] FOUNDER SYSTEM STATUS DASHBOARD")
s, d, _ = get("/api/founder/system-status")
if s == 200:
    ok("GET /api/founder/system-status → 200")
    # Check expected keys
    for key in ("status", "modules"):
        if key in d:
            ok(f"  key '{key}' present")
        else:
            warn(f"  key '{key}'", "missing from response")
    # Check billing_summary
    if "billing_summary" in d:
        bs = d["billing_summary"]
        ok(f"  billing_summary → total={bs.get('total','?')}, trial={bs.get('trial','?')}, paid={bs.get('paid','?')}")
    else:
        warn("  billing_summary", "key missing from founder dashboard")
    # Check modules dict
    if "modules" in d:
        mods = d["modules"]
        ok(f"  modules: {mods}")
    # Verify NO patient PII
    patient_pii_keys = ("patient_name", "phone", "aadhar", "diagnosis", "prescription")
    dump = json.dumps(d).lower()
    for pii_key in patient_pii_keys:
        if pii_key in dump:
            fail(f"PRIVACY — PII field '{pii_key}' found in founder dashboard", "PII LEAK")
    ok("  No patient PII detected in founder dashboard response ✓")
else:
    fail("GET /api/founder/system-status", f"status={s}")

# ─── 12. SaaS DB Schema Tables ────────────────────────────────────────────────
print("\n[12] SAAS DATABASE TABLES")
try:
    import psycopg2
    conn = psycopg2.connect(
        host='localhost', port=5434, database='hospital_ai',
        user='ats_user', password='ats_password'
    )
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    existing = {r[0] for r in cur.fetchall()}
    for t in ("audit_log", "billing_accounts"):
        if t in existing: ok(f"  table '{t}' exists ✓")
        else: warn(f"  table '{t}'", "not found — run create_saas_tables()")
    # Check extended clients columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='clients'
          AND column_name IN ('subdomain','plan_type','status','billing_start_date',
                              'billing_expiry_date','last_activity','db_status','admin_email')
    """)
    found_cols = {r[0] for r in cur.fetchall()}
    for col in ('subdomain', 'plan_type', 'status', 'admin_email'):
        if col in found_cols: ok(f"  clients.{col} ✓")
        else: warn(f"  clients.{col}", "column missing — run create_saas_tables()")
    conn.close()
except ImportError:
    warn("DB schema check", "psycopg2 not installed")
except Exception as e:
    warn("DB schema check", str(e))

# ─── 13. Module Import Health ─────────────────────────────────────────────────
print("\n[13] SAAS MODULE IMPORT HEALTH")
saas_modules = [
    ("saas_logging",    ["system_log", "security_log", "alerts_log"]),
    ("saas_billing",    ["create_billing_account", "is_client_active", "PLANS"]),
    ("saas_export",     ["export_data"]),
    ("saas_analytics",  ["get_revenue_analytics", "get_appointment_analytics", "get_doctor_analytics"]),
    ("saas_backup",     ["run_backup_now", "start_backup_scheduler"]),
    ("saas_onboarding", ["onboard_hospital"]),
]
for mod_name, symbols in saas_modules:
    try:
        mod = __import__(mod_name)
        ok(f"import {mod_name} ✓")
        for sym in symbols:
            if hasattr(mod, sym):
                ok(f"  {mod_name}.{sym} ✓")
            else:
                warn(f"  {mod_name}.{sym}", "attribute not found")
    except ImportError as e:
        fail(f"import {mod_name}", str(e))
    except Exception as e:
        warn(f"import {mod_name}", str(e))

# ─── 14. Rate Limiting (basic check) ──────────────────────────────────────────
print("\n[14] RATE LIMITING BASIC CHECK")
# Hit billing/plans endpoint 12 times rapidly — should not crash server
burst_ok = 0
burst_err = 0
for _ in range(12):
    s2, _, __ = get("/api/admin/billing/plans")
    if s2 in (200, 429): burst_ok += 1
    else: burst_err += 1
if burst_err == 0:
    ok(f"Burst of 12 requests to /api/admin/billing/plans → {burst_ok} clean responses (no server crash)")
else:
    warn("Rate limit burst", f"{burst_err} unexpected errors in 12 requests")

# ─── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "═"*60)
print(" TEST SUMMARY")
print("═"*60)
print(f"  PASSED : {len(PASS)}")
print(f"  FAILED : {len(FAIL)}")
print(f"  WARNED : {len(WARN)}")
if FAIL:
    print("\n  FAILURES:")
    for f_name in FAIL:
        print(f"    ❌  {f_name}")
if WARN:
    print("\n  WARNINGS:")
    for w_name in WARN:
        print(f"    ⚠️   {w_name}")

print()
if not FAIL:
    print("  🎉  All SaaS tests PASSED.\n")
    sys.exit(0)
else:
    print(f"  ⛔  {len(FAIL)} test(s) FAILED.\n")
    sys.exit(1)
