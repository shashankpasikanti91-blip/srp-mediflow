-- ════════════════════════════════════════════════════════════════════════════
--  SRP MediFlow HMS – Security Migration v2
--  Feature : Force Password Change on First Login
--  Date    : 2026-03-09
-- ════════════════════════════════════════════════════════════════════════════
--
--  APPLY TO: every tenant database (srp_<slug>) AND the default hospital_ai DB
--
--  STEP 1 – Run this file once per database:
--    psql -h localhost -p 5434 -U ats_user -d hospital_ai -f migration_security_v2_must_change_password.sql
--    psql -h localhost -p 5434 -U ats_user -d srp_star_hospital -f migration_security_v2_must_change_password.sql
--    (repeat for every tenant DB in tenant_registry.json)
--
--  STEP 2 – Restart srp_mediflow_server.py
--    The server now returns {"status":"password_change_required"} on first login
--    and exposes POST /api/change-password to complete the flow.
-- ════════════════════════════════════════════════════════════════════════════

-- 1. Add must_change_password column to existing staff_users tables
--    (IF NOT EXISTS is safe to run multiple times)
ALTER TABLE staff_users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT TRUE;

-- 2. All existing accounts that do NOT yet have a flag set explicitly
--    should require a password change.  Accounts that were already
--    updated (FALSE) are not touched.
UPDATE staff_users
    SET must_change_password = TRUE
    WHERE must_change_password IS NULL;

-- 3. Verify
SELECT id, username, role, must_change_password
FROM   staff_users
ORDER  BY role, username;

-- ════════════════════════════════════════════════════════════════════════════
--  NOTES
--  ─────
--  • password_hash TEXT  — already in place since v1 (no plain passwords stored)
--  • bcrypt is used for all new hashes; legacy SHA-256 hashes continue to work
--    via the fallback path in auth.verify_password()
--  • After a user changes their password the column is set to FALSE
--    (handled by db.update_password() → POST /api/change-password)
-- ════════════════════════════════════════════════════════════════════════════
