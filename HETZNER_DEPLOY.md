# 🚀 SRP MediFlow — Hetzner Production Deployment Guide

> Last updated: 2026-03-10  
> Server: Hetzner VPS (Ubuntu 22.04)  
> **Live URL**: https://mediflow.srpailabs.com  
> DNS/SSL: Cloudflare (proxy enabled — SSL terminates at Cloudflare)

---

## 0. Architecture Overview

```
Browser (HTTPS)
    │
    ├── mediflow.srpailabs.com          → Platform landing page
    ├── star.mediflow.srpailabs.com     → Star Hospital chatbot/portal
    ├── saicare.mediflow.srpailabs.com  → Sai Care Hospital portal
    └── city.mediflow.srpailabs.com     → City Medical portal
    │
    ▼
Cloudflare  ──  *.mediflow.srpailabs.com  (wildcard, SSL termination)
    │  X-Forwarded-Proto: https
    │  X-Forwarded-For: <client IP>
    │  Host: <subdomain>.mediflow.srpailabs.com   ← used for tenant routing
    ▼
Hetzner VPS  port 7500 (Python server, internal only)
    │
    ▼
Python  srp_mediflow_server.py  :7500
    │  ┌─ Host = mediflow.srpailabs.com     → platform_landing.html
    │  └─ Host = star.mediflow.srpailabs.com → index.html (Star Hospital branding)
    │
    ▼
PostgreSQL  :5432  (localhost only, firewall blocks external)
    ├── srp_platform_db      (SaaS registry: clients, subscriptions, alerts)
    ├── hospital_ai          (Star Hospital — slug: star_hospital)
    ├── srp_sai_care         (Sai Care Hospital — slug: sai_care)
    ├── srp_city_medical     (City Medical — slug: city_medical)
    └── srp_<new_slug>       (auto-created when new client enrolls)
```

> The Python server runs on **port 7500 internally**.  
> Cloudflare proxies HTTPS → port 7500 on the server.  
> PostgreSQL only listens on **localhost** — never exposed publicly.  
> Each hospital gets its **own isolated database** — no cross-client data leakage.

---

## 0A. Client Hierarchy (Parent-Child DB Structure)

Each enrolled hospital follows this structure:

```
SRP MediFlow Platform (srp_platform_db)
└── Client: Star Hospital  (hospital_ai)
    └── Admin: star_hospital_admin
        ├── Doctors
        ├── Nurses
        └── Reception / Lab / Stock staff

└── Client: Sai Care Hospital  (srp_sai_care)
    └── Admin: sai_care_admin
        ├── Doctors
        └── Staff…
```

**How auto-DB creation works:**
- Founder calls `/api/admin/create-client` → tenant DB auto-created + schema applied + admin seeded
- Hospital self-signup via `mediflow.srpailabs.com/signup` → same auto-creation flow
- Admin logs in → creates staff under their own tenant DB (completely isolated)

---

## 0B. Cloudflare Wildcard DNS Setup (CRITICAL — do this first!)

In Cloudflare DNS for `srpailabs.com`:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `mediflow` | `YOUR_HETZNER_IP` | ✅ Proxied |
| CNAME | `*.mediflow` | `mediflow.srpailabs.com` | ✅ Proxied |

> The `*.mediflow` wildcard record routes ALL subdomains to your server.  
> Cloudflare's free plan supports wildcard DNS — no extra cost.

**SSL Certificate in Cloudflare:**
1. Go to SSL/TLS → Overview → set to **Full (strict)**
2. Go to SSL/TLS → Edge Certificates → enable **Always Use HTTPS**
3. The wildcard CNAME automatically gets covered by Cloudflare's wildcard SSL cert

**After setup, these URLs all work:**
- `https://mediflow.srpailabs.com` → Platform landing page
- `https://star.mediflow.srpailabs.com` → Star Hospital
- `https://saicare.mediflow.srpailabs.com` → Sai Care Hospital
- `https://city.mediflow.srpailabs.com` → City Medical Centre
- `https://apollo.mediflow.srpailabs.com` → Apollo Clinic Warangal
- `https://greencross.mediflow.srpailabs.com` → Green Cross Hospital

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

> ⚠️ **Important**: Linux PostgreSQL uses port **5432** (standard).  
> Windows dev uses port **5434** (custom). Always use 5432 on the server.

```bash
# Switch to postgres user
sudo -i -u postgres

# Create the DB user with a strong password
createuser --pwprompt ats_user
# Enter a STRONG password when prompted

# Create all databases
createdb -O ats_user srp_platform_db
createdb -O ats_user hospital_ai
createdb -O ats_user srp_sai_care
createdb -O ats_user srp_city_medical
createdb -O ats_user srp_apollo_warangal
createdb -O ats_user srp_green_cross

exit
```

> **Note**: New client databases (e.g. `srp_newclinic`) are created automatically  
> when a client enrolls via `/api/admin/create-client` or the signup page.  
> You only need to create the initial DBs above manually.

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
# ── PostgreSQL (Hetzner Linux uses port 5432, NOT 5434) ──
PG_HOST=localhost
PG_PORT=5432
PG_DB=hospital_ai
PG_USER=ats_user
PG_PASSWORD=YOUR_STRONG_PASSWORD_HERE
PG_ADMIN_DB=postgres
PG_ADMIN_USER=ats_user
PG_ADMIN_PASS=YOUR_STRONG_PASSWORD_HERE

# ── Platform / SaaS layer database ──
PLATFORM_DB_NAME=srp_platform_db

# ── Web Server ──
PORT=7500
APP_URL=https://mediflow.srpailabs.com
# Root domain (subdomains become tenant entry points)
ROOT_DOMAIN=mediflow.srpailabs.com

# ── Security ──
DEFAULT_ADMIN_PASSWORD=YOUR_STRONG_ADMIN_PASSWORD_HERE
ENABLE_NGROK=0

# ── Optional integrations ──
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
```

---

## 4. Apply Database Schema

```bash
# Apply platform schema first
export PG_PASSWORD="YOUR_STRONG_PASSWORD_HERE"
PGPASSWORD=$PG_PASSWORD psql -U ats_user -d srp_platform_db -f srp_platform_schema.sql

# Apply HMS schema to all tenant databases
for DB in hospital_ai srp_sai_care srp_city_medical srp_apollo_warangal srp_green_cross; do
    echo "Applying schema to $DB..."
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema.sql
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema_hms.sql
done
```

### Migration: Add subdomain column (run if upgrading from older deploy)

```sql
-- Run this if you already have srp_platform_db from an older deploy:
psql -U ats_user -d srp_platform_db -c "ALTER TABLE clients ADD COLUMN IF NOT EXISTS subdomain TEXT DEFAULT '';"
psql -U ats_user -d srp_platform_db -c "CREATE INDEX IF NOT EXISTS idx_clients_subdomain ON clients (subdomain);"

-- Populate subdomain for existing clients:
psql -U ats_user -d srp_platform_db -c "UPDATE clients SET subdomain='star'       WHERE slug='star_hospital';"
psql -U ats_user -d srp_platform_db -c "UPDATE clients SET subdomain='saicare'    WHERE slug='sai_care';"
psql -U ats_user -d srp_platform_db -c "UPDATE clients SET subdomain='city'       WHERE slug='city_medical';"
psql -U ats_user -d srp_platform_db -c "UPDATE clients SET subdomain='apollo'     WHERE slug='apollo_warangal';"
psql -U ats_user -d srp_platform_db -c "UPDATE clients SET subdomain='greencross' WHERE slug='green_cross';"
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

---

## 6. Start the Server

```bash
# Start in foreground (testing):
python3 srp_mediflow_server.py

# Start in background (production):
nohup python3 srp_mediflow_server.py > logs/server.log 2>&1 &
echo $! > server.pid

# Or use systemd (recommended — see section 8)
```

---

## 7. Verify Subdomain Routing

```bash
# Test platform landing (apex domain → landing page)
curl -H "Host: mediflow.srpailabs.com" http://localhost:7500/ -o /dev/null -w "%{http_code}\n"

# Test Star Hospital chatbot (subdomain → hospital page)
curl -H "Host: star.mediflow.srpailabs.com" http://localhost:7500/ -o /dev/null -w "%{http_code}\n"

# Test config API returns correct hospital name per subdomain
curl -H "Host: star.mediflow.srpailabs.com" http://localhost:7500/api/config
# → {"hospital_name": "Star Hospital", "subdomain": "star", ...}

curl -H "Host: saicare.mediflow.srpailabs.com" http://localhost:7500/api/config
# → {"hospital_name": "Sai Care Hospital", "subdomain": "saicare", ...}

# Test login
curl -X POST http://localhost:7500/api/login \
  -H "Content-Type: application/json" \
  -H "Host: star.mediflow.srpailabs.com" \
  -d '{"username":"star_hospital_admin","password":"Star@Admin2026!","tenant_slug":"star_hospital"}'
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

---

## 10. Updating After a Deploy

```bash
cd /home/ubuntu/srp-mediflow
git pull origin main           # Pull latest code
python3 setup_logins.py        # Wipe old + create fresh + auto-test all logins
sudo systemctl restart srp-mediflow
```

---

## 11. Firewall

```bash
sudo ufw allow 22      # SSH
sudo ufw allow 80      # HTTP → Cloudflare redirect
sudo ufw allow 443     # HTTPS (Cloudflare proxy)
# Block direct access to port 7500 from internet (Cloudflare proxies it)
sudo ufw deny 7500
sudo ufw enable
```

---

## 12. Per-Client Subdomain Reference

| Hospital | Subdomain | Live URL | Admin Login |
|----------|-----------|----------|-------------|
| Star Hospital | `star` | https://star.mediflow.srpailabs.com | star_hospital_admin |
| Sai Care Hospital | `saicare` | https://saicare.mediflow.srpailabs.com | sai_care_admin |
| City Medical Centre | `city` | https://city.mediflow.srpailabs.com | city_medical_admin |
| Apollo Clinic Warangal | `apollo` | https://apollo.mediflow.srpailabs.com | apollo_warangal_admin |
| Green Cross Hospital | `greencross` | https://greencross.mediflow.srpailabs.com | green_cross_admin |
| **Platform (Founder)** | *(apex)* | https://mediflow.srpailabs.com/founder | founder |

> **To add a new client**: POST to `/api/admin/create-client` with `hospital_name` + `subdomain`.  
> The server auto-creates the database, applies the schema, seeds the admin, and registers  
> the subdomain in `platform_db.clients` so routing works immediately.

---

## 13. Enroll a New Hospital (after deploy)

```bash
# Via API (authenticated as ADMIN or FOUNDER):
curl -X POST https://mediflow.srpailabs.com/api/admin/create-client \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_TOKEN" \
  -d '{
    "hospital_name": "Sunrise Clinic",
    "subdomain": "sunrise",
    "admin_username": "sunrise_admin",
    "admin_password": "Sunr@Admin2026!",
    "city": "Hyderabad",
    "state": "Telangana",
    "phone": "+91 99999 00000"
  }'

# Response:
# {
#   "status": "created",
#   "slug": "sunrise",
#   "subdomain": "sunrise",
#   "database": "srp_sunrise",
#   "login_url": "https://sunrise.mediflow.srpailabs.com/login",
#   "admin_user": "sunrise_admin",
#   "admin_pass": "Sunr@Admin2026!"
# }
```

The new hospital is immediately accessible at `https://sunrise.mediflow.srpailabs.com`.

---

## 14. Troubleshooting PostgreSQL Port

| Environment | Port | Notes |
|-------------|------|-------|
| Hetzner Linux | **5432** | Standard PostgreSQL default |
| Windows dev | **5434** | Custom port to avoid conflict |

Both are set in `.env` via `PG_PORT`. The application reads this value at startup.  
If you get connection errors after deploying, check `PG_PORT=5432` in your `.env` on the server.


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
