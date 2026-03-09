"""
saas_analytics.py — SRP MediFlow Analytics Module
===================================================
Provides hospital-level analytics for admin dashboards.

Endpoints served:
  GET /api/admin/analytics/revenue       — daily revenue breakdown
  GET /api/admin/analytics/appointments  — appointment statistics
  GET /api/admin/analytics/doctors       — doctor performance metrics

Design:
  - All queries use only aggregate counts / sums — no raw patient PII leaves DB
  - Accepts  ?range=daily|weekly|monthly|yearly  query-string parameter
  - Falls back to empty data if DB unavailable

Usage
-----
    from saas_analytics import get_revenue_analytics, get_appointment_analytics, get_doctor_analytics
    result = get_revenue_analytics(date_range='monthly')
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Optional


# ── Date range helper (shared with saas_export) ───────────────────────────────
def _date_range(range_key: str) -> tuple[date, date]:
    today = date.today()
    if range_key == "daily":
        return today, today
    elif range_key == "weekly":
        return today - timedelta(days=6), today
    elif range_key == "monthly":
        return today.replace(day=1), today
    elif range_key == "yearly":
        return today.replace(month=1, day=1), today
    else:
        return today.replace(day=1), today      # default: monthly


def _get_conn():
    import db
    return db.get_connection()


# ── Revenue analytics ─────────────────────────────────────────────────────────
def get_revenue_analytics(date_range: str = "monthly") -> dict:
    """
    Returns daily revenue totals, plan breakdown, and summary stats.
    No patient names or identifiers are included.
    """
    start, end = _date_range(date_range)
    conn = _get_conn()
    if not conn:
        return _empty_revenue(start, end)
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Daily revenue
        cur.execute("""
            SELECT DATE(created_at)   AS day,
                   SUM(net_amount)    AS total_revenue,
                   COUNT(*)           AS bill_count,
                   SUM(CASE WHEN status='paid' THEN net_amount ELSE 0 END) AS collected,
                   SUM(CASE WHEN status='unpaid' THEN net_amount ELSE 0 END) AS pending
              FROM billing
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY DATE(created_at)
             ORDER BY day
        """, (start, end))
        daily = [dict(r) for r in cur.fetchall()]

        # Bill-type breakdown (OPD vs IPD)
        cur.execute("""
            SELECT bill_type,
                   COUNT(*)        AS count,
                   SUM(net_amount) AS total
              FROM billing
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY bill_type
        """, (start, end))
        by_type = [dict(r) for r in cur.fetchall()]

        # Payment mode breakdown
        cur.execute("""
            SELECT payment_mode,
                   COUNT(*)         AS count,
                   SUM(amount_paid) AS total
              FROM payments p
              JOIN billing b ON b.id = p.bill_id
             WHERE p.paid_at::date BETWEEN %s AND %s
             GROUP BY payment_mode
             ORDER BY total DESC
        """, (start, end))
        by_mode = [dict(r) for r in cur.fetchall()]

        # Summary
        cur.execute("""
            SELECT COALESCE(SUM(net_amount), 0)    AS total_revenue,
                   COALESCE(SUM(CASE WHEN status='paid'   THEN net_amount ELSE 0 END), 0) AS collected,
                   COALESCE(SUM(CASE WHEN status='unpaid' THEN net_amount ELSE 0 END), 0) AS pending,
                   COUNT(*)                        AS total_bills
              FROM billing
             WHERE created_at::date BETWEEN %s AND %s
        """, (start, end))
        summary = dict(cur.fetchone() or {})

        cur.close(); conn.close()
        return {
            "date_range":  date_range,
            "period_start": str(start),
            "period_end":   str(end),
            "summary":      summary,
            "daily":        daily,
            "by_type":      by_type,
            "by_mode":      by_mode,
        }
    except Exception as exc:
        print(f"[analytics] get_revenue_analytics error: {exc}")
        try: conn.close()
        except: pass
        return _empty_revenue(start, end)


def _empty_revenue(start, end) -> dict:
    return {
        "date_range":   "unknown",
        "period_start": str(start),
        "period_end":   str(end),
        "summary":      {"total_revenue": 0, "collected": 0, "pending": 0, "total_bills": 0},
        "daily":        [],
        "by_type":      [],
        "by_mode":      [],
    }


# ── Appointment analytics ─────────────────────────────────────────────────────
def get_appointment_analytics(date_range: str = "monthly") -> dict:
    """
    Returns appointment counts by status, department, and day.
    """
    start, end = _date_range(date_range)
    conn = _get_conn()
    if not conn:
        return {"period_start": str(start), "period_end": str(end), "data": []}
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Daily appointment counts
        cur.execute("""
            SELECT DATE(created_at) AS day,
                   COUNT(*)         AS total,
                   SUM(CASE WHEN status='confirmed'  THEN 1 ELSE 0 END) AS confirmed,
                   SUM(CASE WHEN status='pending'    THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN status='cancelled'  THEN 1 ELSE 0 END) AS cancelled,
                   SUM(CASE WHEN status='completed'  THEN 1 ELSE 0 END) AS completed
              FROM appointments
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY DATE(created_at)
             ORDER BY day
        """, (start, end))
        daily = [dict(r) for r in cur.fetchall()]

        # By department
        cur.execute("""
            SELECT COALESCE(NULLIF(department,''), 'Unknown') AS department,
                   COUNT(*)                                   AS total
              FROM appointments
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY department
             ORDER BY total DESC
             LIMIT 10
        """, (start, end))
        by_dept = [dict(r) for r in cur.fetchall()]

        # Summary
        cur.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
                   SUM(CASE WHEN status='pending'   THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
              FROM appointments
             WHERE created_at::date BETWEEN %s AND %s
        """, (start, end))
        summary = dict(cur.fetchone() or {})

        cur.close(); conn.close()
        return {
            "date_range":   date_range,
            "period_start": str(start),
            "period_end":   str(end),
            "summary":      summary,
            "daily":        daily,
            "by_department": by_dept,
        }
    except Exception as exc:
        print(f"[analytics] get_appointment_analytics error: {exc}")
        try: conn.close()
        except: pass
        return {"period_start": str(start), "period_end": str(end), "data": []}


# ── Doctor performance analytics ──────────────────────────────────────────────
def get_doctor_analytics(date_range: str = "monthly") -> dict:
    """
    Returns per-doctor patient counts, prescriptions, and lab requests.
    No patient medical details are exposed.
    """
    start, end = _date_range(date_range)
    conn = _get_conn()
    if not conn:
        return {"period_start": str(start), "period_end": str(end), "doctors": []}
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Appointments per doctor
        cur.execute("""
            SELECT COALESCE(NULLIF(doctor_name,''), 'Unassigned') AS doctor,
                   department,
                   COUNT(*)                                       AS appointments,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
              FROM appointments
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY doctor_name, department
             ORDER BY appointments DESC
             LIMIT 20
        """, (start, end))
        appt_by_doc = [dict(r) for r in cur.fetchall()]

        # Prescriptions per doctor
        cur.execute("""
            SELECT COALESCE(NULLIF(doctor_name,''), 'Unassigned') AS doctor,
                   COUNT(*)                                       AS prescriptions
              FROM prescriptions
             WHERE created_at::date BETWEEN %s AND %s
             GROUP BY doctor_name
             ORDER BY prescriptions DESC
             LIMIT 10
        """, (start, end))
        rx_by_doc = {r["doctor"]: r["prescriptions"] for r in cur.fetchall()}

        # Lab requests per doctor
        cur.execute("""
            SELECT COALESCE(NULLIF(lo.doctor_username,''), 'Unassigned') AS doctor,
                   COUNT(*) AS lab_requests
              FROM lab_orders lo
             WHERE lo.created_at::date BETWEEN %s AND %s
             GROUP BY lo.doctor_username
             ORDER BY lab_requests DESC
             LIMIT 10
        """, (start, end))
        lab_by_doc = {r["doctor"]: r["lab_requests"] for r in cur.fetchall()}

        # Enrich appointment rows
        for row in appt_by_doc:
            row["prescriptions"] = rx_by_doc.get(row["doctor"], 0)
            row["lab_requests"]  = lab_by_doc.get(row["doctor"], 0)

        # Bed occupancy (IPD)
        cur.execute("""
            SELECT COALESCE(NULLIF(ward_name,''), 'Unknown') AS ward,
                   COUNT(*) AS occupied_beds
              FROM patient_admissions
             WHERE status = 'admitted'
             GROUP BY ward_name
             ORDER BY occupied_beds DESC
        """)
        bed_occupancy = [dict(r) for r in cur.fetchall()]

        cur.close(); conn.close()
        return {
            "date_range":     date_range,
            "period_start":   str(start),
            "period_end":     str(end),
            "doctors":        appt_by_doc,
            "bed_occupancy":  bed_occupancy,
        }
    except Exception as exc:
        print(f"[analytics] get_doctor_analytics error: {exc}")
        try: conn.close()
        except: pass
        return {"period_start": str(start), "period_end": str(end), "doctors": []}
