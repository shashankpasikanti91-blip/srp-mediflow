# 🏥 SRP MediFlow — Hospital Management System

> **Full-featured HMS for 20–50 bed Indian hospitals.**  
> OPD + IPD + Pharmacy + Surgery + GST Billing + Multi-Tenant + Chatbot Booking

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL (port 5434) and ensure database 'hospital_ai' exists

# 3. Run server
python srp_mediflow_server.py

# 4. Open browser
#   http://localhost:7500/admin  ← Admin login
#   http://localhost:7500/       ← Patient chatbot
```

**Or double-click:** `🏥 START SRP MEDIFLOW.bat`

**Default Admin Credentials:**
- Username: `admin`
- Password: `hospital2024`

---

## ✨ Features

### Core (Phase 1 — RBAC + OPD)
- RBAC Auth: 7 roles (ADMIN, DOCTOR, NURSE, LAB, XRAY, STOCK, RECEPTION)
- Chatbot: AI appointment booking (voice + text, Telugu/Hindi/English)
- OPD Flow: Registration → appointment → visit → prescription → lab request
- Patient Vitals: Nurse records BP, temp, pulse, SpO₂, weight

### Extended (Phase 2 — IPD + HMS)
- **IPD Admissions** — Admit to ward/bed, track status (admitted/discharged)
- **Daily Rounds** — Doctors & nurses log vitals + clinical notes per admission
- **Discharge Process** — Final diagnosis, summary, discharge medicines, follow-up
- **Surgery Module** — Records, anesthesia type, estimated/negotiated cost
- **Pharmacy Batches** — Per-batch tracking with expiry date, FIFO stock deduction
- **Expiry Alerts** — Medicines expiring within 90 days
- **Low Stock Alerts** — Items below minimum quantity threshold
- **GST Billing (India)** — Per-item GST (0% consultation/bed, 5–18% medicines)
- **Procedure Charges** — Configurable price list (24+ default procedures)
- **Multi-Tenant** — Each hospital client gets its own isolated PostgreSQL DB

---

## 👤 User Roles & Dashboards

| Role | Dashboard | Key Capabilities |
|---|---|---|
| `ADMIN` | `/admin` | Full system — all modules |
| `DOCTOR` | Doctor dashboard | Appointments, prescriptions, lab, IPD rounds, surgery |
| `NURSE` | Nurse dashboard | Vitals, assignments, IPD round entries |
| `LAB` | Lab dashboard | Test requests, upload results |
| `XRAY` | Lab dashboard | Radiology requests and reports |
| `STOCK` | Stock dashboard | Inventory, pharmacy batches, expiry alerts |
| `RECEPTION` | Admin-lite | Appointment management |

---

## 🏗️ System Architecture

```
srp_mediflow_server.py    ← Main HTTP server (port 7500)
auth.py                   ← RBAC authentication (bcrypt, sessions)
roles.py                  ← 7 roles, permission mapping
db.py                     ← All PostgreSQL operations (psycopg2)
chatbot.py                ← AI chatbot — DO NOT MODIFY
hospital_config.py        ← Hospital identity / config
srp_mediflow_tenant.py    ← Multi-tenant DB provisioning
srp_mediflow_schema.sql   ← Full reference schema + seed data

Dashboards:
admin_dashboard.html      ← Admin: all 8+ sections
doctor_dashboard.html     ← Doctor: OPD + IPD rounds + Surgery
nurse_dashboard.html      ← Nurse: vitals + IPD rounds
lab_dashboard.html        ← Lab: test requests + results
stock_dashboard.html      ← Stock: inventory + pharmacy batches + expiry
```

---

## 🗃️ Database Schema

**PostgreSQL** `localhost:5434 | db: hospital_ai | user: ats_user`

### Phase 1 Tables
```
users, appointments, patient_visits, prescriptions, lab_tests,
nurse_vitals, nurse_assignments, inventory_stock, billing, wards, medicines
```

### Phase 2 Tables
```
patient_admissions  ← IPD admissions (ward, bed, doctor, status)
daily_rounds        ← Per-admission round entries (vitals + notes)
surgery_records     ← Surgery type, anesthesia, estimated/negotiated cost
discharge_summaries ← Final notes, medicines, follow-up date
procedure_charges   ← Configurable procedure price list
bill_items          ← Line items with per-item GST calculation
```

---

## 💰 GST Billing (India)

| Item Type | GST Rate |
|---|---|
| Consultation / Lab / Imaging / Surgery / Bed | 0% |
| Medicines — Essential | 5% |
| Medicines — Standard | 12% |
| Medicines — Branded | 18% |
| Equipment Rental | 18% |

Each bill item stores: `item_type`, `description`, `quantity`, `unit_price`, `tax_rate`, `tax_amount`, `total_amount`.

---

## 💊 Pharmacy Flow

1. Add medicine to `medicines` catalogue (name, generic, type, GST category)
2. Add batch → `POST /api/pharmacy/add-stock` (batch#, expiry, qty, supplier)
3. Sell → `POST /api/pharmacy/sell` — FIFO deduction by earliest expiry date
4. Alerts auto-generated: low stock + expiry warnings (dashboard + API)

---

## 🏥 IPD Patient Flow

```
1. RECEPTION/ADMIN: Admit patient   POST /api/ipd/admit
2. DOCTOR/NURSE: Daily rounds       POST /api/ipd/round/add
3. DOCTOR: Surgery if needed        POST /api/surgery/create
                                    POST /api/surgery/update-cost
4. BILLING: Create bill             POST /api/billing/ipd/create
            Add items + GST         POST /api/billing/add-item
            Mark payment            POST /api/billing/payment
5. ADMIN/DOCTOR: Discharge          POST /api/ipd/discharge
```

---

## 🌐 Multi-Tenant Provisioning

```bash
# Create new client database
python srp_mediflow_tenant.py create \
  --name star_hospital \
  --display "Star Hospital" \
  --city Kothagudem \
  --phone "9876543210" \
  --admin-password "starhosp2024"

# List tenants
python srp_mediflow_tenant.py list

# Delete tenant
python srp_mediflow_tenant.py delete --name star_hospital
```

Each tenant DB: `srp_<slug>`. Registry: `tenant_registry.json`.

---

## 📡 Key API Reference

### IPD
`POST /api/ipd/admit` | `GET /api/ipd/admissions` | `GET /api/ipd/admission/<id>`  
`POST /api/ipd/round/add` | `GET /api/ipd/rounds/<id>` | `POST /api/ipd/discharge`

### Surgery
`POST /api/surgery/create` | `GET /api/surgery/list` | `POST /api/surgery/update-cost`

### Pharmacy
`POST /api/pharmacy/add-stock` | `GET /api/pharmacy/inventory`  
`GET /api/pharmacy/alerts/low-stock` | `GET /api/pharmacy/alerts/expiry`  
`POST /api/pharmacy/sell`

### Billing
`POST /api/billing/add-item` | `GET /api/billing/items/<id>`  
`POST /api/billing/ipd/create` | `POST /api/billing/payment`

---

## 📦 Dependencies

```
psycopg2-binary  ← PostgreSQL driver
bcrypt           ← Password hashing
requests         ← HTTP / ngrok
pyngrok          ← Ngrok tunnel
```

Install: `pip install -r requirements.txt`

---

## 🔐 Security

- Passwords: bcrypt hashed server-side
- Sessions: SHA-256 tokens, 8-hour TTL, in-memory store
- All API routes: role-permission enforced server-side
- Multi-tenant: database-level isolation per client

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file.

---

*SRP MediFlow v2.0 — Built for Indian hospitals (20–50 beds). OPD + IPD + Pharmacy + Surgery + GST Billing.*
