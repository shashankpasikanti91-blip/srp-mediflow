"""
SRP MediFlow v6.2 - Full End-to-End Test Suite
Tests: Config, Chatbot URL, Admin Dashboard, Appointments, Doctors,
       Reception Register, Visit, Prescription, PDF Download, Timeline, Stats
"""
import http.client, json, time

PORT = 7500
ts = int(time.time() * 1000) % 1000000
PASS = 0
FAIL = 0
RESULTS = []

def req(method, path, body=None, cookie='', binary=False):
    conn = http.client.HTTPConnection('localhost', PORT, timeout=15)
    headers = {'Content-Type': 'application/json'}
    if cookie:
        headers['Cookie'] = cookie
    conn.request(method, path, json.dumps(body) if body else None, headers)
    r = conn.getresponse()
    raw = r.read()
    ct = r.getheader('Content-Type', '')
    if binary:
        return r.status, r.getheader('Set-Cookie', ''), raw
    if 'json' in ct:
        try:
            return r.status, r.getheader('Set-Cookie', ''), json.loads(raw) if raw else {}
        except Exception:
            return r.status, r.getheader('Set-Cookie', ''), {}
    return r.status, r.getheader('Set-Cookie', ''), raw  # HTML/other → raw bytes

def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f'  [OK]   {name}')
    else:
        FAIL += 1
        RESULTS.append(f'  [FAIL] {name}' + (f' | {detail}' if detail else ''))

def P(msg): RESULTS.append(str(msg))

P('=' * 60)
P('  SRP MediFlow v6.2  FULL E2E TEST SUITE')
P('=' * 60)

# ── 1. Hospital Config + per-client chatbot URL ───────────────────────
P('\n[1] Hospital Config / Per-Client Chatbot URLs')
s, _, d = req('GET', '/api/config')
check('GET /api/config -> 200', s == 200, f'got {s}')
check('hospital_name in config', isinstance(d, dict) and bool(d.get('hospital_name')), str(d)[:80])
check('doctors list in config', isinstance(d, dict) and isinstance(d.get('doctors'), list))
P(f'     hospital_name = {d.get("hospital_name") if isinstance(d, dict) else "N/A"}')
P(f'     doctors in config: {len(d.get("doctors", [])) if isinstance(d, dict) else 0}')

s2, _, raw2 = req('GET', '/chat/star_hospital')
check('GET /chat/star_hospital -> 200 (per-client URL)', s2 == 200, f'got {s2}')
check('TENANT_SLUG injected in /chat/{slug} HTML',
      isinstance(raw2, bytes) and b'TENANT_SLUG' in raw2,
      f'type={type(raw2).__name__} len={len(raw2) if isinstance(raw2, bytes) else 0}')

# ── 2. Admin Login + Dashboard Data ──────────────────────────────────
P('\n[2] Admin Login + Dashboard Data')
s, ck_admin, d = req('POST', '/api/login',
    {'username': 'star_hospital_admin', 'password': 'Star@Admin2026!', 'tenant_slug': 'auto'})
check('Admin login -> 200', s == 200, str(d)[:80])

s, _, d = req('GET', '/api/admin/data', cookie=ck_admin)
check('GET /api/admin/data -> 200', s == 200, f'got {s}')
regs0 = d.get('registrations', []) if isinstance(d, dict) else []
docs0 = d.get('doctors', []) if isinstance(d, dict) else []
pats0 = d.get('patients', []) if isinstance(d, dict) else []
check('registrations key is list', isinstance(regs0, list))
check('doctors key is list', isinstance(docs0, list))
P(f'     registrations={len(regs0)} doctors={len(docs0)} patients={len(pats0)}')

# ── 3. Appointments Alias ─────────────────────────────────────────────
P('\n[3] Appointments Alias /api/appointments')
s, _, d = req('GET', '/api/appointments', cookie=ck_admin)
check('GET /api/appointments -> 200 (alias fixed)', s == 200, f'got {s}: {str(d)[:80]}')
check('appointments key present', isinstance(d, dict) and 'appointments' in d)
P(f'     appointments count: {len(d.get("appointments", [])) if isinstance(d, dict) else "N/A"}')

# ── 4. Doctors List ───────────────────────────────────────────────────
P('\n[4] Doctors List')
s, _, d = req('GET', '/api/admin/doctors', cookie=ck_admin)
check('GET /api/admin/doctors -> 200', s == 200, f'got {s}')
docs = d.get('doctors', []) if isinstance(d, dict) else []
check('doctors list non-empty', len(docs) > 0, f'got {len(docs)}')
if docs:
    P(f'     Doctor[0]: {docs[0].get("name")} | dept={docs[0].get("department")} | on_duty={docs[0].get("on_duty")}')

# ── 5. Reception: Register Patient ───────────────────────────────────
P('\n[5] Reception: Patient Registration + Telegram')
s, ck_recep, d = req('POST', '/api/login',
    {'username': 'star_hospital_reception', 'password': 'Recep@star2026!', 'tenant_slug': 'auto'})
check('Reception login -> 200', s == 200, str(d)[:60])

pname  = f'E2E_v62_{ts}'
pphone = f'9{ts:09d}'
s, _, d = req('POST', '/api/patients/register', {
    'full_name': pname, 'phone': pphone, 'gender': 'Male',
    'chief_complaint': 'Test E2E fever', 'doctor': 'Dr. K. Ramyanadh'
}, cookie=ck_recep)
check('POST /api/patients/register -> 201', s == 201, f'got {s}: {str(d)[:100]}')
patient_id = d.get('patient_id') if isinstance(d, dict) else None
check('patient_id returned', bool(patient_id), f'got {patient_id}')
P(f'     patient_id={patient_id}, ticket={d.get("op_ticket_no") if isinstance(d, dict) else None}')

# ── 6. Create Visit ───────────────────────────────────────────────────
P('\n[6] Create Patient Visit')
s, _, d = req('POST', '/api/visit/create', {
    'patient_id': patient_id, 'chief_complaint': 'E2E test fever',
    'doctor_assigned': 'Dr. K. Ramyanadh'
}, cookie=ck_recep)
check('POST /api/visit/create -> 201', s == 201, f'got {s}: {str(d)[:100]}')
visit_id = d.get('visit_id') if isinstance(d, dict) else None
check('visit_id returned', bool(visit_id), f'got {visit_id}')

# ── 7. Admin Data After Register ─────────────────────────────────────
P('\n[7] Admin Data Shows New Records')
s, _, d = req('GET', '/api/admin/data', cookie=ck_admin)
regs_after = d.get('registrations', []) if isinstance(d, dict) else []
check('registrations non-empty after register', len(regs_after) > 0, f'got {len(regs_after)}')
P(f'     registrations now: {len(regs_after)}')

# ── 8. Doctor Prescription ────────────────────────────────────────────
P('\n[8] Doctor: Create Prescription')
s, ck_doc, d = req('POST', '/api/login',
    {'username': 'star_hospital_doctor', 'password': 'Doctor@star2026!', 'tenant_slug': 'auto'})
check('Doctor login -> 200', s == 200, str(d)[:60])

s, _, d = req('POST', '/api/doctor/prescription/create', {
    'patient_id': patient_id, 'patient_name': pname, 'patient_phone': pphone,
    'diagnosis': 'Viral Fever (E2E test)', 'notes': 'Rest advised',
    'medicines': [
        {'name': 'Paracetamol 500mg', 'dosage': '1-0-1', 'duration': '5 days'},
        {'name': 'Cetirizine 10mg',   'dosage': '0-0-1', 'duration': '3 days'},
    ]
}, cookie=ck_doc)
check('POST /api/doctor/prescription/create -> 201', s == 201, f'got {s}: {str(d)[:120]}')
rx_id = (d.get('prescription_id') or d.get('id') or d.get('rx_id')) if isinstance(d, dict) else None
check('prescription_id returned', bool(rx_id), f'got keys={list(d.keys()) if isinstance(d,dict) else d}')
P(f'     rx_id={rx_id}')

# ── 9. PDF Download ───────────────────────────────────────────────────
P('\n[9] PDF Download')
if rx_id:
    s, _, pdf_raw = req('GET', f'/api/pdf/rx/{rx_id}', cookie=ck_doc, binary=True)
    check(f'GET /api/pdf/rx/{rx_id} -> 200', s == 200, f'got {s}')
    check('PDF binary starts with %PDF', isinstance(pdf_raw, bytes) and pdf_raw[:4] == b'%PDF',
          f'first 8 bytes: {pdf_raw[:8] if isinstance(pdf_raw, bytes) else "N/A"}')
    P(f'     PDF size: {len(pdf_raw):,} bytes')
else:
    P('     SKIPPED (no rx_id)')

# ── 10. Patient Timeline ──────────────────────────────────────────────
P('\n[10] Patient Timeline')
if patient_id:
    s, _, d = req('GET', f'/api/patient/{patient_id}/timeline', cookie=ck_doc)
    check('GET /api/patient/{id}/timeline -> 200', s == 200, f'got {s}: {str(d)[:80]}')
    check('timeline has patient field', isinstance(d, dict) and 'patient' in d)
    sm = d.get('summary', {}) if isinstance(d, dict) else {}
    P(f'     visits={sm.get("total_visits")} rx={sm.get("total_prescriptions")} labs={sm.get("total_lab_orders")}')
else:
    P('     SKIPPED (no patient_id)')

# ── 11. Visits List ───────────────────────────────────────────────────
P('\n[11] Visits List')
if patient_id:
    s, _, d = req('GET', f'/api/visits?patient_id={patient_id}', cookie=ck_doc)
    check('GET /api/visits?patient_id=X -> 200', s == 200, f'got {s}')
    check('visits key present', isinstance(d, dict) and 'visits' in d)
    vcount = len(d.get('visits', [])) if isinstance(d, dict) else 0
    P(f'     visits found: {vcount}')
else:
    P('     SKIPPED (no patient_id)')

# ── 12. Admin Stats ───────────────────────────────────────────────────
P('\n[12] Admin Dashboard Stats')
s, _, d = req('GET', '/api/admin/dashboard/stats', cookie=ck_admin)
check('GET /api/admin/dashboard/stats -> 200', s == 200, f'got {s}: {str(d)[:80]}')

# ─────────────────────────────────────────────────────────────────────
P('\n' + '=' * 60)
print('\n'.join(RESULTS))
print(f'\n  RESULTS: {PASS} PASS  |  {FAIL} FAIL')
if FAIL == 0:
    print('\n*** ALL TESTS PASSED — SRP MediFlow v6.2 E2E OK ***\n')
else:
    print(f'\n*** {FAIL} TEST(S) FAILED — Review output above ***\n')
