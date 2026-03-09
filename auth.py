"""
auth.py - Role-Based Authentication Module
Handles: password hashing, session tokens, session validation.
Supports bcrypt (preferred) with SHA-256 fallback if bcrypt not installed.
"""

import secrets
import hashlib
import time

try:
    import bcrypt
    _BCRYPT = True
except ImportError:
    _BCRYPT = False
    print("⚠️  bcrypt not installed — using SHA-256 fallback.  Run: pip install bcrypt")

# ── In-memory session store ───────────────────────────────────────────────────
_sessions: dict = {}
SESSION_TTL = 8 * 3600  # 8 hours


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
    """Store session data and return a secure token string."""
    token = secrets.token_hex(32)
    _sessions[token] = {
        'user_id':      user.get('id'),
        'username':     user.get('username', ''),
        'role':         user.get('role', 'RECEPTION').upper(),
        'department':   user.get('department', ''),
        'full_name':    user.get('full_name', user.get('username', '')),
        'tenant_slug':  user.get('tenant_slug', 'star_hospital'),
        'expires':      time.time() + SESSION_TTL,
    }
    return token


def get_session(token: str) -> dict | None:
    """Return session dict if valid and not expired, else None."""
    if not token:
        return None
    session = _sessions.get(token)
    if not session:
        return None
    if session['expires'] < time.time():
        del _sessions[token]
        return None
    return session


def destroy_session(token: str):
    """Invalidate a session token."""
    _sessions.pop(token, None)


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
