# 🏥 SRP MediFlow — AI-Powered Multi-Tenant Hospital Management SaaS

> **Production-ready SaaS platform. Every hospital gets its own AI chatbot, dedicated PostgreSQL database, billing, lab, pharmacy, and staff portals — fully isolated.**

**Version:** `4.0` | **Updated:** March 2026
**Port:** `7500` | **Stack:** Python 3.14 · PostgreSQL · Vanilla JS · HTML5

[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Tenants](https://img.shields.io/badge/live%20hospitals-5-blue)]()
[![Isolation](https://img.shields.io/badge/DB%20isolation-100%25-success)]()

---

## 🚀 Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL (port 5432)

# 3. Run the server
python srp_mediflow_server.py
```

Server starts at **http://localhost:7500**

---

## 🌐 Platform URLs

| URL | Description |
|-----|-------------|
| `http://localhost:7500/` | Marketing landing page |
| `http://localhost:7500/hospital_signup` | Register new hospital (creates isolated DB) |
| `http://localhost:7500/login` | Staff login page |
| `http://localhost:7500/ping` | Health check → `{"status":"ok"}` |
| `http://localhost:7500/api/platform/stats` | Platform stats (active hospitals, version) |
| `http://localhost:7500/founder` | Founder SaaS analytics dashboard |

### Live Hospital Chatbots

| Hospital | Chatbot URL | Admin Login |
|----------|-------------|-------------|
| ⭐ Star Hospital | `/chat/star_hospital` | `star_hospital_admin` / `Star@Admin2026!` |
| 🏥 Sai Care Hospital | `/chat/sai_care` | `sai_care_admin` / `SaiCare@Admin2026!` |
| 🏥 City Medical Centre | `/chat/city_medical` | `city_medical_admin` / `CityMed@Admin2026!` |
| 🏥 Apollo Clinic Warangal | `/chat/apollo_warangal` | `apollo_warangal_admin` / `Apollo@Admin2026!` |
| 🏥 Green Cross Hospital | `/chat/green_cross` | `green_cross_admin` / `GreenCross@Admin2026!` |

> **Change all passwords on first login in production.**

---

## 🏗️ Architecture

```
                ┌─────────────────────────────────┐
                │    SRP MediFlow Server (7500)    │
                │    srp_mediflow_server.py        │
                └────────┬─────────────┬───────────┘
                         │             │
              ┌──────────▼──┐   ┌──────▼──────────┐
              │  Platform DB │   │  Tenant Router  │
              │  (platform_  │   │  (per-request   │
              │   db.py)     │   │   thread-local) │
              └──────────────┘   └──────┬──────────┘
                                        │
          ┌─────────────────────────────┼──────────────────┐
          │              │              │            │      │
    ┌─────▼────┐  ┌──────▼───┐  ┌──────▼───┐  ┌────▼────┐ ...
    │hospital_ │  │srp_sai_  │  │srp_city_ │  │srp_apol │
    │ai (star) │  │care      │  │medical   │  │lo_waran │
    └──────────┘  └──────────┘  └──────────┘  └─────────┘
```

**Each tenant has:**
- Separate PostgreSQL database
- Own branding (name, address, logo, phone)
- Own doctor roster
- Own patients, appointments, billing, lab records
- Own Telegram bot configuration
- Own staff accounts with role-based access

---

## 🧩 Platform Features

| Module | Description |
|--------|-------------|
| **AI Chatbot** | Multi-language (English/Telugu/Hindi), books appointments, registers OPD patients |
| **Patient Management** | UHID, OPD/IPD, visit history, discharge summaries |
| **Digital Prescriptions** | Doctor writes e-Rx → PDF → pharmacy link |
| **Lab Management** | Orders, results, Telegram notification to patient |
| **Billing** | Itemised bills, payment tracking, PDF receipts |
| **Pharmacy & Inventory** | Stock management, expiry alerts, dispensing |
| **Telegram Notifications** | Per-hospital bot — staff group alerts + individual patient updates |
| **Doctor Rounds** | Ward notes, daily rounds, ICU tracking |
| **Role-Based Access** | Admin, Doctor, Nurse, Lab, Pharmacist, Reception |
| **Founder Dashboard** | SaaS analytics, client health, revenue, upgrades |
| **PDF Reports** | OPD/IPD daily, financial, prescriptions |

---

## 👥 Staff Roles & Dashboards

| Role | Dashboard | Key Functions |
|------|-----------|---------------|
| **Admin** | `admin_dashboard.html` | Staff management, settings, billing, Telegram config |
| **Doctor** | `doctor_dashboard.html` | Patients, prescriptions, rounds, lab orders |
| **Nurse** | `nurse_dashboard.html` | Vitals, beds, patient monitoring |
| **Lab Tech** | `lab_dashboard.html` | Lab orders, test results, reports |
| **Pharmacist** | *(inline)* | Medicine dispensing, stock |
| **Reception** | *(inline)* | Registration, appointments, billing |

---

## 📱 Telegram Notifications Setup

### Staff Group Alerts
1. Create bot via **@BotFather** → save the **Bot Token**
2. Create a staff Telegram group → add bot → make it admin
3. Get **Chat ID** (negative number):
   ```
   https://api.telegram.org/bot{TOKEN}/getUpdates
   Look for "chat":{"id":-1001234567890}
   ```
4. In Admin → Notifications → paste **Bot Token + Chat ID** → Save

### Patient Notifications
- Display your bot username (e.g. `@starhospital_bot`) at reception
- Patient sends `/start` to the bot → system captures their Chat ID automatically
- All future appointment, lab, and billing notifications go directly to them

> **Both Bot Token AND Chat ID are required** for staff alerts to work.

---

## 🔒 Security

- bcrypt password hashing (salt rounds = 12)
- Session token authentication (UUID, per-request validation)
- Mandatory password change on first login
- Full audit log of all actions
- Tenant DB isolation — queries never cross tenant boundaries
- Rate limiting per IP
- No cross-tenant data leakage (verified: 26/26 isolation tests)

---

## 🗄️ Database Setup

### Platform DB
```sql
-- Run once for the platform
\i srp_platform_schema.sql
```

### Tenant DB (auto-created on signup)
```sql
-- Each hospital gets its own DB via saas_onboarding.py
-- Schema: srp_mediflow_schema_hms.sql
```

### Manual tenant provisioning
```bash
python _provision_all_tenants.py
```

### Seed demo data
```bash
python _seed_demo_records.py
```

---

## ✅ E2E Test Results (March 2026)

### Chatbot Load Test (all 5 hospitals)
| Hospital | CSS Loaded | JS Loaded | TENANT_SLUG | Status |
|----------|-----------|-----------|-------------|--------|
| star_hospital | ✅ | ✅ | ✅ | PASS |
| sai_care | ✅ | ✅ | ✅ | PASS |
| city_medical | ✅ | ✅ | ✅ | PASS |
| apollo_warangal | ✅ | ✅ | ✅ | PASS |
| green_cross | ✅ | ✅ | ✅ | PASS |

### Tenant Config & DB Isolation
| Tenant | Hospital Name | City | Doctors | Status |
|--------|--------------|------|---------|--------|
| star_hospital | Star Hospital | Khammam | 3 | ✅ |
| sai_care | Sai Care Hospital | Khammam | 4 | ✅ |
| city_medical | City Medical Centre | Hyderabad | 4 | ✅ |
| apollo_warangal | Apollo Clinic Warangal | Warangal | 4 | ✅ |
| green_cross | Green Cross Hospital | Vijayawada | 4 | ✅ |

### Login Test (all 5 admins)
| Tenant | Role | Hospital Name | Status |
|--------|------|--------------|--------|
| star_hospital | ADMIN | Star Hospital | ✅ |
| sai_care | ADMIN | Sai Care Hospital | ✅ |
| city_medical | ADMIN | City Medical Centre | ✅ |
| apollo_warangal | ADMIN | Apollo Clinic Warangal | ✅ |
| green_cross | ADMIN | Green Cross Hospital | ✅ |

### Chat + DB Isolation Test
- **Star Hospital** chat → recommends Dr. K. Ramyanadh (its own DB) ✅
- **Sai Care** chat → shows Dr. Kiran Babu, Dr. Radha Menon, Dr. Suresh Nair, Dr. Asha Kumari (different DB) ✅
- **Zero cross-tenant data leakage confirmed** ✅

---

## 📁 Key Files

| File | Role |
|------|------|
| `srp_mediflow_server.py` | Main HTTP server, all routing and API handlers |
| `hms_db.py` | Hospital database queries (tenant-aware) |
| `platform_db.py` | Platform-level DB (client registry, billing) |
| `auth.py` | Authentication, session management |
| `chatbot.py` | AI chat logic, appointment booking |
| `saas_onboarding.py` | Auto-provisions new hospital DB on signup |
| `saas_billing.py` | Platform billing, plan management |
| `saas_analytics.py` | Founder analytics and reporting |
| `pdf_generator.py` | Prescriptions, bills, reports as PDF |
| `index.html` | Patient-facing chatbot UI |
| `platform_landing.html` | Public marketing landing page |
| `hospital_signup.html` | Hospital registration form |
| `admin_dashboard.html` | Admin portal |
| `doctor_dashboard.html` | Doctor portal |
| `srp_mediflow_schema_hms.sql` | Per-tenant database schema |
| `srp_platform_schema.sql` | Platform database schema |

---

## 🚢 Deployment (Hetzner VPS)

See [HETZNER_DEPLOY.md](HETZNER_DEPLOY.md) for full VPS deployment guide.

### Quick deploy steps
```bash
# On server:
git pull origin main
pip install -r requirements.txt
python srp_mediflow_server.py &

# Configure Nginx reverse proxy for port 7500
# Set up Cloudflare wildcard DNS: *.mediflow.srpailabs.com → server IP
# Each hospital gets: hospitalname.mediflow.srpailabs.com
```

### Environment variables (.env)
```
PG_HOST=localhost
PG_PORT=5432
PG_USER=ats_user
PG_PASSWORD=ats_password
PLATFORM_DB=srp_platform
```

---

## 📝 Changelog

### v4.0 (March 2026)
- ✅ New comprehensive marketing landing page (`platform_landing.html`)
- ✅ Fixed chatbot routing: `/chat/{slug}` properly serves tenant chatbot with CSS/JS
- ✅ Fixed asset paths: `style.css` and `script.js` now use absolute paths — no more unstyled pages
- ✅ Added `/ping` and `/health` JSON endpoints
- ✅ Registration flow: signup buttons → `hospital_signup.html` → auto-provision DB → show credentials
- ✅ Added 24/7 chatbot uptime to Professional plan
- ✅ Platform root routing: `/` → landing, `/?tenant=slug` → chatbot, `/chat/slug` → chatbot
- ✅ All 5 tenant admin logins verified
- ✅ Full DB isolation confirmed across all tenants
- ✅ 26/26 cross-tenant isolation tests passing

### v3.x (February 2026)
- Multi-tenant architecture implementation
- Telegram notification system per hospital
- Digital prescriptions module
- Lab management module
- PDF report generation

---

## 📄 License

See [LICENSE](LICENSE) for details.

---

*Built with ❤️ in Telangana, India · SRP AI Labs · 2026*
