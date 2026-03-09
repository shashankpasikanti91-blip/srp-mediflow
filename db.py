"""
Hospital AI - PostgreSQL Database Module
Handles all DB operations for registrations, attendance, doctors, and rounds.

Connection: localhost:5434 / hospital_ai / ats_user
"""

import os
import threading
import psycopg2
import psycopg2.extras
import json
import time
from contextlib import contextmanager

# â”€â”€â”€ Connection config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DB_CONFIG = {
    "host":     os.getenv("PG_HOST",     "localhost"),
    "port":     int(os.getenv("PG_PORT", "5434")),
    "dbname":   os.getenv("PG_DB",       "hospital_ai"),
    "user":     os.getenv("PG_USER",     "ats_user"),
    "password": os.getenv("PG_PASSWORD", "ats_password"),
    "connect_timeout": 5,
}

# Convenience aliases used by other modules
DB_HOST = DB_CONFIG["host"]
DB_PORT = DB_CONFIG["port"]
DB_NAME = DB_CONFIG["dbname"]
DB_USER = DB_CONFIG["user"]
DB_PASS = DB_CONFIG["password"]

# Thread-local storage for tenant DB overrides (multi-tenant support)
_tenant_local = threading.local()

# â”€â”€â”€ Connection helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@contextmanager
def get_conn():
    # Use per-thread tenant config if set, otherwise fall back to module default
    cfg = getattr(_tenant_local, 'db_config', None) or DB_CONFIG
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def use_tenant_db(slug: str):
    """Thread-safe context manager: route all get_conn() calls in this
    thread to the tenant's own database for the duration of the block.

    Usage::
        with db.use_tenant_db('sai_care'):
            doctors = db.get_all_doctors()   # hits srp_sai_care DB
    """
    cfg = _get_tenant_cfg(slug)
    old = getattr(_tenant_local, 'db_config', None)
    _tenant_local.db_config = cfg
    try:
        yield
    finally:
        _tenant_local.db_config = old


def _get_tenant_cfg(slug: str) -> dict:
    """Return psycopg2 connection config dict for a tenant slug.
    Resolution order:
      1. tenant_router (queries platform_db.clients, then file registry)
      2. DB_CONFIG fallback (star_hospital / hospital_ai)
    The platform database is NEVER returned by this function."""
    if not slug or slug == 'star_hospital':
        return DB_CONFIG
    try:
        # Use tenant_router as the single source of truth.
        # tenant_router queries platform_db first, falls back to tenant_registry.json.
        from tenant_router import resolve_tenant_config
        return resolve_tenant_config(slug)
    except Exception:
        # Absolute last-resort fallback — keeps the server alive even if
        # tenant_router or platform_db are temporarily unavailable.
        try:
            import json as _json
            import os as _os
            reg_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tenant_registry.json')
            with open(reg_path, encoding='utf-8') as _f:
                registry = _json.load(_f)
            info = registry.get(slug, {})
            if not info:
                return DB_CONFIG
            return {
                'host':            info.get('db_host', 'localhost'),
                'port':            int(info.get('db_port', 5434)),
                'dbname':          info.get('db_name', 'hospital_ai'),
                'user':            info.get('db_user', 'ats_user'),
                'password':        os.getenv('PG_PASSWORD', 'ats_password'),
                'connect_timeout': 5,
            }
        except Exception:
            return DB_CONFIG


def set_request_tenant(slug: str):
    """Set the per-thread tenant so that all subsequent get_conn() calls
    in this thread connect to the correct tenant database.
    Call once at the start of each HTTP request handler."""
    _tenant_local.db_config = _get_tenant_cfg(slug)


def clear_request_tenant():
    """Reset per-thread tenant back to the default DB.
    Call at the end of each HTTP request handler."""
    _tenant_local.db_config = None


class TenantDB:
    """Transparent proxy for the `db` module that routes ALL database
    calls to the correct per-tenant PostgreSQL database.

    Every attribute access that resolves to a callable automatically
    wraps the call inside ``use_tenant_db(self.slug)`` so every
    psycopg2 connection in that call goes to the right database.

    Usage in the HTTP server::

        tdb = TenantDB('sai_care')
        doctors = tdb.get_all_doctors()          # uses srp_sai_care
        tdb.save_registration(record)            # writes to srp_sai_care
    """

    def __init__(self, slug: str):
        # Store slug without triggering __setattr__ magic
        object.__setattr__(self, 'slug', slug or 'star_hospital')
        object.__setattr__(self, '_cfg', _get_tenant_cfg(slug or 'star_hospital'))

    # ------------------------------------------------------------------
    # get_conn() for callers that need a raw connection (e.g. inline SQL)
    # ------------------------------------------------------------------
    @contextmanager
    def get_conn(self):
        cfg = object.__getattribute__(self, '_cfg')
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_connection(self):
        """Return a raw psycopg2 connection (caller must commit/close)."""
        cfg = object.__getattribute__(self, '_cfg')
        try:
            conn = psycopg2.connect(**cfg)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"[TenantDB] get_connection failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Transparent proxy: wrap any db.* function with use_tenant_db()
    # ------------------------------------------------------------------
    def __getattr__(self, name: str):
        import db as _db_module
        slug = object.__getattribute__(self, 'slug')
        func = getattr(_db_module, name)  # raises AttributeError if missing
        if callable(func):
            def _wrapper(*args, **kwargs):
                with use_tenant_db(slug):
                    return func(*args, **kwargs)
            _wrapper.__name__ = name
            return _wrapper
        return func  # non-callable attributes returned as-is


def test_connection() -> bool:
    """Returns True if DB is reachable."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"[DB] Connection test failed: {e}")
        return False


def get_connection():
    """
    Return a raw psycopg2 connection (caller must commit/close).
    Used by RBAC functions that manage their own transaction lifecycle.
    Returns None if the database is unreachable.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"[DB] get_connection failed: {e}")
        return None


# â”€â”€â”€ REGISTRATIONS / APPOINTMENTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def save_registration(record: dict) -> int:
    """Insert a new patient registration, return new row id."""
    sql = """
        INSERT INTO registrations
            (name, age, phone, aadhar, issue, doctor, appointment_time, status, source, created_at)
        VALUES
            (%(name)s, %(age)s, %(phone)s, %(aadhar)s, %(issue)s, %(doctor)s,
             %(appointment_time)s, %(status)s, %(source)s, NOW())
        RETURNING id
    """
    params = {
        "name":             record.get("name", ""),
        "age":              str(record.get("age", "")),
        "phone":            record.get("phone", ""),
        "aadhar":           record.get("aadhar", ""),
        "issue":            record.get("issue", ""),
        "doctor":           record.get("doctor", ""),
        "appointment_time": record.get("appointment_time") or record.get("time", ""),
        "status":           record.get("status", "pending"),
        "source":           record.get("source", "chatbot"),
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row_id = cur.fetchone()[0]
    return row_id


def get_all_registrations(limit: int = 200) -> list:
    """Return latest registrations as list of dicts."""
    sql = """
        SELECT id, name, age, phone, aadhar, issue, doctor,
               appointment_time, status, source,
               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS timestamp
        FROM registrations
        ORDER BY created_at DESC
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            return [dict(r) for r in cur.fetchall()]


def update_registration_status(reg_id: int, status: str) -> bool:
    """Update appointment status (confirmed / cancelled / pending)."""
    sql = "UPDATE registrations SET status=%s, updated_at=NOW() WHERE id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, reg_id))
            return cur.rowcount > 0


# â”€â”€â”€ ATTENDANCE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def save_attendance(staff_name: str, action: str, notes: str = "") -> int:
    """Record check-in or check-out, return new row id."""
    sql = """
        INSERT INTO attendance (staff_name, action, notes, recorded_at)
        VALUES (%s, %s, %s, NOW())
        RETURNING id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (staff_name, action, notes))
            return cur.fetchone()[0]


def get_attendance_today() -> list:
    """Return today's attendance records."""
    sql = """
        SELECT id, staff_name, action, notes,
               TO_CHAR(recorded_at, 'YYYY-MM-DD HH24:MI:SS') AS date
        FROM attendance
        WHERE DATE(recorded_at) = CURRENT_DATE
        ORDER BY recorded_at DESC
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def get_attendance_all(limit: int = 500) -> list:
    """Return recent attendance records."""
    sql = """
        SELECT id, staff_name, action, notes,
               TO_CHAR(recorded_at, 'YYYY-MM-DD HH24:MI:SS') AS date
        FROM attendance
        ORDER BY recorded_at DESC
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            return [dict(r) for r in cur.fetchall()]


# â”€â”€â”€ DOCTORS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_all_doctors() -> list:
    """Return all doctors."""
    sql = """
        SELECT id, name, department, specialization, status, on_duty,
               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
        FROM doctors
        ORDER BY name
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def get_doctors_on_duty() -> list:
    """Return doctors currently on duty."""
    sql = "SELECT id, name, department, specialization, status FROM doctors WHERE on_duty=TRUE ORDER BY name"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def doctor_checkin(doctor_name: str) -> bool:
    """Mark doctor as checked-in (on_duty=True, status=available)."""
    sql = "UPDATE doctors SET on_duty=TRUE, status='available' WHERE name ILIKE %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (f"%{doctor_name}%",))
            updated = cur.rowcount > 0
    # Also log in attendance table
    if updated:
        save_attendance(doctor_name, "checkin", "Doctor check-in")
    return updated


def doctor_checkout(doctor_name: str) -> bool:
    """Mark doctor as checked-out (on_duty=False, status=off_duty)."""
    sql = "UPDATE doctors SET on_duty=FALSE, status='off_duty' WHERE name ILIKE %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (f"%{doctor_name}%",))
            updated = cur.rowcount > 0
    if updated:
        save_attendance(doctor_name, "checkout", "Doctor check-out")
    return updated


# â”€â”€â”€ DOCTOR ROUNDS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_doctor_rounds() -> list:
    """Return all doctor rounds."""
    sql = """
        SELECT id, doctor_name, ward, round_time, status, notes,
               TO_CHAR(scheduled_at, 'YYYY-MM-DD HH24:MI:SS') AS scheduled_at,
               TO_CHAR(completed_at, 'YYYY-MM-DD HH24:MI:SS') AS completed_at
        FROM doctor_rounds
        ORDER BY scheduled_at DESC
        LIMIT 50
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def add_doctor_round(doctor_name: str, ward: str, round_time: str) -> int:
    """Schedule a new doctor round."""
    sql = """
        INSERT INTO doctor_rounds (doctor_name, ward, round_time, status, scheduled_at)
        VALUES (%s, %s, %s, 'pending', NOW())
        RETURNING id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (doctor_name, ward, round_time))
            return cur.fetchone()[0]


def complete_doctor_round(round_id: int) -> bool:
    """Mark a round as completed."""
    sql = "UPDATE doctor_rounds SET status='completed', completed_at=NOW() WHERE id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (round_id,))
            return cur.rowcount > 0


# â”€â”€â”€ ADMIN DASHBOARD DATA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_admin_dashboard_data() -> dict:
    """Aggregate data for the admin dashboard."""
    registrations  = get_all_registrations(200)
    attendance_today = get_attendance_today()
    doctors_on_duty  = get_doctors_on_duty()
    rounds           = get_doctor_rounds()

    today_str = time.strftime('%Y-%m-%d')
    today_registrations = [r for r in registrations if r.get('timestamp', '').startswith(today_str)]

    return {
        "status":           "online",
        "timestamp":        time.time(),
        "registrations":    registrations,
        "appointments":     registrations,
        "total_appointments": len(registrations),
        "today_patients":   len(today_registrations),
        "doctors_on_duty":  len(doctors_on_duty),
        "doctors":          doctors_on_duty,
        "attendance_today": attendance_today,
        "doctor_rounds":    rounds,
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RBAC TABLES â€” staff_users, stock, prescriptions, vitals
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def create_all_tables():
    """
    Create the four RBAC tables if they don't exist.
    Call once at server startup.
    """
    ddl = [
        # Staff users (login credentials + role)
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id                   SERIAL PRIMARY KEY,
            username             VARCHAR(80) UNIQUE NOT NULL,
            password_hash        TEXT NOT NULL,
            role                 VARCHAR(20) NOT NULL DEFAULT 'RECEPTION',
            department           VARCHAR(100) DEFAULT '',
            full_name            VARCHAR(150) DEFAULT '',
            is_active            BOOLEAN DEFAULT TRUE,
            must_change_password BOOLEAN DEFAULT TRUE,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Migration: add must_change_password to existing staff_users tables
        """
        ALTER TABLE staff_users
            ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT TRUE
        """,
        # Medical inventory / stock
        """
        CREATE TABLE IF NOT EXISTS stock (
            id           SERIAL PRIMARY KEY,
            item_name    VARCHAR(200) NOT NULL,
            category     VARCHAR(80) DEFAULT 'Medicine',
            quantity     INTEGER DEFAULT 0,
            unit         VARCHAR(30) DEFAULT 'units',
            min_quantity INTEGER DEFAULT 10,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Doctor prescriptions
        """
        CREATE TABLE IF NOT EXISTS prescriptions (
            id              SERIAL PRIMARY KEY,
            patient_name    VARCHAR(150),
            patient_phone   VARCHAR(20),
            doctor_username VARCHAR(80),
            doctor_name     VARCHAR(150),
            diagnosis       TEXT,
            medicines       TEXT,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Nurse vitals
        """
        CREATE TABLE IF NOT EXISTS vitals (
            id              SERIAL PRIMARY KEY,
            patient_name    VARCHAR(150),
            patient_phone   VARCHAR(20),
            nurse_username  VARCHAR(80),
            bp              VARCHAR(20) DEFAULT '',
            pulse           VARCHAR(10) DEFAULT '',
            temperature     VARCHAR(10) DEFAULT '',
            spo2            VARCHAR(10) DEFAULT '',
            weight          VARCHAR(10) DEFAULT '',
            notes           TEXT DEFAULT '',
            recorded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Lab / Xray orders
        """
        CREATE TABLE IF NOT EXISTS lab_orders (
            id              SERIAL PRIMARY KEY,
            patient_name    VARCHAR(150),
            patient_phone   VARCHAR(20),
            doctor_username VARCHAR(80),
            test_type       VARCHAR(30) DEFAULT 'LAB',
            test_name       VARCHAR(200),
            status          VARCHAR(20) DEFAULT 'PENDING',
            result_text     TEXT DEFAULT '',
            result_file     TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at    TIMESTAMP
        )
        """,
    ]
    conn = get_connection()
    if not conn:
        print("âš ï¸  DB not available â€” RBAC tables not created")
        return
    try:
        cur = conn.cursor()
        for stmt in ddl:
            cur.execute(stmt)
        conn.commit()
        cur.close()
        conn.close()
        print("âœ…  RBAC tables ready")
    except Exception as e:
        print(f"âŒ  create_all_tables error: {e}")

    # Also create the full SRP MediFlow HMS extended tables
    create_hms_tables()
    # Phase-2 extended tables: IPD, surgery, billing items, discharge
    create_extended_tables()


# â”€â”€ Staff Users â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_staff_user_by_username(username: str) -> dict | None:
    """Return staff user dict or None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,username,password_hash,role,department,full_name,is_active,"
            "COALESCE(must_change_password, TRUE) AS must_change_password "
            "FROM staff_users WHERE username=%s AND is_active=TRUE",
            (username,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return dict(zip(
                ['id','username','password_hash','role','department','full_name',
                 'is_active','must_change_password'], row
            ))
        return None
    except Exception as e:
        print(f"get_staff_user error: {e}")
        return None


def create_staff_user(username: str, password_hash: str, role: str,
                      department: str = '', full_name: str = '') -> int | None:
    """Insert a new staff user with must_change_password=TRUE. Returns new user id or None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO staff_users "
            "(username,password_hash,role,department,full_name,must_change_password) "
            "VALUES (%s,%s,%s,%s,%s,TRUE) RETURNING id",
            (username, password_hash, role.upper(), department, full_name)
        )
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"create_staff_user error: {e}")
        return None


def update_password(username: str, new_hash: str) -> bool:
    """Update password_hash and clear must_change_password flag for a user."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE staff_users "
            "SET password_hash=%s, must_change_password=FALSE "
            "WHERE username=%s AND is_active=TRUE",
            (new_hash, username)
        )
        affected = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return affected > 0
    except Exception as e:
        print(f"update_password error: {e}")
        return False


def list_staff_users() -> list:
    """Return list of all active staff users (no password_hash).
    Excludes FOUNDER accounts (platform-level, not hospital staff)
    and the old shared legacy default accounts (admin, doctor, nurse, lab, reception).
    """
    LEGACY_ACCOUNTS = {'admin', 'doctor', 'nurse', 'lab', 'reception'}
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,username,role,department,full_name,is_active,created_at "
            "FROM staff_users WHERE role != 'FOUNDER' ORDER BY role,username"
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','username','role','department','full_name','is_active','created_at']
        return [
            dict(zip(keys, r)) for r in rows
            if r[1] not in LEGACY_ACCOUNTS   # r[1] is username
        ]
    except Exception as e:
        print(f"list_staff_users error: {e}")
        return []


def delete_staff_user(user_id: int) -> bool:
    """Soft-delete (deactivate) a staff user by id."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("UPDATE staff_users SET is_active=FALSE WHERE id=%s", (user_id,))
        conn.commit(); cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"delete_staff_user error: {e}")
        return False


def ensure_default_admin(admin_hash: str):
    """Create default admin user if no staff users exist at all."""
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM staff_users")
        count = cur.fetchone()[0]
        if count == 0:
            cur.execute(
                "INSERT INTO staff_users "
                "(username,password_hash,role,full_name,must_change_password) "
                "VALUES (%s,%s,'ADMIN','System Administrator',TRUE)",
                ('admin', admin_hash)
            )
            conn.commit()
            print("✅  Default admin created: admin / hospital2024 (must change password on first login)")
        cur.close(); conn.close()
    except Exception as e:
        print(f"ensure_default_admin error: {e}")


# â”€â”€ Stock / Inventory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_all_stock() -> list:
    """Return all stock items ordered by category, name."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,item_name,category,quantity,unit,min_quantity,updated_at "
            "FROM stock ORDER BY category,item_name"
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','item_name','category','quantity','unit','min_quantity','updated_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_stock error: {e}")
        return []


def add_stock_item(item_name: str, category: str, quantity: int,
                   unit: str = 'units', min_qty: int = 10) -> int | None:
    """Add a new stock item. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO stock (item_name,category,quantity,unit,min_quantity) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (item_name, category, quantity, unit, min_qty)
        )
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_stock_item error: {e}")
        return None


def update_stock_qty(item_id: int, quantity: int) -> bool:
    """Update stock quantity and refresh updated_at."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE stock SET quantity=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (quantity, item_id)
        )
        conn.commit(); cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"update_stock_qty error: {e}")
        return False


# â”€â”€ Prescriptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_prescription(patient_name: str, patient_phone: str,
                     doctor_username: str, doctor_name: str,
                     diagnosis: str, medicines: str, notes: str = '') -> int | None:
    """Save a prescription. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO prescriptions "
            "(patient_name,patient_phone,doctor_username,doctor_name,diagnosis,medicines,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient_name, patient_phone, doctor_username, doctor_name, diagnosis, medicines, notes)
        )
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_prescription error: {e}")
        return None


def get_prescriptions_by_doctor(doctor_username: str, limit: int = 100) -> list:
    """Return prescriptions written by a doctor."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,patient_name,patient_phone,doctor_name,diagnosis,medicines,notes,created_at "
            "FROM prescriptions WHERE doctor_username=%s ORDER BY created_at DESC LIMIT %s",
            (doctor_username, limit)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','patient_name','patient_phone','doctor_name','diagnosis','medicines','notes','created_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_prescriptions_by_doctor error: {e}")
        return []


def get_all_prescriptions(limit: int = 200) -> list:
    """Return all prescriptions (for admin view)."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,patient_name,patient_phone,doctor_name,diagnosis,medicines,notes,created_at "
            "FROM prescriptions ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','patient_name','patient_phone','doctor_name','diagnosis','medicines','notes','created_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_prescriptions error: {e}")
        return []


# â”€â”€ Vitals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_vitals(patient_name: str, patient_phone: str, nurse_username: str,
               bp: str = '', pulse: str = '', temperature: str = '',
               spo2: str = '', weight: str = '', notes: str = '') -> int | None:
    """Save patient vitals. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vitals "
            "(patient_name,patient_phone,nurse_username,bp,pulse,temperature,spo2,weight,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient_name, patient_phone, nurse_username, bp, pulse, temperature, spo2, weight, notes)
        )
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_vitals error: {e}")
        return None


def get_vitals_by_patient(patient_phone: str, limit: int = 50) -> list:
    """Return vitals records for a patient phone number."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,patient_name,patient_phone,nurse_username,bp,pulse,temperature,"
            "spo2,weight,notes,recorded_at "
            "FROM vitals WHERE patient_phone=%s ORDER BY recorded_at DESC LIMIT %s",
            (patient_phone, limit)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','patient_name','patient_phone','nurse_username','bp','pulse',
                'temperature','spo2','weight','notes','recorded_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_vitals_by_patient error: {e}")
        return []


def get_all_vitals(limit: int = 200) -> list:
    """Return all vitals records (for nurse/admin view)."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,patient_name,patient_phone,nurse_username,bp,pulse,temperature,"
            "spo2,weight,notes,recorded_at "
            "FROM vitals ORDER BY recorded_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','patient_name','patient_phone','nurse_username','bp','pulse',
                'temperature','spo2','weight','notes','recorded_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_vitals error: {e}")
        return []


# â”€â”€ Lab / X-Ray Orders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_lab_order(patient_name: str, patient_phone: str,
                  doctor_username: str, test_type: str, test_name: str) -> int | None:
    """Create a lab or xray order. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO lab_orders (patient_name,patient_phone,doctor_username,test_type,test_name) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (patient_name, patient_phone, doctor_username, test_type.upper(), test_name)
        )
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_lab_order error: {e}")
        return None


def get_lab_orders(test_type: str = None, limit: int = 200) -> list:
    """Return lab orders, optionally filtered by test_type (LAB or XRAY)."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        if test_type:
            cur.execute(
                "SELECT id,patient_name,patient_phone,doctor_username,test_type,test_name,"
                "status,result_text,created_at,completed_at "
                "FROM lab_orders WHERE test_type=%s ORDER BY created_at DESC LIMIT %s",
                (test_type.upper(), limit)
            )
        else:
            cur.execute(
                "SELECT id,patient_name,patient_phone,doctor_username,test_type,test_name,"
                "status,result_text,created_at,completed_at "
                "FROM lab_orders ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id','patient_name','patient_phone','doctor_username','test_type','test_name',
                'status','result_text','created_at','completed_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_lab_orders error: {e}")
        return []


def complete_lab_order(order_id: int, result_text: str) -> bool:
    """Mark a lab order as completed and store result text."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE lab_orders SET status='COMPLETED', result_text=%s, "
            "completed_at=CURRENT_TIMESTAMP WHERE id=%s",
            (result_text, order_id)
        )
        conn.commit(); cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"complete_lab_order error: {e}")
        return False


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SRP MEDIFLOW HMS â€” EXTENDED TABLE DEFINITIONS
# All tables use IF NOT EXISTS â€” safe to run at every startup.
# Existing data is never touched.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def create_hms_tables():
    """
    Create (or verify) the full SRP MediFlow HMS table set.
    Safe to call on every server start â€” uses IF NOT EXISTS throughout.
    Tables added:
      patients, departments, doctors (extended), appointments,
      visit_records, prescriptions (extended), lab_tests, lab_orders (extended),
      lab_reports, imaging_tests, imaging_orders, imaging_reports,
      medicines, inventory_stock, pharmacy_sales, pharmacy_sale_items,
      billing, payments, doctor_attendance, nurse_assignments,
      wards, beds, bed_assignments, system_logs
    """
    ddl_statements = [

        # â”€â”€ Patients (master record) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS patients (
            id            SERIAL PRIMARY KEY,
            full_name     VARCHAR(150) NOT NULL,
            dob           DATE,
            gender        VARCHAR(10) DEFAULT 'Unknown',
            phone         VARCHAR(20),
            aadhar        VARCHAR(20),
            address       TEXT DEFAULT '',
            blood_group   VARCHAR(5) DEFAULT '',
            allergies     TEXT DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Departments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS departments (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            head_doctor VARCHAR(150) DEFAULT '',
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Appointments (extended) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20),
            patient_aadhar   VARCHAR(20) DEFAULT '',
            age              VARCHAR(10) DEFAULT '',
            issue            TEXT DEFAULT '',
            doctor_name      VARCHAR(150) DEFAULT '',
            department       VARCHAR(100) DEFAULT '',
            appointment_date DATE,
            appointment_time VARCHAR(20) DEFAULT '',
            status           VARCHAR(30) DEFAULT 'pending',
            source           VARCHAR(30) DEFAULT 'chatbot',
            notes            TEXT DEFAULT '',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Visit Records (doctor consultation notes) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS visit_records (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20) DEFAULT '',
            doctor_username  VARCHAR(80),
            doctor_name      VARCHAR(150) DEFAULT '',
            department       VARCHAR(100) DEFAULT '',
            chief_complaint  TEXT DEFAULT '',
            examination      TEXT DEFAULT '',
            diagnosis        TEXT DEFAULT '',
            treatment_plan   TEXT DEFAULT '',
            follow_up_date   DATE,
            visit_date       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Lab Tests (catalogue) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS lab_tests (
            id          SERIAL PRIMARY KEY,
            test_code   VARCHAR(20) UNIQUE NOT NULL,
            test_name   VARCHAR(200) NOT NULL,
            category    VARCHAR(80) DEFAULT 'Pathology',
            normal_range VARCHAR(100) DEFAULT '',
            unit        VARCHAR(30) DEFAULT '',
            price       NUMERIC(10,2) DEFAULT 0,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Lab Reports (results uploaded by lab staff) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS lab_reports (
            id               SERIAL PRIMARY KEY,
            order_id         INTEGER REFERENCES lab_orders(id) ON DELETE SET NULL,
            patient_name     VARCHAR(150),
            patient_phone    VARCHAR(20) DEFAULT '',
            test_name        VARCHAR(200),
            result_text      TEXT DEFAULT '',
            result_file_path TEXT DEFAULT '',
            remarks          TEXT DEFAULT '',
            lab_username     VARCHAR(80),
            reported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Imaging Tests (catalogue) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS imaging_tests (
            id          SERIAL PRIMARY KEY,
            test_code   VARCHAR(20) UNIQUE NOT NULL,
            test_name   VARCHAR(200) NOT NULL,
            modality    VARCHAR(50) DEFAULT 'X-Ray',
            body_part   VARCHAR(100) DEFAULT '',
            price       NUMERIC(10,2) DEFAULT 0,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Imaging Orders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS imaging_orders (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20) DEFAULT '',
            doctor_username  VARCHAR(80),
            modality         VARCHAR(50) DEFAULT 'X-Ray',
            body_part        VARCHAR(100) DEFAULT '',
            clinical_notes   TEXT DEFAULT '',
            status           VARCHAR(20) DEFAULT 'PENDING',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at     TIMESTAMP
        )
        """,

        # â”€â”€ Imaging Reports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS imaging_reports (
            id               SERIAL PRIMARY KEY,
            order_id         INTEGER REFERENCES imaging_orders(id) ON DELETE SET NULL,
            patient_name     VARCHAR(150),
            modality         VARCHAR(50) DEFAULT 'X-Ray',
            findings         TEXT DEFAULT '',
            impression       TEXT DEFAULT '',
            report_file_path TEXT DEFAULT '',
            radiologist      VARCHAR(150) DEFAULT '',
            reported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Medicines (pharmacy catalogue) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS medicines (
            id            SERIAL PRIMARY KEY,
            medicine_name VARCHAR(200) NOT NULL,
            generic_name  VARCHAR(200) DEFAULT '',
            category      VARCHAR(80) DEFAULT 'Tablet',
            manufacturer  VARCHAR(150) DEFAULT '',
            unit          VARCHAR(30) DEFAULT 'Strip',
            unit_price    NUMERIC(10,2) DEFAULT 0,
            is_active     BOOLEAN DEFAULT TRUE,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Inventory Stock (pharmacy stock levels) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS inventory_stock (
            id            SERIAL PRIMARY KEY,
            medicine_id   INTEGER REFERENCES medicines(id) ON DELETE CASCADE,
            batch_no      VARCHAR(50) DEFAULT '',
            expiry_date   DATE,
            quantity      INTEGER DEFAULT 0,
            min_quantity  INTEGER DEFAULT 10,
            purchase_price NUMERIC(10,2) DEFAULT 0,
            sell_price     NUMERIC(10,2) DEFAULT 0,
            updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Pharmacy Sales (bill header) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS pharmacy_sales (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) DEFAULT 'Walk-in',
            patient_phone    VARCHAR(20) DEFAULT '',
            prescription_id  INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL,
            total_amount     NUMERIC(10,2) DEFAULT 0,
            discount         NUMERIC(10,2) DEFAULT 0,
            net_amount       NUMERIC(10,2) DEFAULT 0,
            payment_mode     VARCHAR(30) DEFAULT 'Cash',
            staff_username   VARCHAR(80),
            sold_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Pharmacy Sale Items (line items) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS pharmacy_sale_items (
            id          SERIAL PRIMARY KEY,
            sale_id     INTEGER REFERENCES pharmacy_sales(id) ON DELETE CASCADE,
            medicine_id INTEGER REFERENCES medicines(id) ON DELETE SET NULL,
            medicine_name VARCHAR(200),
            quantity    INTEGER DEFAULT 1,
            unit_price  NUMERIC(10,2) DEFAULT 0,
            total_price NUMERIC(10,2) DEFAULT 0
        )
        """,

        # â”€â”€ Billing (OPD / IPD bill header) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS billing (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20) DEFAULT '',
            bill_type        VARCHAR(20) DEFAULT 'OPD',
            consultation_fee NUMERIC(10,2) DEFAULT 0,
            lab_charges      NUMERIC(10,2) DEFAULT 0,
            pharmacy_charges NUMERIC(10,2) DEFAULT 0,
            imaging_charges  NUMERIC(10,2) DEFAULT 0,
            misc_charges     NUMERIC(10,2) DEFAULT 0,
            total_amount     NUMERIC(10,2) DEFAULT 0,
            discount         NUMERIC(10,2) DEFAULT 0,
            net_amount       NUMERIC(10,2) DEFAULT 0,
            status           VARCHAR(20) DEFAULT 'unpaid',
            created_by       VARCHAR(80),
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Payments (receipts against a bill) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS payments (
            id            SERIAL PRIMARY KEY,
            bill_id       INTEGER REFERENCES billing(id) ON DELETE CASCADE,
            amount_paid   NUMERIC(10,2) DEFAULT 0,
            payment_mode  VARCHAR(30) DEFAULT 'Cash',
            reference_no  VARCHAR(100) DEFAULT '',
            received_by   VARCHAR(80),
            paid_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Doctor Attendance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS doctor_attendance (
            id           SERIAL PRIMARY KEY,
            doctor_name  VARCHAR(150) NOT NULL,
            action       VARCHAR(20) NOT NULL,
            shift        VARCHAR(20) DEFAULT 'Morning',
            notes        TEXT DEFAULT '',
            recorded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Nurse Assignments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS nurse_assignments (
            id              SERIAL PRIMARY KEY,
            nurse_username  VARCHAR(80) NOT NULL,
            patient_name    VARCHAR(150),
            patient_phone   VARCHAR(20) DEFAULT '',
            ward            VARCHAR(80) DEFAULT '',
            bed_number      VARCHAR(20) DEFAULT '',
            shift           VARCHAR(20) DEFAULT 'Morning',
            assigned_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            discharged_at   TIMESTAMP
        )
        """,

        # â”€â”€ Wards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS wards (
            id          SERIAL PRIMARY KEY,
            ward_name   VARCHAR(100) UNIQUE NOT NULL,
            ward_type   VARCHAR(50) DEFAULT 'General',
            total_beds  INTEGER DEFAULT 0,
            floor       VARCHAR(20) DEFAULT 'Ground',
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Beds â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS beds (
            id          SERIAL PRIMARY KEY,
            ward_id     INTEGER REFERENCES wards(id) ON DELETE CASCADE,
            bed_number  VARCHAR(20) NOT NULL,
            bed_type    VARCHAR(50) DEFAULT 'General',
            status      VARCHAR(20) DEFAULT 'available',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ward_id, bed_number)
        )
        """,

        # â”€â”€ Bed Assignments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS bed_assignments (
            id              SERIAL PRIMARY KEY,
            bed_id          INTEGER REFERENCES beds(id) ON DELETE SET NULL,
            patient_name    VARCHAR(150) NOT NULL,
            patient_phone   VARCHAR(20) DEFAULT '',
            admitted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            discharged_at   TIMESTAMP,
            notes           TEXT DEFAULT ''
        )
        """,

        # â”€â”€ System Logs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS system_logs (
            id          SERIAL PRIMARY KEY,
            username    VARCHAR(80) DEFAULT 'system',
            role        VARCHAR(20) DEFAULT '',
            action      VARCHAR(200) NOT NULL,
            details     TEXT DEFAULT '',
            ip_address  VARCHAR(45) DEFAULT '',
            logged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]

    conn = get_connection()
    if not conn:
        print("âš ï¸  DB not available â€” HMS extended tables not created")
        return
    try:
        cur = conn.cursor()
        for stmt in ddl_statements:
            try:
                cur.execute(stmt)
            except Exception as e:
                print(f"  âš ï¸  DDL warning (skipped): {e}")
                conn.rollback()
                # Re-open cursor after rollback
                cur = conn.cursor()
        conn.commit()
        cur.close()
        conn.close()
        print("âœ…  SRP MediFlow HMS tables verified / created")
    except Exception as e:
        print(f"âŒ  create_hms_tables error: {e}")


# â”€â”€ System Log Helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def log_action(username: str, role: str, action: str,
               details: str = '', ip_address: str = '') -> None:
    """Insert a row into system_logs. Silently fails on DB error."""
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO system_logs (username, role, action, details, ip_address) "
            "VALUES (%s, %s, %s, %s, %s)",
            (username, role, action, details, ip_address)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def get_system_logs(limit: int = 200) -> list:
    """Return recent system log entries."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, role, action, details, ip_address, "
            "TO_CHAR(logged_at, 'YYYY-MM-DD HH24:MI:SS') AS logged_at "
            "FROM system_logs ORDER BY logged_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        keys = ['id', 'username', 'role', 'action', 'details', 'ip_address', 'logged_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_system_logs error: {e}")
        return []


# â”€â”€ Billing helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def create_bill(patient_name: str, patient_phone: str, bill_type: str = 'OPD',
                consultation_fee: float = 0, lab_charges: float = 0,
                pharmacy_charges: float = 0, imaging_charges: float = 0,
                misc_charges: float = 0, discount: float = 0,
                created_by: str = 'reception') -> int | None:
    """Create a new billing record. Returns bill id or None."""
    total = consultation_fee + lab_charges + pharmacy_charges + imaging_charges + misc_charges
    net   = max(0, total - discount)
    conn  = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO billing "
            "(patient_name, patient_phone, bill_type, consultation_fee, lab_charges, "
            " pharmacy_charges, imaging_charges, misc_charges, total_amount, discount, "
            " net_amount, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient_name, patient_phone, bill_type, consultation_fee, lab_charges,
             pharmacy_charges, imaging_charges, misc_charges, total, discount, net, created_by)
        )
        bill_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return bill_id
    except Exception as e:
        print(f"create_bill error: {e}")
        return None


def get_all_bills(limit: int = 200) -> list:
    """Return recent billing records."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, patient_name, patient_phone, bill_type, total_amount, "
            "discount, net_amount, status, created_by, "
            "TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at "
            "FROM billing ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        keys = ['id', 'patient_name', 'patient_phone', 'bill_type', 'total_amount',
                'discount', 'net_amount', 'status', 'created_by', 'created_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_bills error: {e}")
        return []


def record_payment(bill_id: int, amount_paid: float,
                   payment_mode: str = 'Cash', reference_no: str = '',
                   received_by: str = '') -> int | None:
    """Insert a payment record and update bill status. Returns payment id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO payments (bill_id, amount_paid, payment_mode, reference_no, received_by) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (bill_id, amount_paid, payment_mode, reference_no, received_by)
        )
        pay_id = cur.fetchone()[0]
        # Sum payments against the bill
        cur.execute(
            "SELECT net_amount, "
            "(SELECT COALESCE(SUM(amount_paid),0) FROM payments WHERE bill_id=%s) "
            "FROM billing WHERE id=%s",
            (bill_id, bill_id)
        )
        row = cur.fetchone()
        if row:
            net_amount, paid_total = row
            new_status = 'paid' if paid_total >= net_amount else 'partial'
            cur.execute("UPDATE billing SET status=%s, updated_at=NOW() WHERE id=%s",
                        (new_status, bill_id))
        conn.commit()
        cur.close()
        conn.close()
        return pay_id
    except Exception as e:
        print(f"record_payment error: {e}")
        return None


# â”€â”€ Visit Record helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_visit_record(patient_name: str, patient_phone: str,
                     doctor_username: str, doctor_name: str,
                     chief_complaint: str = '', examination: str = '',
                     diagnosis: str = '', treatment_plan: str = '',
                     department: str = '') -> int | None:
    """Save a doctor's visit record. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO visit_records "
            "(patient_name, patient_phone, doctor_username, doctor_name, department, "
            " chief_complaint, examination, diagnosis, treatment_plan) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (patient_name, patient_phone, doctor_username, doctor_name, department,
             chief_complaint, examination, diagnosis, treatment_plan)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        print(f"add_visit_record error: {e}")
        return None


def get_visit_records_by_doctor(doctor_username: str, limit: int = 100) -> list:
    """Return visit records for a doctor."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, patient_name, patient_phone, doctor_name, department, "
            "chief_complaint, diagnosis, treatment_plan, "
            "TO_CHAR(visit_date, 'YYYY-MM-DD HH24:MI') AS visit_date "
            "FROM visit_records WHERE doctor_username=%s "
            "ORDER BY visit_date DESC LIMIT %s",
            (doctor_username, limit)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        keys = ['id', 'patient_name', 'patient_phone', 'doctor_name', 'department',
                'chief_complaint', 'diagnosis', 'treatment_plan', 'visit_date']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_visit_records_by_doctor error: {e}")
        return []


def get_all_visit_records(limit: int = 200) -> list:
    """Return all visit records (admin view)."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, patient_name, patient_phone, doctor_name, department, "
            "chief_complaint, diagnosis, treatment_plan, "
            "TO_CHAR(visit_date, 'YYYY-MM-DD HH24:MI') AS visit_date "
            "FROM visit_records ORDER BY visit_date DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        keys = ['id', 'patient_name', 'patient_phone', 'doctor_name', 'department',
                'chief_complaint', 'diagnosis', 'treatment_plan', 'visit_date']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_visit_records error: {e}")
        return []


# â”€â”€ Nurse Assignment helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def add_nurse_assignment(nurse_username: str, patient_name: str,
                          patient_phone: str = '', ward: str = '',
                          bed_number: str = '', shift: str = 'Morning') -> int | None:
    """Assign a nurse to a patient. Returns new id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO nurse_assignments "
            "(nurse_username, patient_name, patient_phone, ward, bed_number, shift) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (nurse_username, patient_name, patient_phone, ward, bed_number, shift)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        print(f"add_nurse_assignment error: {e}")
        return None


def get_nurse_assignments(nurse_username: str = None, limit: int = 100) -> list:
    """Return nurse assignments, optionally filtered by nurse username."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        if nurse_username:
            cur.execute(
                "SELECT id, nurse_username, patient_name, patient_phone, ward, "
                "bed_number, shift, "
                "TO_CHAR(assigned_at, 'YYYY-MM-DD HH24:MI') AS assigned_at "
                "FROM nurse_assignments WHERE nurse_username=%s "
                "AND discharged_at IS NULL ORDER BY assigned_at DESC LIMIT %s",
                (nurse_username, limit)
            )
        else:
            cur.execute(
                "SELECT id, nurse_username, patient_name, patient_phone, ward, "
                "bed_number, shift, "
                "TO_CHAR(assigned_at, 'YYYY-MM-DD HH24:MI') AS assigned_at "
                "FROM nurse_assignments WHERE discharged_at IS NULL "
                "ORDER BY assigned_at DESC LIMIT %s",
                (limit,)
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        keys = ['id', 'nurse_username', 'patient_name', 'patient_phone',
                'ward', 'bed_number', 'shift', 'assigned_at']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_nurse_assignments error: {e}")
        return []


def get_all_medicines(active_only: bool = True) -> list:
    """Return all medicines from the catalogue (for stock add dropdowns)."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            if active_only:
                cur.execute(
                    "SELECT id, medicine_name, generic_name, category, unit, unit_price "
                    "FROM medicines WHERE is_active = TRUE ORDER BY medicine_name"
                )
            else:
                cur.execute(
                    "SELECT id, medicine_name, generic_name, category, unit, unit_price "
                    "FROM medicines ORDER BY medicine_name"
                )
            keys = ['id', 'medicine_name', 'generic_name', 'category', 'unit', 'unit_price']
            return [dict(zip(keys, r)) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_all_medicines error: {e}")
        return []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SRP MEDIFLOW HMS â€” PHASE 2 EXTENDED TABLES
# IPD Admissions, Surgery, Procedure Charges, Bill Items (GST),
# Discharge Summaries, Enhanced Inventory Stock
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def create_extended_tables():
    """
    Create Phase-2 SRP MediFlow tables.
    Safe to run every startup â€” all use IF NOT EXISTS.
    """
    ddl_statements = [

        # â”€â”€ Patient Admissions (IPD) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS patient_admissions (
            id               SERIAL PRIMARY KEY,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20) DEFAULT '',
            patient_aadhar   VARCHAR(20) DEFAULT '',
            age              VARCHAR(10) DEFAULT '',
            gender           VARCHAR(10) DEFAULT 'Unknown',
            blood_group      VARCHAR(5) DEFAULT '',
            address          TEXT DEFAULT '',
            admission_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            discharge_date   TIMESTAMP,
            ward_name        VARCHAR(100) DEFAULT '',
            bed_number       VARCHAR(20) DEFAULT '',
            admitting_doctor VARCHAR(150) DEFAULT '',
            department       VARCHAR(100) DEFAULT '',
            diagnosis        TEXT DEFAULT '',
            admission_notes  TEXT DEFAULT '',
            status           VARCHAR(20) DEFAULT 'admitted',
            created_by       VARCHAR(80) DEFAULT 'reception',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Procedure Charges Catalogue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS procedure_charges (
            id             SERIAL PRIMARY KEY,
            procedure_name VARCHAR(200) NOT NULL,
            category       VARCHAR(80) DEFAULT 'General',
            default_price  NUMERIC(10,2) DEFAULT 0,
            gst_percent    NUMERIC(5,2) DEFAULT 0,
            description    TEXT DEFAULT '',
            is_active      BOOLEAN DEFAULT TRUE,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Surgery Records â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS surgery_records (
            id               SERIAL PRIMARY KEY,
            admission_id     INTEGER REFERENCES patient_admissions(id) ON DELETE SET NULL,
            patient_name     VARCHAR(150) NOT NULL,
            patient_phone    VARCHAR(20) DEFAULT '',
            surgeon_name     VARCHAR(150) DEFAULT '',
            surgeon_username VARCHAR(80) DEFAULT '',
            surgery_type     VARCHAR(200) NOT NULL,
            anesthesia_type  VARCHAR(100) DEFAULT 'General',
            estimated_cost   NUMERIC(10,2) DEFAULT 0,
            negotiated_cost  NUMERIC(10,2) DEFAULT 0,
            operation_date   TIMESTAMP,
            duration_minutes INTEGER DEFAULT 0,
            operation_notes  TEXT DEFAULT '',
            complications    TEXT DEFAULT '',
            status           VARCHAR(30) DEFAULT 'scheduled',
            created_by       VARCHAR(80) DEFAULT '',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Discharge Summaries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS discharge_summaries (
            id                 SERIAL PRIMARY KEY,
            admission_id       INTEGER REFERENCES patient_admissions(id) ON DELETE CASCADE,
            patient_name       VARCHAR(150) NOT NULL,
            discharge_date     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            final_diagnosis    TEXT DEFAULT '',
            treatment_given    TEXT DEFAULT '',
            discharge_medicines TEXT DEFAULT '',
            follow_up_date     DATE,
            follow_up_notes    TEXT DEFAULT '',
            diet_advice        TEXT DEFAULT '',
            activity_advice    TEXT DEFAULT '',
            doctor_name        VARCHAR(150) DEFAULT '',
            doctor_username    VARCHAR(80) DEFAULT '',
            bill_id            INTEGER REFERENCES billing(id) ON DELETE SET NULL,
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Bill Items (per-line with GST) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS bill_items (
            id             SERIAL PRIMARY KEY,
            bill_id        INTEGER REFERENCES billing(id) ON DELETE CASCADE,
            item_type      VARCHAR(50) DEFAULT 'consultation',
            item_name      VARCHAR(200) NOT NULL,
            item_price     NUMERIC(10,2) DEFAULT 0,
            quantity       INTEGER DEFAULT 1,
            actual_price   NUMERIC(10,2) DEFAULT 0,
            negotiated_price NUMERIC(10,2) DEFAULT 0,
            tax_percent    NUMERIC(5,2) DEFAULT 0,
            tax_amount     NUMERIC(10,2) DEFAULT 0,
            total_amount   NUMERIC(10,2) DEFAULT 0,
            notes          TEXT DEFAULT '',
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # â”€â”€ Daily Rounds (IPD) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        CREATE TABLE IF NOT EXISTS daily_rounds (
            id              SERIAL PRIMARY KEY,
            admission_id    INTEGER REFERENCES patient_admissions(id) ON DELETE CASCADE,
            patient_name    VARCHAR(150) NOT NULL,
            doctor_name     VARCHAR(150) DEFAULT '',
            doctor_username VARCHAR(80) DEFAULT '',
            round_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            bp              VARCHAR(20) DEFAULT '',
            pulse           VARCHAR(10) DEFAULT '',
            temperature     VARCHAR(10) DEFAULT '',
            spo2            VARCHAR(10) DEFAULT '',
            clinical_notes  TEXT DEFAULT '',
            treatment_change TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]

    # Alter inventory_stock to add supplier and batch_number columns
    alter_statements = [
        "ALTER TABLE inventory_stock ADD COLUMN IF NOT EXISTS supplier VARCHAR(150) DEFAULT ''",
        "ALTER TABLE inventory_stock ADD COLUMN IF NOT EXISTS batch_number VARCHAR(50) DEFAULT ''",
    ]
    # Alter billing to add extended charge columns
    billing_alters = [
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS bed_charges NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS surgery_charges NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS procedure_charges NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS admission_id INTEGER",
        "ALTER TABLE billing ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
    ]

    conn = get_connection()
    if not conn:
        print("âš ï¸  DB not available â€” Phase-2 extended tables not created")
        return
    try:
        cur = conn.cursor()
        for stmt in ddl_statements + alter_statements + billing_alters:
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception as e:
                conn.rollback()
                cur = conn.cursor()
        cur.close()
        conn.close()
        print("âœ…  SRP MediFlow Phase-2 tables (IPD/Surgery/Billing) ready")
    except Exception as e:
        print(f"âŒ  create_extended_tables error: {e}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# IPD ADMISSION FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def admit_patient(patient_name: str, patient_phone: str = '', patient_aadhar: str = '',
                  age: str = '', gender: str = 'Unknown', blood_group: str = '',
                  address: str = '', ward_name: str = '', bed_number: str = '',
                  admitting_doctor: str = '', department: str = '',
                  diagnosis: str = '', admission_notes: str = '',
                  created_by: str = 'reception') -> int | None:
    """Record a new IPD admission. Returns admission id or None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO patient_admissions
               (patient_name, patient_phone, patient_aadhar, age, gender, blood_group,
                address, ward_name, bed_number, admitting_doctor, department,
                diagnosis, admission_notes, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (patient_name, patient_phone, patient_aadhar, age, gender, blood_group,
             address, ward_name, bed_number, admitting_doctor, department,
             diagnosis, admission_notes, created_by)
        )
        adm_id = cur.fetchone()[0]
        # Mark bed as occupied
        if bed_number and ward_name:
            cur.execute(
                "UPDATE beds SET status='occupied' WHERE bed_number=%s "
                "AND ward_id=(SELECT id FROM wards WHERE ward_name=%s LIMIT 1)",
                (bed_number, ward_name)
            )
        conn.commit()
        cur.close()
        conn.close()
        return adm_id
    except Exception as e:
        print(f"admit_patient error: {e}")
        return None


def get_all_admissions(status: str = None, limit: int = 200) -> list:
    """Return IPD admissions, optionally filtered by status."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        if status:
            cur.execute(
                """SELECT id, patient_name, patient_phone, age, gender, ward_name, bed_number,
                          admitting_doctor, department, diagnosis, status,
                          TO_CHAR(admission_date, 'YYYY-MM-DD HH24:MI') AS admission_date,
                          TO_CHAR(discharge_date, 'YYYY-MM-DD HH24:MI') AS discharge_date
                   FROM patient_admissions WHERE status=%s
                   ORDER BY admission_date DESC LIMIT %s""",
                (status, limit)
            )
        else:
            cur.execute(
                """SELECT id, patient_name, patient_phone, age, gender, ward_name, bed_number,
                          admitting_doctor, department, diagnosis, status,
                          TO_CHAR(admission_date, 'YYYY-MM-DD HH24:MI') AS admission_date,
                          TO_CHAR(discharge_date, 'YYYY-MM-DD HH24:MI') AS discharge_date
                   FROM patient_admissions
                   ORDER BY admission_date DESC LIMIT %s""",
                (limit,)
            )
        rows = cur.fetchall()
        cur.close(); conn.close()
        keys = ['id', 'patient_name', 'patient_phone', 'age', 'gender', 'ward_name',
                'bed_number', 'admitting_doctor', 'department', 'diagnosis', 'status',
                'admission_date', 'discharge_date']
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        print(f"get_all_admissions error: {e}")
        return []


def get_admission_by_id(admission_id: int) -> dict | None:
    """Return full admission record."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM patient_admissions WHERE id=%s", (admission_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"get_admission_by_id error: {e}")
        return None


def discharge_patient(admission_id: int, doctor_username: str = '',
                      doctor_name: str = '', final_diagnosis: str = '',
                      treatment_given: str = '', discharge_medicines: str = '',
                      follow_up_date: str = None, follow_up_notes: str = '',
                      diet_advice: str = '', activity_advice: str = '') -> int | None:
    """
    Mark patient as discharged and save discharge summary.
    Returns discharge_summary id or None.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        # Update admission status and discharge date
        cur.execute(
            "UPDATE patient_admissions SET status='discharged', discharge_date=NOW(), "
            "updated_at=NOW() WHERE id=%s RETURNING ward_name, bed_number",
            (admission_id,)
        )
        row = cur.fetchone()
        if row:
            ward_name, bed_number = row
            # Free up the bed
            if bed_number and ward_name:
                cur.execute(
                    "UPDATE beds SET status='available' WHERE bed_number=%s "
                    "AND ward_id=(SELECT id FROM wards WHERE ward_name=%s LIMIT 1)",
                    (bed_number, ward_name)
                )
        # Get patient name for summary
        cur.execute("SELECT patient_name FROM patient_admissions WHERE id=%s", (admission_id,))
        name_row = cur.fetchone()
        patient_name = name_row[0] if name_row else ''
        # Save discharge summary
        cur.execute(
            """INSERT INTO discharge_summaries
               (admission_id, patient_name, final_diagnosis, treatment_given,
                discharge_medicines, follow_up_notes, diet_advice, activity_advice,
                doctor_name, doctor_username, follow_up_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (admission_id, patient_name, final_diagnosis, treatment_given,
             discharge_medicines, follow_up_notes, diet_advice, activity_advice,
             doctor_name, doctor_username, follow_up_date or None)
        )
        ds_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return ds_id
    except Exception as e:
        print(f"discharge_patient error: {e}")
        return None


def get_discharge_summary(admission_id: int) -> dict | None:
    """Return discharge summary for an admission."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM discharge_summaries WHERE admission_id=%s ORDER BY created_at DESC LIMIT 1",
            (admission_id,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"get_discharge_summary error: {e}")
        return None


def add_daily_round(admission_id: int, patient_name: str,
                    doctor_name: str = '', doctor_username: str = '',
                    bp: str = '', pulse: str = '', temperature: str = '',
                    spo2: str = '', clinical_notes: str = '',
                    treatment_change: str = '') -> int | None:
    """Record a daily doctor round for an IPD patient."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO daily_rounds
               (admission_id, patient_name, doctor_name, doctor_username,
                bp, pulse, temperature, spo2, clinical_notes, treatment_change)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (admission_id, patient_name, doctor_name, doctor_username,
             bp, pulse, temperature, spo2, clinical_notes, treatment_change)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_daily_round error: {e}")
        return None


def get_daily_rounds(admission_id: int) -> list:
    """Return all daily rounds for an admission."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM daily_rounds WHERE admission_id=%s ORDER BY round_date DESC",
            (admission_id,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_daily_rounds error: {e}")
        return []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SURGERY FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def create_surgery_record(patient_name: str, patient_phone: str = '',
                          admission_id: int = None, surgeon_name: str = '',
                          surgeon_username: str = '', surgery_type: str = '',
                          anesthesia_type: str = 'General',
                          estimated_cost: float = 0, negotiated_cost: float = 0,
                          operation_date: str = None, operation_notes: str = '',
                          created_by: str = '') -> int | None:
    """Record a surgery. Returns surgery id or None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO surgery_records
               (patient_name, patient_phone, admission_id, surgeon_name, surgeon_username,
                surgery_type, anesthesia_type, estimated_cost, negotiated_cost,
                operation_date, operation_notes, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (patient_name, patient_phone, admission_id, surgeon_name, surgeon_username,
             surgery_type, anesthesia_type, estimated_cost, negotiated_cost,
             operation_date, operation_notes, created_by)
        )
        sur_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return sur_id
    except Exception as e:
        print(f"create_surgery_record error: {e}")
        return None


def get_surgery_records(limit: int = 200) -> list:
    """Return all surgery records."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM surgery_records ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_surgery_records error: {e}")
        return []


def update_surgery_negotiated_cost(surgery_id: int, negotiated_cost: float,
                                    notes: str = '') -> bool:
    """Update the negotiated cost for a surgery."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE surgery_records SET negotiated_cost=%s, operation_notes=%s, "
            "updated_at=NOW() WHERE id=%s",
            (negotiated_cost, notes, surgery_id)
        )
        conn.commit()
        cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"update_surgery_negotiated_cost error: {e}")
        return False


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PROCEDURE CHARGES FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def get_procedure_charges(active_only: bool = True) -> list:
    """Return procedure charges catalogue."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if active_only:
            cur.execute(
                "SELECT * FROM procedure_charges WHERE is_active=TRUE ORDER BY category, procedure_name"
            )
        else:
            cur.execute("SELECT * FROM procedure_charges ORDER BY category, procedure_name")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_procedure_charges error: {e}")
        return []


def add_procedure_charge(procedure_name: str, category: str = 'General',
                         default_price: float = 0, gst_percent: float = 0,
                         description: str = '') -> int | None:
    """Add a procedure to the catalogue."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO procedure_charges (procedure_name, category, default_price, "
            "gst_percent, description) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (procedure_name, category, default_price, gst_percent, description)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_procedure_charge error: {e}")
        return None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# FLEXIBLE BILLING FUNCTIONS (with per-item GST)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# GST rates per item type (India)
GST_RATES = {
    'consultation': 0.0,
    'lab':          0.0,
    'imaging':      0.0,
    'surgery':      0.0,
    'bed':          0.0,
    'procedure':    0.0,
    'medicine_5':   5.0,
    'medicine_12':  12.0,
    'medicine_18':  18.0,
    'pharmacy':     5.0,  # default for pharmacy
}


def add_bill_item(bill_id: int, item_type: str, item_name: str,
                  item_price: float, quantity: int = 1,
                  negotiated_price: float = None,
                  tax_percent: float = None, notes: str = '') -> int | None:
    """
    Add a line item to a bill.
    - item_price = default/catalog price
    - negotiated_price = override price (used if provided, else item_price)
    - tax_percent = explicit override; if None, look up from GST_RATES
    Returns new bill_item id.
    """
    if negotiated_price is None:
        negotiated_price = item_price
    if tax_percent is None:
        tax_percent = GST_RATES.get(item_type.lower(), 0.0)

    actual_price   = negotiated_price * quantity
    tax_amount     = round(actual_price * tax_percent / 100, 2)
    total_amount   = round(actual_price + tax_amount, 2)

    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO bill_items
               (bill_id, item_type, item_name, item_price, quantity,
                actual_price, negotiated_price, tax_percent, tax_amount, total_amount, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (bill_id, item_type, item_name, item_price, quantity,
             actual_price, negotiated_price, tax_percent, tax_amount, total_amount, notes)
        )
        item_id = cur.fetchone()[0]
        # Recalculate bill totals
        _recalculate_bill(cur, bill_id)
        conn.commit()
        cur.close(); conn.close()
        return item_id
    except Exception as e:
        print(f"add_bill_item error: {e}")
        return None


def _recalculate_bill(cur, bill_id: int):
    """Internal: recalculate bill totals from bill_items."""
    cur.execute(
        """SELECT COALESCE(SUM(actual_price),0),
                  COALESCE(SUM(tax_amount),0),
                  COALESCE(SUM(total_amount),0)
           FROM bill_items WHERE bill_id=%s""",
        (bill_id,)
    )
    subtotal, tax_total, grand_total = cur.fetchone()
    cur.execute(
        """UPDATE billing
           SET total_amount=%s, tax_amount=%s, net_amount=%s, updated_at=NOW()
           WHERE id=%s""",
        (subtotal, tax_total, grand_total, bill_id)
    )


def get_bill_items(bill_id: int) -> list:
    """Return all line items for a bill."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM bill_items WHERE bill_id=%s ORDER BY created_at", (bill_id,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_bill_items error: {e}")
        return []


def get_bill_with_items(bill_id: int) -> dict | None:
    """Return full bill header + all items + GST breakdown."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM billing WHERE id=%s", (bill_id,))
        bill = cur.fetchone()
        if not bill:
            cur.close(); conn.close()
            return None
        bill = dict(bill)
        cur.execute(
            "SELECT * FROM bill_items WHERE bill_id=%s ORDER BY created_at", (bill_id,)
        )
        items = [dict(r) for r in cur.fetchall()]
        # GST breakdown by rate
        gst_summary: dict = {}
        for it in items:
            rate = float(it.get('tax_percent', 0))
            if rate > 0:
                key = f"{rate}%"
                gst_summary.setdefault(key, {'taxable': 0, 'tax': 0})
                gst_summary[key]['taxable'] += float(it.get('actual_price', 0))
                gst_summary[key]['tax']     += float(it.get('tax_amount', 0))
        subtotal   = sum(float(i.get('actual_price', 0))  for i in items)
        total_tax  = sum(float(i.get('tax_amount', 0))    for i in items)
        grand_total = subtotal + total_tax - float(bill.get('discount', 0))
        bill['items']       = items
        bill['subtotal']    = round(subtotal, 2)
        bill['total_tax']   = round(total_tax, 2)
        bill['grand_total'] = round(grand_total, 2)
        bill['gst_summary'] = gst_summary
        cur.close(); conn.close()
        return bill
    except Exception as e:
        print(f"get_bill_with_items error: {e}")
        return None


def create_ipd_bill(patient_name: str, patient_phone: str,
                    admission_id: int = None,
                    consultation_fee: float = 0, lab_charges: float = 0,
                    imaging_charges: float = 0, pharmacy_charges: float = 0,
                    bed_charges: float = 0, surgery_charges: float = 0,
                    procedure_charges_total: float = 0,
                    misc_charges: float = 0, discount: float = 0,
                    notes: str = '', created_by: str = 'reception') -> int | None:
    """Create a full IPD bill. Returns bill id."""
    total = (consultation_fee + lab_charges + imaging_charges + pharmacy_charges +
             bed_charges + surgery_charges + procedure_charges_total + misc_charges)
    net = max(0.0, total - discount)
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO billing
               (patient_name, patient_phone, bill_type,
                consultation_fee, lab_charges, imaging_charges, pharmacy_charges,
                bed_charges, surgery_charges, procedure_charges,
                misc_charges, total_amount, discount, net_amount,
                admission_id, notes, created_by)
               VALUES (%s,%s,'IPD',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (patient_name, patient_phone,
             consultation_fee, lab_charges, imaging_charges, pharmacy_charges,
             bed_charges, surgery_charges, procedure_charges_total,
             misc_charges, total, discount, net,
             admission_id, notes, created_by)
        )
        bill_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return bill_id
    except Exception as e:
        print(f"create_ipd_bill error: {e}")
        return None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PHARMACY ENHANCED FUNCTIONS (batch / expiry / stock deduction)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def add_medicine_stock(medicine_id: int, batch_number: str, expiry_date: str,
                       quantity: int, purchase_price: float, sell_price: float,
                       supplier: str = '', min_quantity: int = 10) -> int | None:
    """Add a batch of medicine to inventory. Returns stock id."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO inventory_stock
               (medicine_id, batch_no, batch_number, expiry_date, quantity,
                min_quantity, purchase_price, sell_price, supplier)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (medicine_id, batch_number, batch_number, expiry_date,
             quantity, min_quantity, purchase_price, sell_price, supplier)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f"add_medicine_stock error: {e}")
        return None


def get_low_stock_alerts(threshold: int = None) -> list:
    """Return medicines where quantity <= min_quantity."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT s.id, m.medicine_name, s.batch_number, s.batch_no,
                      s.quantity, s.min_quantity, s.expiry_date,
                      s.sell_price, s.supplier
               FROM inventory_stock s
               JOIN medicines m ON m.id = s.medicine_id
               WHERE s.quantity <= s.min_quantity
               ORDER BY s.quantity ASC"""
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_low_stock_alerts error: {e}")
        return []


def get_expiry_alerts(days_ahead: int = 90) -> list:
    """Return medicines expiring within `days_ahead` days."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT s.id, m.medicine_name, s.batch_number, s.batch_no,
                      s.quantity, s.expiry_date, s.sell_price, s.supplier,
                      (s.expiry_date - CURRENT_DATE) AS days_to_expiry
               FROM inventory_stock s
               JOIN medicines m ON m.id = s.medicine_id
               WHERE s.expiry_date IS NOT NULL
                 AND s.expiry_date <= CURRENT_DATE + INTERVAL '%s days'
                 AND s.quantity > 0
               ORDER BY s.expiry_date ASC""",
            (days_ahead,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_expiry_alerts error: {e}")
        return []


def deduct_medicine_stock(medicine_id: int, quantity_sold: int,
                          batch_number: str = None) -> bool:
    """Deduct sold quantity from inventory (FIFO by expiry date)."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        if batch_number:
            cur.execute(
                "UPDATE inventory_stock SET quantity=quantity-%s "
                "WHERE medicine_id=%s AND batch_number=%s AND quantity>=%s",
                (quantity_sold, medicine_id, batch_number, quantity_sold)
            )
        else:
            # FIFO: deduct from batch expiring soonest
            cur.execute(
                "UPDATE inventory_stock SET quantity=quantity-%s "
                "WHERE id=("
                "  SELECT id FROM inventory_stock "
                "  WHERE medicine_id=%s AND quantity>=%s "
                "  ORDER BY expiry_date ASC NULLS LAST LIMIT 1"
                ")",
                (quantity_sold, medicine_id, quantity_sold)
            )
        conn.commit()
        cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"deduct_medicine_stock error: {e}")
        return False


def get_full_inventory() -> list:
    """Return full pharmacy inventory with medicine details."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT s.id, m.medicine_name, m.generic_name, m.category, m.unit,
                      s.batch_number, s.batch_no, s.expiry_date, s.quantity,
                      s.min_quantity, s.purchase_price, s.sell_price,
                      s.supplier, s.updated_at,
                      CASE WHEN s.quantity <= s.min_quantity THEN TRUE ELSE FALSE END AS low_stock,
                      CASE WHEN s.expiry_date <= CURRENT_DATE + INTERVAL '90 days'
                           AND s.quantity > 0 THEN TRUE ELSE FALSE END AS near_expiry
               FROM inventory_stock s
               JOIN medicines m ON m.id = s.medicine_id
               ORDER BY m.medicine_name, s.expiry_date"""
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_full_inventory error: {e}")
        return []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ADMIN DASHBOARD EXTENDED SUMMARY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def get_extended_dashboard_data() -> dict:
    """Extended admin dashboard: includes admissions, surgery, pharmacy alerts."""
    base = get_admin_dashboard_data()
    try:
        active_admissions = get_all_admissions(status='admitted', limit=50)
        low_stock         = get_low_stock_alerts()
        expiry_alerts     = get_expiry_alerts(90)
        pending_surgeries = get_surgery_records(50)
        all_bills         = get_all_bills(100)
        base.update({
            'active_admissions':    active_admissions,
            'total_admissions':     len(active_admissions),
            'low_stock_count':      len(low_stock),
            'expiry_alert_count':   len(expiry_alerts),
            'low_stock_items':      low_stock,
            'expiry_items':         expiry_alerts,
            'surgery_records':      pending_surgeries,
            'all_bills':            all_bills,
            'total_revenue':        sum(float(b.get('net_amount', 0)) for b in all_bills),
        })
    except Exception as e:
        print(f"get_extended_dashboard_data warning: {e}")
    return base


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PHASE 3 â€” STAR HOSPITAL DEPLOYMENT (services catalogue + doctor directory)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def create_phase3_tables() -> None:
    """
    Create Phase-3 tables for Star Hospital deployment.
    Safe to call every startup â€” all DDL uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
      - services_catalogue   (hospital services with default pricing)
      - doctors table extended with qualifications + registration_no columns
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()

        # â”€â”€ services_catalogue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        cur.execute("""
            CREATE TABLE IF NOT EXISTS services_catalogue (
                service_id     SERIAL PRIMARY KEY,
                service_name   VARCHAR(200) NOT NULL,
                department     VARCHAR(100) DEFAULT '',
                default_price  NUMERIC(10,2) DEFAULT 0,
                tax_percentage NUMERIC(5,2)  DEFAULT 0,
                active         BOOLEAN DEFAULT TRUE,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # â”€â”€ extend doctors table with qualifications + registration_no â”€â”€â”€â”€â”€â”€â”€
        for col_def in [
            "ALTER TABLE doctors ADD COLUMN IF NOT EXISTS qualifications  TEXT DEFAULT ''",
            "ALTER TABLE doctors ADD COLUMN IF NOT EXISTS registration_no VARCHAR(50) DEFAULT ''",
        ]:
            try:
                cur.execute(col_def)
            except Exception:
                conn.rollback()

        # â”€â”€ clients master registry (SRP MediFlow multi-client) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id        SERIAL PRIMARY KEY,
                slug             VARCHAR(80)  UNIQUE NOT NULL,
                hospital_name    VARCHAR(150) NOT NULL,
                hospital_phone   VARCHAR(30)  DEFAULT '',
                hospital_address TEXT         DEFAULT '',
                city             VARCHAR(100) DEFAULT '',
                state            VARCHAR(100) DEFAULT '',
                country          VARCHAR(80)  DEFAULT 'India',
                tagline          TEXT         DEFAULT '',
                logo_path        TEXT         DEFAULT '',
                primary_color    VARCHAR(20)  DEFAULT '#1a73e8',
                secondary_color  VARCHAR(20)  DEFAULT '#00b896',
                database_name    VARCHAR(100) DEFAULT '',
                is_active        BOOLEAN      DEFAULT TRUE,
                created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("âœ… Phase-3 tables ready (services_catalogue, doctors extended, clients)")
    except Exception as e:
        print(f"create_phase3_tables error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


def deduplicate_doctors() -> int:
    """
    Remove duplicate doctor rows keeping the record with the smallest id
    for each (name, department) pair.  Returns the number of rows deleted.
    Safe to call at every startup.
    """
    sql = """
        DELETE FROM doctors
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM doctors
            GROUP BY name, department
        )
    """
    deleted = 0
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                deleted = cur.rowcount
        if deleted:
            print(f"\u26a0\ufe0f  deduplicate_doctors: removed {deleted} duplicate doctor rows")
    except Exception as e:
        print(f"deduplicate_doctors error: {e}")
    return deleted


def seed_star_hospital_doctors() -> None:
    """
    Insert the 3 real Star Hospital doctors into:
      departments  (upsert by name)
      doctors      (upsert by name + department)
    Safe to call every startup â€” uses ON CONFLICT DO NOTHING.
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()

        # â”€â”€ Ensure departments exist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        departments = [
            ("Orthopedics",      "Bone & Joint Care",          "Dr. Srujan"),
            ("General Medicine", "General Medicine & Diabetes", "Dr. K. Ramyanadh"),
            ("General Surgery",  "Surgical Procedures",         "Dr. B. Ramachandra Nayak"),
            ("Dental",           "Dental Care",                 ""),
            ("ENT",              "Ear Nose Throat",             ""),
        ]
        for name, desc, head in departments:
            cur.execute("""
                INSERT INTO departments (name, description, head_doctor, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (name) DO NOTHING
            """, (name, desc, head))

        # â”€â”€ Insert / update Star Hospital doctors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        doctors = [
            {
                "name":            "Dr. Srujan",
                "department":      "Orthopedics",
                "specialization":  "Orthopedics",
                "qualifications":  "DNB Ortho FIJR",
                "registration_no": "87679",
                "phone":           "+91 7981971015",
                "status":          "available",
            },
            {
                "name":            "Dr. K. Ramyanadh",
                "department":      "General Medicine",
                "specialization":  "General Medicine / Diabetology",
                "qualifications":  "General Medicine (UK), Diabetology",
                "registration_no": "111431",
                "phone":           "+91 7981971015",
                "status":          "available",
            },
            {
                "name":            "Dr. B. Ramachandra Nayak",
                "department":      "General Surgery",
                "specialization":  "General Surgery",
                "qualifications":  "M.B.B.S., M.S.",
                "registration_no": "13888",
                "phone":           "+91 7981971015",
                "status":          "available",
            },
        ]
        for d in doctors:
            cur.execute("""
                INSERT INTO doctors
                    (name, department, specialization, qualifications,
                     registration_no, status, on_duty)
                SELECT %s, %s, %s, %s, %s, %s, FALSE
                WHERE NOT EXISTS (
                    SELECT 1 FROM doctors WHERE name = %s AND department = %s
                )
            """, (
                d["name"], d["department"], d["specialization"],
                d["qualifications"], d["registration_no"],
                d["status"],
                d["name"], d["department"],
            ))

        conn.commit()
        cur.close()
        conn.close()
        print("âœ… Star Hospital doctor directory seeded (3 doctors)")
    except Exception as e:
        print(f"seed_star_hospital_doctors error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


def seed_services_catalogue() -> None:
    """
    Insert the Star Hospital service catalogue.
    Safe to call every startup â€” uses ON CONFLICT DO NOTHING.
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()

        services = [
            ("OPD Consultation â€“ Orthopedics",            "Orthopedics",      500, 0),
            ("OPD Consultation â€“ General Physician",      "General Medicine",  300, 0),
            ("OPD Consultation â€“ General Surgery",        "General Surgery",   500, 0),
            ("Dental Consultant",                         "Dental",            400, 0),
            ("ENT Consultant",                            "ENT",               400, 0),
            ("Follow-up Consultation",                    "General Medicine",  150, 0),
            ("Emergency Consultation",                    "Emergency",         500, 0),
            ("Dressing / Wound Care",                     "General Surgery",   200, 0),
            ("Fracture Reduction & Casting",              "Orthopedics",      1500, 0),
            ("Minor Surgical Procedure",                  "General Surgery",  1000, 0),
        ]
        for svc_name, dept, price, tax in services:
            cur.execute("""
                INSERT INTO services_catalogue
                    (service_name, department, default_price, tax_percentage, active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT DO NOTHING
            """, (svc_name, dept, price, tax))

        conn.commit()
        cur.close()
        conn.close()
        print("âœ… Services catalogue seeded (10 services)")
    except Exception as e:
        print(f"seed_services_catalogue error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


def get_services_catalogue(active_only: bool = True) -> list:
    """Return the hospital services catalogue."""
    conn = get_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if active_only:
            cur.execute(
                "SELECT * FROM services_catalogue WHERE active = TRUE ORDER BY department, service_name"
            )
        else:
            cur.execute("SELECT * FROM services_catalogue ORDER BY department, service_name")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_services_catalogue error: {e}")
        return []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# MULTI-CLIENT REGISTRY  (SRP MediFlow product â€” clients table)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def seed_client_record() -> None:
    """
    Ensure the default Star Hospital client record exists in `clients`.
    Uses hospital_config.py for values.  Safe to call every startup.
    """
    conn = get_connection()
    if not conn:
        return
    try:
        import hospital_config as hc
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO clients
                (slug, hospital_name, hospital_phone, hospital_address,
                 city, state, country, tagline, database_name, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (slug) DO UPDATE
                SET hospital_name    = EXCLUDED.hospital_name,
                    hospital_phone   = EXCLUDED.hospital_phone,
                    hospital_address = EXCLUDED.hospital_address,
                    city             = EXCLUDED.city,
                    state            = EXCLUDED.state,
                    tagline          = EXCLUDED.tagline,
                    database_name    = EXCLUDED.database_name
        """, (
            "star_hospital",
            getattr(hc, "HOSPITAL_NAME",    "Star Hospital"),
            getattr(hc, "HOSPITAL_PHONE",   "+91 7981971015"),
            getattr(hc, "HOSPITAL_ADDRESS",
                    "Karur Vysya Bank Lane, Ganesh Basthi, Kothagudem, Telangana 507101, India"),
            "Kothagudem",
            "Telangana",
            "India",
            getattr(hc, "HOSPITAL_TAGLINE", "24x7 Emergency Medical Services Available"),
            "hospital_ai",
        ))
        conn.commit()
        cur.close()
        conn.close()
        print("âœ… Client registry: Star Hospital record seeded")
    except Exception as e:
        print(f"seed_client_record error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


def get_all_clients() -> list:
    """Return all registered SRP MediFlow clients (from `clients` table)."""
    conn = get_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT client_id, slug, hospital_name, hospital_phone, city, state, "
            "country, tagline, database_name, primary_color, secondary_color, "
            "is_active, created_at "
            "FROM clients ORDER BY client_id"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_all_clients error: {e}")
        return []


def get_client_by_slug(slug: str) -> dict | None:
    """Return a single client record by its slug, or None if not found."""
    conn = get_connection()
    if not conn:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM clients WHERE slug = %s LIMIT 1", (slug,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"get_client_by_slug error: {e}")
        return None


def create_client_record(
    slug: str,
    hospital_name: str,
    hospital_phone: str = "",
    hospital_address: str = "",
    city: str = "",
    state: str = "",
    country: str = "India",
    tagline: str = "",
    database_name: str = "",
) -> dict | None:
    """
    Insert a new client into the `clients` registry.
    Returns the newly created row as a dict, or None on error.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO clients
                (slug, hospital_name, hospital_phone, hospital_address,
                 city, state, country, tagline, database_name, is_active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
            RETURNING *
        """, (slug, hospital_name, hospital_phone, hospital_address,
              city, state, country, tagline, database_name))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"create_client_record error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SAAS TABLES — billing_accounts, audit_log, clients_registry extended columns
# ══════════════════════════════════════════════════════════════════════════════

def create_saas_tables() -> None:
    """
    Create SaaS-specific tables and extend existing ones.
    Safe to call every startup — all DDL uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.

    New tables:
      billing_accounts   — per-client subscription & billing status
      audit_log          — tamper-evident log of all admin actions

    Column additions to clients:
      subdomain, plan_type, status, billing_start_date, billing_expiry_date,
      last_activity, db_status, admin_email
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()

        # ── billing_accounts ──────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS billing_accounts (
                id                SERIAL PRIMARY KEY,
                client_id         INTEGER UNIQUE NOT NULL,
                plan_name         VARCHAR(50)  DEFAULT 'Starter',
                price             NUMERIC(10,2) DEFAULT 999,
                billing_cycle     VARCHAR(20)  DEFAULT 'monthly',
                next_payment_date DATE,
                trial_end_date    DATE,
                payment_status    VARCHAR(20)  DEFAULT 'trial',
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── audit_log ─────────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          SERIAL PRIMARY KEY,
                client_id   INTEGER,
                username    VARCHAR(80)  DEFAULT 'system',
                role        VARCHAR(20)  DEFAULT '',
                action      VARCHAR(200) NOT NULL,
                details     TEXT         DEFAULT '',
                ip_address  VARCHAR(45)  DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Index for fast client-level audit queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_client_id
            ON audit_log (client_id, created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
            ON audit_log (created_at DESC)
        """)

        # ── extend clients table with SaaS fields ─────────────────────────────
        saas_columns = [
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS subdomain         VARCHAR(80)  DEFAULT ''",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS plan_type         VARCHAR(50)  DEFAULT 'starter'",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS status            VARCHAR(20)  DEFAULT 'active'",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS billing_start_date DATE",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS billing_expiry_date DATE",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_activity     TIMESTAMP",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS db_status         VARCHAR(20)  DEFAULT 'ready'",
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS admin_email       VARCHAR(200) DEFAULT ''",
        ]
        for col_sql in saas_columns:
            try:
                cur.execute(col_sql)
            except Exception:
                conn.rollback()

        conn.commit()
        cur.close()
        conn.close()
        print("✅ SaaS tables ready (billing_accounts, audit_log, clients extended)")
    except Exception as e:
        print(f"create_saas_tables error: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


# ── Audit log helpers ─────────────────────────────────────────────────────────

def log_action(
    username:   str,
    role:       str,
    action:     str,
    details:    str = "",
    ip_address: str = "",
    client_id:  int | None = None,
) -> None:
    """
    Write one row to audit_log AND system_logs.
    Silent on failure — never raise from here.
    """
    # system_logs (existing table)
    try:
        conn = get_connection()
        if conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO system_logs (username, role, action, details, ip_address) "
                "VALUES (%s, %s, %s, %s, %s)",
                (username[:80], role[:20], action[:200], details, ip_address[:45])
            )
            # audit_log (new SaaS table — may not exist on very old installs)
            try:
                cur.execute(
                    "INSERT INTO audit_log (client_id, username, role, action, details, ip_address) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (client_id, username[:80], role[:20], action[:200], details, ip_address[:45])
                )
            except Exception:
                conn.rollback()
            conn.commit()
            cur.close()
            conn.close()
    except Exception:
        pass


def get_audit_logs(limit: int = 200, client_id: int | None = None) -> list:
    """Return recent audit_log entries. Optionally filter by client_id."""
    conn = get_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if client_id is not None:
            cur.execute(
                "SELECT * FROM audit_log WHERE client_id = %s ORDER BY created_at DESC LIMIT %s",
                (client_id, limit)
            )
        else:
            cur.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_audit_logs error: {e}")
        return []


# ── Clients registry extended ─────────────────────────────────────────────────

def get_clients_registry() -> list:
    """
    Return all clients with SaaS fields + billing status joined.
    Suitable for founder dashboard and admin listing.
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                c.client_id,
                c.slug,
                c.hospital_name,
                c.subdomain,
                c.city,
                c.state,
                c.country,
                c.database_name,
                c.plan_type,
                c.status,
                c.db_status,
                c.admin_email,
                c.billing_start_date,
                c.billing_expiry_date,
                c.last_activity,
                c.is_active,
                c.created_at,
                ba.plan_name         AS billing_plan,
                ba.price             AS billing_price,
                ba.payment_status    AS billing_status,
                ba.next_payment_date AS billing_next_due,
                ba.trial_end_date
            FROM clients c
            LEFT JOIN billing_accounts ba ON ba.client_id = c.client_id
            ORDER BY c.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_clients_registry error: {e}")
        return []


def update_client_last_activity(client_id: int) -> None:
    """Touch last_activity timestamp for a client (call on each login)."""
    try:
        conn = get_connection()
        if conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE clients SET last_activity = NOW() WHERE client_id = %s",
                (client_id,)
            )
            conn.commit()
            cur.close(); conn.close()
    except Exception:
        pass


def get_system_logs(limit: int = 200) -> list:
    """Return recent system_logs entries."""
    conn = get_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM system_logs ORDER BY logged_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_system_logs error: {e}")
        return []



