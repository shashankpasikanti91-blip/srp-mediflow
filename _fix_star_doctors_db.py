#!/usr/bin/env python3
"""
_fix_star_doctors_db.py
=======================
Runs via paramiko SSH to Hetzner server.
Tasks:
  1. ALTER doctors table in all 5 tenant DBs — add qualification & registration_no columns
  2. Clean & re-seed Star Hospital (hospital_ai) with correct 3 real doctors only
  3. Leave other hospitals' doctor data intact (they keep fake seed doctors)
"""
import paramiko, sys

SERVER   = "5.223.67.236"
SSH_USER = "root"
SSH_PASS = "856Reey@nsh"
PG_PASS  = "ats_password"
PG_USER  = "ats_user"
PG_HOST  = "localhost"

DBS = [
    "hospital_ai",
    "srp_sai_care",
    "srp_city_medical",
    "srp_apollo_warangal",
    "srp_green_cross",
]

STAR_DOCTORS_SQL = """
-- Remove ALL doctors from Star Hospital
DELETE FROM doctors;

-- Insert the 3 REAL doctors with full details
INSERT INTO doctors (name, specialization, department, qualification, registration_no, phone, status, on_duty)
VALUES
  ('Dr. Sujan',
   'Orthopaedic Specialist',
   'Orthopaedics',
   'DNB Orthopaedics, FIJR',
   '87679',
   '',
   'available',
   false),
  ('Dr. K. Ramnath',
   'General Physician / Diabetes Specialist',
   'General Medicine',
   'General Medicine (UK), Diabetology',
   '111431',
   '',
   'available',
   false),
  ('Dr. B. Ramachandra Nayak',
   'General Surgeon',
   'General Surgery',
   'MBBS, MS – General Surgery',
   '13888',
   '',
   'available',
   false);
"""

ALTER_SQL = """
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS qualification   VARCHAR(200) DEFAULT '';
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS registration_no VARCHAR(30)  DEFAULT '';
"""


def psql_cmd(db: str, sql: str) -> str:
    sql_escaped = sql.replace("'", "'\\''").replace("\n", " ")
    return (
        f"PGPASSWORD={PG_PASS} psql -h {PG_HOST} -U {PG_USER} -d {db} "
        f"-c '{sql_escaped}' 2>&1"
    )


def run_via_heredoc(client: paramiko.SSHClient, db: str, sql: str) -> tuple[str, str]:
    """Run multi-statement SQL via heredoc to avoid quoting issues."""
    cmd = (
        f"PGPASSWORD={PG_PASS} psql -h {PG_HOST} -U {PG_USER} -d {db} <<'ENDSQL'\n"
        + sql
        + "\nENDSQL"
    )
    _, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode(), stderr.read().decode()


def main():
    print(f"[*] Connecting to {SERVER}…")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER, username=SSH_USER, password=SSH_PASS, timeout=15)
    print("[+] Connected\n")

    # ── STEP 1: ALTER all 5 DBs to add new columns ───────────────────────────
    print("=" * 60)
    print("STEP 1 — Adding qualification & registration_no columns")
    print("=" * 60)
    for db in DBS:
        out, err = run_via_heredoc(client, db, ALTER_SQL)
        status = "OK" if not err.strip() else "WARN"
        print(f"  [{status}] {db}")
        if err.strip():
            print(f"        STDERR: {err.strip()[:200]}")
        if out.strip():
            print(f"        OUT:    {out.strip()[:200]}")

    # ── STEP 2: Fix Star Hospital doctors ────────────────────────────────────
    print()
    print("=" * 60)
    print("STEP 2 — Fixing Star Hospital (hospital_ai) doctors")
    print("=" * 60)
    out, err = run_via_heredoc(client, "hospital_ai", STAR_DOCTORS_SQL)
    if err.strip():
        print(f"  [WARN] STDERR: {err.strip()[:400]}")
    else:
        print("  [OK] Star Hospital doctors cleaned & re-inserted")
    if out.strip():
        print(f"  OUT: {out.strip()[:400]}")

    # ── STEP 3: Verify ───────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("STEP 3 — Verification")
    print("=" * 60)
    verify_sql = "SELECT id, name, qualification, registration_no FROM doctors ORDER BY id;"
    out, err = run_via_heredoc(client, "hospital_ai", verify_sql)
    print("  Star Hospital current doctors:")
    print(out.strip() if out.strip() else "  (no output)")

    # Quick column check on all DBs
    col_sql = "SELECT column_name FROM information_schema.columns WHERE table_name='doctors' AND column_name IN ('qualification','registration_no') ORDER BY column_name;"
    for db in DBS:
        out, err = run_via_heredoc(client, db, col_sql)
        cols = out.count("qualification") + out.count("registration_no")
        print(f"  {db}: {cols}/2 new columns present")

    client.close()
    print("\n[+] Done!")


if __name__ == "__main__":
    main()
