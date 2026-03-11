# 🏥 SRP MediFlow — AI-Powered Multi-Tenant Hospital Management SaaS

> **Production-ready SaaS platform. Every hospital gets its own AI chatbot, dedicated PostgreSQL database, billing, lab, pharmacy, and staff portals — fully isolated.**

**Version:** `6.1` | **Updated:** March 2026
**Port:** `7500` | **Stack:** Python 3.14 · PostgreSQL · Vanilla JS · HTML5

[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Tenants](https://img.shields.io/badge/live%20hospitals-5-blue)]()
[![Phase](https://img.shields.io/badge/phase-6.1%20Mobile%20Rx%20Assist-purple)]()

---

## ✨ Phase 6.1 Highlights (March 2026)

| Feature | Status |
|---------|--------|
| 🎤 Voice-to-text on prescription fields (en-IN / hi-IN / te-IN) | ✅ Live |
| 📋 Save Draft (localStorage, resume anytime) | ✅ Live |
| 🕐 Staff self check-in / check-out (no admin needed) | ✅ Live |
| ✈️ Telegram notification on prescription save | ✅ Live |
| 📱 Mobile sticky prescription action bar | ✅ Live |
| 🔔 Toast-based feedback for all key actions | ✅ Live |
| 💬 WhatsApp prescription send | ⏳ Coming Soon |

### Staff Attendance — No Admin Required

Any logged-in staff (doctors, nurses, reception) can check in/out from their own dashboard:
- Doctor Dashboard → **🕐 My Attendance**
- Sends Telegram alert on check-in
- APIs: `POST /api/staff/self-checkin`, `POST /api/staff/self-checkout`, `GET /api/staff/self-status`

### Voice Prescription Assist

Tap the 🎤 mic button next to any prescription field to dictate.  
Doctor can always edit the transcript before saving. Falls back silently to manual typing.

> Voice uses browser Web Speech API — works best in Chrome / Edge.

### WhatsApp Future Activation

To activate WhatsApp prescription sending later:
1. Configure `WHATSAPP_API_BASE_URL`, `WHATSAPP_API_KEY`, `WHATSAPP_SENDER_NUMBER` in `.env`
2. Enable in Admin → Notification Settings → Active Channel = WhatsApp
3. The "Coming Soon" button on doctor dashboard will auto-enable

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
| **Digital Prescriptions** | Doctor writes e-Rx → PDF → pharmacy link · Draft auto-save |
| **🎤 Voice Prescription Assist** | Dictate into any Rx field using mic button (en-IN/hi-IN/te-IN) · **NEW v6.1** |
| **Lab Management** | Orders, results, Telegram notification to patient |
| **Billing** | Itemised bills, payment tracking, PDF receipts |
| **Pharmacy & Inventory** | Stock management, expiry alerts, dispensing |
| **Per-Hospital Telegram Bot** | Each hospital uses its own bot — all events auto-routed, never mixed across hospitals |
| **🕐 Staff Self Check-In/Out** | Any staff checks in from their own dashboard — no admin needed · **NEW v6.1** |
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

## 📱 Telegram Notifications — Complete Guide

### How It Works (Multi-Tenant, Fully Automatic)

Every hospital in SRP MediFlow has **its own Telegram bot**. When any event happens (patient registers, prescription saved, staff checks in, IPD admission, low stock), the system automatically looks up **that hospital's Telegram credentials** and sends the alert to that hospital's own staff channel — never to another hospital's channel.

> **New hospitals added in the future are automatically supported** — they just need to add their Bot Token and Chat ID in Admin → Notifications.

---

### What Telegram Is Used FOR in SRP MediFlow

| Event | Who Gets Notified | Channel |
|-------|------------------|---------|
| New OPD patient registered (chatbot or reception) | Hospital staff group | Hospital's own bot |
| Appointment booked | Hospital staff group | Hospital's own bot |
| Prescription saved by doctor | Hospital staff group | Hospital's own bot |
| IPD patient admitted | Hospital staff group | Hospital's own bot |
| IPD patient discharged | Hospital staff group | Hospital's own bot |
| Surgery scheduled | Hospital staff group | Hospital's own bot |
| Staff self check-in / check-out | Hospital admin + staff | Hospital's own bot |
| Low stock alert | Hospital admin | Hospital's own bot |
| Medicine expiry alert | Hospital admin | Hospital's own bot |
| Daily summary | Hospital admin | Hospital's own bot |
| New hospital registered | Platform founder only | Founder's private bot |
| Server start / crash | Platform founder only | Founder's alert bot |

---

### What Telegram Is NOT Used For

- ❌ Booking appointments (that is done via the AI chatbot at `/chat/{hospital_slug}`)
- ❌ Patient login or registration
- ❌ Viewing prescriptions or lab reports (those are on the staff dashboards)
- ❌ Admin controls (use the Admin Dashboard at `/login`)

---

### Setup for Each Hospital (Admin does this once)

**Step 1 — Create a Telegram bot for your hospital**
```
1. Open Telegram → search @BotFather
2. Send /newbot
3. Enter a name: "Star Hospital Alerts"
4. Enter a username: starhospital_bot
5. Copy the bot token:  7123456789:AABBccDDeeFF...
```

**Step 2 — Create a staff group and add the bot**
```
1. Create a Telegram group: "Star Hospital Staff"
2. Add @starhospital_bot to the group
3. Make the bot an Admin (so it can send messages)
```

**Step 3 — Get the Chat ID of the staff group**
```
Open this URL in browser (replace TOKEN with your bot token):
https://api.telegram.org/botTOKEN/getUpdates

Look for: "chat":{"id":-1001234567890}
The negative number starting with -100 is your Chat ID.
```

**Step 4 — Save credentials in Admin Dashboard**
```
Login → Admin → Settings → Notifications
Paste: Bot Token  → 7123456789:AABBccDDeeFF...
Paste: Chat ID    → -1001234567890
Click: Save All Settings
```

Done. All events for that hospital now automatically go to that hospital's own Telegram channel.

---

### Doctor/Staff View on Telegram

As a doctor (or any staff), you are a **member of the hospital's Telegram staff group**. You will see:

```
🏥 STAR HOSPITAL
💊 PRESCRIPTION SAVED
──────────────────────
👤 Patient: Ravi Kumar
📞 Phone: +91 9876543210
👨‍⚕️ Doctor: Dr. Srujan
🆔 Rx ID: RX-20260311-001
──────────────────────
⏰ 11 Mar 2026 10:45 AM
📍 Kothagudem   📞 +91 7981971015

🏥 STAR HOSPITAL
🟢 STAFF CHECK-IN
──────────────────────
👤 Staff: Dr. Srujan
👔 Role: Doctor
──────────────────────
⏰ 11 Mar 2026 09:01 AM
```

You do **not** need to interact with the bot — it only sends messages to the group, you just read them.

---

### APIs for Telegram (Server Side)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/telegram/send` | POST | ADMIN | Send custom message via hospital bot |
| `/api/settings/notifications` | POST | ADMIN | Save bot token + chat_id |
| `/api/settings/notifications` | GET | ADMIN | Read current settings |

```bash
# Test your Telegram setup
curl -X POST http://localhost:7500/api/telegram/send \
  -H "Cookie: session_token=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{"message": "Test from SRP MediFlow"}'
```

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

- **All API keys in `.env` only** — never hardcoded in source code
- bcrypt password hashing (rounds = 12)
- Session token authentication (64-char hex, DB-persisted)
- Mandatory password change on first login
- Full audit log of all actions
- Tenant DB isolation — queries never cross tenant boundaries
- Rate limiting per IP on all auth endpoints
- Brute-force lockout (3 failed attempts → 15 min, DB-persisted across restarts)
- No internal error details leak to API clients — all exceptions sanitised
- Security HTTP headers on every response: `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`, `CSP`
- CORS locked-down — unknown origins return `null`, not `*`
- Session cookies: `HttpOnly; SameSite=Lax; Path=/`
- No cross-tenant data leakage (verified: 26/26 isolation tests)

### API Keys & Secrets — Checklist

| Secret | Where to configure | Risk if exposed |
|--------|-------------------|-----------------|
| `OPENAI_API_KEY` | `.env` | Billing charges on your OpenAI account |
| `TELEGRAM_BOT_TOKEN` | `.env` | Anyone can send messages as your bot |
| `TELEGRAM_CHAT_ID` | `.env` | Low risk alone, but protects privacy |
| `FOUNDER_CHAT_ID` | `.env` | Your personal Telegram ID |
| `WHATSAPP_API_KEY` | `.env` | SMS/WhatsApp charges on your Meta account |
| `WHATSAPP_WEBHOOK_SECRET` | `.env` | Allows fake webhook payloads |
| `NGROK_AUTH_TOKEN` | `.env` | Tunnel abuse on your ngrok account |
| `PG_PASSWORD` | `.env` | Full database access |
| `credentials.json` | gitignored | Full Google Cloud access |

> **Never put any of the above in source code.** Use `.env.example` as a template — it has no real values.

### Setup
```bash
cp .env.example .env
# Edit .env with your real values
```

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
python saas_onboarding.py --provision-all
```

### Seed demo data
```bash
python saas_onboarding.py --seed-demo
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

### Environment variables (`.env`)
```bash
# Copy template and fill in real values
cp .env.example .env
```

Key variables (see `.env.example` for full list):
```
PG_HOST=localhost
PG_PORT=5432
PG_USER=ats_user
PG_PASSWORD=your_db_password
PLATFORM_DB_NAME=srp_platform_db
APP_URL=https://mediflow.srpailabs.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_staff_group_chat_id
FOUNDER_CHAT_ID=your_personal_telegram_chat_id
OPENAI_API_KEY=your_openai_key
WHATSAPP_API_KEY=your_whatsapp_bearer_token
WHATSAPP_WEBHOOK_SECRET=your_strong_random_secret
```

---

## 📝 Changelog

### v6.1 (March 2026) — Phase 6.1: Mobile Rx Assist + Per-Tenant Telegram
- ✅ **Per-tenant Telegram routing** — every hospital's events go to their own bot, never mixed. Auto-works for all current and future hospitals
- ✅ **Voice-to-text on prescription** — 🎤 mic button on every field (complaint, diagnosis, symptoms, notes, diet, instructions). en-IN/hi-IN/te-IN
- ✅ **Save Draft to localStorage** — auto-restore on page load, never lose partial Rx
- ✅ **Mobile sticky action bar** — Save Draft · Save Final · PDF · Telegram Notify · WhatsApp (Coming Soon)
- ✅ **Toast notification system** — instant feedback for all key actions
- ✅ **Staff self check-in/out** — any logged-in staff from their own dashboard, no admin needed
- ✅ **👨‍⚕️ My Attendance panel** — doctor dashboard section with live clock, check-in/out, today's table
- ✅ **Telegram: prescription saved** — fires to hospital bot after every Rx save
- ✅ **Telegram: staff check-in/out** — fires to hospital bot when any staff self-checks
- ✅ **DB migration** — `username` and `role` columns added to `attendance` table, deployed to production
- ✅ **Landing page updated** — v6.1 badge, 2 new feature cards, updated stats, updated marquee

### v5.0 (March 2026)
- ✅ **Security hardening**: sanitised all 14 API error responses — no internal details leak to clients
- ✅ **Security headers**: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection`, `CSP`, `Referrer-Policy` on every response
- ✅ **CORS locked down**: unknown origins blocked (`null`), never wildcard `*`
- ✅ **All API keys in `.env`**: removed hardcoded Telegram token, ngrok token, WhatsApp secret
- ✅ **Brute-force lockout DB-persisted**: survives server restarts (stored in `auth_lockouts` table)
- ✅ **Session cookies**: `HttpOnly; SameSite=Lax` on all login responses
- ✅ **Codebase cleanup**: removed all 38 debug `_*.py` scripts and 25 `srv*.txt` log files
- ✅ **Founder dashboard**: DB isolation test, all-clients view, system-status health check fully working

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
