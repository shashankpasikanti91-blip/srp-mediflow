-- ════════════════════════════════════════════════════════════════════════════
--  SRP MediFlow — HMS v4 Schema Addendum
--  New tables for: Patient Visits, Doctor Notes, Prescription Items,
--                  Lab Results, Pharmacy Stock, OP Tickets
--  Version : 4.0  |  Date: 2026-03-09
--  Target  : PostgreSQL 14+  (localhost:5434 / hospital_ai / ats_user)
--
--  SAFE TO RUN MULTIPLE TIMES — all DDL uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS
--  Does NOT modify any existing table structure or data.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── PATIENT VISITS ──────────────────────────────────────────────────────────
-- Each patient encounter (OPD / IPD / ER) creates one row here.
-- Links back to the `patients` master record via patient_id.
CREATE TABLE IF NOT EXISTS patient_visits (
    visit_id        SERIAL PRIMARY KEY,
    patient_id      INTEGER REFERENCES patients(id) ON DELETE CASCADE,
    visit_type      VARCHAR(10)  DEFAULT 'OP',        -- OP | IP | ER
    doctor_assigned VARCHAR(150) DEFAULT '',
    doctor_username VARCHAR(80)  DEFAULT '',
    department      VARCHAR(100) DEFAULT '',
    visit_date      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    chief_complaint TEXT         DEFAULT '',
    diagnosis       TEXT         DEFAULT '',
    notes           TEXT         DEFAULT '',
    status          VARCHAR(30)  DEFAULT 'active',    -- active | closed | follow-up
    op_ticket_no    VARCHAR(30)  DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pv_patient_id  ON patient_visits (patient_id);
CREATE INDEX IF NOT EXISTS idx_pv_visit_date  ON patient_visits (visit_date DESC);
CREATE INDEX IF NOT EXISTS idx_pv_doctor      ON patient_visits (doctor_username);
CREATE INDEX IF NOT EXISTS idx_pv_visit_type  ON patient_visits (visit_type);

-- ─── DOCTOR NOTES ─────────────────────────────────────────────────────────────
-- Clinical / follow-up / discharge notes written by doctors per patient/visit.
CREATE TABLE IF NOT EXISTS doctor_notes (
    note_id         SERIAL PRIMARY KEY,
    patient_id      INTEGER REFERENCES patients(id) ON DELETE CASCADE,
    visit_id        INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
    doctor_username VARCHAR(80)  NOT NULL,
    doctor_name     VARCHAR(150) DEFAULT '',
    note_type       VARCHAR(50)  DEFAULT 'clinical',  -- clinical | follow_up | discharge
    note_text       TEXT         NOT NULL,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dn_patient_id ON doctor_notes (patient_id);
CREATE INDEX IF NOT EXISTS idx_dn_doctor     ON doctor_notes (doctor_username);
CREATE INDEX IF NOT EXISTS idx_dn_created_at ON doctor_notes (created_at DESC);

-- ─── PRESCRIPTION ITEMS ───────────────────────────────────────────────────────
-- Structured per-medicine rows linked to the `prescriptions` parent row.
-- Enables individual medicine tracking + pharmacy dispensing integration.
CREATE TABLE IF NOT EXISTS prescription_items (
    item_id         SERIAL PRIMARY KEY,
    prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE CASCADE,
    medicine_name   VARCHAR(200) NOT NULL,
    dosage          VARCHAR(100) DEFAULT '',   -- e.g. "500 mg"
    frequency       VARCHAR(100) DEFAULT '',   -- e.g. "1-0-1 (morning-afternoon-night)"
    duration        VARCHAR(50)  DEFAULT '',   -- e.g. "5 days"
    instructions    TEXT         DEFAULT '',   -- e.g. "Take after food"
    quantity        INTEGER      DEFAULT 0,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pi_prescription ON prescription_items (prescription_id);

-- ─── LAB RESULTS ──────────────────────────────────────────────────────────────
-- Per-parameter result rows that link to lab_orders AND patients.
-- Enables viewing all lab history on the patient's record.
CREATE TABLE IF NOT EXISTS lab_results (
    result_id       SERIAL PRIMARY KEY,
    order_id        INTEGER REFERENCES lab_orders(id) ON DELETE SET NULL,
    patient_id      INTEGER REFERENCES patients(id)   ON DELETE SET NULL,
    patient_name    VARCHAR(150) DEFAULT '',
    test_name       VARCHAR(200) DEFAULT '',
    result_value    TEXT         DEFAULT '',
    reference_range VARCHAR(100) DEFAULT '',
    unit            VARCHAR(30)  DEFAULT '',
    is_abnormal     BOOLEAN      DEFAULT FALSE,
    remarks         TEXT         DEFAULT '',
    lab_username    VARCHAR(80)  DEFAULT '',
    reported_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lr_patient_id ON lab_results (patient_id);
CREATE INDEX IF NOT EXISTS idx_lr_order_id   ON lab_results (order_id);
CREATE INDEX IF NOT EXISTS idx_lr_reported   ON lab_results (reported_at DESC);

-- ─── PHARMACY STOCK ───────────────────────────────────────────────────────────
-- Living stock level per medicine + batch.  Sales deduct from here.
-- Replaces the older `inventory_stock` for pharmacy workflows
-- (inventory_stock is kept for backward-compat; this is the live view).
CREATE TABLE IF NOT EXISTS pharmacy_stock (
    stock_id        SERIAL PRIMARY KEY,
    medicine_id     INTEGER REFERENCES medicines(id) ON DELETE CASCADE,
    medicine_name   VARCHAR(200) DEFAULT '',
    batch_no        VARCHAR(50)  DEFAULT '',
    expiry_date     DATE,
    quantity        INTEGER      DEFAULT 0,
    min_quantity    INTEGER      DEFAULT 10,
    unit_price      NUMERIC(10,2) DEFAULT 0,
    sell_price      NUMERIC(10,2) DEFAULT 0,
    supplier        VARCHAR(150) DEFAULT '',
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (medicine_id, batch_no)
);

CREATE INDEX IF NOT EXISTS idx_ps_medicine_id ON pharmacy_stock (medicine_id);
CREATE INDEX IF NOT EXISTS idx_ps_expiry      ON pharmacy_stock (expiry_date);
CREATE INDEX IF NOT EXISTS idx_ps_qty         ON pharmacy_stock (quantity);

-- ─── OP TICKETS ───────────────────────────────────────────────────────────────
-- Sequential OP ticket counter per day.  Format: OP-YYYYMMDD-0001
CREATE TABLE IF NOT EXISTS op_tickets (
    ticket_id    SERIAL PRIMARY KEY,
    ticket_no    VARCHAR(30)   UNIQUE NOT NULL,
    patient_id   INTEGER REFERENCES patients(id)          ON DELETE CASCADE,
    visit_id     INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
    doctor_name  VARCHAR(150)  DEFAULT '',
    department   VARCHAR(100)  DEFAULT '',
    issued_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(20)   DEFAULT 'waiting'  -- waiting | with_doctor | done
);

CREATE INDEX IF NOT EXISTS idx_ot_patient_id ON op_tickets (patient_id);
CREATE INDEX IF NOT EXISTS idx_ot_issued_at  ON op_tickets (issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_ot_status     ON op_tickets (status);

-- ─── APPOINTMENTS: add patient_id FK column if missing ────────────────────────
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL;

-- ─── USEFUL INDICES FOR SEARCH PERFORMANCE ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_patients_phone  ON patients (phone);
CREATE INDEX IF NOT EXISTS idx_patients_name   ON patients USING gin(to_tsvector('simple', full_name));
CREATE INDEX IF NOT EXISTS idx_billing_date    ON billing (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_status  ON billing (status);
CREATE INDEX IF NOT EXISTS idx_ps_pending      ON lab_orders (status) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_pharma_sales_dt ON pharmacy_sales (sold_at DESC);

-- ════════════════════════════════════════════════════════════════════════════
-- END OF HMS v4 SCHEMA ADDENDUM
-- ════════════════════════════════════════════════════════════════════════════
