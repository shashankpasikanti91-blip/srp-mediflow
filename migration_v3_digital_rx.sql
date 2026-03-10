-- =============================================================================
-- SRP MediFlow v3 — Digital Prescription, Notification Service, Settings
-- Migration file: migration_v3_digital_rx.sql
-- Run once per tenant DB (and platform DB where noted)
-- =============================================================================

-- ─── 1. ENHANCE PRESCRIPTIONS TABLE ──────────────────────────────────────────
-- Add new columns to existing prescriptions table (all IF NOT EXISTS safe)

ALTER TABLE prescriptions
    ADD COLUMN IF NOT EXISTS visit_id          INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS patient_id        INTEGER REFERENCES patients(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS uhid              VARCHAR(20)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS chief_complaint   TEXT         DEFAULT '',
    ADD COLUMN IF NOT EXISTS symptoms          TEXT         DEFAULT '',
    ADD COLUMN IF NOT EXISTS clinical_notes    TEXT         DEFAULT '',
    ADD COLUMN IF NOT EXISTS bp                VARCHAR(20)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS temperature       VARCHAR(10)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS pulse             VARCHAR(10)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS spo2              VARCHAR(10)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS weight            VARCHAR(10)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS diet_advice       TEXT         DEFAULT '',
    ADD COLUMN IF NOT EXISTS special_instructions TEXT      DEFAULT '',
    ADD COLUMN IF NOT EXISTS follow_up_days    INTEGER      DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS follow_up_date    DATE         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS generated_pdf_path TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS created_by_doctor VARCHAR(150) DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_presc_visit_id    ON prescriptions (visit_id);
CREATE INDEX IF NOT EXISTS idx_presc_patient_id  ON prescriptions (patient_id);
CREATE INDEX IF NOT EXISTS idx_presc_doctor_user ON prescriptions (doctor_username);

-- ─── 2. ENHANCE PRESCRIPTION_ITEMS TABLE ─────────────────────────────────────
-- Add route column (Oral/IV/IM/Topical) and notes column

ALTER TABLE prescription_items
    ADD COLUMN IF NOT EXISTS route  VARCHAR(50) DEFAULT 'Oral',
    ADD COLUMN IF NOT EXISTS notes  TEXT        DEFAULT '';

-- ─── 3. FULL PRESCRIPTION_MEDICINES TABLE (NEW — replaces or supplements items)
-- Mirrors prescription_items but with full structured fields

CREATE TABLE IF NOT EXISTS prescription_medicines (
    id              SERIAL PRIMARY KEY,
    prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE CASCADE,
    medicine_name   VARCHAR(200) NOT NULL DEFAULT '',
    dose            VARCHAR(100) DEFAULT '',
    frequency       VARCHAR(100) DEFAULT '',   -- OD / BD / TID / QID / SOS / custom
    duration        VARCHAR(50)  DEFAULT '',   -- "5 days", "10 days", etc.
    route           VARCHAR(50)  DEFAULT 'Oral',
    notes           TEXT         DEFAULT '',
    sort_order      INTEGER      DEFAULT 0,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pm_prescription_id ON prescription_medicines (prescription_id);

-- ─── 4. LAB_ORDERS ENHANCEMENT ───────────────────────────────────────────────
-- Attach prescriptions and add urgency flag

ALTER TABLE lab_orders
    ADD COLUMN IF NOT EXISTS prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS patient_id      INTEGER REFERENCES patients(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS visit_id        INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS urgency         VARCHAR(20) DEFAULT 'routine',  -- routine / urgent / stat
    ADD COLUMN IF NOT EXISTS lab_notes       TEXT        DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_lo_prescription_id ON lab_orders (prescription_id);
CREATE INDEX IF NOT EXISTS idx_lo_patient_id      ON lab_orders (patient_id);
CREATE INDEX IF NOT EXISTS idx_lo_visit_id        ON lab_orders (visit_id);

-- ─── 5. NOTIFICATION SETTINGS TABLE ──────────────────────────────────────────
-- Stores tenant-level notification provider settings (per hospital)

CREATE TABLE IF NOT EXISTS notification_settings (
    id              SERIAL PRIMARY KEY,
    tenant_slug     VARCHAR(80)  DEFAULT '',
    setting_key     VARCHAR(100) NOT NULL,
    setting_value   TEXT         DEFAULT '',
    is_encrypted    BOOLEAN      DEFAULT FALSE,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_by      VARCHAR(80)  DEFAULT '',
    UNIQUE (tenant_slug, setting_key)
);

-- Default rows for a new tenant (safe to insert with ON CONFLICT DO NOTHING)
INSERT INTO notification_settings (tenant_slug, setting_key, setting_value) VALUES
    ('', 'active_provider',          'telegram'),
    ('', 'telegram_enabled',         'true'),
    ('', 'telegram_bot_token',       ''),
    ('', 'telegram_chat_id',         ''),
    ('', 'whatsapp_enabled',         'false'),
    ('', 'whatsapp_provider_name',   'twilio'),
    ('', 'whatsapp_api_base_url',    ''),
    ('', 'whatsapp_api_key',         ''),
    ('', 'whatsapp_sender_number',   ''),
    ('', 'whatsapp_template_id',     ''),
    ('', 'owner_contact_number',     ''),
    ('', 'patient_reminders_enabled','true'),
    ('', 'end_of_day_summary_enabled','true')
ON CONFLICT (tenant_slug, setting_key) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_ns_tenant_key ON notification_settings (tenant_slug, setting_key);

-- ─── 6. NOTIFICATION LOGS TABLE ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notification_logs (
    id               SERIAL PRIMARY KEY,
    tenant_slug      VARCHAR(80)  DEFAULT '',
    channel          VARCHAR(30)  DEFAULT '',   -- telegram / whatsapp / sms / none
    event_type       VARCHAR(80)  DEFAULT '',   -- appointment_created / rx_created / lab_ready …
    recipient        VARCHAR(150) DEFAULT '',
    message_preview  TEXT         DEFAULT '',
    status           VARCHAR(20)  DEFAULT 'sent',   -- sent / failed / skipped
    provider_response TEXT        DEFAULT '',
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nl_tenant     ON notification_logs (tenant_slug);
CREATE INDEX IF NOT EXISTS idx_nl_event      ON notification_logs (event_type);
CREATE INDEX IF NOT EXISTS idx_nl_created_at ON notification_logs (created_at DESC);

-- ─── 7. NOTIFICATION TEMPLATES TABLE ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notification_templates (
    id           SERIAL PRIMARY KEY,
    tenant_slug  VARCHAR(80)  DEFAULT '',
    template_key VARCHAR(80)  NOT NULL,
    subject      VARCHAR(200) DEFAULT '',
    body         TEXT         NOT NULL,
    variables    TEXT         DEFAULT '',   -- comma-separated list of supported vars
    is_active    BOOLEAN      DEFAULT TRUE,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_slug, template_key)
);

-- ─── Default templates ────────────────────────────────────────────────────────
INSERT INTO notification_templates (tenant_slug, template_key, subject, body, variables) VALUES
('', 'appointment_confirmation',
 'Appointment Confirmed',
 '🏥 *{hospital_name}*\n\nDear {patient_name}, your appointment is confirmed.\n📅 Date: {date}\n⏰ Time: {time}\n👨‍⚕️ Doctor: {doctor_name}\n\nPlease arrive 10 minutes early. Call {hospital_phone} for queries.',
 'hospital_name,patient_name,date,time,doctor_name,hospital_phone'
),
('', 'follow_up_reminder',
 'Follow-Up Reminder',
 '🏥 *{hospital_name}*\n\nDear {patient_name}, your follow-up is due today.\n👨‍⚕️ Dr. {doctor_name} advised follow-up on {follow_up_date}.\n\nCall {hospital_phone} to book.',
 'hospital_name,patient_name,doctor_name,follow_up_date,hospital_phone'
),
('', 'lab_report_ready',
 'Lab Report Ready',
 '🏥 *{hospital_name}*\n\nDear {patient_name}, your lab report for *{test_name}* is ready.\nPlease collect from the lab counter.\n\nCall {hospital_phone} for queries.',
 'hospital_name,patient_name,test_name,hospital_phone'
),
('', 'prescription_share',
 'Your Prescription',
 '🏥 *{hospital_name}*\n\nDear {patient_name}, your prescription from Dr. {doctor_name} is ready.\n📄 View/Download: {pdf_url}\n\nFollow the prescribed medicines carefully. Call {hospital_phone} for queries.',
 'hospital_name,patient_name,doctor_name,pdf_url,hospital_phone'
),
('', 'discharge_summary',
 'Discharge Summary',
 '🏥 *{hospital_name}*\n\nDear {patient_name}, you have been discharged on {discharge_date}.\nPlease follow the discharge instructions carefully.\nNext follow-up: {follow_up_date}\n\nCall {hospital_phone} for any concerns.',
 'hospital_name,patient_name,discharge_date,follow_up_date,hospital_phone'
),
('', 'owner_daily_summary',
 'Daily Summary — {date}',
 '📊 *{hospital_name} — Daily Report ({date})*\n\nOPD Patients: {opd_count}\nIPD Patients: {ipd_count}\nTotal Collections: ₹{collections}\nPending Bills: {pending_bills}\nNotifications Sent: {notif_count}\n\nPowered by SRP MediFlow',
 'hospital_name,date,opd_count,ipd_count,collections,pending_bills,notif_count'
)
ON CONFLICT (tenant_slug, template_key) DO NOTHING;

-- ─── 8. APPOINTMENTS ENHANCEMENT ─────────────────────────────────────────────
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS reminder_sent     BOOLEAN   DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reminder_sent_at  TIMESTAMP DEFAULT NULL;

-- ─── DONE ─────────────────────────────────────────────────────────────────────
-- Run: psql -U <user> -d <tenant_db> -f migration_v3_digital_rx.sql
