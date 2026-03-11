"""
auth.py - Role-Based Authentication Module
Handles: password hashing, session tokens, session validation,
         account lockout (3 failed attempts → 15 min lock),
         password-reset OTP system.
Supports bcrypt (preferred) with SHA-256 fallback if bcrypt not installed.
"""

import secrets
import hashlib
import random
import time
import json
import os
from typing import Optional

try:
    import bcrypt
    _BCRYPT = True
except ImportError:
    _BCRYPT = False
    print("⚠️  bcrypt not installed — using SHA-256 fallback.  Run: pip install bcrypt")

# ── In-memory session store (primary, fast) ───────────────────────────────────
_sessions: dict = {}
SESSION_TTL = 8 * 3600  # 8 hours

# ── PostgreSQL-backed session + lockout persistence (survives restarts) ────────
try:
    import psycopg2 as _pg2
    _PG_SESSION = True
except ImportError:
    _pg2 = None
    _PG_SESSION = False

def _pg_conn():
    """Return a psycopg2 connection to the platform DB, or None on error."""
    if not _PG_SESSION:
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return _pg2.connect(
            host=os.getenv('PG_HOST', 'localhost'),
            port=int(os.getenv('PG_PORT', 5432)),
            dbname=os.getenv('PLATFORM_DB', 'srp_platform_db'),
            user=os.getenv('PG_USER', 'postgres'),
            password=os.getenv('PG_PASS', ''),
            connect_timeout=3,
        )
    except Exception:
        return None

def _init_session_table():
    """Create sessions + lockout tables in platform DB if they don't exist."""
    conn = _pg_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        token      TEXT PRIMARY KEY,
                        data       TEXT NOT NULL,
                        expires_at DOUBLE PRECISION NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON auth_sessions(expires_at)")
                # Lockout table — brute-force protection survives restarts
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS auth_lockouts (
                        username    TEXT NOT NULL,
                        tenant_slug TEXT NOT NULL,
                        attempts    INTEGER NOT NULL DEFAULT 0,
                        locked_until DOUBLE PRECISION,
                        PRIMARY KEY (username, tenant_slug)
                    )
                """)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _save_session_db(token: str, session_data: dict):
    """Persist session to DB (non-blocking — ignores errors)."""
    conn = _pg_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO auth_sessions (token, data, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (token) DO UPDATE
                        SET data = EXCLUDED.data,
                            expires_at = EXCLUDED.expires_at
                """, (token, json.dumps(session_data), session_data['expires']))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _load_session_db(token: str) -> dict | None:
    """Load session from DB — used as fallback when not in memory."""
    conn = _pg_conn()
    if not conn:
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM auth_sessions WHERE token = %s AND expires_at > %s",
                    (token, time.time())
                )
                row = cur.fetchone()
                if row:
                    return json.loads(row[0])
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return None

def _delete_session_db(token: str):
    """Delete session record from DB."""
    conn = _pg_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM auth_sessions WHERE token = %s", (token,))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Initialise the sessions table at import time (best-effort, non-blocking)
try:
    _init_session_table()
except Exception:
    pass

# ── Account lockout store ─────────────────────────────────────────────────────
#   key  = (username.lower(), tenant_slug)
#   val  = {"attempts": int, "locked_until": float|None}
_lockout_store: dict = {}
MAX_ATTEMPTS       = 3       # failures before lock
LOCKOUT_SECONDS    = 15 * 60 # 15 minutes

# ── Password-reset OTP store ──────────────────────────────────────────────────
#   key  = (username.lower(), tenant_slug)
#   val  = {"otp": str, "expires": float, "attempts": int}
_otp_store: dict = {}
OTP_TTL        = 10 * 60   # 10 minutes
OTP_MAX_TRIES  = 5


# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Return bcrypt (or SHA-256) hash of plain password."""
    if _BCRYPT:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_password(plain: str, stored: str) -> bool:
    """Return True if plain matches stored hash."""
    if not plain or not stored:
        return False
    # bcrypt hashes start with $2b$ or $2a$
    if _BCRYPT and stored.startswith('$2'):
        try:
            return bcrypt.checkpw(plain.encode(), stored.encode())
        except Exception:
            return False
    # SHA-256 fallback
    return hashlib.sha256(plain.encode()).hexdigest() == stored


# ── Session helpers ───────────────────────────────────────────────────────────
def create_session(user: dict) -> str:
    """
    Store session data and return a secure token string.

    db_layer field encodes which data layer this user belongs to:
      'PLATFORM'  — FOUNDER accounts (srp_platform_db.founder_accounts)
                    May NEVER access patient data in any tenant DB.
      'TENANT'    — Hospital staff  (each hospital's staff_users table)
                    Scoped to their own tenant DB only.
    """
    role = user.get('role', 'RECEPTION').upper()
    token = secrets.token_hex(32)
    sess = {
        'user_id':      user.get('id'),
        'username':     user.get('username', ''),
        'role':         role,
        'department':   user.get('department', ''),
        'full_name':    user.get('full_name', user.get('username', '')),
        'tenant_slug':  user.get('tenant_slug', 'platform' if role == 'FOUNDER' else 'star_hospital'),
        'db_layer':     'PLATFORM' if role == 'FOUNDER' else 'TENANT',
        'expires':      time.time() + SESSION_TTL,
    }
    _sessions[token] = sess
    # Persist to DB so sessions survive server restarts
    try:
        _save_session_db(token, sess)
    except Exception:
        pass
    return token


def get_session(token: str) -> dict | None:
    """Return session dict if valid and not expired, else None.
    Checks in-memory first for speed; falls back to PostgreSQL on cache miss
    (handles server restarts where in-memory dict was cleared).
    """
    if not token:
        return None
    # 1. Fast path — in-memory
    session = _sessions.get(token)
    if session:
        if session['expires'] < time.time():
            del _sessions[token]
            _delete_session_db(token)
            return None
        return session
    # 2. Fallback — PostgreSQL (server restart / new process)
    try:
        session = _load_session_db(token)
    except Exception:
        session = None
    if session:
        if session.get('expires', 0) < time.time():
            _delete_session_db(token)
            return None
        # Re-hydrate in-memory cache
        _sessions[token] = session
        return session
    return None


def destroy_session(token: str):
    """Invalidate a session token (memory + DB)."""
    _sessions.pop(token, None)
    try:
        _delete_session_db(token)
    except Exception:
        pass


def extract_token(cookie_header: str) -> str:
    """Parse 'admin_session=<token>' from a Cookie header string."""
    for part in cookie_header.split(';'):
        part = part.strip()
        if part.startswith('admin_session='):
            return part[len('admin_session='):]
    return ''


def cleanup_expired():
    """Remove all expired sessions. Call periodically."""
    now = time.time()
    expired = [t for t, s in list(_sessions.items()) if s['expires'] < now]
    for t in expired:
        _sessions.pop(t, None)


def session_count() -> int:
    """Return number of active sessions."""
    cleanup_expired()
    return len(_sessions)


# ══════════════════════════════════════════════
# ACCOUNT LOCKOUT
# ══════════════════════════════════════════════

def _lockout_key(username: str, tenant_slug: str) -> tuple:
    return (username.strip().lower(), (tenant_slug or 'star_hospital').strip().lower())


def _save_lockout_db(username: str, tenant_slug: str, attempts: int, locked_until: float | None):
    """Persist lockout record to DB (non-blocking)."""
    conn = _pg_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO auth_lockouts (username, tenant_slug, attempts, locked_until)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (username, tenant_slug) DO UPDATE
                        SET attempts = EXCLUDED.attempts,
                            locked_until = EXCLUDED.locked_until
                """, (username.lower(), (tenant_slug or '').lower(), attempts, locked_until))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_lockout_db(username: str, tenant_slug: str) -> dict | None:
    """Load lockout record from DB — used on in-memory cache miss."""
    conn = _pg_conn()
    if not conn:
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT attempts, locked_until FROM auth_lockouts WHERE username=%s AND tenant_slug=%s",
                    (username.lower(), (tenant_slug or '').lower())
                )
                row = cur.fetchone()
                if row:
                    return {'attempts': row[0], 'locked_until': row[1]}
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return None


def _delete_lockout_db(username: str, tenant_slug: str):
    """Remove lockout record from DB on successful login."""
    conn = _pg_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM auth_lockouts WHERE username=%s AND tenant_slug=%s",
                    (username.lower(), (tenant_slug or '').lower())
                )
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def check_lockout(username: str, tenant_slug: str) -> dict:
    """
    Return {'locked': bool, 'seconds_remaining': int, 'attempts': int}.
    Call BEFORE verifying the password.
    """
    key  = _lockout_key(username, tenant_slug)
    rec  = _lockout_store.get(key)
    if not rec:
        # Try DB (handles server restarts)
        rec = _load_lockout_db(username, tenant_slug)
        if rec:
            _lockout_store[key] = rec
    if not rec:
        return {'locked': False, 'seconds_remaining': 0, 'attempts': 0}

    if rec.get('locked_until') and rec['locked_until'] > time.time():
        remaining = int(rec['locked_until'] - time.time())
        return {'locked': True, 'seconds_remaining': remaining, 'attempts': rec['attempts']}

    # Lock has expired — clear it
    if rec.get('locked_until') and rec['locked_until'] <= time.time():
        del _lockout_store[key]
        _delete_lockout_db(username, tenant_slug)
    return {'locked': False, 'seconds_remaining': 0, 'attempts': rec.get('attempts', 0)}


def record_failed_attempt(username: str, tenant_slug: str) -> dict:
    """
    Increment failed-attempt counter for a user.
    Returns the updated lockout dict (same shape as check_lockout).
    """
    key = _lockout_key(username, tenant_slug)
    rec = _lockout_store.setdefault(key, {'attempts': 0, 'locked_until': None})
    rec['attempts'] += 1

    locked_until = None
    if rec['attempts'] >= MAX_ATTEMPTS:
        locked_until = time.time() + LOCKOUT_SECONDS
        rec['locked_until'] = locked_until
    # Persist to DB so restart doesn't clear the lockout
    _save_lockout_db(username, tenant_slug, rec['attempts'], locked_until)

    if rec['attempts'] >= MAX_ATTEMPTS:
        return {
            'locked': True,
            'seconds_remaining': LOCKOUT_SECONDS,
            'attempts': rec['attempts'],
        }
    return {'locked': False, 'seconds_remaining': 0, 'attempts': rec['attempts']}


def reset_lockout(username: str, tenant_slug: str) -> None:
    """Clear failed attempts on successful login."""
    key = _lockout_key(username, tenant_slug)
    _lockout_store.pop(key, None)
    _delete_lockout_db(username, tenant_slug)


# ══════════════════════════════════════════════
# PASSWORD-RESET OTP
# ══════════════════════════════════════════════

def generate_otp(username: str, tenant_slug: str) -> str:
    """
    Generate a 6-digit OTP for password reset, store it and return the plain string.
    Overwrites any previous OTP for this (username, tenant) pair.
    """
    otp = str(random.randint(100000, 999999))
    key = _lockout_key(username, tenant_slug)
    _otp_store[key] = {
        'otp':      otp,
        'expires':  time.time() + OTP_TTL,
        'attempts': 0,
    }
    return otp


def verify_otp(username: str, tenant_slug: str, otp_input: str) -> dict:
    """
    Verify OTP.  Returns:
      {'valid': True}
      {'valid': False, 'reason': 'expired|invalid|too_many_attempts|not_found'}
    """
    key = _lockout_key(username, tenant_slug)
    rec = _otp_store.get(key)
    if not rec:
        return {'valid': False, 'reason': 'not_found'}
    if time.time() > rec['expires']:
        del _otp_store[key]
        return {'valid': False, 'reason': 'expired'}
    rec['attempts'] += 1
    if rec['attempts'] > OTP_MAX_TRIES:
        del _otp_store[key]
        return {'valid': False, 'reason': 'too_many_attempts'}
    if otp_input.strip() != rec['otp']:
        return {'valid': False, 'reason': 'invalid'}
    # Valid — consume the OTP
    del _otp_store[key]
    return {'valid': True}


def has_valid_otp(username: str, tenant_slug: str) -> bool:
    """Return True if a fresh (non-expired) OTP exists for this user."""
    key = _lockout_key(username, tenant_slug)
    rec = _otp_store.get(key)
    return bool(rec and time.time() < rec['expires'])


def clear_otp(username: str, tenant_slug: str) -> None:
    """Discard OTP (e.g. after successful reset)."""
    key = _lockout_key(username, tenant_slug)
    _otp_store.pop(key, None)

