# 🚀 SRP MediFlow — Hetzner Production Deployment Guide

> Last updated: 2026-03-09  
> Server: Hetzner VPS (Ubuntu 22.04)  
> **Live URL**: https://mediflow.srpailabs.com  
> DNS/SSL: Cloudflare (proxy enabled — SSL terminates at Cloudflare)

---

## 0. Architecture Overview

```
Browser (HTTPS)
    │
    ▼
Cloudflare  ──  mediflow.srpailabs.com  (SSL termination)
    │  X-Forwarded-Proto: https
    │  X-Forwarded-For: <client IP>
    ▼
Hetzner VPS  :443 (Nginx) OR direct :80 → :7500
    │
    ▼
Python  srp_mediflow_server.py  :7500  (HTTP internally)
    │
    ▼
PostgreSQL  :5432  (localhost only, firewall blocks external)
```

> The Python server runs on **port 7500 internally**.  
> Cloudflare proxies HTTPS → port 7500 on the server.  
> PostgreSQL only listens on **localhost** — never exposed publicly.

---

## 1. Server Setup (one-time)

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Python 3.12+
sudo apt install python3 python3-pip python3-venv -y

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

---

## 2. PostgreSQL Setup on Hetzner

```bash
# Switch to postgres user
sudo -i -u postgres

# Create the DB user
createuser --pwprompt ats_user
# Enter a STRONG password when prompted

# Create all databases
createdb -O ats_user hospital_ai
createdb -O ats_user srp_platform_db
createdb -O ats_user srp_sai_care
createdb -O ats_user srp_city_medical
createdb -O ats_user srp_apollo_warangal
createdb -O ats_user srp_green_cross

exit
```

---

## 3. Clone & Configure

```bash
# Clone the repo
git clone git@github.com:shashankpasikanti91-blip/srp-mediflow.git
cd srp-mediflow

# Install Python packages
pip3 install -r requirements.txt

# Create your environment file (NEVER commit .env)
cp .env.example .env
nano .env
```

### Edit `.env` with your Hetzner values:

```env
PG_HOST=localhost
PG_PORT=5432               # Standard PostgreSQL port on Linux
PG_DB=hospital_ai
PG_USER=ats_user
PG_PASSWORD=YOUR_STRONG_PASSWORD_HERE
PLATFORM_DB_NAME=srp_platform_db
PORT=7500
APP_URL=https://mediflow.srpailabs.com
ROOT_DOMAIN=mediflow.srpailabs.com
ENABLE_NGROK=0
DEFAULT_ADMIN_PASSWORD=YOUR_STRONG_ADMIN_PASSWORD_HERE
```

---

## 4. Apply Database Schema

```bash
# Apply schema to all tenant databases
for DB in hospital_ai srp_sai_care srp_city_medical srp_apollo_warangal srp_green_cross; do
    echo "Applying schema to $DB..."
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema.sql
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema_hms.sql
done

# Apply platform schema
PGPASSWORD=$PG_PASSWORD psql -U ats_user -d srp_platform_db -f srp_platform_schema.sql
```

---

## 5. Create All Logins (IMPORTANT — run this after every deploy)

```bash
# This script:
#   - Wipes all old staff_users in every tenant DB
#   - Creates fresh accounts with bcrypt-hashed passwords
#   - Tests every single login
#   - Saves credentials to ADMIN_LOGIN_CREDENTIALS.md (local, NOT on GitHub)

python3 setup_logins.py
```

After running you will see:
```
✅  ALL logins verified successfully!

  Credentials are stored in:
  📄  ADMIN_LOGIN_CREDENTIALS.md  (local only, gitignored)
  📄  tenant_registry.json         (local only, gitignored)
  🔒  DB password → set via PG_PASSWORD environment variable
```

---

## 6. Start the Server

```bash
# Start in foreground (testing):
python3 srp_mediflow_server.py

# Start in background (production):
nohup python3 srp_mediflow_server.py > logs/server.log 2>&1 &
echo $! > server.pid

# Or use systemd (recommended for production — see section 8)
```

---

## 7. Test All Logins via API

```bash
# Test health endpoint
curl https://mediflow.srpailabs.com/health

# Test a login via the real domain
curl -X POST https://mediflow.srpailabs.com/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"star_hospital_admin","password":"Star@Admin2026!","tenant_slug":"star_hospital"}'

# Or test locally from the server:
curl http://localhost:7500/health
```

---

## 8. Systemd Service (Recommended for Auto-restart)

```bash
sudo nano /etc/systemd/system/srp-mediflow.service
```

Paste this:
```ini
[Unit]
Description=SRP MediFlow Hospital Management System
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/srp-mediflow
EnvironmentFile=/home/ubuntu/srp-mediflow/.env
ExecStart=/usr/bin/python3 srp_mediflow_server.py
Restart=always
RestartSec=5
StandardOutput=append:/home/ubuntu/srp-mediflow/logs/server.log
StandardError=append:/home/ubuntu/srp-mediflow/logs/server.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable srp-mediflow
sudo systemctl start srp-mediflow
sudo systemctl status srp-mediflow
```

---

## 9. Where Are Credentials Stored?

| File | Location | On GitHub? | Purpose |
|------|----------|-----------|---------|
| `.env` | Server only | ❌ NEVER | DB password, API keys |
| `ADMIN_LOGIN_CREDENTIALS.md` | Server only | ❌ NEVER | All staff passwords |
| `tenant_registry.json` | Server only | ❌ NEVER | Tenant DB mapping + admin_pw |
| `.env.example` | GitHub ✅ | ✅ YES | Template (no real values) |

> **RULE**: Only `.env.example` goes to GitHub. All real passwords stay on server.

---

## 10. Updating Logins After Deployment

```bash
cd /home/ubuntu/srp-mediflow
git pull origin main         # Pull latest code
python3 setup_logins.py       # Wipe old + create fresh + auto-test all logins
sudo systemctl restart srp-mediflow
```

---

## 11. Firewall

```bash
# Allow SSH always; allow HTTP/HTTPS publicly (Cloudflare fronts the app)
sudo ufw allow 22      # SSH
sudo ufw allow 80      # HTTP (Cloudflare → server, redirect to HTTPS)
sudo ufw allow 443     # HTTPS
# Port 7500 only needs to be open if NOT behind Cloudflare proxy
# If using Cloudflare: block 7500 from public internet for extra security
# sudo ufw deny 7500
sudo ufw enable
```

---

## 12. Quick Credential Reference (After Running `setup_logins.py`)

| Hospital | Admin Username | Password | Live URL |
|----------|---------------|----------|----------|
| Star Hospital | `star_hospital_admin` | `Star@Admin2026!` | https://mediflow.srpailabs.com/admin |
| Sai Care | `sai_care_admin` | `Sai_@Admin2026!` | https://mediflow.srpailabs.com/admin |
| City Medical | `city_medical_admin` | `City@Admin2026!` | https://mediflow.srpailabs.com/admin |
| Apollo Warangal | `apollo_warangal_admin` | `Apol@Admin2026!` | https://mediflow.srpailabs.com/admin |
| Green Cross | `green_cross_admin` | `Gree@Admin2026!` | https://mediflow.srpailabs.com/admin |
| **Founder** | `founder` | `Srp@Founder2026!` | https://mediflow.srpailabs.com/founder |
| **Founder** | `founder` | `Srp@Founder2026!` |

Staff password pattern: `<Role>@<Slug4>2026!`  
Examples: `Doctor@star2026!`, `Nurse@sai_2026!`, `Lab@city2026!`

Full credentials after reset → check `ADMIN_LOGIN_CREDENTIALS.md` on the server.
