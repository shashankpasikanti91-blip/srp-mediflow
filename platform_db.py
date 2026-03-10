"""
platform_db.py  —  SRP MediFlow Platform Database
===================================================
Manages the PLATFORM-LEVEL PostgreSQL database (srp_platform_db).

ISOLATION RULES
───────────────
• This module ONLY connects to the platform database.
• It NEVER connects to any tenant (hospital) database.
• It NEVER stores or returns patient data.
• Tenant databases NEVER import from this module.

Schema tables (platform-only, no patient data):
  clients           — registered hospital clients (master registry)
  subscriptions     — subscription / billing plan records
  system_alerts     — platform-level alerts and events
  audit_logs        — platform audit trail (no patient data)
  founder_accounts  — founder / platform-owner credentials
  system_health     — periodic health snapshots per tenant

Usage
-----
    from platform_db import get_platform_conn, ensure_platform_schema
    from platform_db import get_all_clients, record_system_alert

    # Bootstrap (called once at server start)
    ensure_platform_schema()

    # Query
    clients = get_all_clients()          # list of dicts, no patient data
    record_system_alert('BACKUP_OK', 'All databases backed up successfully')
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import psycopg2
import psycopg2.extras

# ── Platform DB connection config ─────────────────────────────────────────────
#    Lives in a SEPARATE database from any hospital/tenant database.
#    Default name: srp_platform_db  (override with env var PLATFORM_DB_NAME)
PLATFORM_DB_CONFIG: dict[str, Any] = {
    "host":            os.getenv("PG_HOST",          "localhost"),
    "port":            int(os.getenv("PG_PORT",      "5432")),
    "dbname":          os.getenv("PLATFORM_DB_NAME", "srp_platform_db"),
    "user":            os.getenv("PG_USER",          "ats_user"),
    "password":        os.getenv("PG_PASSWORD",      "ats_password"),
    "connect_timeout": 5,
}

# Bootstrap file — used to sync tenant_registry.json → platform_db on first run
_BASE_DIR        = Path(__file__).parent
_REGISTRY_PATH   = _BASE_DIR / "tenant_registry.json"
_PLATFORM_READY  = threading.Event()     # set once schema bootstrap succeeds
_bootstrap_lock  = threading.Lock()


# ── Low-level connection helpers ──────────────────────────────────────────────

@contextmanager
def get_platform_conn():
    """
    Context manager: yields a psycopg2 connection to the PLATFORM database.
    Commits on clean exit, rolls back on exception.
    NEVER connects to a tenant database.
    """
    conn = psycopg2.connect(**PLATFORM_DB_CONFIG)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_platform_connection() -> bool:
    """Return True if the platform database is reachable."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        return True
    except Exception:
        return False


# ── Schema bootstrap ──────────────────────────────────────────────────────────

_PLATFORM_SCHEMA_SQL = """
-- ── clients: master registry of all hospital tenants ─────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id              SERIAL PRIMARY KEY,
    hospital_name   TEXT         NOT NULL,
    slug            TEXT         UNIQUE NOT NULL,
    subdomain       TEXT         DEFAULT '',    -- short URL prefix e.g. 'star' for star.mediflow.srpailabs.com
    city            TEXT         DEFAULT '',
    phone           TEXT         DEFAULT '',
    db_name         TEXT         DEFAULT '',
    db_host         TEXT         DEFAULT 'localhost',
    db_port         INTEGER      DEFAULT 5432,
    db_user         TEXT         DEFAULT 'ats_user',
    admin_user      TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    status          TEXT         DEFAULT 'active',
    last_activity   TIMESTAMP
);
-- Migration: add subdomain column FIRST (must run before index creation)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS subdomain TEXT DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_slug      ON clients (slug);
CREATE INDEX        IF NOT EXISTS idx_clients_subdomain ON clients (subdomain);

-- ── subscriptions: one row per client billing period ─────────────────────────
CREATE TABLE IF NOT EXISTS subscriptions (
    id              SERIAL PRIMARY KEY,
    client_slug     TEXT         NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    plan            TEXT         DEFAULT 'starter',
    status          TEXT         DEFAULT 'trial',   -- trial | active | expired | suspended
    start_date      DATE         DEFAULT CURRENT_DATE,
    expiry_date     DATE,
    amount_paid     NUMERIC(12,2) DEFAULT 0,
    currency        TEXT         DEFAULT 'INR',
    notes           TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_slug ON subscriptions (client_slug);

-- ── system_alerts: platform-level events (no patient PII) ────────────────────
CREATE TABLE IF NOT EXISTS system_alerts (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT         NOT NULL,
    message         TEXT         NOT NULL,
    severity        TEXT         DEFAULT 'info',    -- info | warning | critical
    client_slug     TEXT         DEFAULT NULL,       -- NULL = platform-wide
    resolved        BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON system_alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON system_alerts (severity);

-- ── audit_logs: platform-level audit trail (no patient data) ─────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    actor           TEXT         NOT NULL,          -- username / system
    action          TEXT         NOT NULL,          -- e.g. LOGIN, CLIENT_CREATED
    target          TEXT         DEFAULT '',        -- what was acted on
    ip_address      TEXT         DEFAULT '',
    client_slug     TEXT         DEFAULT NULL,
    details         TEXT         DEFAULT '',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor   ON audit_logs (actor);

-- ── founder_accounts: platform owner credentials ──────────────────────────────
CREATE TABLE IF NOT EXISTS founder_accounts (
    id              SERIAL PRIMARY KEY,
    username        TEXT         UNIQUE NOT NULL,
    password_hash   TEXT         NOT NULL,
    email           TEXT         DEFAULT '',
    full_name       TEXT         DEFAULT '',
    is_active       BOOLEAN      DEFAULT TRUE,
    last_login      TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ── system_health: periodic snapshot per client ───────────────────────────────
CREATE TABLE IF NOT EXISTS system_health (
    id              SERIAL PRIMARY KEY,
    client_slug     TEXT         NOT NULL,
    db_status       TEXT         DEFAULT 'unknown', -- connected | unreachable | error
    tables_present  BOOLEAN      DEFAULT FALSE,
    missing_tables  TEXT         DEFAULT '[]',      -- JSON array
    checked_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_health_slug    ON system_health (client_slug);
CREATE INDEX IF NOT EXISTS idx_health_checked ON system_health (checked_at DESC);
"""


def ensure_platform_schema() -> bool:
    """
    Create the platform database and all required tables if they don't exist.
    Safe to call on every server start (fully idempotent).
    Returns True on success, False on failure.
    """
    with _bootstrap_lock:
        # Step 1: ensure the database itself exists
        admin_cfg = dict(PLATFORM_DB_CONFIG)
        admin_cfg["dbname"] = os.getenv("PG_ADMIN_DB", "postgres")
        target_db = PLATFORM_DB_CONFIG["dbname"]

        try:
            conn = psycopg2.connect(**admin_cfg)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{target_db}"')
                print(f"[platform_db] Created database '{target_db}'")
            else:
                print(f"[platform_db] Database '{target_db}' already exists — skipping creation")
            cur.close()
            conn.close()
        except Exception as exc:
            print(f"[platform_db] WARNING: could not check/create database '{target_db}': {exc}")
            # Non-fatal: database may already exist and we just can't detect it

        # Step 2: run schema DDL
        try:
            with get_platform_conn() as conn:
                cur = conn.cursor()
                statements = [s.strip() for s in _PLATFORM_SCHEMA_SQL.split(';') if s.strip()]
                for stmt in statements:
                    cur.execute(stmt)
                cur.close()
            print(f"[platform_db] Schema bootstrap complete on '{target_db}'")
            _PLATFORM_READY.set()
            return True
        except Exception as exc:
            print(f"[platform_db] Schema bootstrap failed: {exc}")
            return False


# ── Client registry helpers ───────────────────────────────────────────────────

def get_all_clients() -> list[dict]:
    """
    Return all registered hospital clients from the platform database.
    No patient data is ever included.
    Fields: id, hospital_name, slug, city, phone, db_name, db_host, db_port,
            status, created_at, last_activity
    """
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, hospital_name, slug, subdomain, city, phone,
                       db_name, db_host, db_port,
                       status, created_at, last_activity
                  FROM clients
                 ORDER BY hospital_name
            """)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        return rows
    except Exception as exc:
        print(f"[platform_db] get_all_clients error: {exc}")
        return []


def get_client(slug: str) -> Optional[dict]:
    """Return a single client record by slug. No patient data."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM clients WHERE slug = %s",
                (slug,)
            )
            row = cur.fetchone()
            cur.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[platform_db] get_client({slug}) error: {exc}")
        return None


def upsert_client(
    slug: str,
    hospital_name: str,
    subdomain: str = '',
    city: str = '',
    phone: str = '',
    db_name: str = '',
    db_host: str = 'localhost',
    db_port: int = 5432,
    db_user: str = 'ats_user',
    admin_user: str = '',
    status: str = 'active',
) -> bool:
    """
    Insert or update a client record in the platform database.
    Called by the tenant provisioning module after creating a new hospital DB.
    subdomain is the short URL prefix used in  <subdomain>.mediflow.srpailabs.com
    """
    # Default subdomain to slug if not provided
    if not subdomain:
        subdomain = slug.replace('_', '')[:20]
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO clients
                    (slug, subdomain, hospital_name, city, phone, db_name, db_host, db_port,
                     db_user, admin_user, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                    subdomain     = EXCLUDED.subdomain,
                    hospital_name = EXCLUDED.hospital_name,
                    city          = EXCLUDED.city,
                    phone         = EXCLUDED.phone,
                    db_name       = EXCLUDED.db_name,
                    db_host       = EXCLUDED.db_host,
                    db_port       = EXCLUDED.db_port,
                    db_user       = EXCLUDED.db_user,
                    admin_user    = EXCLUDED.admin_user,
                    status        = EXCLUDED.status
            """, (
                slug, subdomain, hospital_name, city, phone, db_name,
                db_host, db_port, db_user, admin_user, status,
            ))
            cur.close()
        return True
    except Exception as exc:
        print(f"[platform_db] upsert_client({slug}) error: {exc}")
        return False


def get_client_by_subdomain(subdomain: str) -> Optional[dict]:
    """
    Return a single client record by its short subdomain label.
    Used by the tenant router to resolve   star  →  star_hospital  etc.
    """
    if not subdomain:
        return None
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM clients WHERE subdomain = %s AND status != 'deleted' LIMIT 1",
                (subdomain.lower().strip(),)
            )
            row = cur.fetchone()
            cur.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[platform_db] get_client_by_subdomain({subdomain}) error: {exc}")
        return None


def update_client_activity(slug: str) -> None:
    """Update the last_activity timestamp for a client."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE clients SET last_activity = CURRENT_TIMESTAMP WHERE slug = %s",
                (slug,)
            )
            cur.close()
    except Exception:
        pass


def get_tenant_connection_params(slug: str) -> Optional[dict]:
    """
    Return psycopg2 connection parameters for a tenant slug by querying
    the platform database.  This is the authoritative source for tenant
    connection info and supports future multi-server deployments.
    Returns None if slug not found.
    """
    client = get_client(slug)
    if not client:
        return None
    return {
        "host":            client.get("db_host", "localhost"),
        "port":            int(client.get("db_port", 5432)),
        "dbname":          client.get("db_name")    or f"srp_{slug}",
        "user":            client.get("db_user")    or "ats_user",
        "password":        os.getenv("PG_PASSWORD", "ats_password"),
        "connect_timeout": 5,
    }


# ── Subscription helpers ──────────────────────────────────────────────────────

def get_subscription(slug: str) -> Optional[dict]:
    """Return the active subscription record for a client slug."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM subscriptions
                 WHERE client_slug = %s
                 ORDER BY created_at DESC
                 LIMIT 1
            """, (slug,))
            row = cur.fetchone()
            cur.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[platform_db] get_subscription({slug}) error: {exc}")
        return None


def upsert_subscription(
    slug: str,
    plan: str = 'starter',
    status: str = 'trial',
    expiry_date: Optional[date] = None,
    amount_paid: float = 0.0,
    notes: str = '',
) -> bool:
    """Insert or update the latest subscription record for a client."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO subscriptions (client_slug, plan, status, expiry_date, amount_paid, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (slug, plan, status, expiry_date, amount_paid, notes))
            cur.close()
        return True
    except Exception as exc:
        print(f"[platform_db] upsert_subscription({slug}) error: {exc}")
        return False


# ── System alerts ─────────────────────────────────────────────────────────────

def record_system_alert(
    event_type: str,
    message: str,
    severity: str = 'info',
    client_slug: Optional[str] = None,
) -> None:
    """
    Write a platform-level alert to the system_alerts table.
    Silently swallows errors so it never interrupts server operation.
    NO patient data must be included in event_type or message.
    """
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO system_alerts (event_type, message, severity, client_slug)
                VALUES (%s, %s, %s, %s)
            """, (event_type, message, severity, client_slug))
            cur.close()
    except Exception:
        pass


def get_recent_alerts(limit: int = 20) -> list[dict]:
    """Return the most recent platform alerts (no patient data)."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, event_type, message, severity, client_slug, resolved, created_at
                  FROM system_alerts
                 ORDER BY created_at DESC
                 LIMIT %s
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        return rows
    except Exception as exc:
        print(f"[platform_db] get_recent_alerts error: {exc}")
        return []


def count_open_alerts() -> int:
    """Return count of unresolved system alerts."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM system_alerts WHERE resolved = FALSE")
            count = cur.fetchone()[0]
            cur.close()
        return count
    except Exception:
        return 0


# ── Audit log ─────────────────────────────────────────────────────────────────

def write_audit_log(
    actor: str,
    action: str,
    target: str = '',
    ip_address: str = '',
    client_slug: Optional[str] = None,
    details: str = '',
) -> None:
    """
    Write a platform-level audit entry.
    MUST NOT contain any patient data.
    """
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO audit_logs (actor, action, target, ip_address, client_slug, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (actor, action, target, ip_address, client_slug, details))
            cur.close()
    except Exception:
        pass


# ── System health snapshots ───────────────────────────────────────────────────

def record_health_snapshot(
    slug: str,
    db_status: str,
    tables_present: bool,
    missing_tables: list[str],
) -> None:
    """Record a health check snapshot for a client into the platform DB."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO system_health (client_slug, db_status, tables_present, missing_tables)
                VALUES (%s, %s, %s, %s)
            """, (slug, db_status, tables_present, json.dumps(missing_tables)))
            cur.close()
    except Exception:
        pass


def get_latest_health(slug: str) -> Optional[dict]:
    """Return the most recent health snapshot for a client."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT * FROM system_health
                 WHERE client_slug = %s
                 ORDER BY checked_at DESC
                 LIMIT 1
            """, (slug,))
            row = cur.fetchone()
            cur.close()
        return dict(row) if row else None
    except Exception:
        return None


# ── Summary metrics (founder dashboard only) ──────────────────────────────────

def get_platform_metrics() -> dict:
    """
    Return aggregate counts for the founder dashboard.
    Reads ONLY from the platform database — no tenant data.
    Returns:
        total_hospitals, active_hospitals, trial_hospitals,
        expired_hospitals, open_alerts, total_subscriptions
    """
    metrics = {
        "total_hospitals":   0,
        "active_hospitals":  0,
        "trial_hospitals":   0,
        "expired_hospitals": 0,
        "suspended_hospitals": 0,
        "open_alerts":       0,
        "total_subscriptions": 0,
    }
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()

            # Client counts by status
            cur.execute("""
                SELECT status, COUNT(*) AS n
                  FROM clients
                 GROUP BY status
            """)
            for row in cur.fetchall():
                status, n = row
                metrics["total_hospitals"] += n
                key = f"{status}_hospitals"
                if key in metrics:
                    metrics[key] = n

            # Open alerts
            cur.execute("SELECT COUNT(*) FROM system_alerts WHERE resolved = FALSE")
            metrics["open_alerts"] = cur.fetchone()[0]

            # Total subscriptions
            cur.execute("SELECT COUNT(*) FROM subscriptions")
            metrics["total_subscriptions"] = cur.fetchone()[0]

            cur.close()
    except Exception as exc:
        print(f"[platform_db] get_platform_metrics error: {exc}")
    return metrics


# ── Sync: tenant_registry.json → platform_db ─────────────────────────────────

def sync_registry_to_platform_db() -> int:
    """
    One-way sync: reads tenant_registry.json and upserts every entry
    into the platform_db.clients table.
    Returns the number of clients synced.
    Called at server startup to populate the platform DB from the file registry.
    """
    if not _REGISTRY_PATH.exists():
        return 0
    try:
        with open(_REGISTRY_PATH, encoding='utf-8') as f:
            registry: dict = json.load(f)
    except Exception as exc:
        print(f"[platform_db] Could not read tenant_registry.json: {exc}")
        return 0

    count = 0
    for slug, info in registry.items():
        ok = upsert_client(
            slug         = slug,
            hospital_name= info.get('display_name', slug),
            city         = info.get('city', ''),
            phone        = info.get('phone', ''),
            db_name      = info.get('db_name', f'srp_{slug}'),
            db_host      = info.get('db_host', 'localhost'),
            db_port      = int(info.get('db_port', 5432)),
            db_user      = info.get('db_user', 'ats_user'),
            admin_user   = info.get('admin_user', ''),
            status       = info.get('status', 'active'),
        )
        if ok:
            count += 1
    print(f"[platform_db] Synced {count}/{len(registry)} clients from tenant_registry.json")
    return count


# ── Health check for all tenants (used by /api/founder/system-status) ─────────

_REQUIRED_TENANT_TABLES = {
    'staff_users', 'patients', 'appointments', 'billing',
    'inventory_stock',
}


def check_all_tenants_health() -> list[dict]:
    """
    Connect to each registered tenant database and verify connectivity +
    required tables.  Results are saved to platform_db.system_health and
    returned as a list of dicts.

    Each dict contains:
        slug, hospital_name, db_status, tables_present, missing_tables,
        last_activity, checked_at
    NO patient data is ever read.
    """
    clients = get_all_clients()
    results = []

    for client in clients:
        slug      = client['slug']
        db_name   = client.get('db_name') or f"srp_{slug}"
        db_host   = client.get('db_host', 'localhost')
        db_port   = int(client.get('db_port', 5432))

        cfg = {
            "host":            db_host,
            "port":            db_port,
            "dbname":          db_name,
            "user":            os.getenv("PG_USER", "ats_user"),
            "password":        os.getenv("PG_PASSWORD", "ats_password"),
            "connect_timeout": 3,
        }

        db_status      = 'unreachable'
        tables_present = False
        missing        = list(_REQUIRED_TENANT_TABLES)
        last_activity  = None

        try:
            conn = psycopg2.connect(**cfg)
            conn.autocommit = True
            cur  = conn.cursor()

            # Table existence
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
            existing = {r[0] for r in cur.fetchall()}
            missing  = sorted(_REQUIRED_TENANT_TABLES - existing)
            tables_present = len(missing) == 0
            db_status = 'connected'

            # Last audit activity (timestamp only, no patient data)
            if 'audit_log' in existing:
                cur.execute("SELECT MAX(created_at) FROM audit_log")
                row = cur.fetchone()
                if row and row[0]:
                    last_activity = str(row[0])

            cur.close()
            conn.close()
        except Exception as exc:
            db_status = 'error'
            print(f"[platform_db] Health check failed for '{slug}' / '{db_name}': {exc}")

        # Persist snapshot to platform_db
        record_health_snapshot(slug, db_status, tables_present, missing)
        # Update last_activity on clients table if we got a live timestamp
        if last_activity:
            try:
                with get_platform_conn() as pconn:
                    pcur = pconn.cursor()
                    pcur.execute(
                        "UPDATE clients SET last_activity = %s WHERE slug = %s",
                        (last_activity, slug)
                    )
                    pcur.close()
            except Exception:
                pass

        results.append({
            'slug':          slug,
            'hospital_name': client.get('hospital_name', slug),
            'city':          client.get('city', ''),
            'db_name':       db_name,
            'db_status':     db_status,
            'tables_present': tables_present,
            'missing_tables': missing,
            'last_activity':  last_activity,
            'checked_at':     datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — FOUNDER / PLATFORM OWNER
# These functions operate on founder_accounts in srp_platform_db ONLY.
# Founder credentials NEVER live in any tenant (hospital) DB.
# ═══════════════════════════════════════════════════════════════════════════════

def get_founder_by_username(username: str) -> Optional[dict]:
    """
    Return a founder account record from the PLATFORM database.
    This is the authoritative lookup for FOUNDER-layer authentication.
    NEVER searches tenant (hospital) databases.
    """
    if not username:
        return None
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM founder_accounts WHERE username = %s AND is_active = TRUE LIMIT 1",
                (username.strip().lower(),)
            )
            row = cur.fetchone()
            cur.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[platform_db] get_founder_by_username({username!r}) error: {exc}")
        return None


def upsert_founder(
    username: str,
    password_hash: str,
    full_name: str = 'SRP Technologies Founder',
    email: str = '',
) -> bool:
    """
    Insert or update a founder account in the PLATFORM database.
    Called by setup_logins.py during initial setup / password reset.
    """
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO founder_accounts
                    (username, password_hash, full_name, email, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (username) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    full_name     = EXCLUDED.full_name,
                    email         = EXCLUDED.email,
                    is_active     = TRUE
            """, (username.strip().lower(), password_hash, full_name, email))
            cur.close()
        return True
    except Exception as exc:
        print(f"[platform_db] upsert_founder({username!r}) error: {exc}")
        return False


def update_founder_password(username: str, new_hash: str) -> bool:
    """Update founder password hash in the platform database."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE founder_accounts SET password_hash = %s WHERE username = %s",
                (new_hash, username.strip().lower())
            )
            updated = cur.rowcount
            cur.close()
        return updated > 0
    except Exception as exc:
        print(f"[platform_db] update_founder_password({username!r}) error: {exc}")
        return False


def update_founder_last_login(username: str) -> None:
    """Stamp last_login for a founder account after successful authentication."""
    try:
        with get_platform_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE founder_accounts SET last_login = CURRENT_TIMESTAMP WHERE username = %s",
                (username.strip().lower(),)
            )
            cur.close()
    except Exception:
        pass  # Non-fatal


# ── Convenience bootstrap called from server at startup ───────────────────────

def init_platform() -> bool:
    """
    Full platform DB init sequence:
      1. Ensure schema exists
      2. Sync tenant_registry.json → clients table
    Returns True if platform DB is ready.
    """
    ok = ensure_platform_schema()
    if ok:
        sync_registry_to_platform_db()
    return ok
