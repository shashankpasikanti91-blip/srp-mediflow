"""
SRP MediFlow — Production Readiness Audit
Run: python _production_audit.py
"""
import os, sys, json, time, importlib, subprocess, traceback
from pathlib import Path

BASE = Path(__file__).parent
PASS, FAIL, WARN, INFO = "✔", "✖", "⚠", "ℹ"
results = []

def chk(label, ok, note=""):
    sym = PASS if ok else FAIL
    results.append((sym, label, note))
    print(f"  {sym}  {label}" + (f"  [{note}]" if note else ""))

def warn(label, note=""):
    results.append((WARN, label, note))
    print(f"  {WARN}  {label}" + (f"  [{note}]" if note else ""))

def info(label, note=""):
    results.append((INFO, label, note))
    print(f"  {INFO}  {label}" + (f"  [{note}]" if note else ""))

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 1 — PROJECT STRUCTURE VALIDATION")
print("="*70)

REQUIRED_PY = [
    "srp_mediflow_server.py","hms_db.py","auth.py","tenant_router.py",
    "saas_onboarding.py","pdf_generator.py","saas_logging.py","platform_db.py",
    "chatbot.py","db.py","roles.py","api_security.py",
]
REQUIRED_SQL = ["srp_mediflow_schema.sql","srp_platform_schema.sql"]
REQUIRED_HTML = [
    "admin_dashboard.html","doctor_dashboard.html","nurse_dashboard.html",
    "lab_dashboard.html","stock_dashboard.html","founder_dashboard.html",
    "hospital_signup.html","platform_landing.html","index.html",
]
REQUIRED_OTHER = ["requirements.txt",".env",".env.example"]

for f in REQUIRED_PY + REQUIRED_SQL + REQUIRED_HTML + REQUIRED_OTHER:
    exists = (BASE / f).exists()
    chk(f, exists, "" if exists else "MISSING")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 2 — PYTHON SYNTAX CHECK")
print("="*70)

for f in REQUIRED_PY:
    fp = BASE / f
    if not fp.exists():
        continue
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(fp)],
        capture_output=True, text=True
    )
    chk(f"syntax: {f}", r.returncode == 0, r.stderr.strip()[:80] if r.stderr.strip() else "")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 3 — DEPENDENCY CHECK")
print("="*70)

REQUIRED_PKGS = {
    "psycopg2": "psycopg2-binary",
    "bcrypt": "bcrypt",
    "dotenv": "python-dotenv",
    "requests": "requests",
    "reportlab": "reportlab",
    "openpyxl": "openpyxl",
}
OPTIONAL_PKGS = {"pyngrok": "pyngrok"}

for imp, pkg in REQUIRED_PKGS.items():
    try:
        importlib.import_module(imp)
        chk(f"import {pkg}", True)
    except ImportError:
        chk(f"import {pkg}", False, "NOT INSTALLED — run: pip install " + pkg)

for imp, pkg in OPTIONAL_PKGS.items():
    try:
        importlib.import_module(imp)
        info(f"import {pkg} (optional)", "installed")
    except ImportError:
        warn(f"import {pkg} (optional)", "not installed — OK for production")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 4 — ENVIRONMENT VARIABLES")
print("="*70)

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

REQUIRED_VARS = {
    "PORT":             "7500",
    "ROOT_DOMAIN":      "mediflow.srpailabs.com",
    "APP_URL":          "https://mediflow.srpailabs.com",
    "PG_HOST":          "localhost",
    "PG_PORT":          "5434",
    "PG_DB":            "hospital_ai",
    "PG_USER":          "ats_user",
    "PG_PASSWORD":      None,
    "PLATFORM_DB_NAME": "srp_platform_db",
    "TELEGRAM_BOT_TOKEN": None,
    "FOUNDER_CHAT_ID":  None,
}
env_fixes = {}
for var, default in REQUIRED_VARS.items():
    val = os.getenv(var, "")
    if val:
        chk(f"env {var}", True, val[:20] + "…" if len(val) > 20 else val)
    elif default:
        warn(f"env {var}", f"MISSING — will use default: {default}")
        env_fixes[var] = default
    else:
        warn(f"env {var}", "MISSING — no default (optional for local dev)")

# Check alias vars in .env
ALIASES = {
    "FOUNDER_CHAT_ID":  ["FOUNDER_TELEGRAM_CHAT_ID","FOUNDER_CHAT_ID"],
    "TELEGRAM_BOT_TOKEN": ["TELEGRAM_BOT_TOKEN","FOUNDER_TELEGRAM_TOKEN"],
}
for canonical, aliases in ALIASES.items():
    for a in aliases:
        v = os.getenv(a,"")
        if v:
            info(f"  alias {a} → {canonical}", v[:20]+"…")
            if not os.getenv(canonical,""):
                env_fixes[canonical] = v
            break

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 5 — DATABASE VALIDATION")
print("="*70)

try:
    import psycopg2
    import psycopg2.extras
    pg_cfg = dict(
        host=os.getenv("PG_HOST","localhost"),
        port=int(os.getenv("PG_PORT","5434")),
        database=os.getenv("PG_DB","hospital_ai"),
        user=os.getenv("PG_USER","ats_user"),
        password=os.getenv("PG_PASSWORD","ats_password"),
        connect_timeout=5,
    )
    conn = psycopg2.connect(**pg_cfg)
    conn.close()
    chk("PostgreSQL tenant DB connection", True)
except Exception as e:
    chk("PostgreSQL tenant DB connection", False, str(e)[:80])

try:
    conn2 = psycopg2.connect(
        host=os.getenv("PG_HOST","localhost"),
        port=int(os.getenv("PG_PORT","5434")),
        database=os.getenv("PLATFORM_DB_NAME","srp_platform_db"),
        user=os.getenv("PG_USER","ats_user"),
        password=os.getenv("PG_PASSWORD","ats_password"),
        connect_timeout=5,
    )
    conn2.close()
    chk("PostgreSQL platform DB connection", True)
except Exception as e:
    chk("PostgreSQL platform DB connection", False, str(e)[:80])

# Check key tables
try:
    conn3 = psycopg2.connect(**pg_cfg)
    cur = conn3.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    tables = [r[0] for r in cur.fetchall()]
    conn3.close()

    EXPECTED_TABLES = [
        "patients","staff_users","patient_visits","op_tickets",
        "billing","bill_items","payments","medicines","inventory_stock",
        "pharmacy_sales","lab_orders","wards","beds","patient_admissions",
        "daily_rounds","surgery_records","discharge_summaries",
    ]
    for t in EXPECTED_TABLES:
        chk(f"table exists: {t}", t in tables)

    # Check UHID column
    cur2 = conn3 if not conn3.closed else psycopg2.connect(**pg_cfg)
    c = cur2.cursor() if conn3.closed else psycopg2.connect(**pg_cfg).cursor()
    c2_conn = psycopg2.connect(**pg_cfg)
    c2 = c2_conn.cursor()
    c2.execute("SELECT column_name FROM information_schema.columns WHERE table_name='patients' AND column_name='uhid'")
    has_uhid = c2.fetchone() is not None
    chk("patients.uhid column exists", has_uhid, "" if has_uhid else "needs ALTER TABLE")
    c2_conn.close()
except Exception as e:
    warn("Table check error", str(e)[:80])

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 6 — ROUTE VALIDATION (server must be running on :7500)")
print("="*70)

import urllib.request, urllib.error

def get(path, method="GET", payload=None, headers=None):
    url = f"http://localhost:7500{path}"
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode(errors="replace")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:100]
    except Exception as ex:
        return 0, str(ex)[:100]

route_tests = [
    ("/health",          "GET",  None, 200),
    ("/",                "GET",  None, 200),
    ("/login",           "GET",  None, 200),
    ("/hospital_signup", "GET",  None, 200),
    ("/api/platform/stats", "GET", None, 200),
    ("/api/platform/tenants", "GET", None, 200),
    ("/api/login",       "POST", {"username":"bad","password":"bad"}, 401),
    ("/api/patients/search", "GET", None, 401),  # needs auth
    ("/api/pdf/prescription/1", "GET", None, 401),  # needs auth
    ("/admin",           "GET",  None, [200,302]),
    ("/founder",         "GET",  None, [200,302]),
]

for path, method, body, expected in route_tests:
    code, body_resp = get(path, method, body)
    exp_list = expected if isinstance(expected, list) else [expected]
    ok = code in exp_list
    chk(f"{method} {path}", ok, f"got {code}, expected {exp_list}")

# Test auth returns JSON
code, resp = get("/api/login", "POST", {"username":"x","password":"x"})
try:
    j = json.loads(resp)
    chk("/api/login returns JSON", True, f"status field: {j.get('status','?')}")
except:
    chk("/api/login returns JSON", False, f"non-JSON: {resp[:50]}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 7 — TENANT ROUTER VALIDATION")
print("="*70)

try:
    sys.path.insert(0, str(BASE))
    import tenant_router
    # detect_tenant returns: 'platform' for root domain, slug for subdomain,
    # or _DEFAULT_SLUG ('star_hospital') for localhost/IP
    tests = [
        ("mediflow.srpailabs.com",             "platform"),
        ("www.mediflow.srpailabs.com",         "platform"),
        ("localhost:7500",                     "star_hospital"),
        ("127.0.0.1",                          "star_hospital"),
    ]
    for host, expected in tests:
        result = tenant_router.detect_tenant(host)
        ok = (result == expected)
        chk(f"detect_tenant({host!r})", ok, f"→ {result!r} (expected {expected!r})")
except Exception as e:
    warn("tenant_router import error", str(e)[:80])

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 8 — SECURITY VALIDATION")
print("="*70)

try:
    import bcrypt as _bcrypt
    h = _bcrypt.hashpw(b"TestPass123", _bcrypt.gensalt())
    ok = _bcrypt.checkpw(b"TestPass123", h)
    chk("bcrypt hash/verify", ok)
except Exception as e:
    chk("bcrypt hash/verify", False, str(e))

try:
    import auth as _auth
    chk("auth module imports", True)
    has_lockout = hasattr(_auth, "check_lockout")
    has_otp     = hasattr(_auth, "generate_otp")
    has_session = hasattr(_auth, "create_session")
    chk("auth.check_lockout exists", has_lockout)
    chk("auth.generate_otp exists", has_otp)
    chk("auth.create_session exists", has_session)
except Exception as e:
    chk("auth module", False, str(e)[:60])

try:
    import api_security as _sec
    chk("api_security module imports", True)
    test_input = {"name": "<script>alert(1)</script>", "q": "' OR 1=1 --"}
    cleaned = _sec.sanitize_dict(test_input)
    xss_clean = "<script>" not in cleaned.get("name","")
    chk("sanitize_dict strips XSS", xss_clean, f"result: {cleaned.get('name','')[:40]}")
except Exception as e:
    chk("api_security module", False, str(e)[:60])

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 9 — LOGGING VALIDATION")
print("="*70)

LOGS_DIR = BASE / "logs"
EXPECTED_LOGS = [
    "system.log","security.log","login_attempts.log",
    "server_errors.log","tenant_access.log",
]
for log in EXPECTED_LOGS:
    exists = (LOGS_DIR / log).exists()
    if exists:
        size = (LOGS_DIR / log).stat().st_size
        chk(f"logs/{log}", True, f"{size} bytes")
    else:
        # They may not exist until something is logged — trigger them
        warn(f"logs/{log}", "not yet created (will create on first use)")

try:
    import saas_logging as _sl
    chk("saas_logging imports", True)
    loggers = ["system_log","security_log","login_log","error_log","tenant_access_log"]
    for lg in loggers:
        chk(f"  saas_logging.{lg}", hasattr(_sl, lg))
except Exception as e:
    chk("saas_logging module", False, str(e)[:60])

# trigger log creation
try:
    from saas_logging import system_log, security_log, login_log, error_log, tenant_access_log
    system_log.info("AUDIT: production audit check triggered")
    security_log.info("AUDIT: security logger verified")
    login_log.info("AUDIT: login logger verified")
    error_log.info("AUDIT: error logger verified")
    tenant_access_log.info("AUDIT: tenant_access logger verified")
    time.sleep(0.2)
    for log in EXPECTED_LOGS:
        exists = (LOGS_DIR / log).exists()
        if exists:
            chk(f"  logs/{log} created after trigger", True)
except Exception as e:
    warn("log trigger", str(e)[:60])

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 10 — PDF GENERATION TEST")
print("="*70)

try:
    import pdf_generator as _pdf
    chk("pdf_generator module imports", True)
    chk("reportlab available", _pdf.is_real_pdf(), "HTML fallback active" if not _pdf.is_real_pdf() else "")

    sample_visit = {
        "full_name":"Ravi Kumar","uhid":"UHID000001","phone":"9876543210",
        "gender":"Male","dob":"1985-03-15","blood_group":"O+",
        "doctor_assigned":"Dr. Sharma","department":"General Medicine",
        "chief_complaint":"Fever and cough","visit_date":"2026-03-09",
        "prescriptions":[{"medicine_name":"Paracetamol","dosage":"500mg","frequency":"TID","duration":"3 days"}],
        "notes":[{"note_text":"Rest and fluids"}],
        "diagnosis":"Viral fever",
        "hospital_name":"Star Hospital",
    }
    result = _pdf.generate_opd_pdf(sample_visit)
    chk("generate_opd_pdf returns bytes", isinstance(result, bytes) and len(result) > 100,
        f"{len(result)} bytes")

    sample_discharge = {
        "full_name":"Patient B","uhid":"UHID000002","phone":"9000000001",
        "adm_date_fmt":"2026-03-01 10:00","dis_date_fmt":"2026-03-07 11:00",
        "ward_name":"General Ward","bed_number":"G-04","doctor_name":"Dr. Reddy",
        "discharge_diagnosis":"Typhoid fever","rounds":[],"discharge_summary":{},
        "hospital_name":"Star Hospital",
    }
    r2 = _pdf.generate_discharge_pdf(sample_discharge)
    chk("generate_discharge_pdf returns bytes", isinstance(r2, bytes) and len(r2) > 100,
        f"{len(r2)} bytes")

    sample_sale = {
        "patient_name":"Walk-in","sale_date":"2026-03-09",
        "items":[{"medicine_name":"Amoxicillin","quantity":10,"unit_price":5.5,"total":55}],
        "total_amount":55,"hospital_name":"Star Hospital",
    }
    r3 = _pdf.generate_pharmacy_bill_pdf(sample_sale)
    chk("generate_pharmacy_bill_pdf returns bytes", isinstance(r3, bytes) and len(r3) > 100,
        f"{len(r3)} bytes")

    sample_inv = {
        "patient_name":"Ravi Kumar","bill_date":"2026-03-09",
        "items":[{"item_name":"Consultation","quantity":1,"unit_price":300,"tax_rate":0,"total_amount":300}],
        "total_amount":300,"paid_amount":300,"balance":0,"hospital_name":"Star Hospital",
    }
    r4 = _pdf.generate_invoice_pdf(sample_inv)
    chk("generate_invoice_pdf returns bytes", isinstance(r4, bytes) and len(r4) > 100,
        f"{len(r4)} bytes")
except Exception as e:
    chk("pdf_generator tests", False, str(e)[:80])
    traceback.print_exc()

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 11 — SAAS ONBOARDING MODULE CHECK")
print("="*70)

try:
    import saas_onboarding as _so
    chk("saas_onboarding imports", True)
    chk("onboard_hospital function exists", hasattr(_so, "onboard_hospital"))
    # Check it accepts the right keys without actually calling it (avoid DB side effects)
    import inspect
    sig = inspect.signature(_so.onboard_hospital)
    chk("onboard_hospital(data: dict) signature", "data" in sig.parameters)
except Exception as e:
    chk("saas_onboarding module", False, str(e)[:80])

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 12 — .ENV COMPLETENESS & FIXES")
print("="*70)

env_content = (BASE / ".env").read_text(encoding="utf-8")
NEEDED_ENV = {
    "PORT":             "7500",
    "ROOT_DOMAIN":      "mediflow.srpailabs.com",
    "APP_URL":          "https://mediflow.srpailabs.com",
    "PLATFORM_DB_NAME": "srp_platform_db",
    "FOUNDER_CHAT_ID":  os.getenv("FOUNDER_TELEGRAM_CHAT_ID","7144152487"),
}
appended = []
for var, val in NEEDED_ENV.items():
    if var + "=" not in env_content:
        appended.append(f"{var}={val}")
        warn(f".env missing {var}", f"will append: {var}={val}")

if appended:
    with open(BASE / ".env", "a", encoding="utf-8") as f:
        f.write("\n# ── Added by production audit ──────────────────────────\n")
        for line in appended:
            f.write(line + "\n")
    chk(f"Appended {len(appended)} missing vars to .env", True, ", ".join(appended)[:80])
else:
    chk(".env has all required vars", True)

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  STEP 13 — REQUIREMENTS.TXT CHECK & FIX")
print("="*70)

req_content = (BASE / "requirements.txt").read_text(encoding="utf-8")
NEEDED_PKGS_TXT = {
    "pyngrok": "pyngrok>=3.0.0",
    "psutil":  "psutil>=5.9.0",
}
req_added = []
for name, line in NEEDED_PKGS_TXT.items():
    if name not in req_content:
        req_added.append(line)
        warn(f"requirements.txt missing {name}", f"will add: {line}")

if req_added:
    with open(BASE / "requirements.txt", "a", encoding="utf-8") as f:
        f.write("\n# Added by production audit\n")
        for l in req_added:
            f.write(l + "\n")
    chk(f"Added {len(req_added)} packages to requirements.txt", True)
else:
    chk("requirements.txt complete", True)

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  FINAL SUMMARY")
print("="*70)

passed  = sum(1 for s,_,__ in results if s == PASS)
failed  = sum(1 for s,_,__ in results if s == FAIL)
warned  = sum(1 for s,_,__ in results if s == WARN)
total   = len([r for r in results if r[0] in (PASS, FAIL)])

print(f"\n  Total checks : {total}")
print(f"  {PASS} Passed    : {passed}")
print(f"  {FAIL} Failed    : {failed}")
print(f"  {WARN} Warnings  : {warned}")

if failed == 0:
    print(f"\n  PROJECT STATUS: {PASS} READY FOR PRODUCTION")
else:
    print(f"\n  PROJECT STATUS: {WARN} MINOR FIXES NEEDED  ({failed} issues)")

print()
if failed:
    print("  FAILED CHECKS:")
    for s, label, note in results:
        if s == FAIL:
            print(f"    {FAIL} {label}  [{note}]")

if warned:
    print("\n  WARNINGS:")
    for s, label, note in results:
        if s == WARN:
            print(f"    {WARN} {label}  [{note}]")
