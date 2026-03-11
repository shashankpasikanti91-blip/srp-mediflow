"""
roles.py - RBAC Permissions & Dashboard Routing

Role hierarchy (top to bottom):
  FOUNDER   → SRP MediFlow platform owner. Sees ALL clients, ALL data, system health.
              Not tied to any hospital. Can create/manage clients.
  ADMIN     → Hospital-level administrator. Single client scope.
  DOCTOR    → Doctor dashboard (own patients/prescriptions).
  NURSE     → Nursing dashboard (vitals, assignments).
  LAB       → Lab orders and results.
  XRAY      → Radiology / X-Ray orders.
  STOCK     → Pharmacy / inventory management.
  RECEPTION → OPD reception, appointment booking.
"""

from __future__ import annotations

# ── Role constants ─────────────────────────────────────────────────────────────
FOUNDER     = 'FOUNDER'   # Platform owner — SRP Technologies
ADMIN       = 'ADMIN'     # Hospital admin (per client)
DOCTOR      = 'DOCTOR'
NURSE       = 'NURSE'
LAB         = 'LAB'
XRAY        = 'XRAY'
STOCK       = 'STOCK'
RECEPTION   = 'RECEPTION'

ALL_ROLES: list[str] = [FOUNDER, ADMIN, DOCTOR, NURSE, LAB, XRAY, STOCK, RECEPTION]

# ── Hierarchy layer groupings ──────────────────────────────────────────────────
#
#  Layer 1 — PLATFORM  (srp_platform_db)
#    Accounts live in: founder_accounts table
#    Database scope:   ALL hospitals (read platform metrics, create tenants)
#    Patient data:     BLOCKED at route level
#
#  Layer 2 — TENANT    (each hospital's own DB, e.g. srp_star_hospital)
#    Accounts live in: staff_users table inside that hospital's DB
#    Database scope:   OWN hospital ONLY
#    Patient data:     Allowed per role (ADMIN full, DOCTOR own patients, etc.)
#
PLATFORM_ROLES: set[str] = {FOUNDER}           # Layer 1 — platform owners
TENANT_ROLES:   set[str] = {                   # Layer 2 — hospital staff
    ADMIN, DOCTOR, NURSE, LAB, XRAY, STOCK, RECEPTION
}

# ── Permission registry ───────────────────────────────────────────────────────
PERMISSIONS: dict[str, set[str]] = {
    FOUNDER: {
        # Platform-level (cross-client)
        'view_all_clients', 'create_client', 'manage_clients',
        'view_system_status', 'view_platform_analytics',
        'manage_billing', 'view_all_databases',
        # All hospital-level permissions too
        'view_dashboard', 'view_patients', 'view_appointments',
        'manage_staff', 'manage_doctors', 'view_attendance',
        'view_reports', 'manage_stock', 'view_stock',
        'view_prescriptions', 'view_vitals', 'view_lab_orders',
        'view_all_doctors', 'export_data', 'view_audit_log',
    },
    ADMIN: {
        'view_dashboard', 'view_patients', 'view_appointments',
        'manage_staff', 'manage_doctors', 'view_attendance',
        'view_reports', 'manage_stock', 'view_stock',
        'view_prescriptions', 'view_vitals', 'view_lab_orders',
        'view_all_doctors', 'export_data',
    },
    DOCTOR: {
        'view_dashboard', 'view_own_appointments', 'add_prescription',
        'view_prescriptions', 'view_vitals', 'request_lab',
        'request_xray', 'view_patients', 'view_lab_orders',
    },
    NURSE: {
        'view_dashboard', 'view_patients', 'add_vitals',
        'view_vitals', 'view_appointments', 'view_prescriptions',
    },
    LAB: {
        'view_dashboard', 'view_lab_orders', 'upload_lab_result',
        'view_patients',
    },
    XRAY: {
        'view_dashboard', 'view_lab_orders', 'upload_lab_result',
        'view_patients',
    },
    STOCK: {
        'view_dashboard', 'view_stock', 'manage_stock',
    },
    RECEPTION: {
        'view_dashboard', 'view_patients', 'view_appointments',
        'view_attendance', 'view_all_doctors',
    },
}

# ── Dashboard routing ─────────────────────────────────────────────────────────
ROLE_DASHBOARD: dict[str, str] = {
    FOUNDER:    '/founder',   # Platform dashboard (all clients)
    ADMIN:      '/admin',
    DOCTOR:     '/doctor',
    NURSE:      '/nurse',
    LAB:        '/lab',
    XRAY:       '/lab',
    STOCK:      '/stock',
    RECEPTION:  '/reception',
}

# Human-readable labels
ROLE_LABELS: dict[str, str] = {
    FOUNDER:    'SRP MediFlow Founder',
    ADMIN:      'Hospital Administrator',
    DOCTOR:     'Doctor',
    NURSE:      'Nurse',
    LAB:        'Lab Technician',
    XRAY:       'Radiology / X-Ray',
    STOCK:      'Stock Manager',
    RECEPTION:  'Receptionist',
}


# ── Helper functions ──────────────────────────────────────────────────────────
def has_permission(role: str, permission: str) -> bool:
    """Return True if role has the given permission."""
    return permission in PERMISSIONS.get(role.upper(), set())


def get_dashboard(role: str) -> str:
    """Return the dashboard URL for the given role."""
    return ROLE_DASHBOARD.get(role.upper(), '/admin')


def role_label(role: str) -> str:
    """Return human-readable label for a role."""
    return ROLE_LABELS.get(role.upper(), role)


def is_valid_role(role: str) -> bool:
    """Return True if role is in the allowed list."""
    return role.upper() in ALL_ROLES


def is_platform_role(role: str) -> bool:
    """Return True if the role is platform-level (not hospital-scoped)."""
    return role.upper() == FOUNDER


def roles_for_select() -> list[dict]:
    """Return list of {value, label} dicts for HTML <select> elements (client roles only)."""
    client_roles = [ADMIN, DOCTOR, NURSE, LAB, XRAY, STOCK, RECEPTION]
    return [{'value': r, 'label': ROLE_LABELS[r]} for r in client_roles]
