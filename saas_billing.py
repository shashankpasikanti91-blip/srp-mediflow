"""
saas_billing.py — SRP MediFlow SaaS Billing & Subscription
===========================================================
Manages:
  - Plan definitions: Starter / Professional / Enterprise
  - billing_accounts table  (per-client subscription record)
  - Access enforcement: restrict login when subscription expires
  - Auto-flag expired accounts
  - 30-day free trial for new clients

Tables used (created by create_saas_tables in db.py):
  billing_accounts

Usage
-----
    from saas_billing import get_billing_account, is_client_active, create_billing_account
    if not is_client_active(client_id=3):
        return {'error': 'Subscription expired — contact support'}, 403
"""

from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta, date
from typing import Optional

# ── Plan catalogue ────────────────────────────────────────────────────────────
PLANS: dict[str, dict] = {
    "starter": {
        "name":          "Starter",
        "price":         999,           # INR / month
        "billing_cycle": "monthly",
        "max_users":     5,
        "max_beds":      20,
        "features":      ["OPD", "Basic Billing", "Chatbot"],
        "description":   "Ideal for small clinics (≤ 20 beds)",
    },
    "professional": {
        "name":          "Professional",
        "price":         2499,
        "billing_cycle": "monthly",
        "max_users":     20,
        "max_beds":      100,
        "features":      [
            "OPD", "IPD", "Pharmacy", "Surgery",
            "GST Billing", "Analytics", "Data Export",
            "Telegram Alerts", "WhatsApp Gateway",
        ],
        "description":   "Full HMS for mid-size hospitals (≤ 100 beds)",
    },
    "enterprise": {
        "name":          "Enterprise",
        "price":         4999,
        "billing_cycle": "monthly",
        "max_users":     -1,            # unlimited
        "max_beds":      -1,
        "features":      [
            "All Professional features",
            "Multi-Branch Support", "Priority Support",
            "Custom Branding", "API Access", "SLA 99.9%",
        ],
        "description":   "Unlimited scale for large hospital chains",
    },
}

DEFAULT_TRIAL_DAYS = 30


def get_plan(plan_type: str) -> dict:
    """Return plan definition dict; defaults to 'starter' for unknown types."""
    return PLANS.get(plan_type.lower(), PLANS["starter"])


# ── DB helpers (lazy-import db to avoid circular dependency) ──────────────────
def _get_conn():
    import db
    return db.get_connection()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_billing_account(client_id: int) -> Optional[dict]:
    """Return billing_accounts row for client_id, or None."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM billing_accounts WHERE client_id = %s LIMIT 1",
            (client_id,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[billing] get_billing_account error: {exc}")
        try: conn.close()
        except: pass
        return None


def get_billing_account_by_slug(slug: str) -> Optional[dict]:
    """Look up billing account via client slug (joins clients ↔ billing_accounts)."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ba.* FROM billing_accounts ba
            JOIN clients c ON c.client_id = ba.client_id
            WHERE c.slug = %s LIMIT 1
        """, (slug,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[billing] get_billing_account_by_slug error: {exc}")
        try: conn.close()
        except: pass
        return None


def create_billing_account(
    client_id:  int,
    plan_name:  str = "starter",
    trial_days: int = DEFAULT_TRIAL_DAYS,
) -> Optional[dict]:
    """
    Create a billing_accounts record for a new client.
    Trial starts immediately; next_payment_date = today + trial_days.
    Returns the newly created row or None on error.
    """
    plan       = get_plan(plan_name)
    now        = datetime.now(timezone.utc)
    trial_end  = now + timedelta(days=trial_days)

    conn = _get_conn()
    if not conn:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO billing_accounts
                (client_id, plan_name, price, billing_cycle,
                 next_payment_date, payment_status, trial_end_date, created_at)
            VALUES
                (%s, %s, %s, %s, %s, 'trial', %s, NOW())
            ON CONFLICT (client_id) DO NOTHING
            RETURNING *
        """, (
            client_id,
            plan["name"],
            plan["price"],
            plan["billing_cycle"],
            trial_end.date(),
            trial_end.date(),
        ))
        row = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[billing] create_billing_account error: {exc}")
        try: conn.rollback(); conn.close()
        except: pass
        return None


def update_billing_status(
    client_id:        int,
    payment_status:   str,
    next_payment_date: Optional[str] = None,
    plan_name:         Optional[str] = None,
) -> bool:
    """
    Update payment_status and optionally next_payment_date / plan_name.
    payment_status values: 'trial' | 'paid' | 'expired' | 'suspended'
    """
    conn = _get_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        if plan_name and next_payment_date:
            cur.execute("""
                UPDATE billing_accounts
                   SET payment_status = %s, next_payment_date = %s, plan_name = %s
                 WHERE client_id = %s
            """, (payment_status, next_payment_date, plan_name, client_id))
        elif next_payment_date:
            cur.execute("""
                UPDATE billing_accounts
                   SET payment_status = %s, next_payment_date = %s
                 WHERE client_id = %s
            """, (payment_status, next_payment_date, client_id))
        else:
            cur.execute("""
                UPDATE billing_accounts
                   SET payment_status = %s
                 WHERE client_id = %s
            """, (payment_status, client_id))
        conn.commit()
        cur.close(); conn.close()
        return True
    except Exception as exc:
        print(f"[billing] update_billing_status error: {exc}")
        try: conn.rollback(); conn.close()
        except: pass
        return False


# ── Access enforcement ────────────────────────────────────────────────────────

def is_client_active(client_id: int) -> bool:
    """
    Return True if the client's subscription allows login.
    - No billing record → open access (not enforcing yet)
    - status 'suspended' → always blocked
    - next_payment_date in the past → blocked
    """
    acct = get_billing_account(client_id)
    if not acct:
        return True       # no billing row → not enforced yet

    status = (acct.get("payment_status") or "").lower()
    if status == "suspended":
        return False

    # Check expiry date
    expiry = acct.get("next_payment_date") or acct.get("trial_end_date")
    if expiry:
        if isinstance(expiry, str):
            try:
                expiry = date.fromisoformat(expiry)
            except Exception:
                return True
        if expiry < date.today():
            return False
    return True


# ── Bulk maintenance ──────────────────────────────────────────────────────────

def flag_expired_accounts() -> list[int]:
    """
    Mark billing_accounts.payment_status = 'expired' for all overdue accounts.
    Returns list of client_ids that were flagged.
    """
    conn = _get_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE billing_accounts
               SET payment_status = 'expired'
             WHERE next_payment_date < %s
               AND payment_status NOT IN ('paid', 'suspended', 'expired')
            RETURNING client_id
        """, (date.today(),))
        flagged = [r[0] for r in cur.fetchall()]
        conn.commit()
        cur.close(); conn.close()
        return flagged
    except Exception as exc:
        print(f"[billing] flag_expired_accounts error: {exc}")
        try: conn.rollback(); conn.close()
        except: pass
        return []


def list_billing_accounts() -> list[dict]:
    """Return all billing_accounts rows (for founder dashboard)."""
    conn = _get_conn()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ba.*, c.hospital_name, c.slug, c.city, c.is_active
              FROM billing_accounts ba
              LEFT JOIN clients c ON c.client_id = ba.client_id
             ORDER BY ba.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[billing] list_billing_accounts error: {exc}")
        return []
