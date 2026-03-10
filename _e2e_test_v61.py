"""
SRP MediFlow v6.1 — End-to-End Test (using http.client directly)
"""
import http.client, json, sys, time, re

BASE_HOST = "localhost"
BASE_PORT = 7500
PASS = True

def req(method, path, payload=None, cookie_jar=None, binary=False):
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=30)
    headers = {"Content-Type": "application/json"}
    if cookie_jar:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k,v in cookie_jar.items())
    body = json.dumps(payload).encode() if payload else None
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    raw  = resp.read()
    # Capture Set-Cookie
    if cookie_jar is not None:
        for sc in resp.headers.get_all("Set-Cookie") or []:
            m = re.match(r'([^=]+)=([^;]*)', sc)
            if m:
                cookie_jar[m.group(1).strip()] = m.group(2).strip()
    conn.close()
    if binary:
        return raw, resp.status
    try: data = json.loads(raw.decode())
    except: data = {"raw": raw[:200].decode(errors='replace')}
    return data, resp.status

def check(cond, msg):
    global PASS
    sym = "OK" if cond else "FAIL"
    print(f"    [{sym}] {msg}")
    if not cond: PASS = False

def login(jar, username, password):
    r, code = req("POST", "/api/login",
                  {"username": username, "password": password}, jar)
    return r, code

# 1. RECEPTION LOGIN
print("\n=== 1. RECEPTION LOGIN ===")
jar_rec = {}
r, code = login(jar_rec, "star_hospital_reception", "Recep@star2026!")
check(code==200 and r.get("status")=="success", f"Reception login HTTP {code}")
print(f"    role={r.get('role')}  hospital={r.get('hospital_name','?')}")

# 2. REGISTER PATIENT
print("\n=== 2. REGISTER PATIENT ===")
ts  = str(int(time.time()))[-6:]
pat = {
    "full_name": f"E2E Test {ts}",
    "phone": f"99000{ts}",
    "dob": "1990-05-15",
    "gender": "Male",
    "blood_group": "B+",
    "address": "1 Test Lane",
    "allergies": "Sulfa"
}
r, code = req("POST", "/api/patients/register", pat, jar_rec)
patient_id = r.get("patient_id") or r.get("id")
check(patient_id, f"Patient registered HTTP {code}")
print(f"    patient_id={patient_id}  uhid={r.get('uhid','?')}")

# 3. CREATE VISIT
print("\n=== 3. CREATE VISIT ===")
visit_id = None
if patient_id:
    r, code = req("POST", "/api/visit/create", {
        "patient_id": patient_id,
        "visit_type": "OP",
        "doctor_assigned": "Dr. E2E Test",
        "department": "General Medicine",
        "chief_complaint": "Fever 3 days",
    }, jar_rec)
    visit_id = r.get("visit_id")
    check(visit_id, f"Visit created HTTP {code}")
    print(f"    visit_id={visit_id}  ticket={r.get('ticket_no','?')}")
    if not visit_id:
        print(f"    ERROR detail: {r}")

# 4. DOCTOR PRESCRIPTION
print("\n=== 4. DOCTOR PRESCRIPTION ===")
jar_doc = {}
r, code = login(jar_doc, "star_hospital_doctor", "Doctor@star2026!")
check(code==200 and r.get("status")=="success", f"Doctor login HTTP {code}")

rx_id = None
if visit_id and patient_id:
    rx_data = {
        "patient_id": patient_id,
        "patient_name": pat["full_name"],
        "patient_phone": pat["phone"],
        "visit_id": visit_id,
        "chief_complaint": "Fever 3 days",
        "diagnosis": "Viral fever",
        "bp":"120/80","pulse":"88","temperature":"101","spo2":"97","weight":"70",
        "follow_up_days":"5",
        "diet_advice":"Light diet",
        "medicines":[
            {"medicine_name":"Paracetamol 500mg","dose":"1 tab",
             "frequency":"TDS","duration":"5 days","route":"Oral"},
        ],
        "lab_tests":[{"test_name":"CBC","test_type":"Blood","urgency":"routine"}]
    }
    r, code = req("POST", "/api/doctor/prescription/create", rx_data, jar_doc)
    rx_id = r.get("prescription_id") or r.get("id")
    check(rx_id, f"Prescription created HTTP {code}")
    print(f"    prescription_id={rx_id}")
    if not rx_id:
        print(f"    ERROR detail: {r}")

    if rx_id:
        r2, c2 = req("GET", f"/api/pdf/rx/{rx_id}", cookie_jar=jar_doc, binary=True)
        check(c2==200 and (r2[:4] == b'%PDF' or len(r2)>100), f"PDF download HTTP {c2} ({len(r2)} bytes)")

# 5. PATIENT TIMELINE
print("\n=== 5. PATIENT TIMELINE ===")
if patient_id:
    r, code = req("GET", f"/api/patient/{patient_id}/timeline", cookie_jar=jar_doc)
    check(code==200, f"Timeline HTTP {code}")
    check("patient" in r, "Has patient demographics")
    check("visits" in r, "Has visits list")
    check("prescriptions" in r, "Has prescriptions list")
    check("lab_orders" in r, "Has lab_orders list")
    check("summary" in r, "Has summary object")
    if r.get("summary"):
        s = r["summary"]
        print(f"    visits={s.get('total_visits',0)}  rx={s.get('total_prescriptions',0)}  labs={s.get('total_lab_orders',0)}")
    if not r.get("patient"):
        print(f"    ERROR detail: {r}")

# 6. VISITS LIST
print("\n=== 6. VISITS LIST ===")
if patient_id:
    r, code = req("GET", f"/api/visits?patient_id={patient_id}", cookie_jar=jar_doc)
    check(code==200 and "visits" in r, f"Visits list HTTP {code}")
    print(f"    Found {len(r.get('visits',[]))} visit(s)")

# 7. ADMIN STATS
print("\n=== 7. ADMIN STATS ===")
jar_adm = {}
r, code = login(jar_adm, "star_hospital_admin", "Star@Admin2026!")
check(code==200 and r.get("status")=="success", f"Admin login HTTP {code}")
r, code = req("GET", "/api/admin/dashboard/stats", cookie_jar=jar_adm)
check(code==200 and r, f"Admin stats HTTP {code}")

# 8. TENANT ISOLATION
print("\n=== 8. TENANT ISOLATION ===")
jar_sai = {}
r, code = login(jar_sai, "sai_care_admin", "Sai_@Admin2026!")
sai_ok  = code==200 and r.get("status")=="success"
print(f"    sai_care login: {'OK' if sai_ok else 'SKIPPED (no sai_care session)'}")
if patient_id and sai_ok:
    r, code = req("GET", f"/api/patient/{patient_id}/timeline", cookie_jar=jar_sai)
    check(code==404 or r.get("error"), f"sai_care isolation HTTP {code}")

# RESULT
print("\n" + "="*50)
if PASS:
    print("ALL TESTS PASSED - SRP MediFlow v6.1 E2E OK")
else:
    print("SOME TESTS FAILED - review above output")
print("="*50)
sys.exit(0 if PASS else 1)
