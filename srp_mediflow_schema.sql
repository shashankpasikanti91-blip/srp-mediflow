-- ════════════════════════════════════════════════════════════════════════════
--  SRP MediFlow – Hospital Management System
--  Complete PostgreSQL Schema — All Tables
--  Version : 3.0  |  Date: 2026-03-08
--  Target  : Small & Mid-size Hospitals in India (20–50 beds)
-- ════════════════════════════════════════════════════════════════════════════
--
--  CONN: localhost:5432 / hospital_ai / ats_user
--
--  HOW TO USE:
--    1. Run this file once per new hospital DB during tenant setup.
--    2. Or use srp_mediflow_tenant.py for automated provisioning.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── STAFF & AUTH ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staff_users (
    id                   SERIAL PRIMARY KEY,
    username             VARCHAR(80)  UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    role                 VARCHAR(20)  NOT NULL DEFAULT 'RECEPTION',
    department           VARCHAR(100) DEFAULT '',
    full_name            VARCHAR(150) DEFAULT '',
    is_active            BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT TRUE,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Migration: ensure must_change_password exists on pre-existing DBs
ALTER TABLE staff_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT TRUE;

-- ─── PATIENTS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patients (
    id          SERIAL PRIMARY KEY,
    full_name   VARCHAR(150) NOT NULL,
    dob         DATE,
    gender      VARCHAR(10)  DEFAULT 'Unknown',
    phone       VARCHAR(20),
    aadhar      VARCHAR(20),
    address     TEXT         DEFAULT '',
    blood_group VARCHAR(5)   DEFAULT '',
    allergies   TEXT         DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DEPARTMENTS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT         DEFAULT '',
    head_doctor VARCHAR(150) DEFAULT '',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DOCTORS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doctors (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    department      VARCHAR(100) DEFAULT '',
    specialization  VARCHAR(200) DEFAULT '',
    phone           VARCHAR(20)  DEFAULT '',
    status          VARCHAR(20)  DEFAULT 'available',
    on_duty         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── REGISTRATIONS (chatbot / OPD) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS registrations (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(150) NOT NULL,
    age              VARCHAR(10)  DEFAULT '',
    phone            VARCHAR(20)  DEFAULT '',
    aadhar           VARCHAR(20)  DEFAULT '',
    issue            TEXT         DEFAULT '',
    doctor           VARCHAR(150) DEFAULT '',
    appointment_time VARCHAR(50)  DEFAULT '',
    status           VARCHAR(20)  DEFAULT 'pending',
    source           VARCHAR(30)  DEFAULT 'chatbot',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── APPOINTMENTS ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appointments (
    id               SERIAL PRIMARY KEY,
    patient_name     VARCHAR(150) NOT NULL,
    patient_phone    VARCHAR(20)  DEFAULT '',
    patient_aadhar   VARCHAR(20)  DEFAULT '',
    age              VARCHAR(10)  DEFAULT '',
    issue            TEXT         DEFAULT '',
    doctor_name      VARCHAR(150) DEFAULT '',
    department       VARCHAR(100) DEFAULT '',
    appointment_date DATE,
    appointment_time VARCHAR(20)  DEFAULT '',
    status           VARCHAR(30)  DEFAULT 'pending',
    source           VARCHAR(30)  DEFAULT 'chatbot',
    notes            TEXT         DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── ATTENDANCE ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id          SERIAL PRIMARY KEY,
    staff_name  VARCHAR(150) NOT NULL,
    action      VARCHAR(20)  NOT NULL,
    notes       TEXT         DEFAULT '',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DOCTOR ATTENDANCE ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doctor_attendance (
    id          SERIAL PRIMARY KEY,
    doctor_name VARCHAR(150) NOT NULL,
    action      VARCHAR(20)  NOT NULL,
    shift       VARCHAR(20)  DEFAULT 'Morning',
    notes       TEXT         DEFAULT '',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DOCTOR ROUNDS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doctor_rounds (
    id           SERIAL PRIMARY KEY,
    doctor_name  VARCHAR(150) NOT NULL,
    ward         VARCHAR(80)  DEFAULT '',
    round_time   VARCHAR(20)  DEFAULT '',
    status       VARCHAR(20)  DEFAULT 'pending',
    notes        TEXT         DEFAULT '',
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- ─── VISIT RECORDS (doctor consultation notes) ────────────────────────────────
CREATE TABLE IF NOT EXISTS visit_records (
    id              SERIAL PRIMARY KEY,
    patient_name    VARCHAR(150) NOT NULL,
    patient_phone   VARCHAR(20)  DEFAULT '',
    doctor_username VARCHAR(80),
    doctor_name     VARCHAR(150) DEFAULT '',
    department      VARCHAR(100) DEFAULT '',
    chief_complaint TEXT         DEFAULT '',
    examination     TEXT         DEFAULT '',
    diagnosis       TEXT         DEFAULT '',
    treatment_plan  TEXT         DEFAULT '',
    follow_up_date  DATE,
    visit_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── PRESCRIPTIONS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prescriptions (
    id              SERIAL PRIMARY KEY,
    patient_name    VARCHAR(150),
    patient_phone   VARCHAR(20)  DEFAULT '',
    doctor_username VARCHAR(80),
    doctor_name     VARCHAR(150),
    diagnosis       TEXT,
    medicines       TEXT,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── VITALS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vitals (
    id             SERIAL PRIMARY KEY,
    patient_name   VARCHAR(150),
    patient_phone  VARCHAR(20)  DEFAULT '',
    nurse_username VARCHAR(80),
    bp             VARCHAR(20)  DEFAULT '',
    pulse          VARCHAR(10)  DEFAULT '',
    temperature    VARCHAR(10)  DEFAULT '',
    spo2           VARCHAR(10)  DEFAULT '',
    weight         VARCHAR(10)  DEFAULT '',
    notes          TEXT         DEFAULT '',
    recorded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── LAB TESTS CATALOGUE ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lab_tests (
    id           SERIAL PRIMARY KEY,
    test_code    VARCHAR(20)  UNIQUE NOT NULL,
    test_name    VARCHAR(200) NOT NULL,
    category     VARCHAR(80)  DEFAULT 'Pathology',
    normal_range VARCHAR(100) DEFAULT '',
    unit         VARCHAR(30)  DEFAULT '',
    price        NUMERIC(10,2) DEFAULT 0,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── LAB ORDERS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lab_orders (
    id              SERIAL PRIMARY KEY,
    patient_name    VARCHAR(150),
    patient_phone   VARCHAR(20)  DEFAULT '',
    doctor_username VARCHAR(80),
    test_type       VARCHAR(30)  DEFAULT 'LAB',
    test_name       VARCHAR(200),
    status          VARCHAR(20)  DEFAULT 'PENDING',
    result_text     TEXT         DEFAULT '',
    result_file     TEXT         DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);

-- ─── LAB REPORTS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lab_reports (
    id               SERIAL PRIMARY KEY,
    order_id         INTEGER REFERENCES lab_orders(id) ON DELETE SET NULL,
    patient_name     VARCHAR(150),
    patient_phone    VARCHAR(20)  DEFAULT '',
    test_name        VARCHAR(200),
    result_text      TEXT         DEFAULT '',
    result_file_path TEXT         DEFAULT '',
    remarks          TEXT         DEFAULT '',
    lab_username     VARCHAR(80),
    reported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── IMAGING TESTS CATALOGUE ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS imaging_tests (
    id        SERIAL PRIMARY KEY,
    test_code VARCHAR(20)  UNIQUE NOT NULL,
    test_name VARCHAR(200) NOT NULL,
    modality  VARCHAR(50)  DEFAULT 'X-Ray',
    body_part VARCHAR(100) DEFAULT '',
    price     NUMERIC(10,2) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── IMAGING ORDERS ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS imaging_orders (
    id              SERIAL PRIMARY KEY,
    patient_name    VARCHAR(150) NOT NULL,
    patient_phone   VARCHAR(20)  DEFAULT '',
    doctor_username VARCHAR(80),
    modality        VARCHAR(50)  DEFAULT 'X-Ray',
    body_part       VARCHAR(100) DEFAULT '',
    clinical_notes  TEXT         DEFAULT '',
    status          VARCHAR(20)  DEFAULT 'PENDING',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);

-- ─── IMAGING REPORTS ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS imaging_reports (
    id               SERIAL PRIMARY KEY,
    order_id         INTEGER REFERENCES imaging_orders(id) ON DELETE SET NULL,
    patient_name     VARCHAR(150),
    modality         VARCHAR(50)  DEFAULT 'X-Ray',
    findings         TEXT         DEFAULT '',
    impression       TEXT         DEFAULT '',
    report_file_path TEXT         DEFAULT '',
    radiologist      VARCHAR(150) DEFAULT '',
    reported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── WARDS ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wards (
    id         SERIAL PRIMARY KEY,
    ward_name  VARCHAR(100) UNIQUE NOT NULL,
    ward_type  VARCHAR(50)  DEFAULT 'General',
    total_beds INTEGER DEFAULT 0,
    floor      VARCHAR(20)  DEFAULT 'Ground',
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── BEDS ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS beds (
    id         SERIAL PRIMARY KEY,
    ward_id    INTEGER REFERENCES wards(id) ON DELETE CASCADE,
    bed_number VARCHAR(20) NOT NULL,
    bed_type   VARCHAR(50)  DEFAULT 'General',
    status     VARCHAR(20)  DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ward_id, bed_number)
);

-- ─── BED ASSIGNMENTS ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bed_assignments (
    id            SERIAL PRIMARY KEY,
    bed_id        INTEGER REFERENCES beds(id) ON DELETE SET NULL,
    patient_name  VARCHAR(150) NOT NULL,
    patient_phone VARCHAR(20)  DEFAULT '',
    admitted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discharged_at TIMESTAMP,
    notes         TEXT DEFAULT ''
);

-- ─── NURSE ASSIGNMENTS ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nurse_assignments (
    id             SERIAL PRIMARY KEY,
    nurse_username VARCHAR(80) NOT NULL,
    patient_name   VARCHAR(150),
    patient_phone  VARCHAR(20)  DEFAULT '',
    ward           VARCHAR(80)  DEFAULT '',
    bed_number     VARCHAR(20)  DEFAULT '',
    shift          VARCHAR(20)  DEFAULT 'Morning',
    assigned_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discharged_at  TIMESTAMP
);

-- ─── IPD PATIENT ADMISSIONS ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patient_admissions (
    id               SERIAL PRIMARY KEY,
    patient_name     VARCHAR(150) NOT NULL,
    patient_phone    VARCHAR(20)  DEFAULT '',
    patient_aadhar   VARCHAR(20)  DEFAULT '',
    age              VARCHAR(10)  DEFAULT '',
    gender           VARCHAR(10)  DEFAULT 'Unknown',
    blood_group      VARCHAR(5)   DEFAULT '',
    address          TEXT         DEFAULT '',
    admission_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discharge_date   TIMESTAMP,
    ward_name        VARCHAR(100) DEFAULT '',
    bed_number       VARCHAR(20)  DEFAULT '',
    admitting_doctor VARCHAR(150) DEFAULT '',
    department       VARCHAR(100) DEFAULT '',
    diagnosis        TEXT         DEFAULT '',
    admission_notes  TEXT         DEFAULT '',
    status           VARCHAR(20)  DEFAULT 'admitted',  -- admitted / discharged
    created_by       VARCHAR(80)  DEFAULT 'reception',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DAILY ROUNDS (IPD) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_rounds (
    id               SERIAL PRIMARY KEY,
    admission_id     INTEGER REFERENCES patient_admissions(id) ON DELETE CASCADE,
    patient_name     VARCHAR(150) NOT NULL,
    doctor_name      VARCHAR(150) DEFAULT '',
    doctor_username  VARCHAR(80)  DEFAULT '',
    round_date       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bp               VARCHAR(20)  DEFAULT '',
    pulse            VARCHAR(10)  DEFAULT '',
    temperature      VARCHAR(10)  DEFAULT '',
    spo2             VARCHAR(10)  DEFAULT '',
    clinical_notes   TEXT         DEFAULT '',
    treatment_change TEXT         DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── DISCHARGE SUMMARIES ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS discharge_summaries (
    id                  SERIAL PRIMARY KEY,
    admission_id        INTEGER REFERENCES patient_admissions(id) ON DELETE CASCADE,
    patient_name        VARCHAR(150) NOT NULL,
    discharge_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    final_diagnosis     TEXT DEFAULT '',
    treatment_given     TEXT DEFAULT '',
    discharge_medicines TEXT DEFAULT '',
    follow_up_date      DATE,
    follow_up_notes     TEXT DEFAULT '',
    diet_advice         TEXT DEFAULT '',
    activity_advice     TEXT DEFAULT '',
    doctor_name         VARCHAR(150) DEFAULT '',
    doctor_username     VARCHAR(80)  DEFAULT '',
    bill_id             INTEGER,   -- FK to billing(id) added after billing table created
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── PROCEDURE CHARGES CATALOGUE ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS procedure_charges (
    id             SERIAL PRIMARY KEY,
    procedure_name VARCHAR(200) NOT NULL,
    category       VARCHAR(80)  DEFAULT 'General',
    default_price  NUMERIC(10,2) DEFAULT 0,
    gst_percent    NUMERIC(5,2)  DEFAULT 0,
    description    TEXT         DEFAULT '',
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── SURGERY RECORDS ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS surgery_records (
    id               SERIAL PRIMARY KEY,
    admission_id     INTEGER REFERENCES patient_admissions(id) ON DELETE SET NULL,
    patient_name     VARCHAR(150) NOT NULL,
    patient_phone    VARCHAR(20)  DEFAULT '',
    surgeon_name     VARCHAR(150) DEFAULT '',
    surgeon_username VARCHAR(80)  DEFAULT '',
    surgery_type     VARCHAR(200) NOT NULL,
    anesthesia_type  VARCHAR(100) DEFAULT 'General',
    estimated_cost   NUMERIC(10,2) DEFAULT 0,
    negotiated_cost  NUMERIC(10,2) DEFAULT 0,
    operation_date   TIMESTAMP,
    duration_minutes INTEGER      DEFAULT 0,
    operation_notes  TEXT         DEFAULT '',
    complications    TEXT         DEFAULT '',
    status           VARCHAR(30)  DEFAULT 'scheduled',  -- scheduled/completed/cancelled
    created_by       VARCHAR(80)  DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── MEDICINES CATALOGUE ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medicines (
    id             SERIAL PRIMARY KEY,
    medicine_name  VARCHAR(200) NOT NULL,
    generic_name   VARCHAR(200) DEFAULT '',
    category       VARCHAR(80)  DEFAULT 'Tablet',
    manufacturer   VARCHAR(150) DEFAULT '',
    unit           VARCHAR(30)  DEFAULT 'Strip',
    unit_price     NUMERIC(10,2) DEFAULT 0,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── INVENTORY STOCK (pharmacy batches) ───────────────────────────────────────
-- batch_number, supplier added in Phase-2 alters
CREATE TABLE IF NOT EXISTS inventory_stock (
    id             SERIAL PRIMARY KEY,
    medicine_id    INTEGER REFERENCES medicines(id) ON DELETE CASCADE,
    batch_no       VARCHAR(50)  DEFAULT '',
    batch_number   VARCHAR(50)  DEFAULT '',
    expiry_date    DATE,
    quantity       INTEGER      DEFAULT 0,
    min_quantity   INTEGER      DEFAULT 10,
    purchase_price NUMERIC(10,2) DEFAULT 0,
    sell_price     NUMERIC(10,2) DEFAULT 0,
    supplier       VARCHAR(150) DEFAULT '',
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── PHARMACY SALES ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pharmacy_sales (
    id              SERIAL PRIMARY KEY,
    patient_name    VARCHAR(150) DEFAULT 'Walk-in',
    patient_phone   VARCHAR(20)  DEFAULT '',
    prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL,
    total_amount    NUMERIC(10,2) DEFAULT 0,
    discount        NUMERIC(10,2) DEFAULT 0,
    net_amount      NUMERIC(10,2) DEFAULT 0,
    payment_mode    VARCHAR(30)  DEFAULT 'Cash',
    staff_username  VARCHAR(80),
    sold_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pharmacy_sale_items (
    id           SERIAL PRIMARY KEY,
    sale_id      INTEGER REFERENCES pharmacy_sales(id) ON DELETE CASCADE,
    medicine_id  INTEGER REFERENCES medicines(id) ON DELETE SET NULL,
    medicine_name VARCHAR(200),
    quantity     INTEGER      DEFAULT 1,
    unit_price   NUMERIC(10,2) DEFAULT 0,
    total_price  NUMERIC(10,2) DEFAULT 0
);

-- ─── BILLING ──────────────────────────────────────────────────────────────────
-- OPD bill, IPD bill — supports all charge types + tax
CREATE TABLE IF NOT EXISTS billing (
    id                SERIAL PRIMARY KEY,
    patient_name      VARCHAR(150) NOT NULL,
    patient_phone     VARCHAR(20)  DEFAULT '',
    bill_type         VARCHAR(20)  DEFAULT 'OPD',   -- OPD / IPD
    admission_id      INTEGER,
    consultation_fee  NUMERIC(10,2) DEFAULT 0,
    lab_charges       NUMERIC(10,2) DEFAULT 0,
    imaging_charges   NUMERIC(10,2) DEFAULT 0,
    pharmacy_charges  NUMERIC(10,2) DEFAULT 0,
    bed_charges       NUMERIC(10,2) DEFAULT 0,
    surgery_charges   NUMERIC(10,2) DEFAULT 0,
    procedure_charges NUMERIC(10,2) DEFAULT 0,
    misc_charges      NUMERIC(10,2) DEFAULT 0,
    total_amount      NUMERIC(10,2) DEFAULT 0,
    tax_amount        NUMERIC(10,2) DEFAULT 0,
    discount          NUMERIC(10,2) DEFAULT 0,
    net_amount        NUMERIC(10,2) DEFAULT 0,
    status            VARCHAR(20)  DEFAULT 'unpaid',
    notes             TEXT         DEFAULT '',
    created_by        VARCHAR(80),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── BILL ITEMS (per-line with GST) ───────────────────────────────────────────
-- India GST rules:
--   Consultation    = 0%    |  Lab tests       = 0%
--   Surgery         = 0%    |  Room charges    = 0%
--   Medicines       = 5 / 12 / 18%
CREATE TABLE IF NOT EXISTS bill_items (
    id               SERIAL PRIMARY KEY,
    bill_id          INTEGER REFERENCES billing(id) ON DELETE CASCADE,
    item_type        VARCHAR(50)  DEFAULT 'consultation',
    item_name        VARCHAR(200) NOT NULL,
    item_price       NUMERIC(10,2) DEFAULT 0,
    quantity         INTEGER      DEFAULT 1,
    actual_price     NUMERIC(10,2) DEFAULT 0,
    negotiated_price NUMERIC(10,2) DEFAULT 0,
    tax_percent      NUMERIC(5,2)  DEFAULT 0,
    tax_amount       NUMERIC(10,2) DEFAULT 0,
    total_amount     NUMERIC(10,2) DEFAULT 0,
    notes            TEXT         DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── PAYMENTS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    bill_id      INTEGER REFERENCES billing(id) ON DELETE CASCADE,
    amount_paid  NUMERIC(10,2) DEFAULT 0,
    payment_mode VARCHAR(30)  DEFAULT 'Cash',
    reference_no VARCHAR(100) DEFAULT '',
    received_by  VARCHAR(80),
    paid_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── SYSTEM LOGS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_logs (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(80)  DEFAULT 'system',
    role       VARCHAR(20)  DEFAULT '',
    action     VARCHAR(200) NOT NULL,
    details    TEXT         DEFAULT '',
    ip_address VARCHAR(45)  DEFAULT '',
    logged_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SEED DATA — Default process charges
-- ════════════════════════════════════════════════════════════════════════════
INSERT INTO procedure_charges (procedure_name, category, default_price, gst_percent)
  VALUES
    ('OPD Consultation',          'Consultation',  300,   0),
    ('Specialist Consultation',   'Consultation',  500,   0),
    ('Dressing / Wound Care',     'Minor Procedure', 200, 0),
    ('Injection Administration',  'Minor Procedure', 100, 0),
    ('IV Cannula Insertion',       'Minor Procedure', 150, 0),
    ('ECG',                        'Diagnostic',    300,   0),
    ('X-Ray Chest PA',             'Imaging',       400,   0),
    ('Ultrasound Abdomen',         'Imaging',       700,   0),
    ('MRI Brain',                  'Imaging',      4500,   0),
    ('CT Scan Head',               'Imaging',      3500,   0),
    ('Complete Blood Count (CBC)', 'Lab',           200,   0),
    ('Blood Sugar Fasting',        'Lab',           120,   0),
    ('Urine Routine',              'Lab',           100,   0),
    ('Lipid Profile',              'Lab',           500,   0),
    ('Thyroid Profile (T3T4TSH)',  'Lab',           800,   0),
    ('Appendicectomy',             'Surgery',     18000,   0),
    ('Caesarean Section',          'Surgery',     35000,   0),
    ('Hernia Repair',              'Surgery',     22000,   0),
    ('Cataract Surgery',           'Surgery',     15000,   0),
    ('LSCS + Tubal Ligation',      'Surgery',     40000,   0),
    ('General Ward (per day)',     'Bed Charge',   500,    0),
    ('Semi-Private Ward (per day)','Bed Charge',  1200,    0),
    ('Private Ward (per day)',     'Bed Charge',  2000,    0),
    ('ICU (per day)',               'Bed Charge', 3500,    0)
ON CONFLICT DO NOTHING;

-- ════════════════════════════════════════════════════════════════════════════
-- SEED DATA — Default wards
-- ════════════════════════════════════════════════════════════════════════════
INSERT INTO wards (ward_name, ward_type, total_beds, floor)
  VALUES
    ('General Male',    'General',   10, 'Ground'),
    ('General Female',  'General',   10, 'Ground'),
    ('Private',         'Private',    5, 'First'),
    ('ICU',             'ICU',        4, 'Ground'),
    ('Maternity',       'Maternity',  6, 'First'),
    ('Paediatrics',     'Paediatrics',5, 'Second')
ON CONFLICT DO NOTHING;

-- ════════════════════════════════════════════════════════════════════════════
-- SAAS PLATFORM TABLES
-- Added for multi-tenant SaaS billing, audit trail, and services catalogue
-- ════════════════════════════════════════════════════════════════════════════

-- ─── AUDIT LOG ────────────────────────────────────────────────────────────────
-- Per-tenant tamper-evident action log (tenant-level, not system-level alerts)
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    client_id   INTEGER,
    username    VARCHAR(80)  DEFAULT 'system',
    role        VARCHAR(20)  DEFAULT '',
    action      VARCHAR(200) NOT NULL,
    details     TEXT         DEFAULT '',
    ip_address  VARCHAR(45)  DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);

-- Add billing FK to discharge_summaries now that billing table exists
DO $fk$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name='fk_ds_billing' AND table_name='discharge_summaries'
  ) THEN
    ALTER TABLE discharge_summaries ADD CONSTRAINT fk_ds_billing
      FOREIGN KEY (bill_id) REFERENCES billing(id) ON DELETE SET NULL;
  END IF;
END $fk$;

-- ─── SERVICES CATALOGUE ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services_catalogue (
    service_id     SERIAL PRIMARY KEY,
    service_name   VARCHAR(200) NOT NULL,
    department     VARCHAR(100) DEFAULT '',
    default_price  NUMERIC(10,2) DEFAULT 0,
    tax_percentage NUMERIC(5,2)  DEFAULT 0,
    active         BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

