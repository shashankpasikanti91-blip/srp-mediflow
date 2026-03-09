"""
api_security.py  â€“  SRP MediFlow Security Middleware
======================================================
Provides:
  â€¢ require_auth(handler)          â€” ensure valid session
  â€¢ require_role(*roles)(handler)  â€” session + role gate
  â€¢ sanitize_input(value)          â€” strip dangerous characters
  â€¢ sanitize_dict(d)               â€” sanitize all string values in a dict
  â€¢ get_request_token(handler)     â€” parse admin_session cookie
  â€¢ log_access(session, action)    â€” write to system_logs table

Usage in server handlers
------------------------
from api_security import require_role, sanitize_dict
from roles import ADMIN, DOCTOR, NURSE, LAB, STOCK

# Protect a route with a role check:
@require_role(ADMIN)
def handle_admin_data(request):
    ...

# Sanitize form data:
body = sanitize_dict(json.loads(request.body))
"""

from __future__ import annotations
import re
import html
import functools
from auth import get_session, extract_token


# â”€â”€ Input sanitization â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_DANGEROUS_PATTERN = re.compile(
    r"(--|;|/\*|\*/|xp_|UNION\s+SELECT|DROP\s+TABLE|INSERT\s+INTO|DELETE\s+FROM"
    r"|UPDATE\s+\w+\s+SET|<script|</script|javascript:|onerror=|onload=)",
    re.IGNORECASE,
)


def sanitize_input(value: str, max_length: int = 500) -> str:
    """
    Return a sanitised string:
      â€¢ HTML-escape special characters (<, >, &, ", ')
      â€¢ Strip leading/trailing whitespace
      â€¢ Truncate to max_length characters
      â€¢ Remove SQL injection patterns
    """
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    value = value.strip()[:max_length]
    value = html.escape(value, quote=True)
    value = _DANGEROUS_PATTERN.sub("", value)
    return value


def sanitize_dict(data: dict, max_length: int = 500) -> dict:
    """
    Return a new dict with all string values sanitised.
    Non-string values (int, float, bool, None) are passed through unchanged.
    """
    result = {}
    for key, val in data.items():
        if isinstance(val, str):
            result[key] = sanitize_input(val, max_length)
        else:
            result[key] = val
    return result


# â”€â”€ Session extraction helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_session_from_headers(headers: dict) -> dict | None:
    """
    Extract and validate the admin_session cookie from a headers dict.
    Returns the session dict or None if absent / expired.
    """
    cookie_header = headers.get("Cookie", "") or headers.get("cookie", "")
    token = extract_token(cookie_header)
    return get_session(token) if token else None


# â”€â”€ Role validation helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def check_role(session: dict | None, *allowed_roles: str) -> bool:
    """
    Return True if the session exists and the user's role is in allowed_roles.
    Comparison is case-insensitive.
    """
    if not session:
        return False
    user_role = session.get("role", "").upper()
    return user_role in {r.upper() for r in allowed_roles}


# â”€â”€ Decorators (for use with raw WSGI / http.server style handlers) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def require_auth(handler_fn):
    """
    Decorator: reject the request with 401 if no valid session is present.
    Expects the wrapped function to accept (self, session, *args, **kwargs).

    Example usage with http.server:

        @require_auth
        def do_GET_api_data(self, session):
            ...
    """
    @functools.wraps(handler_fn)
    def wrapper(self, *args, **kwargs):
        session = get_session_from_headers(dict(self.headers))
        if not session:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Unauthorised - please login","code":401}')
            return
        return handler_fn(self, session, *args, **kwargs)
    return wrapper


def require_role(*allowed_roles: str):
    """
    Decorator factory: reject with 403 if session role is not in allowed_roles.

    Example:
        @require_role('ADMIN', 'RECEPTION')
        def do_GET_admin_data(self, session):
            ...
    """
    def decorator(handler_fn):
        @functools.wraps(handler_fn)
        def wrapper(self, *args, **kwargs):
            session = get_session_from_headers(dict(self.headers))
            if not session:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Unauthorised - please login","code":401}')
                return
            if not check_role(session, *allowed_roles):
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                role = session.get('role', 'unknown')
                msg = (
                    f'{{"error":"Access denied - role {role} '
                    f'not permitted","code":403}}'
                ).encode()
                self.wfile.write(msg)
                return
            return handler_fn(self, session, *args, **kwargs)
        return wrapper
    return decorator


# â”€â”€ Public-route guard (for routes that must stay open) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PUBLIC_PATHS: set[str] = {
    "/",
    "/api/chat",
    "/api/register",
    "/login",
    "/style.css",
    "/script.js",
}


def is_public_path(path: str) -> bool:
    """Return True if the path should be accessible without authentication."""
    # Exact match or starts-with for static files
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/static/"):
        return True
    return False


# â”€â”€ Access log helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def log_access(session: dict | None, action: str,
               details: str = "", ip_address: str = "") -> None:
    """
    Write to system_logs table.  Silently swallows DB errors so a logging
    failure never crashes a request handler.
    """
    try:
        # Import here to avoid circular imports at module load time
        from db import log_action
        username = session.get("username", "anonymous") if session else "anonymous"
        role     = session.get("role", "") if session else ""
        log_action(username, role, action, details, ip_address)
    except Exception:
        pass


# â”€â”€ Rate-limit stub (expandable) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import time as _time
_rate_store: dict[str, list[float]] = {}

RATE_LIMIT_WINDOW  = 60      # seconds
RATE_LIMIT_MAX_REQ = 60      # max requests per window per IP


def check_rate_limit(ip: str) -> bool:
    """
    Simple in-memory rate limiter.
    Returns True if the request is allowed, False if rate-limited.
    """
    now     = _time.time()
    cutoff  = now - RATE_LIMIT_WINDOW
    history = _rate_store.get(ip, [])
    history = [t for t in history if t > cutoff]
    history.append(now)
    _rate_store[ip] = history
    return len(history) <= RATE_LIMIT_MAX_REQ
