"""
saas_onboarding.py — SRP MediFlow Automated Hospital Onboarding
===============================================================
Handles the full onboarding flow for a new hospital client.

POST /api/admin/register-client  →  calls  onboard_hospital()

Steps performed automatically:
  1. Validate input and generate unique client_id / subdomain
  2. Create dedicated PostgreSQL database (via srp_mediflow_tenant)
  3. Initialise full HMS schema (patients, doctors, pharmacy, billing …)
  4. Create the hospital's admin account
  5. Register hospital in clients table (master registry)
  6. Create billing_accounts record (30-day trial)
  7. Log onboarding event to system.log + audit_log
  8. Send founder alert (NEW_CLIENT_REGISTERED)

Usage
-----
    from saas_onboarding import onboard_hospital
    result = onboard_hospital({
        "hospital_name": "Sai Care Hospital",
        "subdomain":     "saicare",
        "admin_email":   "admin@saicare.com",
        "plan_type":     "professional",
        "city":          "Khammam",
    })
    if result['status'] == 'success':
        print(result['login_url'])
"""

from __future__ import annotations
import re
import secrets
import string
from datetime import datetime
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int = 30) -> str:
    """Convert display name or subdomain to a safe DB slug."""
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:max_len]


def _generate_password(length: int = 12) -> str:
    """Generate a random secure password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _validate_input(data: dict) -> Optional[str]:
    """Return error message string or None if valid."""
    if not data.get("hospital_name", "").strip():
        return "hospital_name is required"
    if not data.get("subdomain", "").strip():
        return "subdomain is required"
    subdomain = data["subdomain"].strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9\-]{1,28}[a-z0-9]$", subdomain):
        return ("subdomain must be 3-30 lowercase alphanumeric characters "
                "(hyphens allowed, not at start/end)")
    plan = data.get("plan_type", "starter").lower()
    if plan not in ("starter", "professional", "enterprise"):
        return f"plan_type must be starter | professional | enterprise (got '{plan}')"
    return None


# ── Core onboarding ───────────────────────────────────────────────────────────

def onboard_hospital(data: dict) -> dict:
    """
    Execute complete hospital onboarding flow.

    Parameters (from POST body JSON)
    ---------------------------------
    hospital_name   : str  — Display name, e.g. "Sai Care Hospital"
    subdomain       : str  — e.g. "saicare"  (used as DB slug)
    admin_email     : str  — Hospital admin email (informational for now)
    plan_type       : str  — starter | professional | enterprise
    city            : str  — optional
    state           : str  — optional
    phone           : str  — optional
    admin_username  : str  — default 'admin'
    admin_password  : str  — default auto-generated

    Returns
    -------
    dict with keys: status, client_id, slug, database, login_url,
                    admin_username, admin_password, plan, errors (on failure)
    """
    # ── 1. Validate ───────────────────────────────────────────────────────────
    err = _validate_input(data)
    if err:
        return {"status": "error", "error": err}

    hospital_name  = data["hospital_name"].strip()
    subdomain      = data["subdomain"].strip().lower().replace("-", "_")
    slug           = _slugify(subdomain)
    db_name        = f"srp_{slug}"
    plan_type      = data.get("plan_type", "starter").lower()
    city           = data.get("city", "").strip()
    state          = data.get("state", "").strip()
    phone          = data.get("phone", "").strip()
    admin_username = data.get("admin_username", "admin").strip() or "admin"
    admin_password = data.get("admin_password") or _generate_password()
    admin_email    = data.get("admin_email", "").strip()
    # subdomain: the short URL prefix for  <subdomain>.mediflow.srpailabs.com
    # If not provided, derive from subdomain input (strip underscores)
    subdomain_url  = data.get("subdomain_url", subdomain.replace('_', ''))[:20]
    import os as _os
    root_domain    = _os.getenv('ROOT_DOMAIN', 'mediflow.srpailabs.com')

    from saas_logging import system_log
    system_log.info(
        f"Onboarding started: hospital='{hospital_name}' slug='{slug}' "
        f"plan='{plan_type}' city='{city}'"
    )

    # ── 2. Create tenant database + schema + admin account ────────────────────
    tenant_result: dict = {}
    try:
        from srp_mediflow_tenant import create_tenant_db
        tenant_result = create_tenant_db(
            slug=slug,            subdomain=subdomain_url,            display_name=hospital_name,
            city=city,
            phone=phone,
            admin_username=admin_username,
            admin_password=admin_password,
        )
        system_log.info(f"Tenant DB created: db={db_name}")
    except Exception as exc:
        err_msg = f"Failed to create tenant database: {exc}"
        system_log.error(err_msg)
        return {"status": "error", "error": err_msg, "step": "tenant_db"}

    # ── 3. Register in master clients table ───────────────────────────────────
    client_row: Optional[dict] = None
    client_id: Optional[int]   = None
    try:
        import db
        if db.test_connection():
            client_row = db.create_client_record(
                slug=slug,
                hospital_name=hospital_name,
                hospital_phone=phone,
                hospital_address=data.get("address", ""),
                city=city,
                state=state,
                country=data.get("country", "India"),
                tagline=data.get("tagline", ""),
                database_name=db_name,
            )
            if client_row:
                client_id = client_row.get("client_id")
                system_log.info(f"Client registered: client_id={client_id} slug={slug}")
    except Exception as exc:
        system_log.warning(f"Could not register client in master DB: {exc}")

    # ── 4. Create billing account (trial) ─────────────────────────────────────
    billing_row: Optional[dict] = None
    if client_id:
        try:
            from saas_billing import create_billing_account
            billing_row = create_billing_account(
                client_id=client_id,
                plan_name=plan_type,
                trial_days=30,
            )
            system_log.info(f"Billing account created: client_id={client_id} plan={plan_type}")
        except Exception as exc:
            system_log.warning(f"Could not create billing account: {exc}")

    # ── 5. Write audit log ────────────────────────────────────────────────────
    try:
        import db as _db
        if _db.test_connection():
            _db.log_action(
                username="system",
                role="SYSTEM",
                action="hospital_onboarded",
                details=(
                    f"hospital='{hospital_name}' slug='{slug}' "
                    f"plan='{plan_type}' db='{db_name}' "
                    f"admin='{admin_username}' email='{admin_email}'"
                ),
                ip_address="localhost",
            )
    except Exception:
        pass

    # ── 6. Founder alert ──────────────────────────────────────────────────────
    try:
        from notifications.founder_alerts import send_founder_alert
        send_founder_alert(
            "NEW_CLIENT_REGISTERED",
            f"New hospital onboarded via /api/admin/register-client\n"
            f"Hospital : {hospital_name}\n"
            f"Slug     : {slug}\n"
            f"Database : {db_name}\n"
            f"Plan     : {plan_type}\n"
            f"Location : {city}, {state}\n"
            f"Admin    : {admin_username}\n"
            f"Email    : {admin_email or 'not provided'}"
        )
    except Exception:
        pass

    system_log.info(f"Onboarding complete: slug={slug} client_id={client_id}")

    return {
        "status":          "success",
        "client_id":       client_id,
        "slug":            slug,
        "subdomain":       subdomain_url,
        "hospital_name":   hospital_name,
        "database":        db_name,
        "plan":            plan_type,
        "login_url":       f"https://{subdomain_url}.{root_domain}/login",
        "admin_username":  admin_username,
        "admin_password":  admin_password,
        "admin_email":     admin_email,
        "trial_days":      30,
        "billing":         billing_row,
        "tenant_result":   tenant_result,
        "onboarded_at":    datetime.now().isoformat(),
    }
