import urllib.request, urllib.parse, json, http.cookiejar

BASE = "http://localhost:7500"

# Login
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

login_data = json.dumps({"username":"star_hospital_admin","password":"Star@Admin2026!","tenant_slug":"auto"}).encode()
req = urllib.request.Request(BASE+"/api/login", data=login_data, headers={"Content-Type":"application/json"})
resp = opener.open(req, timeout=10)
login_result = json.loads(resp.read())
print(f"LOGIN: {login_result.get('status')} | Role: {login_result.get('role')} | Hospital: {login_result.get('hospital_name')}")

PASS = []
FAIL = []

def test(label, url, method="GET", body=None):
    try:
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type":"application/json"} if body else {}
        req = urllib.request.Request(BASE+url, data=data, headers=headers, method=method)
        resp = opener.open(req, timeout=10)
        result = json.loads(resp.read())
        status = result.get('status', 'no-status')
        PASS.append(label)
        print(f"  ✅ {label} → {status}")
        return result
    except Exception as e:
        FAIL.append(label)
        print(f"  ❌ {label} → {e}")
        return None

print("\n=== ADMIN PANEL ENDPOINTS ===")
r = test("Config/Phone",       "/api/config")
if r: print(f"      Phone: {r.get('hospital_phone')} | City: {r.get('city')}")

test("Admin Data",         "/api/admin/data")
test("Admin Doctors",      "/api/admin/doctors")
test("Admin Billing",      "/api/admin/billing/list")
test("IPD Admissions",     "/api/ipd/admissions")
test("Surgery List",       "/api/surgery/list")
test("Pharmacy Inventory", "/api/pharmacy/inventory")
test("Lab Orders",         "/api/lab/orders")
test("Staff List",         "/api/staff/list")
test("Stock List",         "/api/stock/list")
test("System Logs",        "/api/admin/logs")
test("Attendance",         "/api/admin/attendance/today")
test("Doctor Rounds",      "/api/admin/rounds")
test("Notif Settings",     "/api/settings/notifications")
test("Reports Extended",   "/api/admin/extended-data")

print("\n=== CHATBOT ===")
import time
session = f"e2e_test_{int(time.time())}"
r1 = test("Chat: Start",    "/api/chat", "POST", {"message":"i have fever","session_id":session})
if r1: print(f"      Bot reply: {r1.get('message','')[:80]}")

print("\n=== SUMMARY ===")
print(f"  PASSED: {len(PASS)}/{len(PASS)+len(FAIL)}")
if FAIL:
    print(f"  FAILED: {FAIL}")
else:
    print("  ALL ENDPOINTS OK ✅")
