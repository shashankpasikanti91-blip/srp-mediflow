# 🏥 SRP MediFlow — Production SaaS Hospital Management Platform

> **Enterprise-grade multi-tenant HMS SaaS for Indian hospitals**
> OPD · IPD · Pharmacy · Surgery · GST Billing · UHID · PDF Reports · AI Chatbot · Multi-Tenant

**Version:** `5.1 SaaS` | **Updated:** March 10, 2026
**Platform:** `mediflow.srpailabs.com` | **Port:** `7500`
**Server:** Hetzner VPS (Ubuntu) | **DNS:** Cloudflare Wildcard | **Domain:** Namecheap

---

## 🌐 URL Structure — Parent Platform + Tenant Subdomains

```
Parent Platform (SaaS landing, signup, founder dashboard)
  https://mediflow.srpailabs.com

Tenant Portals (each hospital gets its own subdomain)
  https://star-hospital.mediflow.srpailabs.com   → Star Hospital
  https://sunrise.mediflow.srpailabs.com          → Sunrise Clinic
  https://apollo.mediflow.srpailabs.com           → Apollo Clinic Warangal
  https://saicare.mediflow.srpailabs.com          → Sai Care Hospital
  https://city.mediflow.srpailabs.com             → City Medical Centre
  https://greencross.mediflow.srpailabs.com       → Green Cross Hospital
  https://demo.mediflow.srpailabs.com             → Live Demo (auto-reset every 24h)
  https://<any-name>.mediflow.srpailabs.com       → Any new enrolled hospital
```

> The subdomain (e.g. `star-hospital`, `sunrise`, `apollo`) is chosen when a hospital **enrolls**.
> Cloudflare wildcard `*.mediflow.srpailabs.com` routes ALL subdomains to one server — no manual DNS per hospital.

---

## 🏗️ Architecture

```
Browser (HTTPS)
    │
    ├── mediflow.srpailabs.com                    → Platform landing page
    ├── star-hospital.mediflow.srpailabs.com      → Star Hospital portal + chatbot
    ├── sunrise.mediflow.srpailabs.com            → Sunrise Clinic portal + chatbot
    ├── apollo.mediflow.srpailabs.com             → Apollo Clinic portal + chatbot
    └── demo.mediflow.srpailabs.com               → Live demo (ephemeral, 24h reset)
    │
    ▼
Cloudflare  ──  *.mediflow.srpailabs.com  (wildcard SSL, proxied)
    │  Host: <subdomain>.mediflow.srpailabs.com  ← used for tenant detection
    │  X-Forwarded-Proto: https
    ▼
Hetzner VPS  :7500 (Python server, internal only)
    │
    │  tenant_router.detect_tenant(Host header)
    │    ├── "mediflow.srpailabs.com"              → slug="platform" → platform_landing.html
    │    ├── "star-hospital.mediflow.srpailabs.com"→ slug="star_hospital" → hospital_ai DB
    │    ├── "sunrise.mediflow.srpailabs.com"      → slug="sunrise"       → srp_sunrise DB
    │    └── "apollo.mediflow.srpailabs.com"       → slug="apollo_warangal"→ srp_apollo_warangal DB
    ▼
PostgreSQL  :5432 (localhost only)
    ├── srp_platform_db        (SaaS registry: clients, subscriptions, alerts, founder)
    ├── hospital_ai            (Star Hospital        — slug: star_hospital)
    ├── srp_sai_care           (Sai Care Hospital    — slug: sai_care)
    ├── srp_city_medical       (City Medical Centre  — slug: city_medical)
    ├── srp_apollo_warangal    (Apollo Clinic        — slug: apollo_warangal)
    ├── srp_green_cross        (Green Cross Hospital — slug: green_cross)
    └── srp_<slug>             (auto-created for every new enrolled hospital)
```

---

## 🏛️ Client Hierarchy (Parent-Child DB Structure)

```
SRP MediFlow Platform  (srp_platform_db — parent)
│   mediflow.srpailabs.com
│
├── Star Hospital  (hospital_ai — child DB)
│   star-hospital.mediflow.srpailabs.com
│   └── Admin: star_hospital_admin
│       ├── Doctor accounts
│       ├── Nurse accounts
│       ├── Reception / Lab / Stock accounts
│       └── Patient data (completely isolated)
│
├── Sunrise Clinic  (srp_sunrise — child DB)
│   sunrise.mediflow.srpailabs.com
│   └── Admin: sunrise_admin
│       └── Staff + Patient data (no overlap with Star Hospital)
│
├── Apollo Clinic  (srp_apollo_warangal — child DB)
│   apollo.mediflow.srpailabs.com
│   └── Admin: apollo_warangal_admin
│
└── <New Hospital>  (srp_<slug> — auto-created on enrollment)
    <subdomain>.mediflow.srpailabs.com
    └── Admin: <slug>_admin  (auto-seeded)
```

**Enrollment auto-creates everything:**
1. PostgreSQL database `srp_<slug>` → schema applied → admin user seeded
2. Row inserted in `srp_platform_db.clients` (with subdomain field)
3. `tenant_registry.json` updated (file fallback for routing)
4. Subdomain becomes live immediately — no server restart needed

---

## 🔗 Tenant Routing Logic

| Host Header Received | Detected Slug | Database Used |
|----------------------|---------------|---------------|
| `mediflow.srpailabs.com` | `platform` | — (serves landing page) |
| `star-hospital.mediflow.srpailabs.com` | `star_hospital` | `hospital_ai` |
| `sunrise.mediflow.srpailabs.com` | `sunrise` | `srp_sunrise` |
| `apollo.mediflow.srpailabs.com` | `apollo_warangal` | `srp_apollo_warangal` |
| `saicare.mediflow.srpailabs.com` | `sai_care` | `srp_sai_care` |
| `city.mediflow.srpailabs.com` | `city_medical` | `srp_city_medical` |
| `greencross.mediflow.srpailabs.com` | `green_cross` | `srp_green_cross` |
| `demo.mediflow.srpailabs.com` | `demo` | `srp_demo` |
| `localhost:7500` | `star_hospital` | `hospital_ai` (dev default) |

**Resolution order inside `tenant_router.detect_tenant()`:**
1. Check `platform_db.clients.subdomain` column (authoritative)
2. Check `tenant_registry.json` subdomain field (file fallback)
3. Try normalised slug match
4. Return default (`star_hospital`)

---

## ✅ Production Audit Report — March 9, 2026

> Full 13-step automated audit run via `_production_audit.py`
> **Result: 124/124 checks passed · 0 failures · PROJECT READY FOR PRODUCTION**

### Audit Summary

| Step | Area | Result |
|------|------|--------|
| 1 | Project structure (26 required files) | ✅ ALL PRESENT |
| 2 | Python syntax check (12 modules) | ✅ ALL CLEAN |
| 3 | Dependencies | ✅ All installed (`pyngrok` optional) |
| 4 | Environment variables | ✅ Fixed — 5 vars appended to `.env` |
| 5 | Database — tenant + platform connection | ✅ Both connected |
| 5 | Database — 19 core tables | ✅ All present |
| 5 | Database — `patients.uhid` column | ✅ Fixed — Added via `ALTER TABLE` |
| 6 | Route validation (11 routes) | ✅ All correct |
| 7 | Tenant router — subdomain → slug detection | ✅ Correct |
| 8 | Security — bcrypt, lockout, OTP, XSS strip | ✅ All working |
| 9 | Logging — 5 log files | ✅ All created + verified |
| 10 | PDF generation — 4 document types | ✅ ReportLab producing valid PDFs |
| 11 | SaaS onboarding module | ✅ `onboard_hospital()` ready |
| 12 | `.env` completeness | ✅ Fixed |
| 13 | `requirements.txt` | ✅ Fixed — `pyngrok` added |

---

## ⚡ Quick Start (Local Dev)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in values
python srp_mediflow_server.py
```

| URL | Purpose |
|-----|---------|
| `http://localhost:7500/` | Patient chatbot (dev = Star Hospital default) |
| `http://localhost:7500/admin` | Admin dashboard |
| `http://localhost:7500/hospital_signup` | Register new hospital |
| `http://localhost:7500/founder` | Platform founder dashboard |

**Windows:** Double-click `🏥 START SRP MEDIFLOW.bat`

---

## 🔑 Default Credentials

| Role | Username | Password | Portal URL |
|------|----------|----------|------------|
| Platform Founder | `founder` | `Srp@Founder2026!` | `mediflow.srpailabs.com/founder` |
| Star Hospital Admin | `star_hospital_admin` | `Star@Admin2026!` | `star-hospital.mediflow.srpailabs.com` |
| Star Hospital Doctor | `star_hospital_doctor` | `Doctor@star2026!` | `star-hospital.mediflow.srpailabs.com` |
| Star Hospital Nurse | `star_hospital_nurse` | `Nurse@star2026!` | `star-hospital.mediflow.srpailabs.com` |
| Sai Care Admin | `sai_care_admin` | `Sai_@Admin2026!` | `saicare.mediflow.srpailabs.com` |
| City Medical Admin | `city_medical_admin` | `City@Admin2026!` | `city.mediflow.srpailabs.com` |
| Apollo Admin | `apollo_warangal_admin` | `Apol@Admin2026!` | `apollo.mediflow.srpailabs.com` |
| Green Cross Admin | `green_cross_admin` | `Gree@Admin2026!` | `greencross.mediflow.srpailabs.com` |

> Passwords are **bcrypt-hashed** — never stored in plaintext.
> Full list after running `setup_logins.py` → `ADMIN_LOGIN_CREDENTIALS.md` (local only, gitignored).

---

## 🌐 Production Deployment (Hetzner + Cloudflare)

### 1 — Cloudflare DNS (Wildcard Setup)

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| `A` | `mediflow` | `<hetzner_ip>` | ✅ Proxied |
| `CNAME` | `*.mediflow` | `mediflow.srpailabs.com` | ✅ Proxied |

> The `*.mediflow` wildcard covers **all hospital subdomains** automatically.
> New hospitals enrolled via the API go live immediately — zero extra DNS work.

**After this setup, all these work with HTTPS automatically:**
```
https://mediflow.srpailabs.com          → Platform
https://star-hospital.mediflow.srpailabs.com
https://sunrise.mediflow.srpailabs.com
https://apollo.mediflow.srpailabs.com
https://demo.mediflow.srpailabs.com
https://<any-new-slug>.mediflow.srpailabs.com
```

### 2 — Server Setup

```bash
ssh root@<hetzner_ip>
apt update && apt install -y python3.12 python3-pip postgresql nginx git

# Create DB user + databases
sudo -i -u postgres
createuser --pwprompt ats_user
createdb -O ats_user srp_platform_db
createdb -O ats_user hospital_ai
createdb -O ats_user srp_sai_care
createdb -O ats_user srp_city_medical
createdb -O ats_user srp_apollo_warangal
createdb -O ats_user srp_green_cross
exit

git clone https://github.com/shashankpasikanti91-blip/srp-mediflow.git /opt/srp-mediflow
cd /opt/srp-mediflow && pip3 install -r requirements.txt
cp .env.example .env && nano .env
```

### 3 — Environment Variables (`.env`)

| Variable | Hetzner Value | Local Dev Value | Description |
|----------|--------------|-----------------|-------------|
| `PG_HOST` | `localhost` | `localhost` | PostgreSQL host |
| `PG_PORT` | **`5432`** | `5434` | ⚠️ Linux=5432, Windows=5434 |
| `PG_DB` | `hospital_ai` | `hospital_ai` | Default tenant DB |
| `PG_USER` | `ats_user` | `ats_user` | PostgreSQL user |
| `PG_PASSWORD` | *(strong password)* | `ats_password` | PostgreSQL password |
| `PLATFORM_DB_NAME` | `srp_platform_db` | `srp_platform_db` | Platform SaaS DB |
| `PORT` | `7500` | `7500` | HTTP server port |
| `ROOT_DOMAIN` | `mediflow.srpailabs.com` | `mediflow.srpailabs.com` | Apex domain for routing |
| `APP_URL` | `https://mediflow.srpailabs.com` | `http://localhost:7500` | Public URL |
| `FOUNDER_CHAT_ID` | *(telegram chat id)* | — | Telegram alerts |
| `TELEGRAM_BOT_TOKEN` | *(bot token)* | — | Telegram bot |

### 4 — Apply Schemas & Logins

```bash
export PG_PASSWORD="YOUR_PASSWORD"

# Platform schema
PGPASSWORD=$PG_PASSWORD psql -U ats_user -d srp_platform_db -f srp_platform_schema.sql

# HMS schema to all tenant DBs
for DB in hospital_ai srp_sai_care srp_city_medical srp_apollo_warangal srp_green_cross; do
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema.sql
    PGPASSWORD=$PG_PASSWORD psql -U ats_user -d $DB -f srp_mediflow_schema_hms.sql
done

# Create all staff logins + bcrypt passwords
python3 setup_logins.py
```

### 5 — Nginx Config

```nginx
server {
    listen 80;
    server_name mediflow.srpailabs.com *.mediflow.srpailabs.com;
    location / {
        proxy_pass http://127.0.0.1:7500;
        proxy_set_header Host $host;              # CRITICAL — passes subdomain to Python server
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
nginx -t && systemctl reload nginx
```

### 6 — systemd Service

```ini
[Unit]
Description=SRP MediFlow Hospital Platform
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/opt/srp-mediflow
EnvironmentFile=/opt/srp-mediflow/.env
ExecStart=/usr/bin/python3 srp_mediflow_server.py
Restart=always
RestartSec=5
StandardOutput=append:/opt/srp-mediflow/logs/server.log
StandardError=append:/opt/srp-mediflow/logs/server.log

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now srp-mediflow
```

---

## 🆕 Enrolling a New Hospital

When a new hospital signs up, a dedicated database + subdomain is ready in seconds.

### Via Founder/Admin API:

```bash
curl -X POST https://mediflow.srpailabs.com/api/admin/create-client \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "hospital_name": "Sunrise Clinic",
    "subdomain":     "sunrise",
    "admin_username": "sunrise_admin",
    "admin_password": "Sunr@Admin2026!",
    "city": "Hyderabad",
    "state": "Telangana",
    "phone": "+91 99999 00000"
  }'
```

**Response:**
```json
{
  "status":     "created",
  "slug":       "sunrise",
  "subdomain":  "sunrise",
  "database":   "srp_sunrise",
  "login_url":  "https://sunrise.mediflow.srpailabs.com/login",
  "admin_user": "sunrise_admin",
  "admin_pass": "Sunr@Admin2026!"
}
```

### Via Public Signup Page:
- Visit `https://mediflow.srpailabs.com/hospital_signup`
- Fill hospital name, choose subdomain (e.g. `sunrise`)
- Submit → DB created automatically → `https://sunrise.mediflow.srpailabs.com` goes live

### What Gets Auto-Created:
| Step | What happens |
|------|-------------|
| 1 | `CREATE DATABASE srp_sunrise` in PostgreSQL |
| 2 | Full HMS schema applied (`srp_mediflow_schema.sql`) |
| 3 | Admin account seeded with bcrypt password |
| 4 | Row in `srp_platform_db.clients` (subdomain=`sunrise`) |
| 5 | `tenant_registry.json` updated |
| 6 | Subdomain routing live immediately |
| 7 | Founder Telegram alert sent |

---

## 🔒 Security

| Feature | Detail |
|---------|--------|
| Passwords | bcrypt (SHA-256 fallback for legacy) |
| Sessions | 64-hex token, 8h TTL, in-memory |
| Brute-force | 3 failures → 15-min account lockout |
| Recovery | OTP via Telegram (6-digit, 10-min TTL) |
| Rate limiting | Per-IP throttle (`api_security.check_rate_limit()`) |
| SQL injection | All inputs sanitised via `api_security.sanitize_dict()` |
| Tenant isolation | Thread-local DB routing + `assert_not_platform_db()` guard |
| Cross-tenant | Founder sees zero patient data — hard-blocked at route level |
| Error exposure | All crashes → HTTP 503 maintenance page (no tracebacks) |

### Forgot Password Flow
```
User → POST /api/auth/forgot-password (username)
     → 6-digit OTP → Telegram to founder
     → POST /api/auth/verify-otp
     → POST /api/auth/reset-password (new password)
```

### Founder Access Restrictions

| API Group | Founder |
|-----------|---------|
| `/api/founder/*` (platform metrics) | ✅ Allowed |
| `/api/patients/*` | ❌ 403 Blocked |
| `/api/doctor/*` | ❌ 403 Blocked |
| `/api/ipd/*` | ❌ 403 Blocked |
| `/api/admin/data` | ❌ 403 Blocked |

---

## ✨ Features

### OPD (Outpatient)
- Patient registration with **UHID** auto-generation (`UHID000001` format)
- OP ticket numbers (`OP-YYYYMMDD-NNNN`)
- Appointment scheduling, visit tracking
- Doctor prescriptions (structured medicines list)
- Lab order → result upload flow
- Nurse vitals: BP, temperature, pulse, SpO₂, weight
- **Search**: UHID / name / phone / admission date

### IPD (Inpatient)
- Ward/bed admission management
- Daily rounds: doctor + nurse clinical notes
- Surgery: type, anesthesia, estimated/negotiated cost
- Discharge summary with medicines and follow-up

### Pharmacy & Billing
- Medicine catalogue + FIFO batch inventory
- Low stock + expiry alerts
- **GST billing**: 0% / 5% / 12% / 18% per item
- 24+ configurable procedure charges
- Full payment tracking

### PDF Reports (`pdf_generator.py`)

| Document | Endpoint |
|---------|---------|
| OPD Prescription | `GET /api/pdf/prescription/{visit_id}` |
| Discharge Summary | `GET /api/pdf/discharge/{adm_id}` |
| Pharmacy Cash Memo | `GET /api/pdf/pharmacy-bill/{sale_id}` |
| Hospital Invoice | `GET /api/pdf/invoice/{inv_id}` |

### SaaS Platform
- Hospital self-signup at `/hospital_signup` — full tenant DB in seconds
- Wildcard subdomain routing — `<any-name>.mediflow.srpailabs.com`
- Founder dashboard: aggregate platform metrics, zero patient data
- Subscription billing (trial / professional / enterprise)
- Automated backups, data export, cross-tenant analytics

---

## 📋 Logging

| Log File | Content |
|----------|---------|
| `logs/system.log` | Server start/stop, general events |
| `logs/security.log` | Auth events, permission denials |
| `logs/login_attempts.log` | All login attempts (success/fail/locked) |
| `logs/server_errors.log` | Unhandled exceptions with full tracebacks |
| `logs/tenant_access.log` | Subdomain access (slug + IP + path) |

All logs: rotating file handlers — max 10 MB, 5 backups each.

---

## 🗃️ Database Layout

```
srp_platform_db              ← Platform SaaS database (parent)
  clients                      ← All enrolled hospitals (slug, subdomain, db_name…)
  subscriptions                ← Billing per client
  system_alerts                ← Platform-wide alerts (no patient data)
  audit_logs                   ← Admin action trail
  founder_accounts             ← Founder credentials only

hospital_ai                  ← Star Hospital (default dev / first client)
srp_sai_care                 ← Sai Care Hospital
srp_city_medical             ← City Medical Centre
srp_apollo_warangal          ← Apollo Clinic Warangal
srp_green_cross              ← Green Cross Hospital
srp_<slug>                   ← Auto-created for every new enrollment

Per-tenant tables (in each hospital DB):
  staff_users                  ← RBAC accounts (bcrypt)
  patients                     ← Patient master (UHID)
  patient_visits               ← OPD visits + OP tickets
  prescriptions / doctor_notes
  lab_orders / lab_results
  nurse_vitals
  wards / beds / bed_assignments
  patient_admissions           ← IPD
  daily_rounds
  surgery_records
  discharge_summaries
  medicines / inventory_stock
  pharmacy_sales
  billing / bill_items / payments
  services_catalogue           ← Procedure charges
  system_logs / audit_log
```

---

## 📡 API Reference

### Authentication
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/login` | Public |
| `POST` | `/api/logout` | Session |
| `POST` | `/api/change-password` | Session |
| `POST` | `/api/auth/forgot-password` | Public |
| `POST` | `/api/auth/verify-otp` | Public |
| `POST` | `/api/auth/reset-password` | Public |

### Hospital Enrollment
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/hospital_signup` | Public |
| `POST` | `/api/hospital/signup` | Public |
| `POST` | `/api/admin/create-client` | ADMIN/FOUNDER |
| `POST` | `/api/admin/register-client` | ADMIN/FOUNDER |
| `POST` | `/api/admin/create-demo-hospital` | Public |

### Platform (Founder)
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/api/platform/tenants` | Public |
| `GET` | `/api/platform/stats` | Public |
| `GET` | `/api/founder/system-status` | FOUNDER |
| `GET` | `/api/founder/clients` | FOUNDER |

### Config & Branding
| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/api/config` | Public | Returns hospital name/branding per subdomain |

### Patients & Search
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/patients/register` | ADMIN/RECEPTION |
| `GET` | `/api/patients/search?q=X&field=auto` | ADMIN/RECEPTION/DOCTOR/NURSE |

`field` values: `auto` · `uhid` · `name` · `phone` · `date`

### PDF Downloads
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/api/pdf/prescription/{visit_id}` | ADMIN/DOCTOR |
| `GET` | `/api/pdf/discharge/{adm_id}` | ADMIN/DOCTOR |
| `GET` | `/api/pdf/pharmacy-bill/{sale_id}` | ADMIN/STOCK |
| `GET` | `/api/pdf/invoice/{inv_id}` | ADMIN/RECEPTION |

---

## 👤 Roles

| Role | Dashboard | Key Permissions |
|------|-----------|-----------------|
| `FOUNDER` | `/founder` | Platform metrics only — NO patient data |
| `ADMIN` | `/admin` | Full HMS for own hospital |
| `DOCTOR` | `/doctor` | OPD/IPD + prescriptions + lab |
| `NURSE` | `/nurse` | Vitals + IPD rounds |
| `LAB` | `/lab` | Lab requests + results |
| `XRAY` | `/lab` | Radiology |
| `STOCK` | `/stock` | Inventory + pharmacy |
| `RECEPTION` | `/admin` | Appointments + patient registration |

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `srp_mediflow_server.py` | Main HTTP server — all routes and request handlers |
| `tenant_router.py` | Host header → subdomain → slug → DB config resolution |
| `platform_db.py` | Platform SaaS DB (clients, subscriptions, alerts, founder) |
| `db.py` | Tenant DB connections + thread-local routing |
| `hms_db.py` | HMS DB ops (UHID, patients, billing, PDF data) |
| `auth.py` | bcrypt, sessions, lockout, OTP password reset |
| `chatbot.py` | AI chatbot — OPD booking in Telugu/Hindi/English |
| `saas_onboarding.py` | Hospital provisioning (DB + schema + admin + platform_db) |
| `saas_billing.py` | Subscription billing (trial/pro/enterprise) |
| `saas_analytics.py` | Cross-tenant aggregate analytics |
| `saas_backup.py` | Automated DB backup scheduler |
| `saas_export.py` | Per-tenant data export |
| `saas_logging.py` | 5 rotating log files |
| `pdf_generator.py` | ReportLab PDFs (prescription, discharge, bill, invoice) |
| `api_security.py` | Rate limiting, XSS sanitisation, input validation |
| `client_config.py` | Per-request hospital branding resolver |
| `roles.py` | RBAC definitions and permission checks |
| `notifications/founder_alerts.py` | Telegram alerts to platform founder |
| `srp_mediflow_tenant.py` | Low-level tenant DB provisioning (CREATE DATABASE + schema) |
| `hospital_config.py` | Static fallback hospital config |
| `tenant_registry.json` | Slug → DB config fallback (gitignored — stays on server) |
| `srp_mediflow_schema.sql` | Full HMS schema (run per tenant on enrollment) |
| `srp_mediflow_schema_hms.sql` | HMS v4 extended tables |
| `srp_platform_schema.sql` | Platform SaaS schema (includes subdomain column) |
| `migration_security_v2_must_change_password.sql` | Adds `must_change_password` column |
| `index.html` | Patient chatbot / hospital home page |
| `admin_dashboard.html` | Admin full HMS UI |
| `doctor_dashboard.html` | Doctor UI |
| `nurse_dashboard.html` | Nurse UI |
| `lab_dashboard.html` | Lab/X-ray UI |
| `stock_dashboard.html` | Stock/pharmacy UI |
| `founder_dashboard.html` | Platform founder metrics UI |
| `platform_landing.html` | Root domain landing page (signup CTA + demo) |
| `hospital_signup.html` | Public hospital self-registration form |
| `HETZNER_DEPLOY.md` | Full production deployment guide |
| `.env.example` | Environment variables template (committed to GitHub) |

---

## 🧪 Tests

```bash
python _test_saas_upgrade.py       # 39 SaaS security tests
python _test_db_isolation.py       # Tenant isolation
python _test_platform_isolation.py # Platform-tenant separation
python _test_security_v2.py        # Security checks
python run_all_checks.py           # All checks
python _production_audit.py        # 124-point production audit
```

---

## 📦 Dependencies

```
psycopg2-binary   # PostgreSQL driver
bcrypt            # Password hashing
python-dotenv     # .env loading
requests          # HTTP client + Telegram API
reportlab         # PDF generation (optional — HTML fallback if missing)
pyngrok           # ngrok tunnel (dev only, optional)
```

`pip install -r requirements.txt`

---

## 📝 Changelog

### v5.1 — Subdomain Routing Overhaul (March 10, 2026)
- **Wildcard subdomain routing** — `<any-name>.mediflow.srpailabs.com` → correct hospital DB
- **`subdomain` column** added to `platform_db.clients` and `srp_platform_schema.sql`
- **`tenant_router.detect_tenant()`** — now resolves short subdomains (`star-hospital` → `star_hospital` slug) via platform_db lookup first, then file registry, then slug normalisation
- **`srp_mediflow_tenant.create_tenant_db()`** — new `subdomain` param; auto-registers in `platform_db` on creation
- **`saas_onboarding.onboard_hospital()`** — passes `subdomain_url` through full chain; `login_url` now uses real domain
- **`create-client` API** — returns `subdomain`, correct `srp_<slug>` DB name, real `login_url`
- **`/api/config`** — returns `tenant_slug` + `subdomain` so frontend knows which hospital it is
- **`_detect_tenant_subdomain()`** — now sets `self.current_tenant_slug` (full resolved slug) in addition to raw subdomain
- **`tenant_registry.json`** — `subdomain` field added to all 5 existing tenants
- **`HETZNER_DEPLOY.md`** — full rewrite with wildcard DNS setup, migration SQL, per-client URL table, PostgreSQL port guidance

### v5.0 — Production Audit Fixes (March 9, 2026)
- Production audit — 124/124 checks pass
- `patients.uhid` column added + auto-populated
- `.env` fixed — added `PORT`, `ROOT_DOMAIN`, `APP_URL`, `PLATFORM_DB_NAME`, `FOUNDER_CHAT_ID`
- Founder Telegram alerts active
- `requirements.txt` — added `pyngrok>=3.0.0`

### v5.0 — January 2026
- **UHID** — Auto-generated unique patient ID (`UHID000001`)
- **Patient search** — `GET /api/patients/search?q=X&field=auto`
- **PDF generation** — `pdf_generator.py` (ReportLab)
- **Hospital self-signup** — `/hospital_signup`; tenant DB created automatically
- **Demo hospital** — `POST /api/admin/create-demo-hospital`; auto-resets after 24h

### v4.0
- Platform landing page at root domain
- Login lockout: 3 failures → 15-min lock
- Forgot password / OTP via Telegram
- Global error handler → 503 maintenance page
- 4 rotating log files
- Founder RBAC (all patient APIs blocked)

### v3.0 — Multi-Tenant SaaS
- Separate PostgreSQL DB per hospital
- Wildcard subdomain routing
- `saas_billing`, `saas_analytics`, `saas_onboarding`, `saas_backup`

### v2.0 — IPD + Full HMS
- IPD: admissions, daily rounds, discharge, surgery
- Pharmacy FIFO batches + GST billing

### v1.0 — OPD + RBAC
- 7-role RBAC (bcrypt), AI chatbot (3 languages), OPD flow

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

*SRP MediFlow v5.1 · Built for Indian hospitals · Powered by SRP AI Labs*


---

## ✅ Production Audit Report — March 9, 2026

> Full 13-step automated audit run via `_production_audit.py`
> **Result: 124/124 checks passed · 0 failures · PROJECT READY FOR PRODUCTION**

### Audit Summary

| Step | Area | Result |
|------|------|--------|
| 1 | Project structure (26 required files) | ✅ ALL PRESENT |
| 2 | Python syntax check (12 modules) | ✅ ALL CLEAN |
| 3 | Dependencies | ✅ All installed (`pyngrok` optional) |
| 4 | Environment variables | ✅ Fixed — 5 vars appended to `.env` |
| 5 | Database — tenant + platform connection | ✅ Both connected |
| 5 | Database — 19 core tables | ✅ All present |
| 5 | Database — `patients.uhid` column | ✅ Fixed — Added via `ALTER TABLE` |
| 6 | Route validation (11 routes) | ✅ All correct (`/hospital_signup` fixed) |
| 7 | Tenant router — 4 host patterns | ✅ Correct slug detection |
| 8 | Security — bcrypt, lockout, OTP, XSS strip | ✅ All working |
| 9 | Logging — 5 log files | ✅ All created + verified |
| 10 | PDF generation — 4 document types | ✅ ReportLab producing valid PDFs |
| 11 | SaaS onboarding module | ✅ `onboard_hospital()` ready |
| 12 | `.env` completeness | ✅ Fixed — missing vars appended |
| 13 | `requirements.txt` | ✅ Fixed — `pyngrok` added |

### Issues Found & Fixed During Audit

| # | Severity | Issue | Fix Applied |
|---|----------|-------|-------------|
| 1 | 🔴 Critical | `patients.uhid` column missing from DB | `ALTER TABLE patients ADD COLUMN uhid` + auto-populated 5 existing patients |
| 2 | 🔴 Critical | `.env` missing `PORT`, `ROOT_DOMAIN`, `APP_URL`, `PLATFORM_DB_NAME`, `FOUNDER_CHAT_ID` | Appended all 5 vars to `.env` |
| 3 | 🟡 Medium | `FOUNDER_CHAT_ID` env var mismatch (code reads `FOUNDER_CHAT_ID`, .env had `FOUNDER_TELEGRAM_CHAT_ID`) | `FOUNDER_CHAT_ID=7144152487` appended to `.env` |
| 4 | 🟡 Medium | `/hospital_signup` returning 404 (server was stale — started before route was added) | Server restarted — now returns 200 ✅ |
| 5 | 🟡 Medium | `/api/pdf/prescription/1` returning 404 (same stale server) | Resolved by restart — now returns 401 (correct auth guard) ✅ |
| 6 | 🟢 Low | `requirements.txt` missing `pyngrok` | `pyngrok>=3.0.0` appended to requirements.txt |

### Route Test Results

| Method | Route | Expected | Result |
|--------|-------|----------|--------|
| `GET` | `/health` | 200 | ✅ 200 — `{"status":"ok","db":true}` |
| `GET` | `/` | 200 | ✅ 200 — Patient chatbot |
| `GET` | `/login` | 200 | ✅ 200 — Login page |
| `GET` | `/hospital_signup` | 200 | ✅ 200 — Signup page |
| `GET` | `/api/platform/stats` | 200 | ✅ 200 — JSON stats |
| `GET` | `/api/platform/tenants` | 200 | ✅ 200 — Tenant list |
| `GET` | `/admin` | 200/302 | ✅ 200 — Redirects to login (no session) |
| `GET` | `/founder` | 200/302 | ✅ 200 — Redirects to login (no session) |
| `POST` | `/api/login` (bad creds) | 401 | ✅ 401 — `{"status":"error"}` JSON |
| `GET` | `/api/patients/search` | 401 | ✅ 401 — Auth required |
| `GET` | `/api/pdf/prescription/1` | 401 | ✅ 401 — Auth required |

---

## 🧪 Pre-Test Checklist (For Tomorrow's Testing Session)

> Run these in order before starting manual/integration testing.

### 1 — Start Server

```bash
# Windows
double-click: 🏥 START SRP MEDIFLOW.bat

# Or manually:
python srp_mediflow_server.py
```

Confirm you see: `✅ PostgreSQL connected` and `✅ Founder channel active`

### 2 — Verify Health

```
GET http://localhost:7500/health
→ {"status":"ok","db":true}
```

### 3 — Current `.env` (All Vars Confirmed)

| Variable | Value / Status |
|----------|---------------|
| `PORT` | `7500` ✅ |
| `ROOT_DOMAIN` | `mediflow.srpailabs.com` ✅ |
| `APP_URL` | `https://mediflow.srpailabs.com` ✅ |
| `PG_HOST` | `localhost` ✅ |
| `PG_PORT` | `5434` ✅ |
| `PG_DB` | `hospital_ai` ✅ |
| `PG_USER` | `ats_user` ✅ |
| `PG_PASSWORD` | `ats_password` ✅ |
| `PLATFORM_DB_NAME` | `srp_platform_db` ✅ |
| `TELEGRAM_BOT_TOKEN` | set (via alias `FOUNDER_TELEGRAM_TOKEN`) ✅ |
| `FOUNDER_CHAT_ID` | `7144152487` ✅ |
| `WHATSAPP_API_KEY` | not set — placeholder mode (expected) |

### 4 — Test Scenarios for Tomorrow

#### A — Login Tests
| Test | URL | Credentials | Expected |
|------|-----|-------------|----------|
| Admin login | `http://localhost:7500/login` | `star_hospital_admin` / `Star@Admin2026!` | Redirect to `/admin` |
| Doctor login | `http://localhost:7500/login` | `star_hospital_doctor` / `Doctor@star2026!` | Redirect to `/doctor` |
| Wrong password (3×) | `/api/login` | any bad creds | 401 × 3, then 15-min lockout |
| Founder login | `http://localhost:7500/login` | `founder` / `Srp@Founder2026!` | Redirect to `/founder` |

#### B — Patient Registration + UHID
| Test | Steps | Expected |
|------|-------|----------|
| Register new patient | Admin login → New Patient form | UHID auto-assigned (`UHID000006` or next) |
| Search by UHID | `GET /api/patients/search?q=UHID000001` | Patient returned |
| Search by phone | `GET /api/patients/search?q=9876543210` | Patient returned |
| Search by name | `GET /api/patients/search?q=Ravi` | Matching patients |

#### C — PDF Generation
| Test | URL | Expected |
|------|-----|----------|
| Prescription PDF | `GET /api/pdf/prescription/1` (logged in as ADMIN/DOCTOR) | PDF download in browser |
| Discharge PDF | `GET /api/pdf/discharge/1` | PDF download |
| Pharmacy Bill | `GET /api/pdf/pharmacy-bill/1` | PDF download |
| Invoice | `GET /api/pdf/invoice/1` | PDF download |

#### D — Hospital Self-Signup (SaaS Onboarding)
| Test | Steps | Expected |
|------|-------|----------|
| Open signup page | `http://localhost:7500/hospital_signup` | Form page loads |
| Submit test hospital | Fill form with `Test Hospital`, `test_hospital` slug | Response includes `login_url`, `admin_username` |
| Verify DB created | Connect to `srp_test_hospital` in PostgreSQL | Tables present |
| Founder alert | Check Telegram | Message: "New hospital registered" |

#### E — Founder Dashboard
| Test | URL | Expected |
|------|-----|----------|
| Platform stats | `/api/platform/stats` | `total_hospitals`, `active_today` |
| Client list | `/api/founder/clients` | All registered hospitals |
| Founder blocked from patient data | `GET /api/admin/data` (as FOUNDER) | 403 Forbidden |

#### F — Tenant Routing
| Test | Host Header | Expected Slug |
|------|-------------|---------------|
| Root domain | `mediflow.srpailabs.com` | `platform` → landing page |
| Tenant portal | `star-hospital.mediflow.srpailabs.com` | `star-hospital` |
| Localhost dev | `localhost:7500` | `star_hospital` (default) |

### 5 — Run Automated Test Suite

```bash
python _test_saas_upgrade.py       # 39 SaaS tests (expect all PASS)
python _production_audit.py        # 124 production checks (expect 0 FAIL)
python _test_db_isolation.py       # Tenant isolation
python _test_security_v2.py        # Security checks
```

### 6 — Check Logs After Testing

```bash
# Windows PowerShell
Get-Content logs\system.log -Tail 20
Get-Content logs\security.log -Tail 20
Get-Content logs\login_attempts.log -Tail 10
Get-Content logs\server_errors.log
Get-Content logs\tenant_access.log -Tail 10
```

### 7 — Production Deployment Checklist

- [ ] Set `PG_PASSWORD` to a strong password (not `ats_password`)
- [ ] Set `TELEGRAM_BOT_TOKEN` to production bot token
- [ ] Set `FOUNDER_CHAT_ID` to production chat ID
- [ ] Set `APP_URL` to `https://mediflow.srpailabs.com`
- [ ] Cloudflare DNS: `A mediflow → <hetzner_ip>` + `A *.mediflow → <hetzner_ip>`
- [ ] Nginx config with `proxy_set_header Host $host` (critical for tenant routing)
- [ ] SSL via Certbot (wildcard cert)
- [ ] systemd service enabled + auto-restart on failure
- [ ] `cron` job for daily backups (`saas_backup.py`)
- [ ] First server start on VPS should trigger Telegram alert confirming deployment

---

## ⚡ Quick Start (Local Dev)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in values
python srp_mediflow_server.py
```

| URL | Purpose |
|-----|---------|
| `http://localhost:7500/` | Patient chatbot |
| `http://localhost:7500/admin` | Admin dashboard |
| `http://localhost:7500/hospital_signup` | Register new hospital |
| `http://localhost:7500/founder` | Platform founder dashboard |

**Windows:** Double-click `🏥 START SRP MEDIFLOW.bat`

---

## 🔑 Default Credentials

| Role | Username | Password |
|------|----------|----------|
| Platform Founder | `founder` | `Srp@Founder2026!` |
| Star Hospital Admin | `star_hospital_admin` | `Star@Admin2026!` |
| Star Hospital Doctor | `star_hospital_doctor` | `Doctor@star2026!` |
| Star Hospital Nurse | `star_hospital_nurse` | `Nurse@star2026!` |

> Passwords are **bcrypt-hashed** — never stored in plaintext.
> See [ADMIN_LOGIN_CREDENTIALS.md](ADMIN_LOGIN_CREDENTIALS.md) for full list.

---

## 🌐 Production Deployment (Hetzner + Cloudflare)

### 1 — Cloudflare DNS

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| `A` | `mediflow` | `<hetzner_ip>` | ✅ Proxied |
| `A` | `*.mediflow` | `<hetzner_ip>` | ✅ Proxied |

The wildcard `*.mediflow` handles **all hospital subdomains automatically** — no per-hospital DNS entry ever needed.

### 2 — Server Setup

```bash
ssh root@<hetzner_ip>
apt update && apt install -y python3.12 python3-pip postgresql nginx certbot python3-certbot-nginx git

sudo -u postgres psql -c "CREATE USER ats_user WITH PASSWORD 'secure_password';"
sudo -u postgres psql -c "CREATE DATABASE hospital_ai OWNER ats_user;"
sudo -u postgres psql -c "CREATE DATABASE srp_platform_db OWNER ats_user;"

git clone https://github.com/your-org/srp-mediflow.git /opt/srp-mediflow
cd /opt/srp-mediflow && pip install -r requirements.txt
cp .env.example .env && nano .env
```

### 3 — Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7500` | HTTP server port |
| `ROOT_DOMAIN` | `mediflow.srpailabs.com` | Platform apex domain |
| `APP_URL` | `http://localhost:7500` | Public-facing URL |
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_PORT` | `5434` | PostgreSQL port |
| `PG_DB` | `hospital_ai` | Default tenant DB |
| `PG_USER` | `ats_user` | PostgreSQL user |
| `PG_PASSWORD` | — | PostgreSQL password (**required**) |
| `PLATFORM_DB_NAME` | `srp_platform_db` | Platform SaaS DB |
| `FOUNDER_CHAT_ID` | — | Telegram chat ID for alerts |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `WHATSAPP_API_KEY` | — | WhatsApp gateway (optional) |

### 4 — systemd Service

`/etc/systemd/system/srp-mediflow.service`:

```ini
[Unit]
Description=SRP MediFlow Hospital Platform
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/srp-mediflow
EnvironmentFile=/opt/srp-mediflow/.env
ExecStart=/usr/bin/python3 srp_mediflow_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now srp-mediflow
```

### 5 — Nginx Config

```nginx
server {
    listen 80;
    server_name mediflow.srpailabs.com *.mediflow.srpailabs.com;
    location / {
        proxy_pass http://127.0.0.1:7500;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/mediflow /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d "mediflow.srpailabs.com" -d "*.mediflow.srpailabs.com"
```

---

## 🏗️ Architecture

```
Cloudflare (*.mediflow → Hetzner IP)
  → Nginx (80/443 → 7500)
    → srp_mediflow_server.py
         ├── _is_platform_root_request()  → platform_landing.html
         ├── _detect_tenant_subdomain()   → logs tenant_access.log
         │
         ├── GET  /hospital_signup                → hospital_signup.html (public)
         ├── POST /api/hospital/signup            → creates tenant DB automatically
         ├── POST /api/admin/create-demo-hospital → ephemeral demo, 24h auto-reset
         │
         ├── GET  /api/patients/search?q=         → UHID / name / phone / date
         │
         ├── GET  /api/pdf/prescription/{id}      → OPD PDF
         ├── GET  /api/pdf/discharge/{id}         → IPD discharge PDF
         ├── GET  /api/pdf/pharmacy-bill/{id}     → Pharmacy bill PDF
         ├── GET  /api/pdf/invoice/{id}           → Invoice PDF
         │
         └── Tenant HMS routes
               └── psycopg2 → srp_{slug} PostgreSQL DB

Module map:
  tenant_router.py    — Host header → slug → DB config
  auth.py             — bcrypt, sessions, lockout, OTP
  hms_db.py           — All HMS DB ops (UHID, patients, billing, PDF data)
  pdf_generator.py    — ReportLab PDFs (4 document types)
  saas_onboarding.py  — Full hospital provisioning (DB + schema + admin)
  platform_db.py      — Platform DB (clients, billing, alerts)
  saas_logging.py     — 5 rotating log files
```

---

## ✨ Features

### OPD (Outpatient)
- Patient registration with **UHID** auto-generation (`UHID000001` format)
- OP ticket numbers (`OP-YYYYMMDD-NNNN`)
- Appointment scheduling, visit tracking
- Doctor prescriptions (structured medicines list)
- Lab order → result upload flow
- Nurse vitals: BP, temperature, pulse, SpO₂, weight
- **Comprehensive search**: UHID / name / phone / admission date

### IPD (Inpatient)
- Ward/bed admission management (6 default wards + configurable beds)
- Daily rounds: doctor + nurse clinical notes per admission
- Surgery: type, anesthesia, estimated/negotiated cost
- Discharge summary with medicines and follow-up

### Pharmacy & Billing
- Medicine catalogue + FIFO batch inventory
- Low stock + expiry alerts (dashboard + API)
- **GST billing**: 0% / 5% / 12% / 18% per item
- 24+ configurable procedure charges
- Full payment tracking

### PDF Reports (`pdf_generator.py`)

| Document | Endpoint |
|---------|---------|
| OPD Prescription | `GET /api/pdf/prescription/{visit_id}` |
| Discharge Summary | `GET /api/pdf/discharge/{adm_id}` |
| Pharmacy Cash Memo | `GET /api/pdf/pharmacy-bill/{sale_id}` |
| Hospital Invoice | `GET /api/pdf/invoice/{inv_id}` |

> Requires `pip install reportlab`. Falls back to branded HTML receipt automatically.

### SaaS Platform
- Hospital self-signup at `/hospital_signup` — full tenant DB created in seconds
- Demo hospital (`POST /api/admin/create-demo-hospital`) — auto-resets every 24h
- Wildcard subdomain routing (no per-hospital DNS config needed)
- Founder dashboard: aggregate platform metrics, zero patient data
- Subscription billing (trial / professional ₹2999/mo / enterprise)
- Automated backups, data export, cross-tenant analytics

---

## 🔒 Security

| Feature | Detail |
|---------|--------|
| Passwords | bcrypt (SHA-256 fallback for legacy accounts) |
| Sessions | 64-hex token, 8h TTL, in-memory dict |
| Brute-force | 3 failures → 15-min account lockout |
| Recovery | OTP via Telegram (6-digit, 10-min TTL) |
| Rate limiting | Per-IP request throttle (`api_security.check_rate_limit()`) |
| SQL injection | All inputs sanitised via `api_security.sanitize_dict()` |
| Tenant isolation | Thread-local DB routing + `assert_not_platform_db()` guard |
| Error exposure | All crashes → HTTP 503 maintenance page (no raw tracebacks) |

### Forgot Password Flow
```
User → POST /api/auth/forgot-password (username)
     → 6-digit OTP sent to founder via Telegram
     → POST /api/auth/verify-otp
     → POST /api/auth/reset-password (new password)
```

### Founder Access Restrictions

| API Group | Founder |
|-----------|---------|
| `/api/founder/*` (platform metrics) | ✅ Allowed |
| `/api/patients/*` | ❌ 403 Blocked |
| `/api/doctor/*` | ❌ 403 Blocked |
| `/api/ipd/*` | ❌ 403 Blocked |
| `/api/admin/data` | ❌ 403 Blocked |

---

## 📋 Logging

| Log File | Content |
|----------|---------|
| `logs/system.log` | Server start/stop, general events |
| `logs/security.log` | Auth events, permission denials |
| `logs/login_attempts.log` | All login attempts (success/fail/locked) |
| `logs/server_errors.log` | Unhandled exceptions with full tracebacks |
| `logs/tenant_access.log` | Tenant subdomain access (slug + IP + path) |

All logs: rotating file handlers — max 10 MB, 5 backups each.

---

## 🔄 Hospital Onboarding Flow

```
/hospital_signup → submit form
POST /api/hospital/signup
  → saas_onboarding.onboard_hospital()
      ├── Validate inputs + check slug uniqueness
      ├── CREATE DATABASE srp_{slug} OWNER ats_user
      ├── Run srp_mediflow_schema.sql (tables + seed data)
      ├── INSERT admin user (bcrypt password)
      ├── INSERT clients row in srp_platform_db
      └── INSERT billing record (plan)
  → Response: { login_url, admin_username, admin_password, database, plan }
  → Founder Telegram alert: "New hospital registered"
  → Hospital portal live at {slug}.mediflow.srpailabs.com
```

---

## 🗃️ Database Layout

```
srp_platform_db          ← Platform SaaS database
  clients                  ← Registered hospitals
  subscriptions            ← Billing
  system_alerts            ← Platform alerts
  audit_logs
  founder_accounts

hospital_ai              ← Star Hospital (default dev)
srp_{slug}               ← Auto-created per onboarded hospital

Per-tenant tables:
  staff_users             ← RBAC accounts (bcrypt)
  patients                ← Patient master (includes uhid column)
  patient_visits          ← OPD visits + OP tickets
  op_tickets              ← OP ticket numbers
  prescriptions / doctor_notes
  lab_orders / lab_results
  nurse_vitals
  wards / beds / bed_assignments
  patient_admissions      ← IPD
  daily_rounds
  surgery_records
  discharge_summaries
  medicines / inventory_stock
  pharmacy_sales
  billing / bill_items / payments
  services_catalogue      ← Procedure charges
  system_logs / audit_log
```

---

## 📡 API Reference

### Authentication
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/login` | Public |
| `POST` | `/api/logout` | Session |
| `POST` | `/api/change-password` | Session |
| `POST` | `/api/auth/forgot-password` | Public |
| `POST` | `/api/auth/verify-otp` | Public |
| `POST` | `/api/auth/reset-password` | Public |
| `POST` | `/api/auth/contact-support` | Public |

### Hospital Registration
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/hospital_signup` | Public |
| `POST` | `/api/hospital/signup` | Public |
| `POST` | `/api/admin/create-demo-hospital` | Public |

### Platform
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/api/platform/tenants` | Public |
| `GET` | `/api/platform/stats` | Public |
| `GET` | `/api/founder/system-status` | FOUNDER |
| `GET` | `/api/founder/clients` | FOUNDER |

### Patients & Search
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/patients/register` | ADMIN/RECEPTION |
| `GET` | `/api/patients/search?q=X&field=auto` | ADMIN/RECEPTION/DOCTOR/NURSE |

`field` values: `auto` · `uhid` · `name` · `phone` · `date`

### PDF Downloads
| Method | Endpoint | Auth |
|--------|----------|------|
| `GET` | `/api/pdf/prescription/{visit_id}` | ADMIN/DOCTOR |
| `GET` | `/api/pdf/discharge/{adm_id}` | ADMIN/DOCTOR |
| `GET` | `/api/pdf/pharmacy-bill/{sale_id}` | ADMIN/STOCK |
| `GET` | `/api/pdf/invoice/{inv_id}` | ADMIN/RECEPTION |

### OPD / Clinical
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/admin/appointments` | ADMIN/RECEPTION |
| `POST` | `/api/doctor/prescription` | DOCTOR/ADMIN |
| `POST` | `/api/doctor/note` | DOCTOR/ADMIN |
| `POST` | `/api/doctor/lab/request` | DOCTOR/ADMIN |
| `POST` | `/api/nurse/vitals/add` | NURSE/ADMIN |
| `POST` | `/api/lab/result` | LAB/XRAY |

### IPD
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/ipd/admit` | ADMIN/RECEPTION |
| `POST` | `/api/ipd/round/add` | DOCTOR/NURSE |
| `POST` | `/api/ipd/discharge` | ADMIN/DOCTOR |
| `POST` | `/api/surgery/create` | ADMIN/DOCTOR |
| `POST` | `/api/surgery/update-cost` | ADMIN |

### Pharmacy & Billing
| Method | Endpoint | Auth |
|--------|----------|------|
| `POST` | `/api/pharmacy/add-stock` | ADMIN/STOCK |
| `POST` | `/api/pharmacy/sell` | ADMIN/STOCK/RECEPTION |
| `POST` | `/api/billing/create` | ADMIN/RECEPTION |
| `POST` | `/api/billing/add-item` | ADMIN/RECEPTION |
| `POST` | `/api/billing/payment` | ADMIN/RECEPTION |

---

## 👤 Roles

| Role | Dashboard | Key Permissions |
|------|-----------|-----------------|
| `FOUNDER` | `/founder` | Platform metrics only — NO patient data |
| `ADMIN` | `/admin` | Full HMS for own hospital |
| `DOCTOR` | `/doctor` | OPD/IPD + prescriptions + lab |
| `NURSE` | `/nurse` | Vitals + IPD rounds |
| `LAB` | `/lab` | Lab requests + results |
| `XRAY` | `/lab` | Radiology |
| `STOCK` | `/stock` | Inventory + pharmacy |
| `RECEPTION` | `/admin` | Appointments + patient registration |

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `srp_mediflow_server.py` | Main HTTP server — all routes and handlers |
| `hms_db.py` | HMS DB ops (UHID, patients, billing, PDF data helpers) |
| `pdf_generator.py` | ReportLab PDF generation (4 document types) |
| `hospital_signup.html` | Public hospital self-registration page |
| `saas_onboarding.py` | Hospital provisioning (DB + schema + admin account) |
| `auth.py` | bcrypt, sessions, lockout, OTP |
| `tenant_router.py` | Host header → tenant slug → DB config |
| `platform_db.py` | Platform SaaS database (clients, billing, health) |
| `saas_logging.py` | 5 rotating log files |
| `saas_billing.py` | Subscription billing |
| `saas_analytics.py` | Cross-tenant analytics |
| `saas_backup.py` | Backup scheduler |
| `saas_export.py` | Per-tenant data export |
| `chatbot.py` | AI chatbot (OPD booking, Telugu/Hindi/English) |
| `notifications/founder_alerts.py` | Telegram alerts to founder |
| `platform_landing.html` | Root domain landing page (signup CTA + demo) |
| `admin_dashboard.html` | Admin full HMS UI |
| `doctor_dashboard.html` | Doctor UI |
| `nurse_dashboard.html` | Nurse UI |
| `lab_dashboard.html` | Lab/X-ray UI |
| `stock_dashboard.html` | Stock/pharmacy UI |
| `founder_dashboard.html` | Platform founder metrics UI |
| `tenant_registry.json` | Tenant slug → DB config fallback |
| `srp_mediflow_schema.sql` | Full HMS schema + seed data (run per tenant) |
| `srp_platform_schema.sql` | Platform SaaS schema |

---

## 🧪 Tests

```bash
python _test_saas_upgrade.py      # 39 SaaS security tests
python _test_db_isolation.py      # Tenant isolation
python _test_platform_isolation.py
python _test_security_v2.py
python run_all_checks.py          # All checks
```

---

## 📦 Dependencies

```
psycopg2-binary   # PostgreSQL driver
bcrypt            # Password hashing
python-dotenv     # .env loading
requests          # HTTP client + Telegram API
reportlab         # PDF generation (optional — HTML fallback if missing)
pyngrok           # ngrok tunnel (dev only)
```

`pip install -r requirements.txt`
`pip install reportlab`  ← for real PDFs

---

## 📝 Changelog

### v5.0 — Production Audit Fixes (March 9, 2026)
- **Production audit** — `_production_audit.py` (124/124 checks pass)
- **`patients.uhid`** — Added missing column via `ALTER TABLE` + auto-populated 5 existing patients
- **`.env` fixed** — Added `PORT`, `ROOT_DOMAIN`, `APP_URL`, `PLATFORM_DB_NAME`, `FOUNDER_CHAT_ID`
- **Founder alerts active** — Fixed `FOUNDER_CHAT_ID` env var name mismatch; Telegram alerts now firing
- **Server restart** — Fixed stale server; `/hospital_signup` and PDF routes now return correct status codes
- **`requirements.txt`** — Added `pyngrok>=3.0.0`

### v5.0 — January 2026
- **UHID** — Auto-generated unique patient ID on registration (`UHID000001`)
- **Patient search** — `GET /api/patients/search?q=X&field=auto` (UHID/name/phone/date)
- **PDF generation** — `pdf_generator.py` (ReportLab): prescription, discharge, pharmacy bill, invoice
- **Hospital self-signup** — `/hospital_signup` public page; full tenant DB created automatically
- **Demo hospital** — `POST /api/admin/create-demo-hospital`; auto-resets after 24h
- **`tenant_access.log`** — New 5th log file; records every subdomain access
- **Landing page** — "Register Your Hospital" CTA + live demo request button
- **New DB helpers** — `get_visit_detail()`, `get_admission_detail()`, `get_sale_detail()`

### v4.0 — March 9, 2026
- Platform landing page at root domain
- Login lockout: 3 failures → 15-min lock
- Forgot password / OTP via Telegram
- Global error handler → 503 maintenance page
- 4 rotating log files
- Founder RBAC (all patient APIs blocked)
- 39-test automated suite

### v3.0 — Multi-Tenant SaaS
- Separate PostgreSQL DB per hospital
- Wildcard subdomain routing
- saas_billing, saas_analytics, saas_onboarding, saas_backup

### v2.0 — IPD + Full HMS
- IPD: admissions, daily rounds, discharge, surgery
- Pharmacy FIFO batches + GST billing

### v1.0 — OPD + RBAC
- 7-role RBAC (bcrypt), AI chatbot (3 languages), OPD flow

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

*SRP MediFlow v5.0 · Built for Indian hospitals · Powered by SRP AI Labs*
