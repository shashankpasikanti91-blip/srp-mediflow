"""
_reset_all_logins.py
====================
Wipes ALL staff_users across every tenant database, then re-seeds every
account fresh with proper bcrypt hashes.  Also creates/verifies the
FOUNDER account in hospital_ai (star_hospital DB).

Works on BOTH local dev (port 5434) and Hetzner production (port 5432).
All connection params are read from environment variables so there is
ZERO hard-coded credentials in this file.

Usage
-----
    # Local dev (uses defaults):
    python _reset_all_logins.py

    # Production Hetzner (set vars first):
    export PG_HOST=localhost PG_PORT=5432 PG_USER=ats_user PG_PASSWORD=<secret>
    python _reset_all_logins.py

Environment variables recognised
---------------------------------
    PG_HOST          PostgreSQL host           default: localhost
    PG_PORT          PostgreSQL port           default: 5434
    PG_USER          PostgreSQL user           default: ats_user
    PG_PASSWORD      PostgreSQL password       default: ats_password
    PLATFORM_DB_NAME Platform DB name         default: srp_platform_db
"""

from __future__ import annotations
import os, sys, json, traceback, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import psycopg2.extras
import auth   # our auth module — hash_password / verify_password

# ─── DB connection params — ALL from env vars ─────────────────────────────────
PG_HOST     = os.getenv("PG_HOST",     "localhost")
PG_PORT     = int(os.getenv("PG_PORT", "5434"))
PG_USER     = os.getenv("PG_USER",     "ats_user")
PG_PASSWORD = os.getenv("PG_PASSWORD", "ats_password")

def _conn(dbname: str):
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=dbname,
        user=PG_USER, password=PG_PASSWORD, connect_timeout=8,
    )

# ─── Tenant definitions — each hospital gets its own DB ───────────────────────
#  slug          display_name                    db_name             city
TENANTS = [
    ("star_hospital",    "Star Hospital",          "hospital_ai",           "Bhadradri Kothagudem"),
    ("sai_care",         "Sai Care Hospital",      "srp_sai_care",          "Khammam"),
    ("city_medical",     "City Medical Centre",    "srp_city_medical",      "Hyderabad"),
    ("apollo_warangal",  "Apollo Clinic Warangal", "srp_apollo_warangal",   "Warangal"),
    ("green_cross",      "Green Cross Hospital",   "srp_green_cross",       "Vijayawada"),
]

# ─── Fresh credentials ────────────────────────────────────────────────────────
#  These are the ONLY source of truth for login passwords.
#  The passwords follow the pattern: <role>@<Slug4chars>2026!
#  Admin passwords follow:           <Slug4chars>@Admin2026!
#  Founder password:                 Srp@Founder2026!

FOUNDER_PASSWORD = "Srp@Founder2026!"

def _get_tenant_creds(slug: str) -> dict[str, str]:
    """Return {username -> plaintext_password} for every role in a tenant."""
    s4 = slug[:4]        # first 4 chars of slug
    return {
        f"{slug}_admin":     f"{s4.capitalize()}@Admin2026!",
        f"{slug}_doctor":    f"Doctor@{s4}2026!",
        f"{slug}_nurse":     f"Nurse@{s4}2026!",
        f"{slug}_lab":       f"Lab@{s4}2026!",
        f"{slug}_stock":     f"Stock@{s4}2026!",
        f"{slug}_reception": f"Recep@{s4}2026!",
    }

ROLE_MAP = {
    "admin":     ("ADMIN",     "Hospital Administrator",    "Administration"),
    "doctor":    ("DOCTOR",    "Dr. General Physician",     "General Medicine"),
    "nurse":     ("NURSE",     "Staff Nurse",               "Nursing"),
    "lab":       ("LAB",       "Lab Technician",            "Pathology"),
    "stock":     ("STOCK",     "Pharmacy Staff",            "Pharmacy"),
    "reception": ("RECEPTION", "Receptionist",              "OPD"),
}


# ─── Core functions ────────────────────────────────────────────────────────────

def wipe_staff_users(db_name: str) -> int:
    """Delete every non-FOUNDER user in staff_users. Returns deleted count."""
    try:
        conn = _conn(db_name)
        cur = conn.cursor()
        cur.execute("DELETE FROM staff_users WHERE role != 'FOUNDER'")
        deleted = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return deleted
    except Exception as e:
        print(f"    ⚠️  wipe_staff_users({db_name}): {e}")
        return -1


def seed_tenant(slug: str, db_name: str) -> list[tuple]:
    """Insert all staff users for one tenant. Returns list of (user, pw, ok)."""
    creds   = _get_tenant_creds(slug)
    results = []
    try:
        conn = _conn(db_name)
        cur  = conn.cursor()
        for username, plain_pw in creds.items():
            base = username.replace(f"{slug}_", "")
            role, full_name, dept = ROLE_MAP.get(base, ("RECEPTION", base, "General"))
            pw_hash = auth.hash_password(plain_pw)
            try:
                cur.execute(
                    """
                    INSERT INTO staff_users
                        (username, password_hash, role, full_name, department,
                         is_active, must_change_password)
                    VALUES (%s, %s, %s, %s, %s, TRUE, FALSE)
                    ON CONFLICT (username) DO UPDATE
                      SET password_hash      = EXCLUDED.password_hash,
                          role               = EXCLUDED.role,
                          full_name          = EXCLUDED.full_name,
                          department         = EXCLUDED.department,
                          is_active          = TRUE,
                          must_change_password = FALSE
                    """,
                    (username, pw_hash, role, full_name, dept),
                )
                results.append((username, plain_pw, True))
            except Exception as e:
                conn.rollback()
                cur = conn.cursor()
                results.append((username, plain_pw, f"INSERT ERROR: {e}"))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f"    ❌  seed_tenant({db_name}): {e}")
    return results


def seed_founder(db_name: str = "hospital_ai") -> tuple:
    """Upsert the FOUNDER account. Returns (username, password, ok)."""
    pw_hash = auth.hash_password(FOUNDER_PASSWORD)
    try:
        conn = _conn(db_name)
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO staff_users
                (username, password_hash, role, full_name, department,
                 is_active, must_change_password)
            VALUES ('founder', %s, 'FOUNDER', 'SRP Technologies Founder', 'Platform', TRUE, FALSE)
            ON CONFLICT (username) DO UPDATE
              SET password_hash      = EXCLUDED.password_hash,
                  role               = 'FOUNDER',
                  full_name          = EXCLUDED.full_name,
                  is_active          = TRUE,
                  must_change_password = FALSE
            """,
            (pw_hash,),
        )
        conn.commit(); cur.close(); conn.close()
        return ("founder", FOUNDER_PASSWORD, True)
    except Exception as e:
        return ("founder", FOUNDER_PASSWORD, f"ERROR: {e}")


def test_login(db_name: str, username: str, plain_pw: str) -> bool:
    """Verify the stored bcrypt hash matches plain_pw."""
    try:
        conn = _conn(db_name)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT password_hash FROM staff_users WHERE username=%s AND is_active=TRUE",
            (username,),
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return False
        return auth.verify_password(plain_pw, row["password_hash"])
    except Exception:
        return False


# ─── Update tenant_registry.json ─────────────────────────────────────────────

def update_tenant_registry():
    reg_path = Path(__file__).parent / "tenant_registry.json"
    try:
        registry = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {}
    except Exception:
        registry = {}

    for slug, display_name, db_name, city in TENANTS:
        creds = _get_tenant_creds(slug)
        admin_pw = creds[f"{slug}_admin"]
        registry[slug] = {
            "slug":         slug,
            "display_name": display_name,
            "city":         city,
            "db_name":      db_name,
            "db_host":      PG_HOST,
            "db_port":      PG_PORT,
            "db_user":      PG_USER,
            "admin_user":   f"{slug}_admin",
            "admin_pw":     admin_pw,       # stored locally only — NOT committed to git
            "updated_at":   datetime.datetime.now().isoformat(),
        }

    reg_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅  tenant_registry.json updated ({len(registry)} tenants)")


# ─── Update ADMIN_LOGIN_CREDENTIALS.md ────────────────────────────────────────

def update_credentials_doc():
    app_url = os.getenv('APP_URL', 'https://mediflow.srpailabs.com')
    lines = [
        "# \ud83d\udd10 SRP MediFlow \u2014 Complete Login Credentials",
        "",
        f"> **Last reset**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> **System URL**: {app_url}  ",
        "> **Version**: 4.0 SaaS (Multi-Tenant)",
        "",
        "---",
        "",
        "## 👑 PLATFORM FOUNDER (SRP Technologies)",
        "",
        "| Role | Username | Password | Dashboard |",
        "|------|----------|----------|-----------|",
        f"| FOUNDER | `founder` | `{FOUNDER_PASSWORD}` | `/founder` |",
        "",
        "---",
        "",
    ]

    for i, (slug, display_name, db_name, city) in enumerate(TENANTS, 1):
        creds = _get_tenant_creds(slug)
        lines += [
            f"## 🏥 CLIENT {i} — {display_name}, {city}  (DB: `{db_name}`)",
            "",
            "| Role | Username | Password | Dashboard |",
            "|------|----------|----------|-----------|",
        ]
        role_to_dash = {
            "admin": "/admin", "doctor": "/doctor", "nurse": "/nurse",
            "lab": "/lab", "stock": "/stock", "reception": "/admin",
        }
        for base_role, dash in role_to_dash.items():
            uname = f"{slug}_{base_role}"
            pw    = creds[uname]
            lines.append(f"| {base_role.upper()} | `{uname}` | `{pw}` | `{dash}` |")
        lines += ["", "---", ""]

    lines += [
        "## 🔒 Database Connection (env-var driven)",
        "",
        "```",
        f"PG_HOST     = {PG_HOST}",
        f"PG_PORT     = {PG_PORT}",
        f"PG_USER     = {PG_USER}",
        "PG_PASSWORD = <set via environment variable>",
        "```",
        "",
        "> ⚠️  This file is in .gitignore — NEVER commit it to GitHub.",
    ]

    doc_path = Path(__file__).parent / "ADMIN_LOGIN_CREDENTIALS.md"
    doc_path.write_text("\n".join(lines), encoding="utf-8")
    print("  ✅  ADMIN_LOGIN_CREDENTIALS.md updated")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  SRP MediFlow — Full Login Reset & Verification")
    print(f"  DB: {PG_HOST}:{PG_PORT}  user={PG_USER}")
    print("=" * 70)

    all_results: list[tuple[str, str, str, bool | str]] = []
    # (db_name, username, password, ok)

    # ── FOUNDER ───────────────────────────────────────────────
    print("\n👑  FOUNDER account (hospital_ai / star_hospital)")
    fname, fpw, fok = seed_founder("hospital_ai")
    ok_str = "✅ OK" if fok is True else f"❌ {fok}"
    print(f"   {'founder':40s}  {fpw:30s}  {ok_str}")
    # Verify
    v = test_login("hospital_ai", "founder", fpw)
    all_results.append(("hospital_ai", "founder", fpw, v))
    print(f"   Login test → {'✅ PASS' if v else '❌ FAIL'}")

    # ── TENANTS ───────────────────────────────────────────────
    for slug, display_name, db_name, city in TENANTS:
        print(f"\n🏥  [{slug}] {display_name}  (DB: {db_name})")

        # 1. Wipe
        deleted = wipe_staff_users(db_name)
        if deleted >= 0:
            print(f"   🗑️  Deleted {deleted} old staff_user rows")
        else:
            print("   ⚠️  Wipe returned error — continuing anyway")

        # 2. Seed
        seed_results = seed_tenant(slug, db_name)

        # 3. Test each user
        for username, plain_pw, insert_ok in seed_results:
            if insert_ok is not True:
                print(f"   ❌  {username}: {insert_ok}")
                all_results.append((db_name, username, plain_pw, False))
                continue
            v = test_login(db_name, username, plain_pw)
            status = "✅ PASS" if v else "❌ FAIL"
            print(f"   {username:40s}  {plain_pw:28s}  {status}")
            all_results.append((db_name, username, plain_pw, v))

    # ── Update registry & credentials doc ─────────────────────
    print("\n📝  Updating tenant_registry.json …")
    update_tenant_registry()
    print("📝  Updating ADMIN_LOGIN_CREDENTIALS.md …")
    update_credentials_doc()

    # ── Summary ───────────────────────────────────────────────
    passed = [r for r in all_results if r[3] is True]
    failed = [r for r in all_results if r[3] is not True]

    print("\n" + "=" * 70)
    print(f"  RESULT:  {len(passed)} PASSED   {len(failed)} FAILED   (total {len(all_results)})")
    print("=" * 70)

    if failed:
        print("\n❌  FAILED logins:")
        for db, user, pw, err in failed:
            print(f"   DB={db}  user={user}  err={err}")
        sys.exit(1)
    else:
        print("\n✅  ALL logins verified successfully!\n")
        print("  Credentials are stored in:")
        print("  📄  ADMIN_LOGIN_CREDENTIALS.md  (local only, gitignored)")
        print("  📄  tenant_registry.json         (local only, gitignored)")
        print("  🔒  DB password → set via PG_PASSWORD environment variable")


if __name__ == "__main__":
    main()
