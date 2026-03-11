-- ============================================================
-- SRP MediFlow — Migration v5: Phase 6.1 Staff Attendance
-- File: migration_v5_phase61_attendance.sql
-- Date: 2026-03-11
-- ============================================================
-- Adds username + role columns to attendance table so self
-- check-in/checkout records are linked to login accounts.
-- Safe to re-run (uses ALTER TABLE IF NOT EXISTS style).
-- ============================================================

-- 1. Add username column if not present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='attendance' AND column_name='username'
  ) THEN
    ALTER TABLE attendance ADD COLUMN username VARCHAR(80) DEFAULT '';
  END IF;
END$$;

-- 2. Add role column if not present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='attendance' AND column_name='role'
  ) THEN
    ALTER TABLE attendance ADD COLUMN role VARCHAR(30) DEFAULT '';
  END IF;
END$$;

-- 3. Index for fast lookup by username + date (self-status API)
CREATE INDEX IF NOT EXISTS idx_attendance_username_date
  ON attendance (username, recorded_at);

-- 4. Ensure base table exists (in case this runs before initial setup)
CREATE TABLE IF NOT EXISTS attendance (
  id          SERIAL PRIMARY KEY,
  staff_name  VARCHAR(120) NOT NULL,
  username    VARCHAR(80)  DEFAULT '',
  role        VARCHAR(30)  DEFAULT '',
  action      VARCHAR(20)  NOT NULL DEFAULT 'checkin',
  notes       TEXT         DEFAULT '',
  recorded_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Done
SELECT 'migration_v5_phase61_attendance: OK' AS status;
