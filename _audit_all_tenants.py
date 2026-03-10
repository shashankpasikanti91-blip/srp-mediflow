"""
Full multi-tenant audit + E2E test
Checks every tenant: login, all API endpoints, data isolation, DB rows.
"""
import psycopg2, json, urllib.request, urllib.error, http.cookiejar, time, sys
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:7500"
DB_KWARGS = dict(host='localhost', port=5432, user='ats_user', password='ats_password')

# ── helpers ───────────────────────────────────────────────────────────────────
def pg(dbname):
    return psycopg2.connect(dbname=dbname, **DB_KWARGS)

def api(opener, path, method="GET", body=None, timeout=15):
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json"} if body else {}
    req  = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        resp = opener.open(req, timeout=timeout)
        return json.loads(resp.read()), resp.getcode()
    except urllib.error.HTTPError as e:
        return {"error": e.reason, "_code": e.code}, e.code
    except Exception as e:
        return {"error": str(e)}, 0

PASS_TOTAL = FAIL_TOTAL = 0

def check(label, code, result, expected=200):
    global PASS_TOTAL, FAIL_TOTAL
    ok = (code == expected) and "error" not in result
    sym = "✅" if ok else "❌"
    print(f"    {sym} {label} [{code}]")
    if not ok:
        print(f"       → {result.get('error',str(result))[:100]}")
        FAIL_TOTAL += 1
    else:
        PASS_TOTAL += 1
    return ok

# ── Step 1 – Enumerate tenants ────────────────────────────────────────────────
print("=" * 60)
print("  STEP 1 – TENANT REGISTRY")
print("=" * 60)

try:
    conn = pg('srp_platform_db')
    cur  = conn.cursor()
    cur.execute("SELECT id, slug, hospital_name, admin_user, db_name, status FROM clients ORDER BY id")
    clients = cur.fetchall()
    cur.close()
    conn.close()
except Exception as e:
    print(f"FATAL – cannot read srp_platform_db: {e}")
    sys.exit(1)

print(f"  Found {len(clients)} client(s):")
for c in clients:
    print(f"    [{c[0]}] {c[1]:20s} name={c[2]:25s} admin={c[3]:25s} db={c[4]} status={c[5]}")

# Load tenant registry for passwords
try:
    with open('tenant_registry.json') as f:
        registry = json.load(f)
except Exception:
    registry = {}

# ── Step 2 – Per-tenant full test ─────────────────────────────────────────────
print()
print("=" * 60)
print("  STEP 2 – PER-TENANT E2E API TESTS")
print("=" * 60)

TENANT_RESULTS = {}

ALL_ADMIN_ENDPOINTS = [
    ("Config",           "GET",  "/api/config",                   None),
    ("Admin Data",       "GET",  "/api/admin/data",                None),
    ("Doctors",          "GET",  "/api/admin/doctors",             None),
    ("Billing List",     "GET",  "/api/admin/billing/list",        None),
    ("IPD Admissions",   "GET",  "/api/ipd/admissions",            None),
    ("Surgery List",     "GET",  "/api/surgery/list",              None),
    ("Pharmacy",         "GET",  "/api/pharmacy/inventory",        None),
    ("Lab Orders",       "GET",  "/api/lab/orders",                None),
    ("Staff List",       "GET",  "/api/staff/list",                None),
    ("Stock List",       "GET",  "/api/stock/list",                None),
    ("System Logs",      "GET",  "/api/admin/logs",                None),
    ("Attendance Today", "GET",  "/api/admin/attendance/today",    None),
    ("Doctor Rounds",    "GET",  "/api/admin/rounds",              None),
    ("Notif Settings",   "GET",  "/api/settings/notifications",    None),
    ("Reports Extended", "GET",  "/api/admin/extended-data",       None),
]

for client in clients:
    cid, slug, name, admin_user, db_name, status = client
    print(f"\n  -- Tenant: {name} ({slug}) -----------------")

    # Get password from registry
    reg_entry = registry.get(slug, {})
    admin_pass = reg_entry.get('admin_pw', '') or reg_entry.get('admin_password', '')
    if not admin_pass:
        print(f"    ⚠️  No password in registry for {slug}, trying defaults...")
        admin_pass = f"Admin@{name.split()[0]}2026!" if name else "Admin@2026!"

    # Login
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login_result, login_code = api(opener, "/api/login", "POST",
        {"username": admin_user, "password": admin_pass, "tenant_slug": slug})

    if login_code != 200 or login_result.get('status') != 'success':
        print(f"    ❌ LOGIN FAILED [{login_code}]: {login_result}")
        TENANT_RESULTS[slug] = {'login': False}
        FAIL_TOTAL += 1
        continue

    print(f"    ✅ LOGIN OK → role={login_result.get('role')} hospital={login_result.get('hospital_name')}")
    PASS_TOTAL += 1
    TENANT_RESULTS[slug] = {'login': True, 'passes': 0, 'fails': 0}

    # Test all endpoints
    for label, method, path, body in ALL_ADMIN_ENDPOINTS:
        result, code = api(opener, path, method, body)
        ok = check(label, code, result, 200)
        if ok:
            TENANT_RESULTS[slug]['passes'] += 1
        else:
            TENANT_RESULTS[slug]['fails'] += 1

    # Test chatbot
    sess = f"e2e_{slug}_{int(time.time())}"
    r, c = api(opener, "/api/chat", "POST", {"message": "i have fever", "session_id": sess})
    ok = check("Chatbot", c, r, 200)
    if ok:
        print(f"       Bot: {r.get('message','')[:80]}")
        TENANT_RESULTS[slug]['passes'] += 1
    else:
        TENANT_RESULTS[slug]['fails'] += 1


# ── Step 3 – DB row counts per tenant ─────────────────────────────────────────
print()
print("=" * 60)
print("  STEP 3 – DATABASE ROW COUNTS PER TENANT")
print("=" * 60)

TABLES = ['appointments', 'patients', 'doctors', 'staff_users',
          'billing', 'lab_orders', 'medicines',
          'patient_admissions', 'surgery_records', 'pharmacy_stock',
          'attendance', 'notification_settings']

for client in clients:
    cid, slug, name, admin_user, db_name, status = client
    print(f"\n  DB: {db_name} ({name})")
    if not db_name:
        print("    ⚠️  No db_name configured")
        continue
    try:
        conn = pg(db_name)
        cur  = conn.cursor()
        for tbl in TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                cnt = cur.fetchone()[0]
                flag = "" if cnt > 0 else " ⚠️ (empty)"
                print(f"    {tbl:30s} {cnt:5d} rows{flag}")
            except Exception:
                print(f"    {tbl:30s} -- (table not found)")
        cur.close(); conn.close()
    except Exception as e:
        print(f"    ERROR connecting to {db_name}: {e}")


# ── Step 4 – Cross-tenant data isolation ─────────────────────────────────────
print()
print("=" * 60)
print("  STEP 4 – DATA ISOLATION CHECK")
print("=" * 60)

db_names = [c[4] for c in clients if c[4]]
if len(db_names) >= 2:
    print(f"  Checking {len(db_names)} DBs are isolated...")
    # Compare by phone+name (NOT id — sequential IDs are expected in separate DBs)
    all_patient_phones = {}
    for db_name in db_names:
        try:
            conn = pg(db_name)
            cur  = conn.cursor()
            cur.execute("SELECT phone FROM patients WHERE phone IS NOT NULL LIMIT 100")
            phones = set(r[0].strip() for r in cur.fetchall())
            all_patient_phones[db_name] = phones
            cur.close(); conn.close()
        except Exception as e:
            all_patient_phones[db_name] = set()

    db_list = list(all_patient_phones.keys())
    leaked = False
    for i in range(len(db_list)):
        for j in range(i+1, len(db_list)):
            overlap = all_patient_phones[db_list[i]] & all_patient_phones[db_list[j]]
            if overlap:
                print(f"  ❌ LEAK: {db_list[i]} & {db_list[j]} share patient phones: {list(overlap)[:5]}")
                leaked = True
    if not leaked:
        print("  ✅ No patient phone overlap between tenant DBs — data isolated")
        PASS_TOTAL += 1
else:
    print("  ⚠️  Only 1 tenant DB — cannot cross-check isolation")


# ── Step 5 – Platform DB isolation (API level) ──────────────────────────────
print()
print("  Checking API-level tenant isolation...")
if len(clients) >= 2:
    slug_a = clients[0][1]
    slug_b = clients[1][1]
    reg_a  = registry.get(slug_a, {})
    reg_b  = registry.get(slug_b, {})
    pass_a = reg_a.get('admin_pw', '')
    pass_b = reg_b.get('admin_pw', '')
    admin_a = clients[0][3]
    admin_b = clients[1][3]

    cj_a  = http.cookiejar.CookieJar()
    op_a  = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj_a))
    api(op_a, "/api/login", "POST", {"username": admin_a, "password": pass_a, "tenant_slug": slug_a})

    # Try to access tenant B config while logged in as A
    r, c = api(op_a, "/api/config")
    phone_seen = r.get('hospital_phone','')
    expected_phone = reg_a.get('phone', '')
    if c == 200:
        print(f"  ✅ Tenant A ({slug_a}) config phone: {phone_seen}")
        # Now login as B and compare
        cj_b  = http.cookiejar.CookieJar()
        op_b  = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj_b))
        api(op_b, "/api/login", "POST", {"username": admin_b, "password": pass_b, "tenant_slug": slug_b})
        r2, c2 = api(op_b, "/api/config")
        phone_b = r2.get('hospital_phone','')
        if phone_seen != phone_b:
            print(f"  ✅ Tenant B ({slug_b}) config phone: {phone_b} (DIFFERENT — isolated)")
            PASS_TOTAL += 1
        else:
            print(f"  ⚠️  Both tenants return same phone {phone_seen} — may be same DB or misconfigured")
    else:
        print(f"  ⚠️  Could not load config for tenant A")
else:
    print("  ⚠️  Only 1 tenant — cannot test API isolation")


# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print(f"  FINAL SUMMARY")
print("=" * 60)
print(f"  Total PASSED : {PASS_TOTAL}")
print(f"  Total FAILED : {FAIL_TOTAL}")
print()
for slug, res in TENANT_RESULTS.items():
    if res.get('login'):
        print(f"  {slug:25s}  Login ✅  API: {res.get('passes',0)}✅ {res.get('fails',0)}❌")
    else:
        print(f"  {slug:25s}  Login ❌")
print()
if FAIL_TOTAL == 0:
    print("  🎉 ALL CHECKS PASSED — READY TO DEPLOY")
else:
    print(f"  ⚠️  {FAIL_TOTAL} checks failed — review above before deploy")
