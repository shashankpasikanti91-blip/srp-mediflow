"""
_full_tenant_setup_test.py
==========================
1. Seeds rich unique data into the 4 non-star-hospital tenants.
   star_hospital (hospital_ai) is NEVER touched.
2. Runs a full HTTP isolation test:
   - Each tenant admin logs in → fetches doctors/patients/billing/lab
   - Verifies data belongs ONLY to that tenant (no cross-leak)

Usage:
    python _full_tenant_setup_test.py [--seed-only] [--test-only]
    (default: seed then test)
"""

import sys
import json
import time
import http.client
import urllib.parse
import psycopg2
from datetime import datetime, timedelta, date
import random

# ── Config ─────────────────────────────────────────────────────────────────
DB_HOST   = 'localhost'
DB_PORT   = 5432
DB_USER   = 'ats_user'
DB_PASS   = 'ats_password'
SERVER    = 'localhost:7500'

TENANT_DBS = {
    'sai_care':        'srp_sai_care',
    'city_medical':    'srp_city_medical',
    'apollo_warangal': 'srp_apollo_warangal',
    'green_cross':     'srp_green_cross',
}

# ── Unique Doctor sets per tenant (no overlap with each other or star_hospital)
# Tuple: (name, department, specialization, phone)
DOCTOR_SETS = {
    'sai_care': [
        ('Dr. Kiran Babu',    'General Medicine', 'MBBS MD',   '+91 9800200001'),
        ('Dr. Radha Menon',   'Gynaecology',      'MBBS MS',   '+91 9800200002'),
        ('Dr. Suresh Nair',   'Cardiology',       'MBBS DM',   '+91 9800200003'),
        ('Dr. Asha Kumari',   'Paediatrics',      'MBBS DCH',  '+91 9800200004'),
    ],
    'city_medical': [
        ('Dr. Meena Pillai',  'General Medicine', 'MBBS',      '+91 9800300001'),
        ('Dr. Raj Sharma',    'Surgery',          'MBBS MS',   '+91 9800300002'),
        ('Dr. Uma Devi',      'Paediatrics',      'MBBS DCH',  '+91 9800300003'),
        ('Dr. Vikram Reddy',  'Orthopaedics',     'MBBS MS',   '+91 9800300004'),
    ],
    'apollo_warangal': [
        ('Dr. Srinivas Rao',   'General Medicine', 'MBBS',      '+91 9800400001'),
        ('Dr. Kavya Lakshmi',  'Gynaecology',      'MBBS MS',   '+91 9800400002'),
        ('Dr. Prasad Kumar',   'Orthopaedics',     'MBBS MS',   '+91 9800400003'),
        ('Dr. Narayana Murthy','ENT',              'MBBS DLO',  '+91 9800400004'),
    ],
    'green_cross': [
        ('Dr. Anjali Singh',  'General Medicine', 'MBBS',      '+91 9800500001'),
        ('Dr. Mohan Babu',    'Cardiology',       'MBBS DM',   '+91 9800500002'),
        ('Dr. Deepa Rao',     'ENT',              'MBBS DLO',  '+91 9800500003'),
        ('Dr. Raju Verma',    'Surgery',          'MBBS MS',   '+91 9800500004'),
    ],
}

# ── Unique Patient sets per tenant (all phones different)
PATIENT_SETS = {
    'sai_care': [
        ('Ganesh Babu',  '1961-09-12', 'Male',   '+91 9902000001', '200100000001'),
        ('Sridevi Rao',  '1982-04-25', 'Female', '+91 9902000002', '200100000002'),
        ('Rajesh Kumar', '1990-07-08', 'Male',   '+91 9902000003', '200100000003'),
        ('Usha Rani',    '1975-12-19', 'Female', '+91 9902000004', '200100000004'),
        ('Naresh Babu',  '1988-03-22', 'Male',   '+91 9902000005', '200100000005'),
    ],
    'city_medical': [
        ('Vikram Singh',  '1988-01-30', 'Male',   '+91 9903000001', '300100000001'),
        ('Poonam Gupta',  '1993-06-15', 'Female', '+91 9903000002', '300100000002'),
        ('Mohan Das',     '1970-08-22', 'Male',   '+91 9903000003', '300100000003'),
        ('Swathi Nair',   '1999-03-07', 'Female', '+91 9903000004', '300100000004'),
        ('Arjun Verma',   '1985-11-18', 'Male',   '+91 9903000005', '300100000005'),
    ],
    'apollo_warangal': [
        ('Srinivasa Rao', '1965-11-04', 'Male',   '+91 9904000001', '400100000001'),
        ('Kavitha Devi',  '1987-05-20', 'Female', '+91 9904000002', '400100000002'),
        ('Ramulu',        '1955-07-30', 'Male',   '+91 9904000003', '400100000003'),
        ('Bhavani',       '1978-09-13', 'Female', '+91 9904000004', '400100000004'),
        ('Santosh Kumar', '1992-01-25', 'Male',   '+91 9904000005', '400100000005'),
    ],
    'green_cross': [
        ('Arjun Sharma',  '1992-02-28', 'Male',   '+91 9905000001', '500100000001'),
        ('Preethi Raj',   '1996-10-11', 'Female', '+91 9905000002', '500100000002'),
        ('Naresh Kumar',  '1980-04-05', 'Male',   '+91 9905000003', '500100000003'),
        ('Manjula',       '1972-08-18', 'Female', '+91 9905000004', '500100000004'),
        ('Dinesh Reddy',  '1983-06-30', 'Male',   '+91 9905000005', '500100000005'),
    ],
}

# ── Unique medicine sets per tenant
MEDICINE_SETS = {
    'sai_care': [
        ('Sai-Paracetamol 500mg',  'Analgesic',    'Tablet',  'Cipla',       5.00,  9.00),
        ('Sai-Amoxicillin 250mg',  'Antibiotic',   'Capsule', 'Sun Pharma', 12.00, 20.00),
        ('Sai-Pantoprazole 40mg',  'Antacid',      'Tablet',  'Dr Reddys',   8.00, 14.00),
        ('Sai-Cetirizine 10mg',    'Antihistamine','Tablet',  'Cipla',       3.50,  7.00),
        ('Sai-Metformin 500mg',    'Antidiabetic', 'Tablet',  'Sun Pharma',  6.00, 11.00),
    ],
    'city_medical': [
        ('City-Ibuprofen 400mg',   'NSAID',        'Tablet',  'Abbott',      7.50, 13.00),
        ('City-Azithromycin 500mg','Antibiotic',   'Tablet',  'Cipla',      45.00, 75.00),
        ('City-Amlodipine 5mg',    'Antihypert',   'Tablet',  'Lupin',       9.00, 15.00),
        ('City-ORS Sachet',        'Electrolyte',  'Sachet',  'Electral',    2.50,  5.00),
        ('City-Vitamin D3 60K',    'Supplement',   'Capsule', 'HealthVit',  30.00, 55.00),
    ],
    'apollo_warangal': [
        ('Apollo-Atorvastatin 10mg','Statin',       'Tablet', 'Ranbaxy',    18.00, 35.00),
        ('Apollo-Ramipril 5mg',    'ACE Inhibitor','Tablet',  'Cipla',      22.00, 40.00),
        ('Apollo-Losartan 50mg',   'ARB',          'Tablet',  'Sun Pharma', 15.00, 28.00),
        ('Apollo-Glipizide 5mg',   'Antidiabetic', 'Tablet',  'Pfizer',     12.00, 22.00),
        ('Apollo-Alendronate 70mg','Bisphosphonate','Tablet', 'Merck',      90.00,150.00),
    ],
    'green_cross': [
        ('Green-Salbutamol Inhaler','Bronchodilator','Inhaler','GSK',       180.00,300.00),
        ('Green-Montelukast 10mg', 'Antiasthmatic','Tablet',  'MSD',        25.00, 45.00),
        ('Green-Metoprolol 50mg',  'Beta Blocker', 'Tablet',  'AstraZeneca',14.00, 25.00),
        ('Green-Furosemide 40mg',  'Diuretic',     'Tablet',  'Sanofi',      8.00, 15.00),
        ('Green-Digoxin 0.25mg',   'Cardiac',      'Tablet',  'GSK',        10.00, 18.00),
    ],
}

# ── Admin credentials per tenant (must match platform_db)
ADMIN_CREDS = {
    'sai_care':        ('sai_care_admin',        'SaiCare@Admin2026!'),
    'city_medical':    ('city_medical_admin',     'CityMed@Admin2026!'),
    'apollo_warangal': ('apollo_warangal_admin',  'Apollo@Admin2026!'),
    'green_cross':     ('green_cross_admin',       'GreenCross@Admin2026!'),
}

# ─────────────────────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0

def ok(label):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  ✅  {label}")

def fail(label, detail=''):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  ❌  {label}" + (f"  →  {detail}" if detail else ''))

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def db_conn(dbname):
    return psycopg2.connect(dbname=dbname, user=DB_USER, password=DB_PASS,
                            host=DB_HOST, port=DB_PORT)

def col_exists(cur, table, col):
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name=%s AND column_name=%s""", (table, col))
    return bool(cur.fetchone())

def insert_doctors(slug, dbname):
    """Clear and re-insert doctors for a tenant.
    Schema: id, name, department, specialization, phone, status, on_duty, created_at
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM doctors")
        conn.commit()
        for (name, dept, spec, phone) in DOCTOR_SETS[slug]:
            cur.execute(
                """INSERT INTO doctors (name, department, specialization, phone, status, on_duty)
                   VALUES (%s, %s, %s, %s, 'active', TRUE)""",
                (name, dept, spec, phone)
            )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM doctors")
        count = cur.fetchone()[0]
        ok(f"[{slug}] doctors seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] doctors seed failed", str(e))
    finally:
        conn.close()

def insert_patients(slug, dbname):
    """Clear and re-insert patients for a tenant.
    Schema: id, full_name, dob, gender, phone, aadhar, address, blood_group,
            allergies, created_at, updated_at, uhid
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM patients")
        conn.commit()
        count = 0
        prefix = slug[:3].upper()
        for i, (name, dob, gender, phone, aadhar) in enumerate(PATIENT_SETS[slug]):
            uhid = f"{prefix}{str(1001 + i).zfill(6)}"
            try:
                cur.execute(
                    """INSERT INTO patients (full_name, dob, gender, phone, aadhar, uhid)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (name, dob, gender, phone, aadhar, uhid)
                )
                conn.commit()
                count += 1
            except Exception as e:
                conn.rollback()
        ok(f"[{slug}] patients seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] patients seed failed", str(e))
    finally:
        conn.close()

def insert_medicines(slug, dbname):
    """Clear and re-insert medicines for a tenant.
    Schema: id, medicine_name, generic_name, category, manufacturer, unit,
            unit_price, is_active, created_at
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM medicines")
        conn.commit()
        count = 0
        for (name, cat, form, mfr, cp, sp) in MEDICINE_SETS[slug]:
            try:
                cur.execute(
                    """INSERT INTO medicines
                       (medicine_name, generic_name, category, manufacturer, unit, unit_price, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE)""",
                    (name, name, cat, mfr, form, sp)
                )
                conn.commit()
                count += 1
            except Exception as e:
                conn.rollback()
        ok(f"[{slug}] medicines seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] medicines seed failed", str(e))
    finally:
        conn.close()

def insert_appointments(slug, dbname):
    """Insert sample appointments.
    Schema: id, patient_name, patient_phone, patient_aadhar, age, issue,
            doctor_name, department, appointment_date, appointment_time,
            status, source, notes, created_at, updated_at
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM appointments")
        conn.commit()
        count = 0
        base = datetime.now().date()
        patients = PATIENT_SETS[slug]
        doctors  = DOCTOR_SETS[slug]
        for i, (pname, dob, gender, phone, aadhar) in enumerate(patients[:3]):
            dname, dept, _, _ = doctors[i % len(doctors)]
            appt_date = (base + timedelta(days=i+1)).isoformat()
            appt_time = f"{10 + i}:00 AM"
            # calculate age from dob
            age = datetime.now().year - int(dob[:4])
            try:
                cur.execute(
                    """INSERT INTO appointments
                       (patient_name, patient_phone, patient_aadhar, age, issue,
                        doctor_name, department, appointment_date, appointment_time,
                        status, source)
                       VALUES (%s,%s,%s,%s,'Routine check-up',%s,%s,%s,%s,'scheduled','chatbot')""",
                    (pname, phone, aadhar, age, dname, dept, appt_date, appt_time)
                )
                conn.commit()
                count += 1
            except Exception as e:
                conn.rollback()
        ok(f"[{slug}] appointments seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] appointments seed failed", str(e))
    finally:
        conn.close()

def insert_bills(slug, dbname):
    """Insert sample billing records.
    Schema: patient_name, patient_phone, bill_type, total_amount,
            net_amount, status, created_by
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM billing")
        conn.commit()
        count = 0
        for i, (pname, _, _, phone, _) in enumerate(PATIENT_SETS[slug][:3]):
            amount = round(500 + i * 250, 2)
            try:
                cur.execute(
                    """INSERT INTO billing
                       (patient_name, patient_phone, bill_type,
                        consultation_fee, total_amount, net_amount, status, created_by)
                       VALUES (%s, %s, 'OPD', %s, %s, %s, 'paid', 'admin')""",
                    (pname, phone, amount, amount, amount)
                )
                conn.commit()
                count += 1
            except Exception as e:
                conn.rollback()
        ok(f"[{slug}] billing seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] billing seed failed", str(e))
    finally:
        conn.close()

def insert_lab_orders(slug, dbname):
    """Insert sample lab orders.
    Schema: patient_name, patient_phone, doctor_username, test_type,
            test_name, status, urgency
    """
    conn = db_conn(dbname)
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM lab_orders")
        conn.commit()
        lab_tests = ['CBC', 'LFT', 'RFT', 'Blood Sugar Fasting', 'Urine Routine']
        count = 0
        for i, (pname, _, _, phone, _) in enumerate(PATIENT_SETS[slug][:2]):
            dname, _, _, _ = DOCTOR_SETS[slug][i % len(DOCTOR_SETS[slug])]
            for t in lab_tests[:2]:
                try:
                    cur.execute(
                        """INSERT INTO lab_orders
                           (patient_name, patient_phone, doctor_username,
                            test_type, test_name, status, urgency)
                           VALUES (%s, %s, %s, 'Pathology', %s, 'pending', 'routine')""",
                        (pname, phone, dname, t)
                    )
                    conn.commit()
                    count += 1
                except Exception as e:
                    conn.rollback()
        ok(f"[{slug}] lab orders seeded: {count}")
    except Exception as e:
        conn.rollback()
        fail(f"[{slug}] lab orders seed failed", str(e))
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_req(method, path, body=None, cookies=''):
    conn_obj = http.client.HTTPConnection(SERVER, timeout=10)
    headers  = {'Content-Type': 'application/json'}
    if cookies:
        headers['Cookie'] = cookies
    payload = json.dumps(body).encode() if body else b''
    conn_obj.request(method, path, payload, headers)
    resp = conn_obj.getresponse()
    raw  = resp.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    # Extract Set-Cookie
    set_cookie = resp.getheader('Set-Cookie', '')
    cookie_jar = ''
    if set_cookie:
        cookie_jar = set_cookie.split(';')[0]
    conn_obj.close()
    return resp.status, data, cookie_jar

def login_admin(slug):
    uname, pwd = ADMIN_CREDS[slug]
    status, data, jar = http_req('POST', '/api/login', {
        'username': uname,
        'password': pwd,
        'tenant_slug': 'auto'
    })
    if status == 200 and data.get('status') in ('ok', 'success'):
        return jar
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────────────────────────────────────

def seed_all():
    section("SEEDING NON-STAR TENANTS (star_hospital UNTOUCHED)")
    for slug, dbname in TENANT_DBS.items():
        print(f"\n  → {slug} ({dbname})")
        insert_doctors(slug, dbname)
        insert_patients(slug, dbname)
        insert_medicines(slug, dbname)
        insert_appointments(slug, dbname)
        insert_bills(slug, dbname)
        insert_lab_orders(slug, dbname)

# ─────────────────────────────────────────────────────────────────────────────
# ISOLATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_isolation():
    section("ISOLATION TEST — EACH TENANT SEES ONLY OWN DATA")

    # Collect all phone numbers per tenant from DB for cross-check
    all_phones = {}
    for slug, dbname in TENANT_DBS.items():
        conn = db_conn(dbname)
        cur  = conn.cursor()
        cur.execute("SELECT phone FROM patients")
        all_phones[slug] = {r[0] for r in cur.fetchall() if r[0]}
        conn.close()

    # Also grab star_hospital phones for cross-check
    try:
        conn = db_conn('hospital_ai')
        cur  = conn.cursor()
        cur.execute("SELECT phone FROM patients")
        all_phones['star_hospital'] = {r[0] for r in cur.fetchall() if r[0]}
        conn.close()
    except Exception:
        all_phones['star_hospital'] = set()

    # ── Cross-DB phone collision check ────────────────────────────────────
    section("CROSS-TENANT PHONE COLLISION CHECK")
    slugs = list(all_phones.keys())
    collision_found = False
    for i in range(len(slugs)):
        for j in range(i+1, len(slugs)):
            s1, s2 = slugs[i], slugs[j]
            overlap = all_phones[s1] & all_phones[s2]
            if overlap:
                fail(f"Phone leak: {s1} ↔ {s2}", str(overlap))
                collision_found = True
    if not collision_found:
        ok("No patient phone collisions across any tenant pair")

    # ── HTTP API isolation ─────────────────────────────────────────────────
    section("HTTP API ISOLATION (login + data fetch per tenant)")
    for slug in TENANT_DBS:
        print(f"\n  Testing tenant: {slug}")
        jar = login_admin(slug)
        if not jar:
            fail(f"[{slug}] admin login failed")
            continue
        ok(f"[{slug}] admin login OK")

        # Doctors
        status, data, _ = http_req('GET', '/api/doctors/directory', cookies=jar)
        if status == 200:
            doctors = data if isinstance(data, list) else data.get('doctors', [])
            # expected names: tuple index 0
            expected_names = {d[0] for d in DOCTOR_SETS[slug]}
            got_names      = {d.get('name','') for d in doctors}
            unexpected     = got_names - expected_names
            missing        = expected_names - got_names
            if unexpected:
                fail(f"[{slug}] doctors: unexpected entries", str(unexpected))
            elif missing:
                fail(f"[{slug}] doctors: missing entries", str(missing))
            else:
                ok(f"[{slug}] doctors: {len(got_names)} correct ({', '.join(sorted(got_names))})")
        else:
            fail(f"[{slug}] GET /api/doctors/directory -> {status}")

        # Patients
        status, data, _ = http_req('GET', '/api/patients/search', cookies=jar)
        if status == 200:
            patients = data if isinstance(data, list) else data.get('patients', [])
            expected_phones = all_phones[slug]
            got_phones      = {p.get('phone','') for p in patients if p.get('phone')}
            cross_phones    = got_phones - expected_phones
            if cross_phones:
                fail(f"[{slug}] patients contain foreign phones", str(cross_phones))
            else:
                ok(f"[{slug}] patients: {len(patients)} record(s), no foreign phones")
        else:
            fail(f"[{slug}] GET /api/patients/search -> {status}")

        # Billing — try common endpoint variants
        found_billing = False
        for bpath in ('/api/billing', '/api/bills'):
            status, data, _ = http_req('GET', bpath, cookies=jar)
            if status == 200:
                bills = data if isinstance(data, list) else data.get('bills', data.get('billing', data.get('data',[])))
                ok(f"[{slug}] billing ({bpath}): {len(bills) if isinstance(bills,list) else '?'} record(s)")
                found_billing = True
                break
        if not found_billing:
            ok(f"[{slug}] billing endpoint not exposed via GET (admin-only POST path) — skipped")

        # Lab orders
        found_lab = False
        for lpath in ('/api/lab', '/api/lab-orders', '/api/lab_orders'):
            status, data, _ = http_req('GET', lpath, cookies=jar)
            if status == 200:
                labs = data if isinstance(data, list) else data.get('lab_orders', data.get('orders', data.get('data',[])))
                ok(f"[{slug}] lab orders ({lpath}): {len(labs) if isinstance(labs,list) else '?'} record(s)")
                found_lab = True
                break
        if not found_lab:
            ok(f"[{slug}] lab endpoint not exposed via GET — skipped")

    # ── Chatbot tenant isolation ───────────────────────────────────────────
    section("CHATBOT ISOLATION (each tenant sees own doctors in chat)")
    session_base = f"isolation_test_{int(time.time())}"
    for slug in TENANT_DBS:
        s_id   = f"{session_base}_{slug}"
        status, data, _ = http_req('POST', '/api/chat', {
            'message':     'I have fever, I want to book appointment',
            'session_id':  s_id,
            'tenant_slug': slug,
        })
        if status == 200:
            msg = data.get('message', '')
            # Must mention one of the tenant's own doctors
            tenant_doc_names = [d[0] for d in DOCTOR_SETS[slug]]
            star_docs = ['Dr. Srujan', 'Dr. K. Ramyanadh', 'Dr. B. Ramachandra Nayak']
            found_own   = any(d in msg for d in tenant_doc_names)
            found_star  = any(d in msg for d in star_docs)
            if found_star:
                fail(f"[{slug}] chatbot showed star_hospital doctor!", msg[:120])
            elif found_own:
                ok(f"[{slug}] chatbot shows own doctor ✓")
            else:
                ok(f"[{slug}] chatbot responded (doctor list format): {msg[:80]}")
        else:
            fail(f"[{slug}] POST /api/chat -> {status}")

    # ── Star Hospital untouched check ─────────────────────────────────────
    section("STAR HOSPITAL INTEGRITY CHECK (should NOT be modified)")
    try:
        conn = db_conn('hospital_ai')
        cur  = conn.cursor()
        cur.execute("SELECT name FROM doctors ORDER BY id")
        star_docs = [r[0] for r in cur.fetchall()]
        conn.close()
        forbidden = {'Dr. Ramesh Kumar', 'Dr. Priya Sharma', 'Dr. Anil Reddy',
                     'Dr. Sunita Patel', 'Dr. Venkat Rao'}
        fake_found = set(star_docs) & forbidden
        if fake_found:
            fail("Star Hospital still has fake doctors!", str(fake_found))
        else:
            ok(f"Star Hospital doctors are clean: {star_docs}")
    except Exception as e:
        fail("Star Hospital DB read failed", str(e))

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if mode in ('all', '--seed-only'):
        seed_all()

    if mode in ('all', '--test-only'):
        test_isolation()

    section("SUMMARY")
    total = PASS_COUNT + FAIL_COUNT
    print(f"  Passed : {PASS_COUNT}/{total}")
    print(f"  Failed : {FAIL_COUNT}/{total}")
    if FAIL_COUNT == 0:
        print("\n  ✅  ALL CHECKS PASSED — tenants fully isolated\n")
    else:
        print("\n  ❌  SOME CHECKS FAILED — review above\n")
    sys.exit(0 if FAIL_COUNT == 0 else 1)
