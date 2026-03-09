-- =============================================================================
-- SRP MediFlow HMS v4 — Platform Database Schema
-- File: srp_platform_schema.sql
-- =============================================================================
-- Database: srp_platform_db  (created separately from all tenant databases)
--
-- ISOLATION RULES:
--   • This schema lives ONLY in srp_platform_db.
--   • It NEVER contains patient data.
--   • Tenant databases NEVER reference these tables.
--   • All founder / SaaS monitoring queries read from here only.
-- =============================================================================

-- ── clients: master registry of all hospital tenants ─────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id              SERIAL PRIMARY KEY,
    hospital_name   TEXT         NOT NULL,
    slug            TEXT         UNIQUE NOT NULL,
    city            TEXT         DEFAULT '',
    phone           TEXT         DEFAULT '',
    db_name         TEXT         DEFAULT '',       -- e.g. hospital_ai, srp_sai_care
    db_host         TEXT         DEFAULT 'localhost',
    db_port         INTEGER      DEFAULT 5434,
    db_user         TEXT         DEFAULT 'ats_user',
    admin_user      TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    status          TEXT         DEFAULT 'active', -- active | suspended | trial | expired
    last_activity   TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_slug ON clients (slug);

-- Example rows (DO NOT hard-code generated IDs in data migrations):
-- INSERT INTO clients (hospital_name, slug, city, db_name, status)
-- VALUES ('Star Hospital', 'star_hospital', 'Bhadradri Kothagudem', 'hospital_ai', 'active');

-- ── subscriptions: one billing record per client period ───────────────────────
CREATE TABLE IF NOT EXISTS subscriptions (
    id              SERIAL PRIMARY KEY,
    client_slug     TEXT         NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    plan            TEXT         DEFAULT 'starter',   -- starter | pro | enterprise
    status          TEXT         DEFAULT 'trial',     -- trial | active | expired | suspended
    start_date      DATE         DEFAULT CURRENT_DATE,
    expiry_date     DATE,
    amount_paid     NUMERIC(12,2) DEFAULT 0,
    currency        TEXT         DEFAULT 'INR',
    notes           TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_slug   ON subscriptions (client_slug);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions (status);

-- ── system_alerts: platform-level events (NO patient PII allowed) ─────────────
CREATE TABLE IF NOT EXISTS system_alerts (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT         NOT NULL,             -- e.g. BACKUP_FAILED, DB_UNREACHABLE
    message         TEXT         NOT NULL,
    severity        TEXT         DEFAULT 'info',       -- info | warning | critical
    client_slug     TEXT         DEFAULT NULL,          -- NULL = platform-wide alert
    resolved        BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_alerts_created  ON system_alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON system_alerts (severity);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON system_alerts (resolved);

-- ── audit_logs: platform-level audit trail (NO patient data) ──────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    actor           TEXT         NOT NULL,             -- username or 'system'
    action          TEXT         NOT NULL,             -- LOGIN | CLIENT_CREATED | BACKUP_OK …
    target          TEXT         DEFAULT '',
    ip_address      TEXT         DEFAULT '',
    client_slug     TEXT         DEFAULT NULL,
    details         TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor   ON audit_logs (actor);
CREATE INDEX IF NOT EXISTS idx_audit_action  ON audit_logs (action);

-- ── founder_accounts: platform owner login credentials ────────────────────────
-- Note: hospital staff accounts live in each tenant DB (staff_users table).
-- founder_accounts is ONLY for SaaS platform owners / SRP Technologies staff.
CREATE TABLE IF NOT EXISTS founder_accounts (
    id              SERIAL PRIMARY KEY,
    username        TEXT         UNIQUE NOT NULL,
    password_hash   TEXT         NOT NULL,             -- bcrypt hash
    email           TEXT         DEFAULT '',
    full_name       TEXT         DEFAULT '',
    is_active       BOOLEAN      DEFAULT TRUE,
    last_login      TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ── system_health: periodic tenant DB health snapshots ────────────────────────
CREATE TABLE IF NOT EXISTS system_health (
    id              SERIAL PRIMARY KEY,
    client_slug     TEXT         NOT NULL,
    db_status       TEXT         DEFAULT 'unknown',   -- connected | unreachable | error
    tables_present  BOOLEAN      DEFAULT FALSE,
    missing_tables  TEXT         DEFAULT '[]',         -- JSON array of missing table names
    checked_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_health_slug    ON system_health (client_slug);
CREATE INDEX IF NOT EXISTS idx_health_checked ON system_health (checked_at DESC);

-- =============================================================================
-- END OF PLATFORM SCHEMA
-- =============================================================================
-- Tenant databases (hospital_ai, srp_sai_care, srp_city_medical, …) are
-- created and managed by srp_mediflow_tenant.py using srp_mediflow_schema.sql.
-- They NEVER reference any table in this file.
-- =============================================================================
