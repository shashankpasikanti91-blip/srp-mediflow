"""Check if all tenant DBs exist, have required tables, and admin users are set up."""
import psycopg2, sys

DB_KWARGS = dict(host='localhost', port=5432, user='ats_user', password='ats_password')

TENANTS = [
    ('hospital_ai',         'star_hospital_admin',   'Star@Admin2026!'),
    ('srp_sai_care',        'sai_care_admin',         'saicare@2026'),
    ('srp_city_medical',    'city_medical_admin',     'citymed@2026'),
    ('srp_apollo_warangal', 'apollo_warangal_admin',  'apollo@2026'),
    ('srp_green_cross',     'green_cross_admin',      'greencross@2026'),
]

REQUIRED_TABLES = [
    'appointments', 'patients', 'doctors', 'staff_users',
    'billing_records', 'lab_orders', 'pharmacy_inventory',
    'ipd_admissions', 'surgery_records', 'stock_items',
    'system_logs', 'attendance_records', 'doctor_rounds',
    'hospital_config', 'notifications_log'
]

print("=" * 70)
print("  TENANT DB AUDIT")
print("=" * 70)

missing_dbs = []
missing_tables = {}
missing_admins = []

# Check postgres DB list
try:
    conn = psycopg2.connect(dbname='postgres', **DB_KWARGS)
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname")
    existing_dbs = {r[0] for r in cur.fetchall()}
    conn.close()
    print(f"\nExisting DBs: {sorted(existing_dbs)}")
except Exception as e:
    print(f"Cannot check DB list: {e}")
    existing_dbs = set()

for db_name, admin_user, admin_pass in TENANTS:
    print(f"\n  [{db_name}]")
    if db_name not in existing_dbs:
        print(f"    ❌ DATABASE DOES NOT EXIST")
        missing_dbs.append(db_name)
        continue

    try:
        conn = psycopg2.connect(dbname=db_name, **DB_KWARGS)
        cur = conn.cursor()

        # Check tables
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        existing_tables = {r[0] for r in cur.fetchall()}
        print(f"    Tables found: {sorted(existing_tables)}")
        missing = [t for t in REQUIRED_TABLES if t not in existing_tables]
        if missing:
            print(f"    ❌ MISSING TABLES: {missing}")
            missing_tables[db_name] = missing
        else:
            print(f"    ✅ All required tables present")

        # Row counts
        for tbl in REQUIRED_TABLES:
            if tbl in existing_tables:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                cnt = cur.fetchone()[0]
                flag = " ⚠️ EMPTY" if cnt == 0 else ""
                print(f"    {tbl:30s}: {cnt:4d}{flag}")

        # Check admin user
        try:
            cur.execute("SELECT username, role, must_change_password FROM staff_users WHERE username=%s", (admin_user,))
            row = cur.fetchone()
            if row:
                print(f"    ✅ Admin user '{admin_user}' role={row[1]} must_change_pw={row[2]}")
            else:
                print(f"    ❌ Admin user '{admin_user}' NOT FOUND in staff_users")
                missing_admins.append((db_name, admin_user, admin_pass))
        except Exception as e:
            print(f"    ⚠️  Cannot check admin user: {e}")

        cur.close(); conn.close()
    except Exception as e:
        print(f"    ❌ Error accessing DB: {e}")

print()
print("=" * 70)
print("  SUMMARY")
print("=" * 70)
if missing_dbs:
    print(f"  ❌ Missing DBs: {missing_dbs}")
else:
    print("  ✅ All DBs exist")
if missing_tables:
    for db, tbls in missing_tables.items():
        print(f"  ❌ {db} missing tables: {tbls}")
else:
    print("  ✅ All tables present in all DBs")
if missing_admins:
    print(f"  ❌ Missing admin users: {[a[1] for a in missing_admins]}")
else:
    print("  ✅ All admin users present")
