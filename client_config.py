"""
════════════════════════════════════════════════════════════════════════════════
  SRP MediFlow — Dynamic Client Configuration
  Module  : client_config.py
  Version : 1.0

PURPOSE:
  SRP MediFlow is the SOFTWARE PRODUCT.
  Each hospital is a CLIENT.

  This module resolves the active client for each request and returns
  its branding/config so that every page shows the hospital name — not
  "SRP MediFlow" as the hospital name.

CLIENT RESOLUTION ORDER (first match wins):
  1. SRP_CLIENT_SLUG   env var  (e.g.  star_hospital)
  2. Host: header subdomain     (e.g.  starhospital.mydomain.com)
  3. DB slug for active PG_DB   (derived from PG_DB env var)
  4. Default: Star Hospital     (hardcoded fallback)

USAGE:
  from client_config import get_client_config, get_product_info

  cfg = get_client_config()
  print(cfg['hospital_name'])   # → "Star Hospital"
  print(cfg['product_name'])    # → "SRP MediFlow"
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import os
import re
import json
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger("client_config")

# ── Product identity (never changes) ─────────────────────────────────────────
PRODUCT_NAME    = "SRP MediFlow"
PRODUCT_TAGLINE = "Hospital Management System"
PRODUCT_VENDOR  = "SRP Technologies"
PRODUCT_VERSION = "3.0"

# ── Fallback: read from hospital_config.py ────────────────────────────────────
def _from_hospital_config() -> dict:
    """Read static config from hospital_config.py (always available)."""
    try:
        import hospital_config as hc
        return {
            "hospital_name":    getattr(hc, "HOSPITAL_NAME",    "Star Hospital"),
            "hospital_name_te": getattr(hc, "HOSPITAL_NAME_TE", "స్టార్ హాస్పిటల్"),
            "hospital_name_hi": getattr(hc, "HOSPITAL_NAME_HI", "स्टार अस्पताल"),
            "hospital_phone":   getattr(hc, "HOSPITAL_PHONE",   "+91 7981971015"),
            "hospital_address": getattr(hc, "HOSPITAL_ADDRESS",
                                         "Karur Vysya Bank Lane, Ganesh Basthi, "
                                         "Kothagudem, Telangana 507101, India"),
            "hospital_email":   getattr(hc, "HOSPITAL_EMAIL",   ""),
            "hospital_website": getattr(hc, "HOSPITAL_WEBSITE", ""),
            "hospital_logo":    getattr(hc, "HOSPITAL_LOGO",    ""),
            "hospital_tagline": getattr(hc, "HOSPITAL_TAGLINE",
                                         "24x7 Emergency Medical Services Available"),
            "city":             "Kothagudem",
            "state":            "Telangana",
            "country":          "India",
            "primary_color":    getattr(hc, "PRIMARY_COLOR",    "#1a73e8"),
            "secondary_color":  getattr(hc, "SECONDARY_COLOR",  "#00b896"),
            "slug":             "star_hospital",
            "db_name":          os.getenv("PG_DB", "hospital_ai"),
            # ── product identity (injected so templates can use it) ─────────
            "product_name":     PRODUCT_NAME,
            "product_tagline":  PRODUCT_TAGLINE,
            "product_vendor":   PRODUCT_VENDOR,
        }
    except ImportError:
        logger.warning("hospital_config.py not found — using hardcoded defaults")
        return _hardcoded_default()


def _hardcoded_default() -> dict:
    return {
        "hospital_name":    "Star Hospital",
        "hospital_name_te": "స్టార్ హాస్పిటల్",
        "hospital_name_hi": "स्टार अस्पताल",
        "hospital_phone":   "+91 7981971015",
        "hospital_address": "Karur Vysya Bank Lane, Ganesh Basthi, Kothagudem, Telangana 507101, India",
        "hospital_email":   "",
        "hospital_website": "",
        "hospital_logo":    "",
        "hospital_tagline": "24x7 Emergency Medical Services Available",
        "city":             "Kothagudem",
        "state":            "Telangana",
        "country":          "India",
        "primary_color":    "#1a73e8",
        "secondary_color":  "#00b896",
        "slug":             "star_hospital",
        "db_name":          "hospital_ai",
        "product_name":     PRODUCT_NAME,
        "product_tagline":  PRODUCT_TAGLINE,
        "product_vendor":   PRODUCT_VENDOR,
    }


# ── DB client record → config dict ───────────────────────────────────────────
def _from_db_record(row: dict) -> dict:
    """Convert a `clients` table row into a config dict."""
    base = _from_hospital_config()   # fill in any missing keys from static config
    base.update({
        "client_id":        row.get("client_id"),
        "hospital_name":    row.get("hospital_name",    base["hospital_name"]),
        "hospital_phone":   row.get("hospital_phone",   base["hospital_phone"]),
        "hospital_address": row.get("hospital_address", base["hospital_address"]),
        "city":             row.get("city",             base["city"]),
        "state":            row.get("state",            base["state"]),
        "country":          row.get("country",          base["country"]),
        "hospital_logo":    row.get("logo_path",        base["hospital_logo"]),
        "primary_color":    row.get("primary_color",    base["primary_color"]),
        "secondary_color":  row.get("secondary_color",  base["secondary_color"]),
        "db_name":          row.get("database_name",    base["db_name"]),
        "slug":             row.get("slug",             base["slug"]),
        "hospital_tagline": row.get("tagline",          base.get("hospital_tagline", "")),
        "product_name":     PRODUCT_NAME,
        "product_tagline":  PRODUCT_TAGLINE,
        "product_vendor":   PRODUCT_VENDOR,
    })
    return base


# ── Client resolution ─────────────────────────────────────────────────────────
def _slug_from_host(host_header: str) -> Optional[str]:
    """
    Extract client slug from a Host header.
    starhospital.srpmediflow.com  →  starhospital
    localhost:7500                →  None
    """
    host = host_header.split(":")[0].lower()
    # ignore localhost / raw IPs
    if host == "localhost" or re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return None
    parts = host.split(".")
    if len(parts) >= 3:
        # first segment is the subdomain / slug
        return re.sub(r"[^a-z0-9_]", "_", parts[0])
    return None


def _lookup_client_in_db(slug: str) -> Optional[dict]:
    """
    Query the `clients` table in the master DB.
    Returns None if not found or DB unavailable.
    """
    try:
        import db as _db
        import psycopg2.extras
        with _db.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM clients WHERE slug = %s AND is_active = TRUE LIMIT 1",
                (slug,)
            )
            row = cur.fetchone()
            cur.close()
        return _from_db_record(dict(row)) if row else None
    except Exception as e:
        logger.debug("_lookup_client_in_db: %s", e)
        return None


def get_client_config(host_header: str = "") -> dict:
    """
    Resolve and return the active client configuration.

    Resolution order:
      1. SRP_CLIENT_SLUG env var
      2. Host: header subdomain
      3. PG_DB env var slug
      4. Static hospital_config.py fallback

    Args:
        host_header: Value of the HTTP Host: header (optional)

    Returns:
        dict with hospital_name, hospital_phone, hospital_address,
        primary_color, product_name, product_tagline, ...
    """
    # 1. Explicit env var
    slug = os.getenv("SRP_CLIENT_SLUG", "").strip()

    # 2. Subdomain from Host header
    if not slug and host_header:
        slug = _slug_from_host(host_header) or ""

    # 3. Derive from PG_DB env var  (  srp_star_hospital → star_hospital )
    if not slug:
        pg_db = os.getenv("PG_DB", "")
        if pg_db.startswith("srp_"):
            slug = pg_db[4:]

    # 4. Try DB lookup
    if slug:
        cfg = _lookup_client_in_db(slug)
        if cfg:
            return cfg

    # 5. Fallback to static config (always available)
    return _from_hospital_config()


def get_product_info() -> dict:
    """Return SRP MediFlow product metadata (never client-specific)."""
    return {
        "name":    PRODUCT_NAME,
        "tagline": PRODUCT_TAGLINE,
        "vendor":  PRODUCT_VENDOR,
        "version": PRODUCT_VERSION,
    }


def config_to_js_vars(cfg: dict) -> str:
    """
    Return a JavaScript snippet that injects client config into HTML pages.
    Embed this in a <script> tag.
    """
    safe = {k: str(v).replace("'", "\\'") for k, v in cfg.items()
            if isinstance(v, (str, int, float)) and k != "db_name"}
    lines = ["const SRP_CLIENT = {"]
    for k, v in safe.items():
        lines.append(f"  {k}: '{v}',")
    lines.append("};")
    return "\n".join(lines)


# ── Singleton cache (refreshes every 5 min) ────────────────────────────────────
import time as _time

_cache_cfg:  dict  = {}
_cache_ts:   float = 0.0
_CACHE_TTL:  int   = 300    # seconds


def get_cached_config(host_header: str = "") -> dict:
    """
    Like get_client_config() but cached to avoid per-request DB hits.
    Cache is refreshed every 5 minutes.
    """
    global _cache_cfg, _cache_ts
    now = _time.monotonic()
    if not _cache_cfg or (now - _cache_ts) > _CACHE_TTL:
        _cache_cfg = get_client_config(host_header)
        _cache_ts  = now
    return _cache_cfg
