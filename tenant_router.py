"""
tenant_router.py  —  SRP MediFlow Tenant Router
=================================================
Determines which hospital (tenant) database to connect to based on the
incoming request's hostname or explicit tenant slug.

ARCHITECTURE
────────────
                ┌─────────────────────────────────────┐
  HTTP request  │         Tenant Router               │
  ──────────►   │  slug = detect_tenant(host_header)  │
                │  cfg  = resolve_tenant_config(slug) │──► psycopg2.connect(cfg)
                └─────────────────────────────────────┘
                               │ reads from
                               ▼
                      platform_db.clients  ← authoritative source
                      tenant_registry.json ← fallback (file cache)

ISOLATION RULES
───────────────
• This module resolves connection parameters ONLY — it never executes
  queries against tenant databases directly.
• Connection params are sourced from platform_db first, then fall back
  to tenant_registry.json, then to the default (star_hospital).
• No cross-tenant connections are ever created (one slug → one DB).
• The platform database is NEVER returned as a tenant connection.

SCALE READINESS
───────────────
Because db_host and db_port are stored per-client in platform_db.clients,
individual tenant databases can later be migrated to different servers
without changing any application code — only their platform_db row changes.

Public API
──────────
    detect_tenant(host_header: str) -> str
        Parse the subdomain from a Host header, return slug.
        e.g.  'starhospital.srpailabs.com'  → 'star_hospital'

    resolve_tenant_config(slug: str) -> dict
        Return psycopg2 connect kwargs for the given slug.
        Reads platform_db first, falls back to registry file.

    get_tenant_db_name(slug: str) -> str
        Return just the database name for a tenant slug.

    list_available_tenants() -> list[str]
        Return all known tenant slugs (from platform_db or registry).

    assert_not_platform_db(cfg: dict) -> None
        Raise RuntimeError if cfg would connect to the platform database.
        Used as a safety guard in tenant code paths.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

# ── Registry fallback path ────────────────────────────────────────────────────
_BASE_DIR      = Path(__file__).parent
_REGISTRY_PATH = _BASE_DIR / "tenant_registry.json"

# ── Default (star_hospital) connection — matches db.py DB_CONFIG ──────────────
_DEFAULT_SLUG = "star_hospital"
_DEFAULT_CFG  = {
    "host":            os.getenv("PG_HOST",     "localhost"),
    "port":            int(os.getenv("PG_PORT", "5434")),
    "dbname":          os.getenv("PG_DB",       "hospital_ai"),
    "user":            os.getenv("PG_USER",     "ats_user"),
    "password":        os.getenv("PG_PASSWORD", "ats_password"),
    "connect_timeout": 5,
}

# ── Platform DB name — MUST never be returned as a tenant config ──────────────
_PLATFORM_DB_NAME = os.getenv("PLATFORM_DB_NAME", "srp_platform_db")

# ── Subdomain-to-slug mapping hints (optional, speeds up lookup) ──────────────
# If a subdomain doesn't match a slug exactly, the router tries normalisation.
_SUBDOMAIN_OVERRIDES: dict[str, str] = {
    # 'starhospital' → 'star_hospital'  (derived automatically via normalise)
}


# ── Slug normalisation ────────────────────────────────────────────────────────

def _normalise_slug(raw: str) -> str:
    """
    Convert a raw string (subdomain, form input, etc.) to a canonical slug.
    e.g.  'StarHospital' → 'star_hospital'
          'sai-care'     → 'sai_care'
          'starhospital' → 'starhospital'  (unchanged if it matches a registry key)
    """
    return re.sub(r'[^a-z0-9_]', '_', raw.lower().strip())[:40]


# ── Load file registry (fallback) ────────────────────────────────────────────

def _load_file_registry() -> dict:
    """Load tenant_registry.json as a plain dict. Returns {} on failure."""
    try:
        if _REGISTRY_PATH.exists():
            with open(_REGISTRY_PATH, encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _registry_cfg(slug: str, registry: Optional[dict] = None) -> Optional[dict]:
    """Build a psycopg2 config dict from a tenant_registry.json entry."""
    if registry is None:
        registry = _load_file_registry()
    info = registry.get(slug)
    if not info:
        return None
    db_name = info.get("db_name") or f"srp_{slug}"
    return {
        "host":            info.get("db_host", "localhost"),
        "port":            int(info.get("db_port", 5434)),
        "dbname":          db_name,
        "user":            info.get("db_user", "ats_user"),
        "password":        os.getenv("PG_PASSWORD", "ats_password"),
        "connect_timeout": 5,
    }


# ── Platform DB lookup (primary source) ──────────────────────────────────────

def _platform_cfg(slug: str) -> Optional[dict]:
    """
    Query platform_db.clients for tenant connection parameters.
    Returns None if platform_db is unavailable or slug not found.
    This is always tried first; file registry is the fallback.
    """
    try:
        from platform_db import get_tenant_connection_params
        return get_tenant_connection_params(slug)
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def detect_tenant(host_header: str) -> str:
    """
    Extract the tenant slug from an HTTP Host header.

    Mapping rules (in order):
      1. Check _SUBDOMAIN_OVERRIDES dict.
      2. Take the first label of the hostname (subdomain).
      3. Normalise: lowercase + replace non-alphanumeric with '_'.
      4. If that slug exists in platform_db or registry → return it.
      5. Otherwise return the default slug (star_hospital).

    Examples:
      'starhospital.srpailabs.com'   → 'star_hospital'  (via alias in DB)
      'sai_care.srpailabs.com'       → 'sai_care'
      'localhost:7500'               → 'star_hospital'  (default)
      ''                             → 'star_hospital'  (default)
    """
    if not host_header:
        return _DEFAULT_SLUG

    # Strip port  →  'starhospital.srpailabs.com'
    hostname = host_header.split(':')[0].strip().lower()

    # Localhost / IP → default
    if hostname in ('localhost', '127.0.0.1', '0.0.0.0') or not hostname:
        return _DEFAULT_SLUG

    # Take first label (subdomain)
    subdomain = hostname.split('.')[0]

    # Check static overrides
    if subdomain in _SUBDOMAIN_OVERRIDES:
        return _SUBDOMAIN_OVERRIDES[subdomain]

    # Normalise and check registry / platform_db
    slug = _normalise_slug(subdomain)
    known = list_available_tenants()
    if slug in known:
        return slug

    # Try exact match before normalisation (some slugs already have underscores)
    if subdomain in known:
        return subdomain

    return _DEFAULT_SLUG


def resolve_tenant_config(slug: str) -> dict:
    """
    Return psycopg2 connection kwargs for the given tenant slug.

    Resolution order:
      1. platform_db.clients  (authoritative; supports multi-server)
      2. tenant_registry.json (local file fallback)
      3. Default config       (star_hospital / hospital_ai)

    SAFETY: asserts that the returned config does NOT point to the
    platform database.
    """
    if not slug or slug == _DEFAULT_SLUG:
        assert_not_platform_db(_DEFAULT_CFG)
        return _DEFAULT_CFG

    # 1. Platform DB (preferred)
    cfg = _platform_cfg(slug)
    if cfg:
        assert_not_platform_db(cfg)
        return cfg

    # 2. File registry fallback
    cfg = _registry_cfg(slug)
    if cfg:
        assert_not_platform_db(cfg)
        return cfg

    # 3. Default fallback
    assert_not_platform_db(_DEFAULT_CFG)
    return _DEFAULT_CFG


def get_tenant_db_name(slug: str) -> str:
    """Return just the database name for a tenant slug."""
    cfg = resolve_tenant_config(slug)
    return cfg.get("dbname", f"srp_{slug}")


def list_available_tenants() -> list[str]:
    """
    Return all known tenant slugs.
    Combines platform_db.clients and tenant_registry.json (deduped).
    """
    slugs: set[str] = set()

    # From platform_db
    try:
        from platform_db import get_all_clients
        for c in get_all_clients():
            if c.get('slug'):
                slugs.add(c['slug'])
    except Exception:
        pass

    # From file registry (fallback / complement)
    for slug in _load_file_registry().keys():
        slugs.add(slug)

    return sorted(slugs)


def assert_not_platform_db(cfg: dict) -> None:
    """
    Safety guard: raise RuntimeError if cfg would connect to the
    platform database (srp_platform_db).  Call before handing a config
    dict to any tenant data access function.
    """
    db = cfg.get("dbname", "")
    if db == _PLATFORM_DB_NAME:
        raise RuntimeError(
            f"SECURITY VIOLATION: attempted to use platform database "
            f"'{_PLATFORM_DB_NAME}' as a tenant connection. "
            "Tenant code must never connect to the platform database."
        )
