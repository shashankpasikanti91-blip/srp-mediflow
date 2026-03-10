# 🏥 SRP MediFlow — Production SaaS Hospital Management Platform

> **Enterprise-grade multi-tenant HMS SaaS for Indian hospitals**
> OPD · IPD · Pharmacy · Surgery · GST Billing · UHID · PDF Reports · AI Chatbot · Multi-Tenant

**Version:** `6.1 SaaS` | **Updated:** March 2026
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

### 🔑 Platform Founder
| Role | Username | Password | Dashboard |
|------|----------|----------|-----------|
| Platform Founder | `founder` | `Srp@Founder2026!` | `/founder` |

### 🏥 Star Hospital (`hospital_ai` DB)
| Role | Username | Password | Dashboard |
|------|----------|----------|-----------|
| Admin | `star_hospital_admin` | `Star@Admin2026!` | `/admin` |
| Doctor | `star_hospital_doctor` | `Doctor@Star2026!` | `/doctor` |
| Nurse | `star_hospital_nurse` | `Nurse@Star2026!` | `/nurse` |
| Lab | `star_hospital_lab` | `Lab@Star2026!` | `/lab` |
| Stock | `star_hospital_stock` | `Stock@Star2026!` | `/stock` |
| Reception | `star_hospital_reception` | `Recep@Star2026!` | `/admin` |
| Patient Chatbot | — | — | `/chat/star_hospital` |

### 🏥 Sai Care Hospital (`srp_sai_care` DB)
| Role | Username | Password |
|------|----------|----------|
| Admin | `sai_care_admin` | `SaiCare@Admin2026!` |
| Doctor | `sai_care_doctor` | `Doctor@SaiCare2026!` |
| Nurse | `sai_care_nurse` | `Nurse@SaiCare2026!` |
| Patient Chatbot | — | `/chat/sai_care` |

### 🏥 City Medical Centre (`srp_city_medical` DB)
| Role | Username | Password |
|------|----------|----------|
| Admin | `city_medical_admin` | `CityMed@Admin2026!` |
| Doctor | `city_medical_doctor` | `Doctor@CityMed2026!` |
| Patient Chatbot | — | `/chat/city_medical` |

### 🏥 Apollo Clinic Warangal (`srp_apollo_warangal` DB)
| Role | Username | Password |
|------|----------|----------|
| Admin | `apollo_warangal_admin` | `Apollo@Admin2026!` |
| Doctor | `apollo_warangal_doctor` | `Doctor@Apollo2026!` |
| Patient Chatbot | — | `/chat/apollo_warangal` |

### 🏥 Green Cross Hospital (`srp_green_cross` DB)
| Role | Username | Password |
|------|----------|----------|
| Admin | `green_cross_admin` | `GreenCross@Admin2026!` |
| Doctor | `green_cross_doctor` | `Doctor@GrnCross2026!` |
| Patient Chatbot | — | `/chat/green_cross` |

> All passwords are **bcrypt-hashed** in PostgreSQL — never stored in plaintext.  
> Each client has a **completely isolated PostgreSQL database** — data never mixes.  
> Per-client chatbot URL: `http://localhost:7500/chat/{slug}` — auto-injects hospital branding.

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

### v6.7 — Full Responsive Dashboards · Founder Mobile · Per-Client Chatbots (March 10, 2026)

#### 📱 All Dashboards Fully Responsive (Mobile / Tablet / Laptop / Desktop)
- **All 6 dashboards** now have complete `@media` responsive CSS:
  - `admin_dashboard.html` — compact 13px base, sidebar collapses to horizontal scroll strip on mobile, stat cards stack to 2-col then 1-col
  - `doctor_dashboard.html` — sidebar becomes horizontal tab strip at ≤900px; tables scroll horizontally
  - `nurse_dashboard.html` — same responsive pattern with teal color theme
  - `lab_dashboard.html` — same responsive pattern with purple theme
  - `stock_dashboard.html` — stat grid reduces 3→2→1 col; form grids stack to single column
  - `founder_dashboard.html` — full mobile treatment: header stacks, tabs become horizontal scroll strip, cards go to 1-col at 600px
- Breakpoints: desktop (>900px full layout) → tablet (900px sidebar collapses) → mobile (600px topbar stacks) → small phone (380px minimal UI)

#### 🤖 Per-Client Chatbot URLs (Confirmed Working)
- Each hospital has its own dedicated chatbot: `http://localhost:7500/chat/{slug}`
  - Star Hospital → `/chat/star_hospital`
  - Sai Care → `/chat/sai_care`
  - City Medical → `/chat/city_medical`
  - Apollo Warangal → `/chat/apollo_warangal`
  - Green Cross → `/chat/green_cross`
- Server injects `window.TENANT_SLUG = "{slug}"` → `/api/config` loads correct hospital name/branding automatically
- On mobile: renders as WhatsApp-style chat (green bubbles, bottom input bar)

#### 👑 Founder Dashboard Access Verified
- Login: `founder` / `Srp@Founder2026!` → redirects to `/founder`
- Sees: all 5 client cards, system status, platform-wide stats, data isolation test runner
- CANNOT see any patient data — hard-blocked at route level
- Fully responsive on mobile

#### 🔑 All Credentials Reset & Verified
- All passwords for all 5 clients + founder reset to known values (bcrypt re-hashed)
- Tested: founder ✅, star_hospital_admin ✅, all other clients ✅

---

### v6.6 — 5 Fake Clients · WhatsApp Mobile Chatbot · Layout Compact · Cleanup (March 10, 2026)

#### 🏥 5 Separate Tenant Databases Provisioned
- **5 isolated PostgreSQL databases** created and seeded:
  - `hospital_ai` — Star Hospital, Khammam (5 appointments, 16 pharmacy items)
  - `srp_sai_care` — Sai Care Hospital, Khammam (3 appointments)
  - `srp_city_medical` — City Medical Centre, Hyderabad (3 appointments)
  - `srp_apollo_warangal` — Apollo Clinic Warangal (3 appointments)
  - `srp_green_cross` — Green Cross Hospital, Vijayawada (3 appointments)
- Each DB has 6 staff users: admin, doctor, nurse, lab, stock, reception
- **Data isolation verified**: Star Hospital patients never appear in Sai Care dashboard and vice versa
- `_provision_demo_clients.py` port fixed: 5434 → 5432 (Windows PostgreSQL)

#### 📱 WhatsApp-Style Mobile Chatbot (`style.css`)
- At ≤768px, the patient chatbot transforms to WhatsApp-style UI:
  - Bot messages: white left bubble with left-pointing tail
  - Patient messages: `#DCF8C6` green right bubble (WhatsApp sent colour)
  - Quick action buttons: horizontal scroll chips in WhatsApp teal (`#075E54`)
  - Bottom input bar: circular Send button (➤), circular mic button, full-width text field
  - Header changes to WhatsApp dark green `#075E54`
  - Info sidebar hidden on mobile — chat takes full screen
  - Modal becomes fullscreen on mobile
  - Extra-small phones (<380px): language buttons hidden to save space
- Desktop view unchanged — only applies at ≤768px

#### 🗜️ Admin Dashboard Compact Layout
- Base font reduced from 16px → 13px (`html { font-size: 13px }`)
- Sidebar width 250px → 200px, padding reduced
- Table cell padding 12px → 8px, font 14px → 12px
- Stat cards: number 32px → 26px, padding tightened
- Reduces need to zoom out to 70% — fits comfortably at 100% on standard screens

#### 🧹 Folder Cleanup
- `.gitignore` updated to exclude: `_e2e_test_*.py`, `_seed_demo_records.py`, `test_results*.txt`, `apidata.json`
- All `srvout_*.txt` / `srverr_*.txt` already gitignored

---

### v6.3 — Click Actions · AI Messages · Date Field · Branding · Demo Data (March 2026)

#### 🖱️ Click Actions on All Admin Dashboard Tables
- **Patients table** — every row now has `cursor:pointer` + `onclick='viewPatient(...)'`; an **👁 View** button launches a detail modal showing name, phone, age, issue, doctor, preferred date/time, status
- **Doctors table** — every row clickable; **👁 View** modal shows department, specialization, qualification, duty status
- **Billing table** — every row clickable; **👁 View** modal shows full fee breakdown (consultation, lab, pharmacy, imaging, surgery, bed, misc, discount, net) with payment status
- **Surgery table** — every row clickable; **👁 View** modal shows surgeon, surgery type, anaesthesia, cost, operation notes, complications
- **Lab Reports** — all rows (PENDING and COMPLETED) are now clickable; COMPLETED shows 🗒 Report button, PENDING shows 👁 View button — both open the full lab report modal
- Action column added to thead for: Patients, Doctors, Billing, Surgery tables
- `_showDetailModal(title, rows)` helper renders a clean overlay modal; `viewPatient()`, `viewDoctor()`, `viewBill()`, `viewSurgery()` functions all use it

#### ✨ AI Smart Message Generator (OpenAI GPT-4o-mini)
- New **`GET /api/ai/generate-message`** endpoint accepts `type`, `patient_name`, `doctor_name`, `details` query params
- Also exposed as **`POST /api/ai/generate-message`** for form-based usage
- Uses `OPENAI_API_KEY` from `.env` with GPT-4o-mini model; falls back gracefully to a professional template if key is unavailable
- 5 message types: **Appointment Confirmation**, **Prescription Ready**, **Lab Results Ready**, **Discharge Notice**, **General Alert**
- New UI panel in Admin → Notification Settings → **✨ AI Smart Message Generator**:
  - Select type, enter patient name, doctor (optional), details (optional)
  - Click **✨ Generate Message** → AI drafts a professional SMS under 160 chars
  - **📋 Copy** to clipboard or **📱 Send via Telegram** directly from the dashboard
  - Source badge shows "AI generated" vs "Template (AI unavailable)"

#### 📅 Date Field in Chatbot Registration
- `index.html` appointment form now includes **Preferred Date** (`<input type="date">`) before the time field
- Previously only Preferred Time was available — patients can now specify both date and time

#### 🏷️ Branding: SRP AI Labs
- Footer changed from `© SRP Technologies` → `© SRP AI Labs` across all 6 HTML dashboards: `admin_dashboard.html`, `doctor_dashboard.html`, `index.html`, `lab_dashboard.html`, `nurse_dashboard.html`, `stock_dashboard.html`

#### 🗄️ Demo / Seed Records
- New seed data for fresh deployments (idempotent — safe to re-run):
  - **IPD admission**: Narsimha Reddy, General Ward B-12, Typhoid Fever
  - **Surgery**: Lakshmi Devi, Appendectomy by Dr. B. Ramachandra Nayak, Scheduled
  - **Pharmacy**: 4 medicines (Paracetamol, Cetirizine, Metformin, Amoxicillin) with stock batches
  - **Lab**: 1 COMPLETED CBC report + 1 PENDING X-Ray
  - **Billing**: 2 bills (OPD ₹1550 net, IPD ₹17500 net)
  - **Notification settings**: Telegram token + chat ID pre-loaded in key-value format

#### 🔧 DB Schema Corrections
- Server routes now use correct table names: `surgery_records` (not `surgeries`), `pharmacy_stock` (not `medicine_inventory`), `billing` (not `invoices`)
- `notification_settings` saves/reads correctly using key-value row format: `(tenant_slug, setting_key, setting_value, is_encrypted)`

---

### v6.2 — Dashboard Fix · Per-Client Chatbot URLs · Telegram on Registration (March 2026)

#### 🐛 Critical Bug Fixes — Admin Dashboard Data Loading
- **`registrations` table empty → dashboard showed "Loading..." / "No patients yet"** — Fixed `get_all_registrations()` in `db.py` to use a fall-through cascade: `registrations` → `patient_visits` (with OP tickets) → `op_tickets` → `patients` table directly; data now always loads
- **`p.age` UndefinedColumn error** — `patients` table stores `dob` not `age`; fixed fallback SQL to use `EXTRACT(YEAR FROM AGE(COALESCE(p.dob, CURRENT_DATE)))::INTEGER AS age`
- **Doctors count showed 0** — `get_doctors_on_duty()` filtered to `on_duty=True` only (all doctors had `on_duty=False`); changed to `get_all_doctors()` so dashboard always shows all doctors
- **`GET /api/appointments` → 404** — route only existed as `/api/appointments/list`; added alias so both paths work

#### 🤖 Per-Client Chatbot URLs (Mobile-Friendly)
- **`GET /chat/{hospital_slug}`** — new route serving `index.html` with `window.TENANT_SLUG = "{slug}"` injected; every client gets a unique shareable chatbot link (e.g. `/chat/star_hospital`)
- **`GET /chat`** — generic chatbot without tenant context
- **`index.html` branding fix** — `applyHospitalBranding()` now reads `window.TENANT_SLUG` (or `?tenant=` URL param) and passes it to `/api/config?tenant=SLUG` so the correct hospital name/logo loads immediately on the chatbot page
- **`GET /api/config?tenant=SLUG`** — accepts optional `tenant` query param to return branding config for any hospital without requiring session login

#### 📲 Telegram Notifications Wired to Reception
- **`POST /api/patients/register` now fires Telegram** — `notify_new_registration()` called after every successful reception-side registration (was previously only on chatbot self-registration)
- Staff/admin receive instant Telegram alert: patient name, phone, chief complaint, assigned doctor

#### 🔌 New Endpoints
- **`GET /api/hospital/config`** — public endpoint returning hospital name, logo, contact, doctors list (suitable for patient-facing pages without auth)

#### ✅ E2E Test Suite — 29/29 PASS
- Full test file: `_e2e_test_v62.py`
- Covers: Config API, per-client chatbot injection, admin login, dashboard counts, appointments alias, doctors list, reception register, visit create, prescription create, PDF download (%PDF binary verified), patient timeline, visits list, admin stats

---

### v6.1 — Patient Timeline · Full DB Provisioning · Function Aliases (March 2026)

#### 📋 Patient History Timeline (New Feature)
- **One-screen patient history** — doctors can view a patient's complete medical story in a single page: demographics, all visits, all prescriptions with medicines, lab orders, vitals chart, billing history
- **`GET /api/patient/{id}/timeline`** — returns `{patient, visits, prescriptions(+medicines), lab_orders, vitals, bills, summary}`
- **`summary` object** — `total_visits`, `total_prescriptions`, `total_lab_orders`, `follow_up_pending`
- **Doctor dashboard** — Patient History section now has tabbed timeline view (Visits | Prescriptions | Lab | Vitals | Bills), patient search with filter, "📋 Timeline" button on each visit row

#### 🏥 Visit Management API
- **`POST /api/visit/create`** — creates OPD/IPD/ER visit ticket; returns `{visit_id, ticket_no, visit_date, ...}`
- **`GET /api/visits?patient_id=&doctor_username=&date_from=&limit=`** — list visits with filtering
- **`GET /api/visit/{id}`** — visit detail with latest prescription + medicines JSON
- **`POST /api/ipd/admit`** — admit patient to IPD (creates `patient_admissions` record)
- **`POST /api/ipd/discharge`** — discharge IPD patient + create discharge summary

#### 🔧 Missing Function Aliases Fixed
Added to `hms_db.py` (were referenced by server routes but didn't exist):
- `create_visit(data)` — OPD/IPD/ER visit record + OP ticket
- `list_visits(patient_id, doctor_username, date_from, limit)` — paged visit list
- `get_visit_with_prescription(visit_id)` — visit + prescription + medicines
- `get_patient_timeline(patient_id)` — complete patient history
- `search_patients(query, field)` — alias for `search_patients_comprehensive`
- `create_lab_order(data)` — alias for `order_lab_test`
- `update_lab_result(data)` — alias for `record_lab_result`
- `admit_patient(data)` — IPD admission
- `discharge_patient(data)` — IPD discharge + summary
- `create_bill(data)` — wraps `create_invoice`
- `get_bill_detail(bill_id)` — wraps `get_invoice`

#### 🗄️ Full Database Provisioning
- **All 5 tenant DBs now provisioned** — previously `srp_sai_care`, `srp_city_medical`, `srp_apollo_warangal`, `srp_green_cross` had only notification tables; now ALL have the complete HMS schema
- **`_provision_all_tenants.py`** — runs `psql -f srp_mediflow_schema.sql` + inline `SAFE_EXTRAS` SQL for all tenants
- **`srp_mediflow_schema.sql` fixes** — corrected FK ordering for `discharge_summaries` (billing FK was defined before billing table), fixed port comment `5434→5432`

#### 🐛 Bug Fixes
- **Server prescription handler** — normalises `medicines` key → `medicines_list` before DB call (was throwing `ProgrammingError: can't adapt type 'dict'`)

#### 📝 Provisioning
```bash
# Re-run any time to apply latest schema to all tenant DBs (idempotent)
python _provision_all_tenants.py
```

---

### v6.0 — Digital Prescriptions · Notifications · Responsive UI (March 11, 2026)

#### 💊 Digital Prescription System
- **Replaced half-handwritten prescriptions** — full structured digital form (vitals, medicines, lab orders, advice, follow-up)
- **`POST /api/doctor/prescription/create`** — saves prescription + medicines + lab orders atomically; returns `prescription_id`
- **`GET /api/pdf/rx/{prescription_id}`** — generates branded A4 PDF via ReportLab (hospital letterhead, medicine table, lab orders, QR-ready)
- **`GET /api/doctor/prescription/visit/{visit_id}`** — fetches full prescription JSON for a visit
- **`GET /api/medicines/search?q=X`** — autocomplete for medicine names
- **`GET /api/lab/tests/list`** — returns available lab test catalogue
- **Doctor dashboard** — new prescription section with: patient lookup bar, 5-field vitals grid (BP/Temp/Pulse/SpO₂/Weight), medicine rows with quick frequency/duration/route chips, lab order rows with urgency selector, advice/follow-up area, Save + Print PDF buttons
- **Quick-add chips** — Paracetamol, Cetirizine, Azithromycin, Inj.PCM, Syp.Amox, Pantoprazole, Metronidazole; lab: CBP, CRP, RFT, LFT, Electrolytes, Malaria, Dengue, CXR
- **DB migration** — `migration_v3_digital_rx.sql`: adds `chief_complaint`, `bp`, `pulse`, `spo2`, `follow_up_days` to `prescriptions` table; creates `prescription_medicines`, `notification_settings`, `notification_logs`, `notification_templates` tables

#### 🔔 Notification System
- **`notifications/`** package — `base_provider.py`, `telegram_provider.py`, `whatsapp_provider.py`, `service.py`
- **Telegram-first**: all events (prescription created, lab result ready, appointment reminder) → Telegram bot; WhatsApp framework ready (stub provider)
- **`POST /api/settings/notifications`** — save provider credentials (ADMIN/FOUNDER); allowed keys whitelisted server-side
- **`GET /api/settings/notifications`** — load current provider config
- **`POST /api/settings/notifications/test`** — fire a test message via configured channel
- **Doctor + Admin dashboards** now have `🔔 Notifications` section for provider configuration
- Credentials stored per-tenant in `notification_settings` DB table (never in flat files)

#### 📊 Admin Dashboard Enhancements
- **`GET /api/admin/dashboard/stats`** — live KPI: `today_opd`, `today_ipd`, `today_collections` (₹), `pending_bills`, `lab_pending`, `followup_today`, `notifications_today`
- **`GET /api/admin/activity`** — recent activity feed (last 20 events with type + actor + timestamp)
- 7 enhanced stat cards auto-refresh every 3 minutes
- Activity feed with icon-coded event types (💊 prescription, 🔬 lab, 👤 admission, 🔔 notification)

#### 📱 Responsive UI
- `srp_mediflow_responsive.css` — mobile-first breakpoints for all dashboards
- Prescription form collapses to single column on ≤768 px
- Sidebars collapse to icon-only mode on ≤600 px

#### 🐛 Bug Fixes
- **`db.py`**: Fixed default `PG_PORT` from `5434` → `5432` — DB connections were failing on fresh installs

#### 🗄️ Running the Migration
```bash
# Connect to PostgreSQL (all tenant DBs that have the prescriptions table)
psql -U ats_user -d hospital_ai -f migration_v3_digital_rx.sql
# Repeat for each tenant DB that has HMS schema installed
```

#### 🔑 Environment Variables (new/updated)
| Variable | Default | Notes |
|----------|---------|-------|
| `PG_PORT` | `5432` | Was previously defaulting to 5434 — fix required |
| `TELEGRAM_BOT_TOKEN` | — | Set in notification_settings table per tenant |
| `TELEGRAM_CHAT_ID` | — | Set in notification_settings table per tenant |

---

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

*SRP MediFlow v6.3 · Built for Indian hospitals · Powered by SRP AI Labs*
