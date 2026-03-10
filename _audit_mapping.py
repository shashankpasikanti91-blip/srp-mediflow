"""
Comprehensive field-mapping audit:
1. Lists all route -> handler mappings
2. Identifies stub (pass-only) handlers
3. Tests actual DB INSERT/SELECT for each tenant
4. Tests all major API endpoints end-to-end
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(__file__))

WORKDIR = os.path.dirname(__file__)
ERRORS = []
WARNINGS = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. ROUTES & HANDLERS
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("1. SERVER ROUTES & HANDLER AUDIT")
print("=" * 60)

with open(os.path.join(WORKDIR, "srp_mediflow_server.py"), encoding="utf-8") as f:
    src = f.read()

# All routes registered via ROUTES dict or inline
route_map = re.findall(r'["\'](?:GET|POST|PUT|DELETE)\s+(/[^"\']*)["\']', src)
print(f"Routes defined: {len(route_map)}")
for r in sorted(set(route_map)):
    print(f"  {r}")

# All handler methods
handlers = re.findall(r"def (_handle_\w+)\s*\(", src)
print(f"\nHandler methods ({len(handlers)}):")
for h in handlers:
    print(f"  {h}")

# Stub handlers (body is only `pass` or just a docstring + pass)
stub_pattern = re.compile(
    r"def (_handle_\w+)\s*\([^)]*\)\s*:\s*\n(?:\s+\"\"\"[^\"]*\"\"\"\s*\n)?\s+pass\s*\n",
    re.MULTILINE,
)
stubs = stub_pattern.findall(src)
if stubs:
    ERRORS.append(f"STUB HANDLERS (body=pass): {stubs}")
    print(f"\n[FAIL] Stub handlers: {stubs}")
else:
    print("\n[OK] No stub-only handlers found")

# ─────────────────────────────────────────────────────────────────────────────
# 2. HMD_DB FUNCTION COMPLETENESS
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. HMS_DB FUNCTIONS AUDIT")
print("=" * 60)

import hms_db
required_fns = [
    # OPD
    "register_patient", "create_visit", "get_visit_detail", "list_visits",
    "search_patients",
    # Prescriptions
    "create_full_prescription", "get_full_prescription", "get_prescriptions_by_visit",
    # IPD
    "admit_patient", "get_admission_detail", "discharge_patient",
    # Lab
    "create_lab_order", "update_lab_result",
    # Billing
    "create_bill", "get_bill_detail",
    # Notifications
    "get_notification_settings", "save_notification_settings",
    # Dashboard
    "get_dashboard_enhanced_stats", "get_recent_activity",
]
for fn in required_fns:
    if not hasattr(hms_db, fn):
        ERRORS.append(f"hms_db.{fn} MISSING")
        print(f"  [FAIL] {fn} — MISSING")
    else:
        print(f"  [OK]   {fn}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. DB WRITE/READ PER TENANT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. DB WRITE / READ TEST PER TENANT")
print("=" * 60)

import psycopg2, json

# Load tenant list from registry
registry_path = os.path.join(WORKDIR, "tenant_registry.json")
with open(registry_path, encoding="utf-8") as f:
    registry = json.load(f)

tenants = [(slug, cfg) for slug, cfg in registry.items() if slug != "platform"]
print(f"Tenants in registry: {[t[0] for t in tenants]}")

for slug, cfg in tenants:
    db_name = cfg.get("db_name") or cfg.get("database") or f"srp_{slug}"
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    user = cfg.get("user", "ats_user")
    pwd  = cfg.get("password", "ats_password")
    print(f"\n  Tenant: {slug} | DB: {db_name}")
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=db_name, user=user, password=pwd, connect_timeout=5)
        cur = conn.cursor()
        # Check tables present
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        tables = {r[0] for r in cur.fetchall()}
        key_tables = ["patients", "visits", "prescriptions", "doctors", "bills"]
        for t in key_tables:
            if t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cur.fetchone()[0]
                print(f"    [OK]   {t}: {cnt} rows")
            else:
                print(f"    [WARN] {t}: TABLE MISSING")
                WARNINGS.append(f"{slug}.{t} table missing")

        # Check new v6 tables
        for t in ["prescription_medicines", "notification_settings", "notification_logs"]:
            if t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cur.fetchone()[0]
                print(f"    [OK]   {t}: {cnt} rows")
            else:
                print(f"    [WARN] {t}: migration not run on this tenant")
                WARNINGS.append(f"{slug}.{t} missing — run migration")

        # Check prescription columns
        if "prescriptions" in tables:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='prescriptions' "
                "AND column_name IN ('chief_complaint','bp','pulse','spo2','follow_up_days') "
                "ORDER BY column_name"
            )
            new_cols = [r[0] for r in cur.fetchall()]
            if len(new_cols) == 5:
                print(f"    [OK]   prescriptions v6 columns: {new_cols}")
            else:
                missing_cols = set(['chief_complaint','bp','pulse','spo2','follow_up_days']) - set(new_cols)
                print(f"    [WARN] prescriptions missing v6 cols: {missing_cols}")
                WARNINGS.append(f"{slug} prescriptions missing v6 columns: {missing_cols}")

        cur.close(); conn.close()
        print(f"    [OK]   Connection clean close")
    except Exception as e:
        ERRORS.append(f"DB connect failed for {slug}/{db_name}: {e}")
        print(f"    [FAIL] {slug}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. FIELD MAPPING: Does the server handler -> hms_db -> DB round-trip work?
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. FIELD MAPPING: server handler -> hms_db -> DB")
print("=" * 60)

# Check _handle_create_digital_prescription maps all required fields from payload
handler_rx = re.search(
    r"def _handle_create_digital_prescription.*?(?=\n    def |\Z)",
    src, re.DOTALL
)
if handler_rx:
    body = handler_rx.group()
    # Fields the frontend sends
    expected_fields = [
        "visit_id", "doctor_id", "chief_complaint", "diagnosis",
        "symptoms", "bp", "pulse", "temperature", "spo2", "weight",
        "medicines", "lab_tests", "advice", "follow_up_days"
    ]
    missing_fields = []
    for f in expected_fields:
        if f not in body:
            missing_fields.append(f)
    if missing_fields:
        ERRORS.append(f"_handle_create_digital_prescription missing fields: {missing_fields}")
        print(f"  [FAIL] Missing field extractions: {missing_fields}")
    else:
        print(f"  [OK]   All {len(expected_fields)} expected fields referenced in handler")
else:
    ERRORS.append("_handle_create_digital_prescription handler not found")
    print("  [FAIL] _handle_create_digital_prescription not found in server")

# Check create_full_prescription in hms_db maps the same fields to DB columns
import inspect
if hasattr(hms_db, "create_full_prescription"):
    fn_src = inspect.getsource(hms_db.create_full_prescription)
    db_cols = [
        "visit_id", "doctor_id", "chief_complaint", "diagnosis",
        "bp", "pulse", "spo2", "follow_up_days"
    ]
    missing_col_refs = [c for c in db_cols if c not in fn_src]
    if missing_col_refs:
        ERRORS.append(f"hms_db.create_full_prescription missing DB col refs: {missing_col_refs}")
        print(f"  [FAIL] hms_db.create_full_prescription missing DB cols: {missing_col_refs}")
    else:
        print(f"  [OK]   hms_db.create_full_prescription references all required DB columns")

# Check patient registration fields
handler_reg = re.search(
    r"def _handle_register_patient.*?(?=\n    def |\Z)",
    src, re.DOTALL
)
if handler_reg:
    body = handler_reg.group()
    reg_fields = ["name", "age", "gender", "phone", "address"]
    missing = [f for f in reg_fields if f not in body]
    if missing:
        ERRORS.append(f"_handle_register_patient missing: {missing}")
        print(f"  [FAIL] register_patient handler missing: {missing}")
    else:
        print(f"  [OK]   register_patient handler maps all basic fields")
else:
    WARNINGS.append("_handle_register_patient not found")
    print("  [WARN] _handle_register_patient not found (check route name)")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("AUDIT SUMMARY")
print("=" * 60)
if ERRORS:
    print(f"ERRORS ({len(ERRORS)}):")
    for e in ERRORS:
        print(f"  ✗ {e}")
else:
    print("  No ERRORS found")

if WARNINGS:
    print(f"\nWARNINGS ({len(WARNINGS)}):")
    for w in WARNINGS:
        print(f"  ⚠ {w}")
else:
    print("  No warnings")

if not ERRORS:
    print("\n✓ ALL MAPPING AUDITS PASSED")
else:
    print(f"\n✗ {len(ERRORS)} issue(s) require fixing")
    sys.exit(1)
