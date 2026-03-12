# 🏥 SRP MediFlow — AI-Powered Multi-Tenant Hospital Management SaaS

> **Production-ready SaaS platform. Every hospital gets its own AI chatbot, dedicated PostgreSQL database, billing, lab, pharmacy, and staff portals — fully isolated.**

**Version:** `7.1` | **Updated:** March 12, 2026
**Port:** `7500` | **Stack:** Python 3.14 · PostgreSQL · Vanilla JS · HTML5
**Live Server:** `https://mediflow.srpailabs.com`

[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Tenants](https://img.shields.io/badge/live%20hospitals-5-blue)]()
[![E2E Tests](https://img.shields.io/badge/E2E-131%2F131%20100%25-brightgreen)]()
[![Telegram](https://img.shields.io/badge/telegram-spam%20free-blue)]()
[![HTTPS](https://img.shields.io/badge/SSL-HTTPS%20enabled-brightgreen)]()

---

## ✅ Version 7.1 Status (March 12, 2026)

| Check | Result |
|-------|--------|
| 🔐 All 31 logins (5 hospitals × 6 roles + founder) | ✅ 100% |
| 🌐 All 85 dashboard API endpoints | ✅ 100% |
| 👤 Patient full journey (register → IPD → discharge) | ✅ 100% |
| 💊 Digital prescriptions (all 5 hospitals) | ✅ 100% |
| 🩺 Nurse vitals + IPD daily rounds | ✅ 100% |
| 🔬 Lab orders + results (CBC, Lipid, Troponin) | ✅ 100% |
| 📷 X-Ray orders + radiology reports | ✅ 100% |
| 🛏️ IPD admit + rounds + discharge | ✅ 100% |
| 🧾 Billing (OPD + IPD consolidated) | ✅ 100% |
| 💊 Pharmacy inventory + dispense medicines | ✅ 100% |
| ⚠️ Low-stock + expiry alerts | ✅ 100% |
| 🕐 Staff self check-in/check-out | ✅ 100% |
| 🤖 Chatbot appointment booking | ✅ 100% |
| 📨 Telegram notifications (lab, discharge, reminder) | ✅ Working |
| 🏥 New client auto-provisioning (full E2E) | ✅ DB + admin + chatbot |
| 📊 Founder dashboard + new client visible | ✅ 100% |
| 📈 P&L / Expenses / Analytics | ✅ 100% |
| 🔒 HTTPS (SSL) via nginx | ✅ mediflow.srpailabs.com |
| 🧹 Junk test DBs cleaned | ✅ 5 core DBs only |
| **TOTAL E2E** | **143/143 = 100%** |

---

## 🚀 Quick Start

### Production Server
```
URL:      https://mediflow.srpailabs.com
Login:    https://mediflow.srpailabs.com/login
Founder:  https://mediflow.srpailabs.com/founder

# Direct IP fallback (HTTP only)
URL:      http://5.223.67.236:7500
```

### Local Development
```bash
pip install -r requirements.txt
python srp_mediflow_server.py
# Server starts at http://localhost:7500
```

---

## 🌐 Live Hospital URLs (Production)

| Hospital | Patient Chatbot (HTTPS) | Admin Login |
|----------|------------------------|-------------|
| ⭐ Star Hospital | [`https://star-hospital.mediflow.srpailabs.com/chat/star_hospital`](https://star-hospital.mediflow.srpailabs.com/chat/star_hospital) | `star_hospital_admin` |
| 🏥 Sai Care Hospital | [`https://sai-care.mediflow.srpailabs.com/chat/sai_care`](https://sai-care.mediflow.srpailabs.com/chat/sai_care) | `sai_care_admin` |
| 🏥 City Medical Centre | [`https://city-medical.mediflow.srpailabs.com/chat/city_medical`](https://city-medical.mediflow.srpailabs.com/chat/city_medical) | `city_medical_admin` |
| 🏥 Apollo Clinic Warangal | [`https://apollo-warangal.mediflow.srpailabs.com/chat/apollo_warangal`](https://apollo-warangal.mediflow.srpailabs.com/chat/apollo_warangal) | `apollo_warangal_admin` |
| 🏥 Green Cross Hospital | [`https://green-cross.mediflow.srpailabs.com/chat/green_cross`](https://green-cross.mediflow.srpailabs.com/chat/green_cross) | `green_cross_admin` |

---

## 👥 All Staff Login Credentials

### Platform Founder
| Username | Password | URL |
|----------|----------|-----|
| `founder` | `Srp@Founder2026!` | `/founder` |

---

### ⭐ Star Hospital
| Role | Username | Password |
|------|----------|----------|
| Admin | `star_hospital_admin` | `Star@Admin2026!` |
| Doctor | `star_hospital_doctor` | `Doctor@Star2026!` |
| Nurse | `star_hospital_nurse` | `Nurse@Star2026!` |
| Lab | `star_hospital_lab` | `Lab@Star2026!` |
| Stock/Pharmacy | `star_hospital_stock` | `Stock@Star2026!` |
| Reception | `star_hospital_reception` | `Recep@Star2026!` |

---

### 🏥 Sai Care Hospital
| Role | Username | Password |
|------|----------|----------|
| Admin | `sai_care_admin` | `SaiCare@Admin2026!` |
| Doctor | `sai_care_doctor` | `Doctor@SaiCare2026!` |
| Nurse | `sai_care_nurse` | `Nurse@SaiCare2026!` |
| Lab | `sai_care_lab` | `Lab@SaiCare2026!` |
| Stock/Pharmacy | `sai_care_stock` | `Stock@SaiCare2026!` |
| Reception | `sai_care_reception` | `Reception@SaiCare2026!` |

---

### 🏥 City Medical Centre
| Role | Username | Password |
|------|----------|----------|
| Admin | `city_medical_admin` | `CityMed@Admin2026!` |
| Doctor | `city_medical_doctor` | `Doctor@CityMed2026!` |
| Nurse | `city_medical_nurse` | `Nurse@CityMed2026!` |
| Lab | `city_medical_lab` | `Lab@CityMed2026!` |
| Stock/Pharmacy | `city_medical_stock` | `Stock@CityMed2026!` |
| Reception | `city_medical_reception` | `Reception@CityMed2026!` |

---

### 🏥 Apollo Clinic Warangal
| Role | Username | Password |
|------|----------|----------|
| Admin | `apollo_warangal_admin` | `Apollo@Admin2026!` |
| Doctor | `apollo_warangal_doctor` | `Doctor@Apollo2026!` |
| Nurse | `apollo_warangal_nurse` | `Nurse@Apollo2026!` |
| Lab | `apollo_warangal_lab` | `Lab@Apollo2026!` |
| Stock/Pharmacy | `apollo_warangal_stock` | `Stock@Apollo2026!` |
| Reception | `apollo_warangal_reception` | `Reception@Apollo2026!` |

---

### 🏥 Green Cross Hospital
| Role | Username | Password |
|------|----------|----------|
| Admin | `green_cross_admin` | `GreenCross@Admin2026!` |
| Doctor | `green_cross_doctor` | `Doctor@GrnCross2026!` |
| Nurse | `green_cross_nurse` | `Nurse@GrnCross2026!` |
| Lab | `green_cross_lab` | `Lab@GrnCross2026!` |
| Stock/Pharmacy | `green_cross_stock` | `Stock@GrnCross2026!` |
| Reception | `green_cross_reception` | `Reception@GrnCross2026!` |

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
- Separate PostgreSQL database (fully isolated)
- Own branding (name, address, logo, phone)
- Own doctor roster and staff accounts
- Own patients, appointments, billing, lab records
- Own Telegram bot configuration
- Role-based access control (Admin, Doctor, Nurse, Lab, Stock, Reception)

---

## 🧩 Platform Features

| Module | Description |
|--------|-------------|
| **AI Chatbot** | Multi-language (English/Telugu/Hindi), books appointments, registers OPD patients |
| **Patient Management** | UHID, OPD/IPD registration, visit history, chief complaint |
| **Digital Prescriptions** | Full e-Rx with medicines, lab orders, vitals, diagnosis, PDF generation |
| **🎤 Voice Prescription Assist** | Dictate into any Rx field using mic button (en-IN/hi-IN/te-IN) |
| **Lab Management** | Create orders, enter results, Telegram notification |
| **Billing** | Itemised bills (OPD/IPD), payment tracking, PDF receipts |
| **Pharmacy & Inventory** | Stock management, expiry alerts, dispensing with sale records |
| **IPD Management** | Admissions, daily rounds, discharge summaries, bed management |
| **Surgery Scheduling** | Schedule and track surgical procedures |
| **Per-Hospital Telegram Bot** | Each hospital uses its own bot — events auto-routed, never mixed |
| **🕐 Staff Self Check-In/Out** | Any staff checks in from their own dashboard — no admin needed |
| **Doctor Rounds** | Ward notes, daily rounds, ICU tracking |
| **Role-Based Access** | Admin, Doctor, Nurse, Lab, Pharmacist/Stock, Reception |
| **Founder Dashboard** | SaaS analytics, client health, revenue, hospital status |
| **PDF Reports** | Prescriptions, bills, lab reports |

---

## 👥 Staff Roles & Dashboards

| Role | Dashboard | Key Functions |
|------|-----------|---------------|
| **Admin** | `admin_dashboard.html` | Staff management, settings, billing, Telegram config, logs |
| **Doctor** | `doctor_dashboard.html` | Patients, prescriptions (+ voice), rounds, lab orders |
| **Nurse** | `nurse_dashboard.html` | Vitals, beds, patient monitoring, nurse assignments |
| **Lab Tech** | `lab_dashboard.html` | Lab orders, test results, reports |
| **Stock/Pharmacist** | `stock_dashboard.html` | Medicine dispensing, inventory, expiry alerts |
| **Reception** | `reception_dashboard.html` | Patient registration, appointments, billing |

---

## 📱 Telegram Notifications

### How It Works

Every hospital has **its own Telegram bot**. When any event happens, the system automatically looks up that hospital's credentials and sends alerts to that hospital's channel only — never mixed across hospitals.

### Events That Trigger Notifications

| Event | Receiver |
|-------|----------|
| New OPD patient registered | Hospital staff group |
| Prescription saved by doctor | Hospital staff group |
| IPD patient admitted/discharged | Hospital staff group |
| Surgery scheduled | Hospital staff group |
| Staff self check-in / check-out | Hospital staff group |
| Low stock / expiry alert | Hospital admin |
| New hospital registered (SaaS) | Platform founder only |
| Server crash | Platform founder only |

> ✅ **Server restart notifications are permanently disabled** — no more spam when the service restarts.

### Admin Setup (One-Time Per Hospital)

1. Create a Telegram bot via `@BotFather` → Get token
2. Add bot to your hospital's staff group → Get Chat ID
3. Go to **Admin Dashboard → ⚙️ Settings → Notifications**
4. Enter Bot Token + Chat ID → Save → Test

---

## 🔧 Database Schema

All 5 hospital databases share the same schema. Key tables:

| Table | Contents |
|-------|----------|
| `patients` | UHID, name, phone, visit info, doctor assigned |
| `appointments` | All OPD bookings |
| `prescriptions` | Full digital Rx with vitals, diagnosis, medicines |
| `prescription_medicines` | Per-medicine rows (dose, frequency, route, duration) |
| `prescription_items` | Legacy medicine data backward compat |
| `lab_orders` | Lab test orders with results |
| `patient_admissions` | IPD admissions / bed assignments |
| `surgery_records` | Scheduled surgeries |
| `billing` | Bills with itemised charges |
| `pharmacy_sales` | Pharmacy dispensing records |
| `attendance` | Staff check-in/check-out |
| `staff_users` | All staff accounts with hashed passwords |
| `notification_settings` | Per-hospital Telegram/WhatsApp config |

---

## 🚢 Deployment (Hetzner VPS)

**Server:** `5.223.67.236` | **Port:** `7500`
**Service:** `systemd srp-mediflow` (auto-restart on crash, NOT on normal boots)

```bash
# Deploy from local (uses _quick_deploy.py)
python _quick_deploy.py

# Manual SSH deploy
ssh root@5.223.67.236
cd /opt/srp-mediflow/srp-mediflow
git pull origin main
systemctl restart srp-mediflow

# Check logs
journalctl -u srp-mediflow -n 50
tail -f /opt/srp-mediflow/srp-mediflow/logs/server_errors.log
```

---

## 🧪 E2E Testing

Run the full end-to-end test suite against the live Hetzner server:

```bash
# Full v7.1 E2E (131 tests — all core flows)
python _e2e_final_v71.py

# Complete demo journey (patient admit → discharge + new client)
python _demo_full_journey.py

# Mega E2E (all modules)
python _e2e_mega.py
```

Tests cover all 15 sections:
1. Server health check
2. All 31 logins
3. All 85 dashboard APIs
4. Patient registration (5 hospitals × 3 patients)
5. Digital prescriptions
6. Nurse vitals
7. Lab orders + results
8. IPD admit + rounds
9. Billing + payment
10. Pharmacy sales
11. Staff check-in/check-out
12. Surgery scheduling
13. Chatbot appointment booking
14. Telegram notifications
15. Database verification (row counts)

**Latest result: 143/143 = 100% ✅** (v7.1 final E2E, March 12 2026)

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `srp_mediflow_server.py` | Main server — all routes, middleware, HTML serving |
| `hms_db.py` | All database operations (per-tenant) |
| `platform_db.py` | Platform/SaaS database operations |
| `tenant_router.py` | Per-request tenant isolation (thread-local DB connections) |
| `auth.py` | Session management, role verification |
| `chatbot.py` | AI chatbot logic (appointment booking) |
| `notifications/` | Telegram + WhatsApp notification system |
| `pdf_generator.py` | PDF generation for prescriptions and bills |
| `_e2e_mega.py` | Full end-to-end test suite |
| `_quick_deploy.py` | One-click deploy to Hetzner |
| `_seed_all_hospitals.py` | Seed demo data across all hospitals |
| `requirements.txt` | Python dependencies |

---

## ⚙️ Environment Variables (.env)

```env
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=hospital_ai        # Star Hospital (default/platform)
DB_USER=ats_user
DB_PASSWORD=ats_password

# Platform
PLATFORM_DB_NAME=srp_platform
PORT=7500

# Founder Telegram bot (optional)
FOUNDER_TG_TOKEN=...
FOUNDER_TG_CHAT_ID=...
```

---

## 📜 Changelog

### v7.1 — March 12, 2026
- ✅ **143/143 E2E tests 100% pass rate** — full patient journey + new client onboarding
- 🔒 **HTTPS enforced** — nginx SSL proxy via Let's Encrypt (`mediflow.srpailabs.com`)
- 🏥 **Full demo patient journey** — Registration → IPD → Lab → X-Ray → Pharmacy → Discharge
- 🔬 **X-Ray / Radiology orders** — XRAY test type, radiology results, impression report
- 📷 **Radiology reports** — Chest PA/Lateral, cardiomegaly detection, impression
- 🧹 **Junk test DBs cleaned** — 6 stale test DBs dropped, registry trimmed to 5 core
- 🔧 **Tenant bug fixed** — admin re-seeded when slug already exists (was causing 401s)
- 🎲 **E2E suffix upgraded** — 6-digit random suffix (1M combos, never collides)
- 🏥 **New client E2E** — DB + schema + admin + chatbot all verified post-provisioning
- 📊 **README + landing page** — updated URLs to HTTPS, version badges, E2E count

### v7.0 — March 11, 2026
- ✅ **100% E2E test pass rate** (233/233) — up from 92%
- 🚫 **Telegram spam permanently fixed** — no more server-restart messages
- 🗄️ **Schema fully migrated** across all 5 hospital DBs:
  - `prescriptions`: added `visit_id`, `uhid`, `created_by_doctor`, `clinical_notes`, `bp`, `temperature`, `pulse`, `spo2`, `weight`, `special_instructions`, `chief_complaint`, `symptoms`, `diet_advice`, `follow_up_days`
  - `prescription_medicines` table created in all 5 DBs
  - `prescription_items` table created/fixed (added `route` column) in all 5 DBs
  - `lab_orders`: added `visit_id`, `prescription_id`, `lab_notes`
- 🧹 Codebase cleaned up (removed 30+ debug/fix scripts)

### v6.1 — March 2026
- 🎤 Voice-to-text on prescription fields (en-IN / hi-IN / te-IN)
- 📋 Draft auto-save (localStorage)
- 🕐 Staff self check-in / check-out
- ✈️ Telegram notification on prescription save
- 📱 Mobile sticky prescription action bar

### v6.0 — February 2026
- Full multi-tenant SaaS architecture
- Per-hospital isolated databases
- IPD patient admissions and rounds
- Surgery scheduling
- Pharmacy inventory and dispensing
- Telegram bot per hospital (fully isolated routing)

---

## 📞 Support & Contact

**SRP MediFlow** — Enterprise Hospital Management Platform
Built with ❤️ for Indian healthcare

> **IMPORTANT:** Change all default passwords before going live with real patient data.
