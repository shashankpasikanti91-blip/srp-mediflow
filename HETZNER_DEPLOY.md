# 🚀 SRP MediFlow — Hetzner Production Deployment Guide

> Last updated: 2026-03-09  
> Server: Hetzner VPS (Ubuntu 22.04 recommended)

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
HOSPITAL_PORT=7500
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

python3 _reset_all_logins.py
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
# Test health endpoint first
curl http://localhost:7500/health

# Test a login (replace with actual tenant_slug and password)
curl -X POST http://localhost:7500/api/login \
  -H "Content-Type: application/json" \
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

> **RULE**: Only `.env.example` goes to GitHub. All real passwords stay on server.

---

## 10. Updating Logins After Deployment

```bash
cd /home/ubuntu/srp-mediflow
git pull origin main         # Pull latest code
python3 _reset_all_logins.py # Reset all logins fresh
sudo systemctl restart srp-mediflow
```

---

## 11. Firewall

```bash
# Allow only necessary ports
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP (if using reverse proxy)
sudo ufw allow 443   # HTTPS
sudo ufw allow 7500  # MediFlow (or restrict to your IP)
sudo ufw enable
```

---

## 12. Quick Credential Reference (After Running _reset_all_logins.py)

| Hospital | Admin Username | Password Pattern |
|----------|---------------|-----------------|
| Star Hospital | `star_hospital_admin` | `Star@Admin2026!` |
| Sai Care | `sai_care_admin` | `Sai_@Admin2026!` |
| City Medical | `city_medical_admin` | `City@Admin2026!` |
| Apollo Warangal | `apollo_warangal_admin` | `Apol@Admin2026!` |
| Green Cross | `green_cross_admin` | `Gree@Admin2026!` |
| **Founder** | `founder` | `Srp@Founder2026!` |

Staff password pattern: `<Role>@<Slug4>2026!`  
Examples: `Doctor@star2026!`, `Nurse@sai_2026!`, `Lab@city2026!`

Full credentials after reset → check `ADMIN_LOGIN_CREDENTIALS.md` on the server.
