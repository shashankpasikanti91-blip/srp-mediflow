"""
hms_db.py  –  SRP MediFlow HMS Core Module Database Layer
==========================================================
Implements all database functions for the 7 hospital modules:
  1. Patient Registration Module
  2. Billing System
  3. Doctor Workflow
  4. Pharmacy Inventory
  5. Lab & Diagnostics
  6. Owner Analytics Dashboard
  7. Mobile-Ready API Helpers

Rules:
  - Never break existing tables or APIs.
  - All writes use parameterised queries (SQL-injection proof).
  - Multi-tenant safe: all reads are implicitly scoped to the
    connected tenant DB (each hospital has its own DB on localhost:5434).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import psycopg2
import psycopg2.extras

# Reuse the existing connection helpers so we stay on the same DB
from db import get_conn, get_connection


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA BOOTSTRAP  –  call once at server startup
# ─────────────────────────────────────────────────────────────────────────────

def create_hms_v4_tables() -> None:
    """
    Idempotent: create HMS v4 tables if they don't already exist.
    Safe to call on every server start.
    """
    ddl_statements = [
        # ── patient_visits ────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS patient_visits (
            visit_id        SERIAL PRIMARY KEY,
            patient_id      INTEGER REFERENCES patients(id) ON DELETE CASCADE,
            visit_type      VARCHAR(10)  DEFAULT 'OP',      -- OP / IP / ER
            doctor_assigned VARCHAR(150) DEFAULT '',
            doctor_username VARCHAR(80)  DEFAULT '',
            department      VARCHAR(100) DEFAULT '',
            visit_date      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            chief_complaint TEXT         DEFAULT '',
            diagnosis       TEXT         DEFAULT '',
            notes           TEXT         DEFAULT '',
            status          VARCHAR(30)  DEFAULT 'active',  -- active / closed / follow-up
            op_ticket_no    VARCHAR(30)  DEFAULT '',
            created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pv_patient_id ON patient_visits (patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_pv_visit_date ON patient_visits (visit_date DESC)",

        # ── doctor_notes ──────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS doctor_notes (
            note_id         SERIAL PRIMARY KEY,
            patient_id      INTEGER REFERENCES patients(id) ON DELETE CASCADE,
            visit_id        INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
            doctor_username VARCHAR(80)  NOT NULL,
            doctor_name     VARCHAR(150) DEFAULT '',
            note_type       VARCHAR(50)  DEFAULT 'clinical', -- clinical / follow_up / discharge
            note_text       TEXT         NOT NULL,
            created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_dn_patient_id  ON doctor_notes (patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_dn_doctor      ON doctor_notes (doctor_username)",

        # ── prescription_items (structured per-medicine rows) ─────────────────
        """
        CREATE TABLE IF NOT EXISTS prescription_items (
            item_id         SERIAL PRIMARY KEY,
            prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE CASCADE,
            medicine_name   VARCHAR(200) NOT NULL,
            dosage          VARCHAR(100) DEFAULT '',
            frequency       VARCHAR(100) DEFAULT '',  -- e.g. "1-0-1"
            duration        VARCHAR(50)  DEFAULT '',  -- e.g. "5 days"
            instructions    TEXT         DEFAULT '',
            quantity        INTEGER      DEFAULT 0,
            created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pi_prescription ON prescription_items (prescription_id)",

        # ── appointments (ensure patient_id FK column exists) ─────────────────
        """
        ALTER TABLE appointments
            ADD COLUMN IF NOT EXISTS patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL
        """,

        # ── lab_results (result rows linked to lab_orders and patients) ───────
        """
        CREATE TABLE IF NOT EXISTS lab_results (
            result_id       SERIAL PRIMARY KEY,
            order_id        INTEGER REFERENCES lab_orders(id) ON DELETE SET NULL,
            patient_id      INTEGER REFERENCES patients(id) ON DELETE SET NULL,
            patient_name    VARCHAR(150) DEFAULT '',
            test_name       VARCHAR(200) DEFAULT '',
            result_value    TEXT         DEFAULT '',
            reference_range VARCHAR(100) DEFAULT '',
            unit            VARCHAR(30)  DEFAULT '',
            is_abnormal     BOOLEAN      DEFAULT FALSE,
            remarks         TEXT         DEFAULT '',
            lab_username    VARCHAR(80)  DEFAULT '',
            reported_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lr_patient_id ON lab_results (patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_lr_order_id   ON lab_results (order_id)",

        # ── pharmacy_stock (living stock level per medicine) ──────────────────
        """
        CREATE TABLE IF NOT EXISTS pharmacy_stock (
            stock_id        SERIAL PRIMARY KEY,
            medicine_id     INTEGER REFERENCES medicines(id) ON DELETE CASCADE,
            medicine_name   VARCHAR(200) DEFAULT '',
            batch_no        VARCHAR(50)  DEFAULT '',
            expiry_date     DATE,
            quantity        INTEGER      DEFAULT 0,
            min_quantity    INTEGER      DEFAULT 10,
            unit_price      NUMERIC(10,2) DEFAULT 0,
            sell_price      NUMERIC(10,2) DEFAULT 0,
            supplier        VARCHAR(150) DEFAULT '',
            updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (medicine_id, batch_no)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ps_medicine_id  ON pharmacy_stock (medicine_id)",
        "CREATE INDEX IF NOT EXISTS idx_ps_expiry        ON pharmacy_stock (expiry_date)",

        # ── op_tickets (sequential OP ticket counter per day) ─────────────────
        """
        CREATE TABLE IF NOT EXISTS op_tickets (
            ticket_id    SERIAL PRIMARY KEY,
            ticket_no    VARCHAR(30)  UNIQUE NOT NULL,
            patient_id   INTEGER REFERENCES patients(id) ON DELETE CASCADE,
            visit_id     INTEGER REFERENCES patient_visits(visit_id) ON DELETE SET NULL,
            doctor_name  VARCHAR(150) DEFAULT '',
            department   VARCHAR(100) DEFAULT '',
            issued_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            status       VARCHAR(20)  DEFAULT 'waiting'  -- waiting / with_doctor / done
        )
        """,

        # ── UHID: Unique Hospital ID per patient (added as optional migration) ─
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS uhid VARCHAR(20) DEFAULT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_uhid ON patients (uhid) WHERE uhid IS NOT NULL",
    ]

    conn = get_connection()
    if not conn:
        print("⚠️  hms_db: DB not available — HMS v4 tables not created")
        return
    try:
        cur = conn.cursor()
        for stmt in ddl_statements:
            cur.execute(stmt)
        conn.commit()
        cur.close()
        conn.close()
        print("✅  HMS v4 tables ready (patient_visits, doctor_notes, "
              "prescription_items, lab_results, pharmacy_stock, op_tickets)")
    except Exception as exc:
        print(f"❌  create_hms_v4_tables error: {exc}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. PATIENT REGISTRATION MODULE
# ─────────────────────────────────────────────────────────────────────────────

def register_patient(data: dict) -> dict:
    """
    Register a new patient or return existing patient record if same phone exists.
    Returns: {patient_id, full_name, op_ticket_no, is_new, ...}
    """
    phone     = (data.get("phone") or "").strip()
    full_name = (data.get("full_name") or data.get("name") or "").strip()
    dob       = data.get("dob") or None
    gender    = (data.get("gender") or "Unknown").strip()
    aadhar    = (data.get("aadhar") or "").strip()
    address   = (data.get("address") or "").strip()
    blood_grp = (data.get("blood_group") or "").strip()
    allergies = (data.get("allergies") or "").strip()

    if not full_name:
        return {"error": "full_name is required"}

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check existing by phone
            existing = None
            if phone:
                cur.execute(
                    "SELECT * FROM patients WHERE phone = %s ORDER BY created_at LIMIT 1",
                    (phone,)
                )
                existing = cur.fetchone()

            if existing:
                patient_id = existing["id"]
                is_new = False
                uhid_val = existing.get("uhid") or f"UHID{patient_id:06d}"
            else:
                cur.execute(
                    """
                    INSERT INTO patients
                        (full_name, dob, gender, phone, aadhar, address, blood_group, allergies)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (full_name, dob, gender, phone, aadhar, address, blood_grp, allergies)
                )
                patient_id = cur.fetchone()["id"]
                is_new = True
                # Generate UHID: UHID + zero-padded patient_id
                uhid_val = f"UHID{patient_id:06d}"
                cur.execute(
                    "UPDATE patients SET uhid=%s WHERE id=%s AND uhid IS NULL",
                    (uhid_val, patient_id)
                )

            # Create a new visit record for this encounter
            doctor   = (data.get("doctor") or data.get("doctor_assigned") or "").strip()
            dept     = (data.get("department") or "").strip()
            visit_type = (data.get("visit_type") or "OP").strip().upper()
            complaint  = (data.get("chief_complaint") or data.get("issue") or "").strip()

            cur.execute(
                """
                INSERT INTO patient_visits
                    (patient_id, visit_type, doctor_assigned, department,
                     chief_complaint, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                RETURNING visit_id
                """,
                (patient_id, visit_type, doctor, dept, complaint)
            )
            visit_id = cur.fetchone()["visit_id"]

            # Generate OP ticket  (pattern must match stored format: OP-YYYYMMDD-NNNN)
            today_prefix = datetime.now().strftime("%Y%m%d")
            cur.execute(
                "SELECT COUNT(*) FROM op_tickets WHERE ticket_no LIKE %s",
                (f"OP-{today_prefix}%",)
            )
            count = cur.fetchone()["count"] + 1
            ticket_no = f"OP-{today_prefix}-{count:04d}"

            cur.execute(
                """
                INSERT INTO op_tickets (ticket_no, patient_id, visit_id, doctor_name, department)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (ticket_no, patient_id, visit_id, doctor, dept)
            )

            # Also update visit with ticket number
            cur.execute(
                "UPDATE patient_visits SET op_ticket_no=%s WHERE visit_id=%s",
                (ticket_no, visit_id)
            )

    return {
        "patient_id":    patient_id,
        "uhid":          uhid_val,
        "visit_id":      visit_id,
        "op_ticket_no":  ticket_no,
        "full_name":     full_name,
        "phone":         phone,
        "doctor":        doctor,
        "department":    dept,
        "visit_type":    visit_type,
        "is_new_patient": is_new,
        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def search_patients_comprehensive(query: str, field: str = "auto") -> list:
    """
    Search patients by UHID, name, phone, or admission date.
    field: 'uhid' | 'name' | 'phone' | 'date' | 'auto'
    Returns list of dicts with patient + last visit info.
    """
    query = query.strip()
    if not query:
        return []

    # Auto-detect field from query format
    if field == "auto":
        if query.upper().startswith("UHID") or ("-" in query and query.replace("-", "").isalnum()):
            field = "uhid"
        elif query.isdigit() and len(query) >= 7:
            field = "phone"
        elif len(query) == 10 and query.isdigit():
            field = "phone"
        elif "-" in query and len(query) == 10:  # YYYY-MM-DD
            field = "date"
        else:
            field = "name"

    sql_map = {
        "uhid":  "SELECT p.*, pv.visit_id, pv.doctor_assigned, pv.created_at AS last_visit"
                 " FROM patients p LEFT JOIN patient_visits pv ON pv.patient_id=p.id"
                 " AND pv.visit_id=(SELECT MAX(visit_id) FROM patient_visits WHERE patient_id=p.id)"
                 " WHERE p.uhid ILIKE %s ORDER BY p.id LIMIT 50",
        "name":  "SELECT p.*, pv.visit_id, pv.doctor_assigned, pv.created_at AS last_visit"
                 " FROM patients p LEFT JOIN patient_visits pv ON pv.patient_id=p.id"
                 " AND pv.visit_id=(SELECT MAX(visit_id) FROM patient_visits WHERE patient_id=p.id)"
                 " WHERE p.full_name ILIKE %s ORDER BY p.id LIMIT 50",
        "phone": "SELECT p.*, pv.visit_id, pv.doctor_assigned, pv.created_at AS last_visit"
                 " FROM patients p LEFT JOIN patient_visits pv ON pv.patient_id=p.id"
                 " AND pv.visit_id=(SELECT MAX(visit_id) FROM patient_visits WHERE patient_id=p.id)"
                 " WHERE p.phone LIKE %s ORDER BY p.id LIMIT 50",
        "date":  "SELECT p.*, pv.visit_id, pv.doctor_assigned, pv.created_at AS last_visit"
                 " FROM patients p LEFT JOIN patient_visits pv ON pv.patient_id=p.id"
                 " AND pv.visit_id=(SELECT MAX(visit_id) FROM patient_visits WHERE patient_id=p.id)"
                 " WHERE DATE(p.created_at)=%s ORDER BY p.id LIMIT 100",
    }

    sql  = sql_map.get(field, sql_map["name"])
    param = f"%{query}%" if field in ("uhid", "name", "phone") else query

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (param,))
            rows = cur.fetchall()
    return [dict(r) for r in (rows or [])]


def search_patient_by_phone(phone: str) -> list:
    """Return list of patients matching the phone number."""
    phone = phone.strip()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id AS patient_id, full_name, dob, gender, phone,
                       aadhar, address, blood_group, allergies,
                       TO_CHAR(created_at, 'YYYY-MM-DD') AS registered_on
                FROM patients
                WHERE phone ILIKE %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (f"%{phone}%",)
            )
            return [dict(r) for r in cur.fetchall()]


def get_patient_history(patient_id: int) -> dict:
    """
    Return complete patient history: demographics + all visits + prescriptions +
    lab results + vitals + billing.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Patient demographics
            cur.execute(
                "SELECT * FROM patients WHERE id = %s",
                (patient_id,)
            )
            patient = cur.fetchone()
            if not patient:
                return {"error": "Patient not found"}
            patient = dict(patient)

            # Visits
            cur.execute(
                """
                SELECT visit_id, visit_type, doctor_assigned, department,
                       visit_date, chief_complaint, diagnosis, notes,
                       status, op_ticket_no
                FROM patient_visits WHERE patient_id = %s
                ORDER BY visit_date DESC
                """,
                (patient_id,)
            )
            visits = [dict(r) for r in cur.fetchall()]

            # Prescriptions (by patient phone)
            prescs: list = []
            if patient.get("phone"):
                cur.execute(
                    """
                    SELECT p.id AS prescription_id, p.doctor_name, p.diagnosis,
                           p.medicines, p.notes,
                           TO_CHAR(p.created_at, 'YYYY-MM-DD HH24:MI') AS prescribed_on,
                           json_agg(
                               json_build_object(
                                   'medicine', pi.medicine_name,
                                   'dosage', pi.dosage,
                                   'duration', pi.duration,
                                   'instructions', pi.instructions
                               )
                           ) FILTER (WHERE pi.item_id IS NOT NULL) AS items
                    FROM prescriptions p
                    LEFT JOIN prescription_items pi ON pi.prescription_id = p.id
                    WHERE p.patient_phone = %s
                    GROUP BY p.id
                    ORDER BY p.created_at DESC
                    LIMIT 50
                    """,
                    (patient["phone"],)
                )
                prescs = [dict(r) for r in cur.fetchall()]

            # Lab results
            cur.execute(
                """
                SELECT lr.result_id, lr.test_name, lr.result_value,
                       lr.reference_range, lr.unit, lr.is_abnormal,
                       lr.remarks, lr.lab_username,
                       TO_CHAR(lr.reported_at, 'YYYY-MM-DD HH24:MI') AS reported_at
                FROM lab_results lr
                WHERE lr.patient_id = %s
                ORDER BY lr.reported_at DESC
                LIMIT 50
                """,
                (patient_id,)
            )
            lab_results = [dict(r) for r in cur.fetchall()]

            # Vitals (by phone)
            vitals: list = []
            if patient.get("phone"):
                cur.execute(
                    """
                    SELECT bp, pulse, temperature, spo2, weight, notes,
                           TO_CHAR(recorded_at, 'YYYY-MM-DD HH24:MI') AS recorded_at
                    FROM vitals WHERE patient_phone = %s
                    ORDER BY recorded_at DESC LIMIT 20
                    """,
                    (patient["phone"],)
                )
                vitals = [dict(r) for r in cur.fetchall()]

            # Bills
            bills: list = []
            if patient.get("phone"):
                cur.execute(
                    """
                    SELECT id AS bill_id, bill_type, total_amount, net_amount,
                           tax_amount, status,
                           TO_CHAR(created_at, 'YYYY-MM-DD') AS billed_on
                    FROM billing WHERE patient_phone = %s
                    ORDER BY created_at DESC LIMIT 20
                    """,
                    (patient["phone"],)
                )
                bills = [dict(r) for r in cur.fetchall()]

    # Serialise datetime/date objects
    patient = _serialise(patient)
    visits  = [_serialise(v) for v in visits]

    return {
        "patient":      patient,
        "visits":       visits,
        "prescriptions": prescs,
        "lab_results":  lab_results,
        "vitals":       vitals,
        "bills":        bills,
        "total_visits": len(visits),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. BILLING SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def create_invoice(data: dict) -> dict:
    """
    Create a hospital invoice with line items.
    Supports: OPD / IPD / Pharmacy / Lab / Surgery packages.
    Returns the new bill id and invoice summary.
    """
    patient_name     = (data.get("patient_name") or "").strip()
    patient_phone    = (data.get("patient_phone") or "").strip()
    bill_type        = (data.get("bill_type") or "OPD").strip().upper()
    items            = data.get("items") or []           # list of {item_type, item_name, quantity, price, tax_percent}
    discount         = float(data.get("discount") or 0)
    notes            = (data.get("notes") or "").strip()
    created_by       = (data.get("created_by") or "reception").strip()
    admission_id     = data.get("admission_id")

    if not patient_name:
        return {"error": "patient_name is required"}

    # Compute totals
    subtotal  = 0.0
    tax_total = 0.0
    line_rows = []
    for it in items:
        qty     = int(it.get("quantity") or 1)
        price   = float(it.get("price") or it.get("item_price") or 0)
        tax_pct = float(it.get("tax_percent") or 0)
        tax_amt = round(price * qty * tax_pct / 100, 2)
        total   = round(price * qty + tax_amt, 2)
        subtotal  += price * qty
        tax_total += tax_amt
        line_rows.append({
            "item_type":    str(it.get("item_type") or "consultation"),
            "item_name":    str(it.get("item_name") or ""),
            "item_price":   price,
            "quantity":     qty,
            "tax_percent":  tax_pct,
            "tax_amount":   tax_amt,
            "total_amount": total,
        })

    total_amount = round(subtotal + tax_total, 2)
    net_amount   = round(total_amount - discount, 2)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO billing
                    (patient_name, patient_phone, bill_type, admission_id,
                     total_amount, tax_amount, discount, net_amount,
                     status, notes, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'unpaid',%s,%s)
                RETURNING id
                """,
                (patient_name, patient_phone, bill_type,
                 admission_id, total_amount, tax_total,
                 discount, net_amount, notes, created_by)
            )
            bill_id = cur.fetchone()[0]

            for row in line_rows:
                cur.execute(
                    """
                    INSERT INTO bill_items
                        (bill_id, item_type, item_name, item_price, quantity,
                         tax_percent, tax_amount, total_amount)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (bill_id, row["item_type"], row["item_name"],
                     row["item_price"], row["quantity"],
                     row["tax_percent"], row["tax_amount"], row["total_amount"])
                )

    return {
        "bill_id":       bill_id,
        "patient_name":  patient_name,
        "patient_phone": patient_phone,
        "bill_type":     bill_type,
        "subtotal":      round(subtotal, 2),
        "tax_amount":    round(tax_total, 2),
        "discount":      discount,
        "total_amount":  total_amount,
        "net_amount":    net_amount,
        "status":        "unpaid",
        "items_count":   len(line_rows),
    }


def get_invoice(invoice_id: int) -> dict | None:
    """Return full invoice with line items."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.*,
                       TO_CHAR(b.created_at, 'YYYY-MM-DD HH24:MI') AS invoice_date
                FROM billing b WHERE b.id = %s
                """,
                (invoice_id,)
            )
            bill = cur.fetchone()
            if not bill:
                return None
            bill = dict(bill)

            cur.execute(
                "SELECT * FROM bill_items WHERE bill_id = %s ORDER BY id",
                (invoice_id,)
            )
            bill["items"] = [dict(r) for r in cur.fetchall()]

            # Payment history
            cur.execute(
                """
                SELECT amount_paid, payment_mode, reference_no,
                       TO_CHAR(paid_at, 'YYYY-MM-DD HH24:MI') AS paid_at
                FROM payments WHERE bill_id = %s ORDER BY paid_at
                """,
                (invoice_id,)
            )
            bill["payments"] = [dict(r) for r in cur.fetchall()]
    return _serialise(bill)


def get_visit_detail(visit_id: int) -> dict | None:
    """Return full visit record with patient info and prescriptions (for OPD PDF)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT pv.*, p.full_name, p.phone, p.dob, p.gender,
                       p.blood_group, p.allergies, p.uhid,
                       TO_CHAR(pv.created_at, 'YYYY-MM-DD HH24:MI') AS visit_date
                FROM patient_visits pv
                JOIN patients p ON p.id = pv.patient_id
                WHERE pv.visit_id = %s
                """,
                (visit_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            visit = dict(row)
            # Structured prescriptions
            cur.execute(
                "SELECT * FROM prescriptions WHERE visit_id=%s ORDER BY id",
                (visit_id,)
            )
            presc_rows = cur.fetchall() or []
            visit["prescriptions"] = [dict(r) for r in presc_rows]
            # Doctor notes
            cur.execute(
                "SELECT * FROM doctor_notes WHERE visit_id=%s ORDER BY id",
                (visit_id,)
            )
            note_rows = cur.fetchall() or []
            visit["notes"] = [dict(r) for r in note_rows]
    return _serialise(visit)


def get_admission_detail(adm_id: int) -> dict | None:
    """Return full IPD admission record with rounds for discharge PDF."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT pa.*, p.full_name, p.phone, p.dob, p.gender,
                       p.blood_group, p.allergies, p.uhid,
                       w.ward_name, b.bed_number,
                       TO_CHAR(pa.admission_date, 'YYYY-MM-DD HH24:MI') AS adm_date_fmt,
                       TO_CHAR(pa.discharge_date, 'YYYY-MM-DD HH24:MI') AS dis_date_fmt
                FROM patient_admissions pa
                JOIN patients p ON p.id = pa.patient_id
                LEFT JOIN beds b ON b.id = pa.bed_id
                LEFT JOIN wards w ON w.id = pa.ward_id
                WHERE pa.id = %s
                """,
                (adm_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            adm = dict(row)
            # Daily rounds
            cur.execute(
                "SELECT * FROM daily_rounds WHERE admission_id=%s ORDER BY round_date",
                (adm_id,)
            )
            rounds_rows = cur.fetchall() or []
            adm["rounds"] = [dict(r) for r in rounds_rows]
            # Discharge summary text
            cur.execute(
                "SELECT * FROM discharge_summaries WHERE admission_id=%s ORDER BY id DESC LIMIT 1",
                (adm_id,)
            )
            ds = cur.fetchone()
            adm["discharge_summary"] = dict(ds) if ds else {}
    return _serialise(adm)


def get_sale_detail(sale_id: int) -> dict | None:
    """Return full pharmacy sale record with items (for pharmacy bill PDF)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT ps.*,
                       TO_CHAR(ps.sold_at, 'YYYY-MM-DD HH24:MI') AS sale_date
                FROM pharmacy_sales ps
                WHERE ps.id = %s
                """,
                (sale_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            sale = dict(row)
            # Individual line items from medicines JSON or separate table
            items = sale.get("items") or sale.get("medicines") or []
            if isinstance(items, str):
                import json as _j
                try:
                    items = _j.loads(items)
                except Exception:
                    items = []
            sale["items"] = items
    return _serialise(sale)


def get_daily_revenue_report(target_date: Optional[str] = None) -> dict:
    """
    Returns daily revenue breakdown:
      total_revenue, opd_revenue, ipd_revenue, pharmacy_revenue,
      lab_revenue, surgery_revenue, num_invoices, num_paid.
    target_date: 'YYYY-MM-DD', defaults to today.
    """
    if not target_date:
        target_date = date.today().isoformat()

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(net_amount), 0)                          AS total_revenue,
                    COALESCE(SUM(CASE WHEN bill_type='OPD' THEN net_amount ELSE 0 END), 0) AS opd_revenue,
                    COALESCE(SUM(CASE WHEN bill_type='IPD' THEN net_amount ELSE 0 END), 0) AS ipd_revenue,
                    COALESCE(SUM(CASE WHEN bill_type='PHARMACY' THEN net_amount ELSE 0 END), 0) AS pharmacy_revenue,
                    COALESCE(SUM(CASE WHEN bill_type='LAB' THEN net_amount ELSE 0 END), 0) AS lab_revenue,
                    COALESCE(SUM(CASE WHEN bill_type='SURGERY' THEN net_amount ELSE 0 END), 0) AS surgery_revenue,
                    COUNT(*)                                              AS num_invoices,
                    COUNT(*) FILTER (WHERE status='paid')                AS num_paid,
                    COUNT(*) FILTER (WHERE status='unpaid')              AS num_unpaid
                FROM billing
                WHERE DATE(created_at) = %s
                """,
                (target_date,)
            )
            row = dict(cur.fetchone())

    # Pharmacy sales revenue
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(net_amount),0) AS pharma_sales,
                       COUNT(*) AS pharma_txns
                FROM pharmacy_sales WHERE DATE(sold_at) = %s
                """,
                (target_date,)
            )
            pharma = dict(cur.fetchone())

    row["pharmacy_sales_revenue"] = float(pharma["pharma_sales"])
    row["pharmacy_transactions"]  = int(pharma["pharma_txns"])
    row["date"]                   = target_date
    row["generated_at"]           = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return _float_row(row)


# ─────────────────────────────────────────────────────────────────────────────
# 3. DOCTOR WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────

def get_doctor_patient_queue(doctor_username: str, doctor_name: str = "") -> list:
    """
    Return today's patient queue for a doctor.
    Pulls from op_tickets (status=waiting) + registrations.
    """
    today = date.today().isoformat()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # From op_tickets
            cur.execute(
                """
                SELECT
                    t.ticket_no, t.status AS ticket_status,
                    p.id AS patient_id, p.full_name, p.phone, p.gender,
                    p.blood_group, p.allergies,
                    v.visit_id, v.chief_complaint, v.visit_type,
                    TO_CHAR(t.issued_at, 'HH24:MI') AS issued_time
                FROM op_tickets t
                JOIN patients p      ON p.id = t.patient_id
                JOIN patient_visits v ON v.visit_id = t.visit_id
                WHERE DATE(t.issued_at) = %s
                  AND (t.doctor_name ILIKE %s OR t.doctor_name = '')
                  AND t.status != 'done'
                ORDER BY t.issued_at
                """,
                (today, f"%{doctor_name}%" if doctor_name else "%%")
            )
            queue = [dict(r) for r in cur.fetchall()]

            # Also pull from appointments for today's scheduled patients
            cur.execute(
                """
                SELECT a.id AS appointment_id, a.patient_name AS full_name,
                       a.patient_phone AS phone, a.issue AS chief_complaint,
                       a.appointment_time AS issued_time,
                       a.doctor_name, a.status AS ticket_status,
                       NULL::INTEGER AS patient_id,
                       NULL::INTEGER AS visit_id,
                       'OP' AS visit_type,
                       'APPT' AS ticket_no
                FROM appointments a
                WHERE (a.appointment_date = %s
                       OR (a.appointment_date IS NULL AND DATE(a.created_at) = %s))
                  AND (a.doctor_name ILIKE %s OR %s = '')
                  AND a.status NOT IN ('done', 'cancelled', 'completed')
                ORDER BY a.created_at
                """,
                (today, today, f"%{doctor_name}%", doctor_name)
            )
            appts = [dict(r) for r in cur.fetchall()]

    # Combine and deduplicate
    combined = queue + appts
    return combined


def get_patient_full_record_for_doctor(patient_id: int) -> dict:
    """
    Return a doctor-friendly full patient record (same as history but with
    a visit-oriented top-level structure).
    """
    return get_patient_history(patient_id)


def add_doctor_note(data: dict) -> dict:
    """Add a clinical note to a patient visit."""
    patient_id      = data.get("patient_id")
    visit_id        = data.get("visit_id")
    doctor_username = (data.get("doctor_username") or "").strip()
    doctor_name     = (data.get("doctor_name") or "").strip()
    note_type       = (data.get("note_type") or "clinical").strip()
    note_text       = (data.get("note_text") or data.get("notes") or "").strip()

    if not patient_id or not note_text:
        return {"error": "patient_id and note_text are required"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO doctor_notes
                    (patient_id, visit_id, doctor_username, doctor_name, note_type, note_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING note_id
                """,
                (patient_id, visit_id, doctor_username, doctor_name, note_type, note_text)
            )
            note_id = cur.fetchone()[0]

    return {"note_id": note_id, "status": "saved"}


def add_structured_prescription(data: dict) -> dict:
    """
    Save a prescription with structured per-medicine items.
    data.medicines_list = [{medicine_name, dosage, frequency, duration, instructions, quantity}]
    """
    patient_name    = (data.get("patient_name") or "").strip()
    patient_phone   = (data.get("patient_phone") or "").strip()
    doctor_username = (data.get("doctor_username") or "").strip()
    doctor_name     = (data.get("doctor_name") or "").strip()
    diagnosis       = (data.get("diagnosis") or "").strip()
    notes           = (data.get("notes") or "").strip()
    medicines_list  = data.get("medicines_list") or []

    # Flatten medicine list for legacy `medicines` text column
    medicines_text = "; ".join(
        f"{m.get('medicine_name','')} {m.get('dosage','')} × {m.get('duration','')}"
        for m in medicines_list
    ) if medicines_list else (data.get("medicines") or "")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prescriptions
                    (patient_name, patient_phone, doctor_username, doctor_name,
                     diagnosis, medicines, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (patient_name, patient_phone, doctor_username,
                 doctor_name, diagnosis, medicines_text, notes)
            )
            presc_id = cur.fetchone()[0]

            for med in medicines_list:
                cur.execute(
                    """
                    INSERT INTO prescription_items
                        (prescription_id, medicine_name, dosage, frequency,
                         duration, instructions, quantity)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        presc_id,
                        med.get("medicine_name", ""),
                        med.get("dosage", ""),
                        med.get("frequency", ""),
                        med.get("duration", ""),
                        med.get("instructions", ""),
                        int(med.get("quantity") or 0),
                    )
                )

    return {
        "prescription_id": presc_id,
        "patient_name":    patient_name,
        "medicines_count": len(medicines_list),
        "status":          "saved",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. PHARMACY INVENTORY SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def get_pharmacy_stock_list() -> list:
    """Return current pharmacy stock with medicine details."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    ps.stock_id,
                    m.id AS medicine_id,
                    m.medicine_name,
                    m.generic_name,
                    m.category,
                    m.unit,
                    ps.batch_no,
                    ps.expiry_date,
                    ps.quantity,
                    ps.min_quantity,
                    ps.unit_price,
                    ps.sell_price,
                    ps.supplier,
                    CASE
                        WHEN ps.quantity = 0           THEN 'out_of_stock'
                        WHEN ps.quantity <= ps.min_quantity THEN 'low_stock'
                        ELSE 'in_stock'
                    END AS stock_status,
                    CASE
                        WHEN ps.expiry_date IS NOT NULL AND ps.expiry_date <= CURRENT_DATE + 30
                             THEN TRUE ELSE FALSE
                    END AS expiring_soon
                FROM pharmacy_stock ps
                JOIN medicines m ON m.id = ps.medicine_id
                ORDER BY m.medicine_name, ps.expiry_date
                """
            )
            return [_serialise(dict(r)) for r in cur.fetchall()]


def record_pharmacy_sale(data: dict) -> dict:
    """
    Record a pharmacy sale transaction.
    data.items = [{medicine_id, quantity, unit_price}]
    """
    patient_name    = (data.get("patient_name") or "Walk-in").strip()
    patient_phone   = (data.get("patient_phone") or "").strip()
    prescription_id = data.get("prescription_id")
    payment_mode    = (data.get("payment_mode") or "Cash").strip()
    staff_username  = (data.get("staff_username") or "pharmacy").strip()
    discount        = float(data.get("discount") or 0)
    items           = data.get("items") or []

    total_amount = sum(
        float(it.get("unit_price") or 0) * int(it.get("quantity") or 1)
        for it in items
    )
    net_amount = round(total_amount - discount, 2)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pharmacy_sales
                    (patient_name, patient_phone, prescription_id, total_amount,
                     discount, net_amount, payment_mode, staff_username)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (patient_name, patient_phone, prescription_id,
                 total_amount, discount, net_amount, payment_mode, staff_username)
            )
            sale_id = cur.fetchone()[0]

            for it in items:
                med_id   = it.get("medicine_id")
                qty      = int(it.get("quantity") or 1)
                uprice   = float(it.get("unit_price") or 0)
                med_name = (it.get("medicine_name") or "").strip()
                total    = round(uprice * qty, 2)

                cur.execute(
                    """
                    INSERT INTO pharmacy_sale_items
                        (sale_id, medicine_id, medicine_name, quantity, unit_price, total_price)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (sale_id, med_id, med_name, qty, uprice, total)
                )

                # Deduct from pharmacy_stock
                if med_id:
                    cur.execute(
                        """
                        UPDATE pharmacy_stock
                        SET quantity = GREATEST(0, quantity - %s),
                            updated_at = NOW()
                        WHERE medicine_id = %s AND quantity > 0
                        """,
                        (qty, med_id)
                    )

                    # Trigger low-stock notification (fire-and-forget flag)
                    cur.execute(
                        """
                        SELECT quantity, min_quantity, medicine_name
                        FROM pharmacy_stock ps JOIN medicines m ON m.id=ps.medicine_id
                        WHERE ps.medicine_id=%s
                        LIMIT 1
                        """,
                        (med_id,)
                    )
                    row = cur.fetchone()
                    if row and row[0] <= row[1]:
                        _schedule_low_stock_alert(row[2], row[0], row[1])

    return {
        "sale_id":       sale_id,
        "patient_name":  patient_name,
        "total_amount":  total_amount,
        "discount":      discount,
        "net_amount":    net_amount,
        "items_sold":    len(items),
        "status":        "completed",
    }


def get_pharmacy_alerts() -> dict:
    """Returns combined low-stock and expiry alerts."""
    alerts: dict = {"low_stock": [], "expiring": [], "out_of_stock": []}

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Low stock
            cur.execute(
                """
                SELECT m.medicine_name, m.category, ps.quantity, ps.min_quantity,
                       ps.batch_no, ps.supplier
                FROM pharmacy_stock ps
                JOIN medicines m ON m.id = ps.medicine_id
                WHERE ps.quantity <= ps.min_quantity AND ps.quantity > 0
                ORDER BY ps.quantity
                """
            )
            alerts["low_stock"] = [dict(r) for r in cur.fetchall()]

            # Out of stock
            cur.execute(
                """
                SELECT m.medicine_name, m.category, ps.batch_no
                FROM pharmacy_stock ps
                JOIN medicines m ON m.id = ps.medicine_id
                WHERE ps.quantity = 0
                """
            )
            alerts["out_of_stock"] = [dict(r) for r in cur.fetchall()]

            # Expiring within 90 days
            expiry_cutoff = (date.today() + timedelta(days=90)).isoformat()
            cur.execute(
                """
                SELECT m.medicine_name, m.category, ps.batch_no,
                       ps.expiry_date, ps.quantity,
                       (ps.expiry_date - CURRENT_DATE) AS days_to_expiry
                FROM pharmacy_stock ps
                JOIN medicines m ON m.id = ps.medicine_id
                WHERE ps.expiry_date IS NOT NULL AND ps.expiry_date <= %s
                  AND ps.quantity > 0
                ORDER BY ps.expiry_date
                """,
                (expiry_cutoff,)
            )
            alerts["expiring"] = [_serialise(dict(r)) for r in cur.fetchall()]

    alerts["summary"] = {
        "low_stock_count":   len(alerts["low_stock"]),
        "out_of_stock_count": len(alerts["out_of_stock"]),
        "expiring_count":    len(alerts["expiring"]),
        "total_alerts":      len(alerts["low_stock"]) + len(alerts["out_of_stock"]) + len(alerts["expiring"]),
    }
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# 5. LAB & DIAGNOSTIC MODULE
# ─────────────────────────────────────────────────────────────────────────────

def order_lab_test(data: dict) -> dict:
    """
    Create a lab test order and link to patient.
    Supports both catalogue-based and free-text test orders.
    """
    patient_name    = (data.get("patient_name") or "").strip()
    patient_phone   = (data.get("patient_phone") or "").strip()
    patient_id      = data.get("patient_id")
    doctor_username = (data.get("doctor_username") or "").strip()
    test_names      = data.get("tests") or [data.get("test_name", "General")]
    test_type       = (data.get("test_type") or "LAB").strip().upper()
    visit_id        = data.get("visit_id")

    if isinstance(test_names, str):
        test_names = [test_names]

    created_ids = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for test in test_names:
                cur.execute(
                    """
                    INSERT INTO lab_orders
                        (patient_name, patient_phone, doctor_username,
                         test_type, test_name, status)
                    VALUES (%s, %s, %s, %s, %s, 'PENDING')
                    RETURNING id
                    """,
                    (patient_name, patient_phone, doctor_username,
                     test_type, str(test))
                )
                created_ids.append(cur.fetchone()[0])

    return {
        "order_ids":    created_ids,
        "patient_name": patient_name,
        "tests":        test_names,
        "test_type":    test_type,
        "status":       "PENDING",
    }


def record_lab_result(data: dict) -> dict:
    """
    Record lab test result and link it to the patient's history.
    """
    order_id        = data.get("order_id")
    patient_id      = data.get("patient_id")
    patient_name    = (data.get("patient_name") or "").strip()
    test_name       = (data.get("test_name") or "").strip()
    result_value    = (data.get("result_value") or data.get("result_text") or "").strip()
    reference_range = (data.get("reference_range") or "").strip()
    unit            = (data.get("unit") or "").strip()
    is_abnormal     = bool(data.get("is_abnormal") or False)
    remarks         = (data.get("remarks") or "").strip()
    lab_username    = (data.get("lab_username") or "lab").strip()

    if not result_value:
        return {"error": "result_value is required"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Insert into lab_results
            cur.execute(
                """
                INSERT INTO lab_results
                    (order_id, patient_id, patient_name, test_name,
                     result_value, reference_range, unit, is_abnormal,
                     remarks, lab_username)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING result_id
                """,
                (order_id, patient_id, patient_name, test_name,
                 result_value, reference_range, unit, is_abnormal,
                 remarks, lab_username)
            )
            result_id = cur.fetchone()[0]

            # Update lab_order status to COMPLETED
            if order_id:
                cur.execute(
                    """
                    UPDATE lab_orders
                    SET status='COMPLETED', result_text=%s, completed_at=NOW()
                    WHERE id=%s
                    """,
                    (result_value, order_id)
                )

                # Also sync to lab_reports for legacy support
                cur.execute(
                    """
                    INSERT INTO lab_reports
                        (order_id, patient_name, test_name, result_text,
                         remarks, lab_username)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (order_id, patient_name, test_name,
                     result_value, remarks, lab_username)
                )

    return {
        "result_id":    result_id,
        "order_id":     order_id,
        "test_name":    test_name,
        "is_abnormal":  is_abnormal,
        "status":       "COMPLETED",
    }


def get_patient_lab_reports(patient_id: int) -> list:
    """Return all lab results for a patient, ordered by latest first."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    lr.result_id,
                    lr.test_name,
                    lr.result_value,
                    lr.reference_range,
                    lr.unit,
                    lr.is_abnormal,
                    lr.remarks,
                    lr.lab_username,
                    TO_CHAR(lr.reported_at, 'YYYY-MM-DD HH24:MI') AS reported_at,
                    lo.doctor_username AS ordered_by,
                    lo.test_type
                FROM lab_results lr
                LEFT JOIN lab_orders lo ON lo.id = lr.order_id
                WHERE lr.patient_id = %s
                ORDER BY lr.reported_at DESC
                """,
                (patient_id,)
            )
            return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# 6. OWNER ANALYTICS DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def get_analytics_revenue(period: str = "daily") -> dict:
    """
    Owner-level revenue analytics.
    period: daily | weekly | monthly | yearly
    """
    period = period.lower()
    today  = date.today()

    if period == "daily":
        start = today
        end   = today
        label = today.isoformat()
    elif period == "weekly":
        start = today - timedelta(days=6)
        end   = today
        label = f"{start.isoformat()} to {end.isoformat()}"
    elif period == "monthly":
        start = today.replace(day=1)
        end   = today
        label = today.strftime("%B %Y")
    elif period == "yearly":
        start = today.replace(month=1, day=1)
        end   = today
        label = str(today.year)
    else:
        start = today
        end   = today
        label = today.isoformat()

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Revenue by day in period
            cur.execute(
                """
                SELECT
                    DATE(created_at)                                          AS day,
                    COALESCE(SUM(net_amount), 0)                              AS revenue,
                    COUNT(*)                                                  AS invoices,
                    COALESCE(SUM(CASE WHEN status='paid' THEN net_amount ELSE 0 END),0) AS collected
                FROM billing
                WHERE DATE(created_at) BETWEEN %s AND %s
                GROUP BY day ORDER BY day
                """,
                (start, end)
            )
            daily_rows = [_float_row(dict(r)) for r in cur.fetchall()]

            # Summary
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(net_amount), 0)                             AS total_revenue,
                    COALESCE(SUM(CASE WHEN status='paid' THEN net_amount ELSE 0 END),0) AS collected,
                    COALESCE(SUM(CASE WHEN status='unpaid' THEN net_amount ELSE 0 END),0) AS outstanding,
                    COUNT(*)                                                 AS total_invoices,
                    COUNT(*) FILTER (WHERE status='paid')                   AS paid_invoices,
                    COALESCE(AVG(net_amount), 0)                            AS avg_bill_value,
                    COALESCE(SUM(CASE WHEN bill_type='OPD'      THEN net_amount ELSE 0 END),0) AS opd,
                    COALESCE(SUM(CASE WHEN bill_type='IPD'      THEN net_amount ELSE 0 END),0) AS ipd,
                    COALESCE(SUM(CASE WHEN bill_type='PHARMACY' THEN net_amount ELSE 0 END),0) AS pharmacy,
                    COALESCE(SUM(CASE WHEN bill_type='LAB'      THEN net_amount ELSE 0 END),0) AS lab,
                    COALESCE(SUM(CASE WHEN bill_type='SURGERY'  THEN net_amount ELSE 0 END),0) AS surgery
                FROM billing
                WHERE DATE(created_at) BETWEEN %s AND %s
                """,
                (start, end)
            )
            summary = _float_row(dict(cur.fetchone()))

            # Pharmacy sales (separate table)
            cur.execute(
                """
                SELECT COALESCE(SUM(net_amount),0) AS pharma_total, COUNT(*) AS pharma_count
                FROM pharmacy_sales
                WHERE DATE(sold_at) BETWEEN %s AND %s
                """,
                (start, end)
            )
            pharma = _float_row(dict(cur.fetchone()))

    return {
        "period":          period,
        "label":           label,
        "start_date":      start.isoformat(),
        "end_date":        end.isoformat(),
        "summary":         summary,
        "pharmacy_sales":  pharma,
        "daily_breakdown": daily_rows,
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_analytics_patients(period: str = "daily") -> dict:
    """Patient volume analytics for the owner dashboard."""
    period = period.lower()
    today  = date.today()

    if period == "daily":
        start, end = today, today
    elif period == "weekly":
        start = today - timedelta(days=6); end = today
    elif period == "monthly":
        start = today.replace(day=1); end = today
    else:
        start = today.replace(month=1, day=1); end = today

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # New registrations
            cur.execute(
                """
                SELECT COUNT(*) AS new_patients
                FROM patients WHERE DATE(created_at) BETWEEN %s AND %s
                """,
                (start, end)
            )
            new_patients = int(cur.fetchone()["new_patients"])

            # OPD visits
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_visits,
                    COUNT(*) FILTER (WHERE visit_type='OP') AS opd_visits,
                    COUNT(*) FILTER (WHERE visit_type='IP') AS ipd_visits,
                    COUNT(*) FILTER (WHERE visit_type='ER') AS er_visits
                FROM patient_visits
                WHERE DATE(visit_date) BETWEEN %s AND %s
                """,
                (start, end)
            )
            visits = _float_row(dict(cur.fetchone()))

            # Visit trend by day
            cur.execute(
                """
                SELECT DATE(visit_date) AS day, COUNT(*) AS count
                FROM patient_visits
                WHERE DATE(visit_date) BETWEEN %s AND %s
                GROUP BY day ORDER BY day
                """,
                (start, end)
            )
            trend = [_float_row(dict(r)) for r in cur.fetchall()]

            # Registered patients total
            cur.execute("SELECT COUNT(*) AS total FROM patients")
            total_patients = int(cur.fetchone()["total"])

            # Bed occupancy
            cur.execute(
                """
                SELECT COUNT(*) AS occupied
                FROM patient_admissions
                WHERE status = 'admitted'
                """
            )
            occupied_beds = int(cur.fetchone()["occupied"])

            cur.execute("SELECT COALESCE(SUM(total_beds),0) AS total FROM wards WHERE is_active=TRUE")
            total_beds = int(cur.fetchone()["total"])

    occupancy_pct = round(occupied_beds / total_beds * 100, 1) if total_beds else 0

    return {
        "period":           period,
        "new_patients":     new_patients,
        "total_patients":   total_patients,
        "visits":           visits,
        "visit_trend":      trend,
        "bed_occupancy": {
            "occupied":    occupied_beds,
            "total_beds":  total_beds,
            "occupancy_pct": occupancy_pct,
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_analytics_doctors() -> dict:
    """Doctor performance analytics for the owner dashboard."""
    today = date.today()
    month_start = today.replace(day=1)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Prescriptions per doctor this month
            cur.execute(
                """
                SELECT doctor_name,
                       COUNT(*) AS prescriptions,
                       COUNT(DISTINCT patient_phone) AS unique_patients
                FROM prescriptions
                WHERE DATE(created_at) BETWEEN %s AND %s
                  AND doctor_name != ''
                GROUP BY doctor_name
                ORDER BY prescriptions DESC
                LIMIT 20
                """,
                (month_start, today)
            )
            presc_stats = [dict(r) for r in cur.fetchall()]

            # Doctors on duty today
            cur.execute(
                "SELECT name, department, specialization FROM doctors WHERE on_duty=TRUE"
            )
            on_duty = [dict(r) for r in cur.fetchall()]

            # Visit records per doctor this month
            cur.execute(
                """
                SELECT doctor_name,
                       COUNT(*) AS visits_recorded
                FROM visit_records
                WHERE DATE(visit_date) BETWEEN %s AND %s
                  AND doctor_name != ''
                GROUP BY doctor_name
                ORDER BY visits_recorded DESC
                LIMIT 20
                """,
                (month_start, today)
            )
            visit_stats = [dict(r) for r in cur.fetchall()]

    return {
        "period":              f"{month_start.isoformat()} to {today.isoformat()}",
        "doctors_on_duty":     on_duty,
        "doctors_on_duty_count": len(on_duty),
        "prescriptions_by_doctor": presc_stats,
        "visits_by_doctor":    visit_stats,
        "generated_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. MOBILE-READY DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def get_mobile_dashboard() -> dict:
    """
    Lightweight mobile dashboard for hospital owners.
    Returns key metrics all in one call (optimised for low bandwidth).
    """
    today = date.today()

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Today's revenue
            cur.execute(
                "SELECT COALESCE(SUM(net_amount),0) AS rev FROM billing WHERE DATE(created_at)=%s",
                (today,)
            )
            today_revenue = float(cur.fetchone()["rev"])

            # Today's patients
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM patient_visits WHERE DATE(visit_date)=%s",
                (today,)
            )
            today_patients = int(cur.fetchone()["cnt"])

            # Admitted patients
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM patient_admissions WHERE status='admitted'"
            )
            admitted = int(cur.fetchone()["cnt"])

            # Doctors on duty
            cur.execute("SELECT COUNT(*) AS cnt FROM doctors WHERE on_duty=TRUE")
            on_duty = int(cur.fetchone()["cnt"])

            # Low stock alerts
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM pharmacy_stock
                WHERE quantity <= min_quantity AND quantity >= 0
                """
            )
            low_stock = int(cur.fetchone()["cnt"])

            # Expiry alerts (within 30 days)
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM pharmacy_stock
                WHERE expiry_date <= CURRENT_DATE + 30 AND quantity > 0
                """
            )
            expiring = int(cur.fetchone()["cnt"])

            # Pending lab orders
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM lab_orders WHERE status='PENDING'"
            )
            pending_labs = int(cur.fetchone()["cnt"])

            # Monthly revenue
            cur.execute(
                """
                SELECT COALESCE(SUM(net_amount),0) AS rev FROM billing
                WHERE DATE(created_at) >= %s
                """,
                (today.replace(day=1),)
            )
            month_revenue = float(cur.fetchone()["rev"])

    return {
        "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "today": {
            "revenue":      today_revenue,
            "patients":     today_patients,
            "admitted_ipd": admitted,
            "doctors_on_duty": on_duty,
        },
        "month": {
            "revenue":      month_revenue,
        },
        "alerts": {
            "low_stock_medicines": low_stock,
            "expiring_medicines":  expiring,
            "pending_lab_orders":  pending_labs,
            "total_alerts":        low_stock + expiring + pending_labs,
        },
        "status": "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# APPOINTMENT SCHEDULING  (Reception Module)
# ─────────────────────────────────────────────────────────────────────────────

def create_appointment(data: dict) -> dict:
    """Book an appointment and link to patient record if exists."""
    patient_name   = (data.get("patient_name") or "").strip()
    patient_phone  = (data.get("patient_phone") or data.get("phone") or "").strip()
    doctor_name    = (data.get("doctor_name") or data.get("doctor") or "").strip()
    department     = (data.get("department") or "").strip()
    appt_date      = data.get("appointment_date") or date.today().isoformat()
    appt_time      = (data.get("appointment_time") or "").strip()
    issue          = (data.get("issue") or data.get("chief_complaint") or "").strip()
    source         = (data.get("source") or "reception").strip()

    if not patient_name:
        return {"error": "patient_name is required"}

    # Try to link to existing patient
    patient_id = None
    if patient_phone:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM patients WHERE phone=%s LIMIT 1", (patient_phone,)
                )
                row = cur.fetchone()
                if row:
                    patient_id = row[0]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO appointments
                    (patient_name, patient_phone, doctor_name, department,
                     appointment_date, appointment_time, issue, patient_id, source, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
                RETURNING id
                """,
                (patient_name, patient_phone, doctor_name, department,
                 appt_date, appt_time, issue, patient_id, source)
            )
            appt_id = cur.fetchone()[0]

    return {
        "appointment_id":   appt_id,
        "patient_name":     patient_name,
        "patient_phone":    patient_phone,
        "doctor_name":      doctor_name,
        "appointment_date": appt_date,
        "appointment_time": appt_time,
        "patient_id":       patient_id,
        "status":           "pending",
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _serialise(obj: Any) -> Any:
    """Recursively convert date/datetime/Decimal objects to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(i) for i in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
    except ImportError:
        pass
    if hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
        return str(obj)
    return obj


def _float_row(row: dict) -> dict:
    """Convert all numeric-ish values in a dict row to float/int for JSON serialisation."""
    from decimal import Decimal
    result = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, (datetime, date)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _schedule_low_stock_alert(medicine_name: str, qty: int, min_qty: int) -> None:
    """
    Fire-and-forget internal low-stock notification.
    Writes to system_logs; also calls founder_alerts if available.
    """
    try:
        from db import get_connection as _gc
        conn = _gc()
        if conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO system_logs (username, role, action, details) "
                "VALUES ('pharmacy','STOCK','LOW_STOCK_ALERT',%s)",
                (f"{medicine_name}: qty={qty} min={min_qty}",)
            )
            conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

    try:
        from notifications.founder_alerts import send_founder_alert
        send_founder_alert(
            "LOW_STOCK_ALERT",
            f"Low stock: {medicine_name} (qty={qty}, min={min_qty})"
        )
    except Exception:
        pass
