"""
srp_mediflow_tenant.py
══════════════════════
SRP MediFlow – Multi-Tenant Hospital Provisioning
Each hospital client gets a dedicated PostgreSQL database.

Usage (CLI):
    python srp_mediflow_tenant.py --create --name "star_hospital" \
        --display "Star Hospital" --city "Kothagudem"

Usage (Python):
    from srp_mediflow_tenant import create_tenant_db, list_tenants
    create_tenant_db("sai_care_hospital", "Sai Care Hospital", "Khammam")
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import psycopg2
import psycopg2.extras
from pathlib import Path

# ── Admin (superuser) connection — used only for DB creation ──────────────────
ADMIN_DB_CONFIG = {
    "host":     os.getenv("PG_HOST",          "localhost"),
    "port":     int(os.getenv("PG_PORT",      "5434")),
    "dbname":   os.getenv("PG_ADMIN_DB",      "postgres"),
    "user":     os.getenv("PG_ADMIN_USER",    "ats_user"),
    "password": os.getenv("PG_ADMIN_PASS",    "ats_password"),
}

# Registry file that maps tenant slugs → connection details
TENANT_REGISTRY = Path(__file__).parent / "tenant_registry.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_registry() -> dict:
    if TENANT_REGISTRY.exists():
        with open(TENANT_REGISTRY, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_registry(data: dict):
    with open(TENANT_REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _slug(name: str) -> str:
    """Convert display name to safe DB/username slug."""
    import re
    return re.sub(r'[^a-z0-9_]', '_', name.lower().strip())[:30]


# ── Core: create a new tenant ─────────────────────────────────────────────────

def create_tenant_db(
    slug: str,
    display_name: str,
    city: str = '',
    phone: str = '',
    admin_username: str = 'admin',
    admin_password: str = 'hospital2024',
) -> dict:
    """
    1. Create a dedicated PostgreSQL database for the tenant.
    2. Run the full SRP MediFlow schema.
    3. Seed a default admin user.
    4. Register in tenant_registry.json.
    Returns connection info dict.
    """
    db_name  = f"srp_{slug}"
    db_user  = ADMIN_DB_CONFIG['user']     # reuse same DB user (simple setup)
    db_pass  = ADMIN_DB_CONFIG['password']
    host     = ADMIN_DB_CONFIG['host']
    port     = ADMIN_DB_CONFIG['port']

    registry = _load_registry()
    if slug in registry:
        print(f"ℹ️  Tenant '{slug}' already exists — skipping DB creation.")
        return registry[slug]

    # Step 1: create database (must use autocommit=True for CREATE DATABASE)
    try:
        conn = psycopg2.connect(**ADMIN_DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f'CREATE DATABASE "{db_name}"')
        cur.close(); conn.close()
        print(f"✅  Database '{db_name}' created.")
    except psycopg2.errors.DuplicateDatabase:
        print(f"ℹ️  Database '{db_name}' already exists — continuing schema setup.")
    except Exception as e:
        print(f"❌  Failed to create database: {e}")
        raise

    # Step 2: run schema
    tenant_conn_cfg = {
        "host": host, "port": port,
        "dbname": db_name, "user": db_user, "password": db_pass,
    }
    schema_path = Path(__file__).parent / "srp_mediflow_schema.sql"
    if schema_path.exists():
        with open(schema_path, encoding='utf-8') as f:
            schema_sql = f.read()
        try:
            tconn = psycopg2.connect(**tenant_conn_cfg)
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
            tcur = tconn.cursor()
            for stmt in statements:
                try:
                    tcur.execute(stmt)
                except Exception as e:
                    tconn.rollback()
                    tcur = tconn.cursor()
            tconn.commit()
            tcur.close(); tconn.close()
            print(f"✅  Schema applied to '{db_name}'.")
        except Exception as e:
            print(f"⚠️  Schema apply warning: {e}")
    else:
        print(f"⚠️  Schema file not found at {schema_path}. Skipping schema setup.")

    # Step 3: seed admin user
    try:
        import auth as auth_module
        pw_hash = auth_module.hash_password(admin_password)
        tconn = psycopg2.connect(**tenant_conn_cfg)
        tcur = tconn.cursor()
        tcur.execute(
            "INSERT INTO staff_users (username, password_hash, role, full_name) "
            "VALUES (%s,%s,'ADMIN','Hospital Administrator') ON CONFLICT DO NOTHING",
            (admin_username, pw_hash)
        )
        tconn.commit()
        tcur.close(); tconn.close()
        print(f"✅  Admin user '{admin_username}' created.")
    except Exception as e:
        print(f"⚠️  Admin user seed warning: {e}")

    # Step 4: register tenant
    tenant_info = {
        "slug":         slug,
        "display_name": display_name,
        "city":         city,
        "phone":        phone,
        "db_name":      db_name,
        "db_host":      host,
        "db_port":      port,
        "db_user":      db_user,
        "admin_user":   admin_username,
        "created_at":   __import__('datetime').datetime.now().isoformat(),
    }
    registry[slug] = tenant_info
    _save_registry(registry)
    print(f"✅  Tenant '{display_name}' registered in tenant_registry.json")
    print(f"    DB : {db_name}  |  Admin: {admin_username} / {admin_password}")
    return tenant_info


def list_tenants() -> list:
    """Return all registered tenants."""
    return list(_load_registry().values())


def get_tenant_db_config(slug: str) -> dict | None:
    """
    Return psycopg2 connection config for a specific tenant.
    Usage: psycopg2.connect(**get_tenant_db_config('star_hospital'))
    """
    registry = _load_registry()
    tenant = registry.get(slug)
    if not tenant:
        return None
    return {
        "host":     tenant['db_host'],
        "port":     tenant['db_port'],
        "dbname":   tenant['db_name'],
        "user":     tenant['db_user'],
        "password": ADMIN_DB_CONFIG['password'],
    }


def delete_tenant_db(slug: str, confirm: bool = False) -> bool:
    """
    Drop a tenant database and remove from registry.
    Requires confirm=True — irreversible!
    """
    if not confirm:
        print("⛔ Set confirm=True to drop a tenant database. This is IRREVERSIBLE.")
        return False
    registry = _load_registry()
    tenant = registry.pop(slug, None)
    if not tenant:
        print(f"❌  Tenant '{slug}' not found.")
        return False
    db_name = tenant['db_name']
    try:
        conn = psycopg2.connect(**ADMIN_DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()
        # Terminate open connections first
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            (db_name,)
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        cur.close(); conn.close()
        _save_registry(registry)
        print(f"✅  Tenant '{slug}' (DB: {db_name}) deleted.")
        return True
    except Exception as e:
        print(f"❌  Failed to delete tenant: {e}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="SRP MediFlow — Hospital Tenant Manager"
    )
    sub = parser.add_subparsers(dest='cmd')

    # create
    c = sub.add_parser('create', help='Provision a new hospital client DB')
    c.add_argument('--name',     required=True, help='Slug, e.g. star_hospital')
    c.add_argument('--display',  required=True, help='Display name, e.g. "Star Hospital"')
    c.add_argument('--city',     default='',    help='City')
    c.add_argument('--phone',    default='',    help='Main phone')
    c.add_argument('--admin-pw', default='hospital2024', help='Admin password')

    # list
    sub.add_parser('list', help='List all tenant hospitals')

    # delete
    d = sub.add_parser('delete', help='Delete a tenant DB (IRREVERSIBLE)')
    d.add_argument('--name', required=True, help='Slug to delete')
    d.add_argument('--confirm', action='store_true')

    args = parser.parse_args()

    if args.cmd == 'create':
        create_tenant_db(
            slug=_slug(args.name),
            display_name=args.display,
            city=args.city,
            phone=args.phone,
            admin_password=args.admin_pw,
        )
    elif args.cmd == 'list':
        tenants = list_tenants()
        if not tenants:
            print("No tenants registered yet.")
        else:
            print(f"\n{'Slug':<25} {'Display Name':<30} {'City':<20} {'DB Name'}")
            print('-' * 90)
            for t in tenants:
                print(f"{t['slug']:<25} {t['display_name']:<30} {t['city']:<20} {t['db_name']}")
    elif args.cmd == 'delete':
        delete_tenant_db(args.name, confirm=args.confirm)
    else:
        parser.print_help()


if __name__ == '__main__':
    _cli()
