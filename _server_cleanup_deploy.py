"""
_server_cleanup_deploy.py
─────────────────────────
1. Drop 6 junk test DBs from server (srp_tv7xxxxx)
2. Clean tenant_registry.json to 5 core entries
3. Verify nginx HTTPS config + reload
4. Restart srp-mediflow service
5. Verify service + HTTPS endpoint
6. Pull latest git code on server
"""
import paramiko, json, time, sys

HOST  = "5.223.67.236"
PORT  = 22
USER  = "root"
PASS  = "856Reey@nsh"
PROJ  = "/opt/srp-mediflow/srp-mediflow"

# ─── Core registry (5 hospitals only) ───────────────────────────────────────
CLEAN_REGISTRY = {
    "star_hospital": {
        "db_name": "hospital_ai",
        "subdomain": "star-hospital",
        "hospital_name": "Star Hospital",
        "admin_username": "star_hospital_admin"
    },
    "sai_care": {
        "db_name": "srp_sai_care",
        "subdomain": "sai-care",
        "hospital_name": "Sai Care Hospital",
        "admin_username": "sai_care_admin"
    },
    "city_medical": {
        "db_name": "srp_city_medical",
        "subdomain": "city-medical",
        "hospital_name": "City Medical Centre",
        "admin_username": "city_medical_admin"
    },
    "apollo_warangal": {
        "db_name": "srp_apollo_warangal",
        "subdomain": "apollo-warangal",
        "hospital_name": "Apollo Clinic Warangal",
        "admin_username": "apollo_warangal_admin"
    },
    "green_cross": {
        "db_name": "srp_green_cross",
        "subdomain": "green-cross",
        "hospital_name": "Green Cross Hospital",
        "admin_username": "green_cross_admin"
    }
}

JUNK_DBS = [
    "srp_tv712961", "srp_tv710596", "srp_tv710350",
    "srp_tv713372", "srp_tv717583", "srp_tv719490",
]

NGINX_CONF = r"""
server {
    listen 80;
    server_name mediflow.srpailabs.com *.mediflow.srpailabs.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mediflow.srpailabs.com *.mediflow.srpailabs.com;

    ssl_certificate     /etc/letsencrypt/live/mediflow.srpailabs.com-0001/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mediflow.srpailabs.com-0001/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 20M;
    proxy_read_timeout   120s;
    proxy_connect_timeout 30s;
    proxy_send_timeout   120s;

    location / {
        proxy_pass         http://127.0.0.1:7500;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
    }
}
"""

def run(ssh, cmd, timeout=30):
    c, o, e = ssh.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    return out, err

def ok(label):  print(f"  ✅  {label}")
def fail(label): print(f"  ❌  {label}")
def step(title): print(f"\n{'─'*60}\n  {title}\n{'─'*60}")

print("=" * 60)
print("  SRP MediFlow — Server Cleanup & Deploy")
print(f"  Target: {HOST}")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    ok("SSH connected")
except Exception as e:
    fail(f"SSH connection failed: {e}")
    sys.exit(1)

# ─── Step 1: Git pull ────────────────────────────────────────────────────────
step("1. Git Pull latest code")
out, err = run(ssh, f"cd {PROJ} && git pull origin main 2>&1", timeout=60)
print(out.strip()[:500])
if "Already up to date" in out or "Fast-forward" in out or "up to date" in out:
    ok("Git pull OK")
else:
    print(f"  Git output: {out[:200]}")

# ─── Step 2: Drop junk DBs ───────────────────────────────────────────────────
step("2. Drop junk test DBs")
for db in JUNK_DBS:
    out, _ = run(ssh,
        f'sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname=\'{db}\'" 2>/dev/null',
        timeout=10)
    if "1" in out:
        out2, err2 = run(ssh,
            f'sudo -u postgres psql -c "DROP DATABASE IF EXISTS \\"{db}\\";" 2>&1',
            timeout=15)
        if "DROP DATABASE" in out2 or "does not exist" in out2:
            ok(f"Dropped DB: {db}")
        else:
            print(f"  ⚠️  {db}: {out2[:100]}")
    else:
        print(f"  ℹ️   {db} not found (already clean)")

# ─── Step 3: Clean tenant registry ──────────────────────────────────────────
step("3. Write clean tenant_registry.json (5 core)")
clean_json = json.dumps(CLEAN_REGISTRY, indent=2)
# Upload via sftp
sftp = ssh.open_sftp()
reg_path = f"{PROJ}/tenant_registry.json"
try:
    import io
    with sftp.file(reg_path, "w") as f:
        f.write(clean_json)
    ok(f"tenant_registry.json cleaned → 5 entries")
except Exception as e:
    fail(f"Registry write failed: {e}")
finally:
    sftp.close()

# Also update local registry
import os, pathlib
local_reg = pathlib.Path(__file__).parent / "tenant_registry.json"
local_reg.write_text(clean_json, encoding="utf-8")
ok("Local tenant_registry.json cleaned")

# ─── Step 4: Nginx HTTPS config ──────────────────────────────────────────────
step("4. Nginx HTTPS config")
out, _ = run(ssh,
    'ls /etc/letsencrypt/live/ 2>/dev/null | head -5',
    timeout=10)
print(f"  Certs: {out.strip()}")

# Write nginx config
sftp2 = ssh.open_sftp()
nginx_conf_path = "/etc/nginx/conf.d/srp-mediflow.conf"
try:
    with sftp2.file(nginx_conf_path, "w") as nf:
        nf.write(NGINX_CONF)
    ok(f"Nginx config written: {nginx_conf_path}")
except Exception as e:
    fail(f"Nginx config write failed: {e}")
finally:
    sftp2.close()

out, err = run(ssh, "nginx -t 2>&1", timeout=10)
print(f"  nginx -t: {out.strip() + err.strip()}")
if "ok" in (out + err).lower():
    out2, _ = run(ssh, "systemctl reload nginx 2>&1", timeout=10)
    ok("nginx reloaded")
else:
    fail(f"nginx config test failed: {out + err}")

# ─── Step 5: Restart service ─────────────────────────────────────────────────
step("5. Restart srp-mediflow service")
out, err = run(ssh, "systemctl restart srp-mediflow 2>&1", timeout=20)
time.sleep(4)
out2, _ = run(ssh, "systemctl is-active srp-mediflow", timeout=10)
svc_status = out2.strip()
if svc_status == "active":
    ok(f"srp-mediflow: {svc_status}")
else:
    fail(f"srp-mediflow: {svc_status}")
    out3, _ = run(ssh, "journalctl -u srp-mediflow --no-pager -n 20 2>&1", timeout=10)
    print(out3[:500])

# ─── Step 6: Verify HTTPS ────────────────────────────────────────────────────
step("6. Verify HTTPS endpoint")
out, _ = run(ssh,
    "curl -sk https://mediflow.srpailabs.com/ping -o - | head -100",
    timeout=15)
print(f"  HTTPS ping: {out.strip()[:120]}")
if "pong" in out.lower() or '"status"' in out.lower():
    ok("HTTPS https://mediflow.srpailabs.com is UP")
else:
    print(f"  ⚠️  HTTPS response: {out[:200]}")

# HTTP direct (should redirect)
out2, _ = run(ssh, "curl -sk http://localhost:7500/ping", timeout=10)
if "pong" in out2.lower() or '"status"' in out2.lower():
    ok("Direct HTTP localhost:7500 working")
else:
    print(f"  Direct: {out2[:150]}")

# ─── Step 7: Print final status ──────────────────────────────────────────────
step("7. Final Status")
out, _ = run(ssh,
    "systemctl is-active srp-mediflow; systemctl is-active nginx; "
    "echo 'Tenants:'; python3 -c \""
    "import json; r=json.load(open('/opt/srp-mediflow/srp-mediflow/tenant_registry.json'));"
    "print(list(r.keys()))\"",
    timeout=15)
print(out.strip())

ssh.close()

print("\n" + "=" * 60)
print("  Server Cleanup & Deploy COMPLETE")
print()
print("  Live URLs:")
print("    https://mediflow.srpailabs.com")
print("    https://mediflow.srpailabs.com/login")
print("    https://mediflow.srpailabs.com/founder")
print("    https://star-hospital.mediflow.srpailabs.com/chat/star_hospital")
print("=" * 60)
