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

        # ── hospital_expenses: monthly operating cost tracking ────────────────
        """
        CREATE TABLE IF NOT EXISTS hospital_expenses (
            expense_id   SERIAL PRIMARY KEY,
            expense_date DATE         NOT NULL DEFAULT CURRENT_DATE,
            category     VARCHAR(80)  NOT NULL,
            sub_category VARCHAR(120) DEFAULT '',
            description  VARCHAR(300) DEFAULT '',
            amount       NUMERIC(12,2) NOT NULL DEFAULT 0,
            payment_mode VARCHAR(40)  DEFAULT 'Cash',
            vendor       VARCHAR(150) DEFAULT '',
            invoice_ref  VARCHAR(80)  DEFAULT '',
            recurring    BOOLEAN      DEFAULT FALSE,
            created_by   VARCHAR(60)  DEFAULT 'admin',
            created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_exp_date     ON hospital_expenses (expense_date)",
        "CREATE INDEX IF NOT EXISTS idx_exp_category ON hospital_expenses (category)",

        # ── staff_headcount: quick snapshot (one row per role per month) ──────
        """
        CREATE TABLE IF NOT EXISTS staff_headcount (
            hc_id        SERIAL PRIMARY KEY,
            snapshot_month DATE    NOT NULL,
            role         VARCHAR(60) NOT NULL,
            headcount    INTEGER     DEFAULT 0,
            avg_salary   NUMERIC(10,2) DEFAULT 0,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (snapshot_month, role)
        )
        """,

        # ── notification_settings: per-tenant provider config ─────────────────
        """
        CREATE TABLE IF NOT EXISTS notification_settings (
            id            SERIAL PRIMARY KEY,
            tenant_slug   VARCHAR(80)  DEFAULT '',
            setting_key   VARCHAR(100) NOT NULL,
            setting_value TEXT         DEFAULT '',
            is_encrypted  BOOLEAN      DEFAULT FALSE,
            updated_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            updated_by    VARCHAR(80)  DEFAULT '',
            UNIQUE (tenant_slug, setting_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ns_tenant_key ON notification_settings (tenant_slug, setting_key)",

        # ── notification_logs: audit trail of every sent notification ─────────
        """
        CREATE TABLE IF NOT EXISTS notification_logs (
            id               SERIAL PRIMARY KEY,
            tenant_slug      VARCHAR(80)  DEFAULT '',
            channel          VARCHAR(30)  DEFAULT '',
            event_type       VARCHAR(60)  DEFAULT '',
            recipient        VARCHAR(120) DEFAULT '',
            message_preview  TEXT         DEFAULT '',
            status           VARCHAR(20)  DEFAULT 'sent',
            provider_response TEXT        DEFAULT '',
            created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_nl_tenant    ON notification_logs (tenant_slug)",
        "CREATE INDEX IF NOT EXISTS idx_nl_created   ON notification_logs (created_at DESC)",
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
# 3b. FULL DIGITAL PRESCRIPTION (v3 — enhanced with vitals, route, advice)
# ─────────────────────────────────────────────────────────────────────────────

def create_full_prescription(data: dict) -> dict:
    """
    Save a complete structured digital prescription (v3).
    Stores vitals, chief complaint, diagnosis, per-medicine rows with route,
    lab orders linked to the prescription, and follow-up instructions.

    Required in data:
      patient_id, visit_id, doctor_username, doctor_name
    Optional but recommended:
      uhid, patient_name, patient_phone, chief_complaint, symptoms,
      clinical_notes, diagnosis, notes,
      bp, temperature, pulse, spo2, weight,
      medicines_list (list of dicts), lab_tests (list of dicts),
      diet_advice, special_instructions, follow_up_days

    Returns: {prescription_id, patient_name, medicines_count, status, pdf_url}
    """
    # ── Core fields ────────────────────────────────────────────────────────
    patient_id      = data.get("patient_id")
    visit_id        = data.get("visit_id")
    doctor_username = (data.get("doctor_username") or "").strip()
    doctor_name     = (data.get("doctor_name") or "").strip()
    patient_name    = (data.get("patient_name") or "").strip()
    patient_phone   = (data.get("patient_phone") or "").strip()
    uhid            = (data.get("uhid") or "").strip()

    # ── Clinical ───────────────────────────────────────────────────────────
    chief_complaint    = (data.get("chief_complaint") or "").strip()
    symptoms           = (data.get("symptoms") or "").strip()
    clinical_notes     = (data.get("clinical_notes") or "").strip()
    diagnosis          = (data.get("diagnosis") or "").strip()
    notes              = (data.get("notes") or "").strip()

    # ── Vitals ─────────────────────────────────────────────────────────────
    bp          = (data.get("bp") or "").strip()
    temperature = (data.get("temperature") or "").strip()
    pulse       = (data.get("pulse") or "").strip()
    spo2        = (data.get("spo2") or "").strip()
    weight      = (data.get("weight") or "").strip()

    # ── Advice & Follow-up ─────────────────────────────────────────────────
    diet_advice           = (data.get("diet_advice") or "").strip()
    special_instructions  = (data.get("special_instructions") or "").strip()
    follow_up_days_raw    = data.get("follow_up_days")
    follow_up_days: Optional[int] = int(follow_up_days_raw) if follow_up_days_raw else None
    follow_up_date = None
    if follow_up_days:
        from datetime import date, timedelta
        follow_up_date = (date.today() + timedelta(days=follow_up_days)).isoformat()

    medicines_list = data.get("medicines_list") or []
    lab_tests      = data.get("lab_tests") or []

    # Flatten for legacy medicines text column
    medicines_text = "; ".join(
        f"{m.get('medicine_name','')} {m.get('dose','')}"
        f" {m.get('frequency','')} × {m.get('duration','')}"
        for m in medicines_list
    ) if medicines_list else (data.get("medicines") or "")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # ── Main prescription row ──────────────────────────────────────
            cur.execute(
                """
                INSERT INTO prescriptions
                    (patient_name, patient_phone, patient_id, visit_id, uhid,
                     doctor_username, doctor_name, created_by_doctor,
                     diagnosis, medicines, notes,
                     chief_complaint, symptoms, clinical_notes,
                     bp, temperature, pulse, spo2, weight,
                     diet_advice, special_instructions,
                     follow_up_days, follow_up_date)
                VALUES
                    (%s,%s,%s,%s,%s,
                     %s,%s,%s,
                     %s,%s,%s,
                     %s,%s,%s,
                     %s,%s,%s,%s,%s,
                     %s,%s,
                     %s,%s)
                RETURNING id
                """,
                (
                    patient_name, patient_phone, patient_id, visit_id, uhid,
                    doctor_username, doctor_name, doctor_name,
                    diagnosis, medicines_text, notes,
                    chief_complaint, symptoms, clinical_notes,
                    bp, temperature, pulse, spo2, weight,
                    diet_advice, special_instructions,
                    follow_up_days, follow_up_date
                )
            )
            presc_id = cur.fetchone()[0]

            # ── Medicine rows ──────────────────────────────────────────────
            for idx, med in enumerate(medicines_list):
                cur.execute(
                    """
                    INSERT INTO prescription_medicines
                        (prescription_id, medicine_name, dose, frequency,
                         duration, route, notes, sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        presc_id,
                        (med.get("medicine_name") or med.get("name") or "").strip(),
                        (med.get("dose") or med.get("dosage") or "").strip(),
                        (med.get("frequency") or "").strip(),
                        (med.get("duration") or "").strip(),
                        (med.get("route") or "Oral").strip(),
                        (med.get("notes") or "").strip(),
                        idx,
                    )
                )
                # Also insert into legacy prescription_items for backward compat
                cur.execute(
                    """
                    INSERT INTO prescription_items
                        (prescription_id, medicine_name, dosage, frequency,
                         duration, instructions, route)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        presc_id,
                        (med.get("medicine_name") or med.get("name") or "").strip(),
                        (med.get("dose") or med.get("dosage") or "").strip(),
                        (med.get("frequency") or "").strip(),
                        (med.get("duration") or "").strip(),
                        (med.get("notes") or "").strip(),
                        (med.get("route") or "Oral").strip(),
                    )
                )

            # ── Lab orders ─────────────────────────────────────────────────
            for lt in lab_tests:
                cur.execute(
                    """
                    INSERT INTO lab_orders
                        (patient_name, patient_phone, patient_id, visit_id,
                         prescription_id, doctor_username,
                         test_type, test_name, urgency, lab_notes, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING')
                    """,
                    (
                        patient_name, patient_phone, patient_id, visit_id,
                        presc_id, doctor_username,
                        (lt.get("test_type") or "LAB").strip(),
                        (lt.get("test_name") or lt.get("name") or "").strip(),
                        (lt.get("urgency") or "routine").strip(),
                        (lt.get("notes") or lt.get("lab_notes") or "").strip(),
                    )
                )

    return {
        "prescription_id": presc_id,
        "patient_name":    patient_name,
        "medicines_count": len(medicines_list),
        "lab_tests_count": len(lab_tests),
        "follow_up_date":  follow_up_date,
        "status":          "saved",
    }


def get_full_prescription(prescription_id: int) -> Optional[dict]:
    """
    Return complete prescription with medicines list and lab orders.
    Used by PDF generation and frontend preview.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Main prescription
            cur.execute(
                "SELECT * FROM prescriptions WHERE id = %s",
                (prescription_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            presc = _serialise(dict(row))

            # Medicines (from prescription_medicines, fall back to prescription_items)
            cur.execute(
                """
                SELECT medicine_name, dose, frequency, duration, route, notes, sort_order
                FROM prescription_medicines
                WHERE prescription_id = %s
                ORDER BY sort_order, id
                """,
                (prescription_id,)
            )
            meds = cur.fetchall()
            if not meds:
                # fallback to legacy table
                cur.execute(
                    """
                    SELECT medicine_name,
                           dosage AS dose,
                           frequency,
                           duration,
                           COALESCE(route, 'Oral') AS route,
                           COALESCE(instructions, '') AS notes
                    FROM prescription_items
                    WHERE prescription_id = %s
                    ORDER BY item_id
                    """,
                    (prescription_id,)
                )
                meds = cur.fetchall()
            presc["medicines_list"] = [dict(m) for m in meds]

            # Lab orders
            cur.execute(
                """
                SELECT id AS order_id, test_type, test_name, urgency, lab_notes, status
                FROM lab_orders
                WHERE prescription_id = %s
                ORDER BY id
                """,
                (prescription_id,)
            )
            presc["lab_orders"] = [dict(r) for r in cur.fetchall()]

            # Patient demographics (if patient_id linked)
            if presc.get("patient_id"):
                cur.execute(
                    "SELECT full_name, dob, gender, phone, uhid FROM patients WHERE id=%s",
                    (presc["patient_id"],)
                )
                pat = cur.fetchone()
                if pat:
                    presc["patient_gender"]  = pat["gender"]
                    presc["patient_dob"]     = str(pat["dob"]) if pat["dob"] else ""
                    if not presc.get("patient_name"):
                        presc["patient_name"] = pat["full_name"]
                    if not presc.get("uhid"):
                        presc["uhid"] = pat["uhid"] or ""

    return presc


def get_prescriptions_by_visit(visit_id: int) -> list:
    """Return all prescriptions for a visit."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id AS prescription_id, doctor_name, diagnosis,
                       chief_complaint, created_at, follow_up_date,
                       generated_pdf_path
                FROM prescriptions
                WHERE visit_id = %s
                ORDER BY id DESC
                """,
                (visit_id,)
            )
            return [_serialise(dict(r)) for r in cur.fetchall()]


# ── Notification Settings ──────────────────────────────────────────────────

def get_notification_settings(tenant_slug: str = "") -> dict:
    """Load all notification settings for tenant as a flat dict."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT setting_key, setting_value
                    FROM notification_settings
                    WHERE tenant_slug = %s OR tenant_slug = ''
                    ORDER BY tenant_slug DESC
                    """,
                    (tenant_slug,)
                )
                rows = cur.fetchall()
                settings: dict = {}
                for key, val in rows:
                    settings[key] = val
                return settings
    except Exception as exc:
        print(f"⚠️  get_notification_settings error: {exc}")
        return {}


def save_notification_settings(tenant_slug: str, settings: dict,
                                 updated_by: str = "") -> bool:
    """Upsert notification setting key/value pairs for tenant."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for key, val in settings.items():
                    cur.execute(
                        """
                        INSERT INTO notification_settings
                            (tenant_slug, setting_key, setting_value, updated_at, updated_by)
                        VALUES (%s, %s, %s, NOW(), %s)
                        ON CONFLICT (tenant_slug, setting_key)
                        DO UPDATE SET
                            setting_value = EXCLUDED.setting_value,
                            updated_at    = NOW(),
                            updated_by    = EXCLUDED.updated_by
                        """,
                        (tenant_slug, key, str(val), updated_by)
                    )
        return True
    except Exception as exc:
        print(f"⚠️  save_notification_settings error: {exc}")
        return False


def get_dashboard_enhanced_stats(tenant_slug: str = "") -> dict:
    """
    Return enhanced dashboard stats:
    today's OPD, IPD, collections, pending bills,
    low stock count, lab pending, follow-up due today,
    notifications sent today.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                stats: dict = {}

                # Today's OPD visits
                cur.execute(
                    "SELECT COUNT(*) FROM patient_visits "
                    "WHERE visit_type='OP' AND visit_date::date = CURRENT_DATE"
                )
                stats["today_opd"] = cur.fetchone()[0]

                # Today's IPD admissions
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM ipd_admissions "
                        "WHERE admission_date::date = CURRENT_DATE"
                    )
                    stats["today_ipd"] = cur.fetchone()[0]
                except Exception:
                    stats["today_ipd"] = 0

                # Today's collections (billing)
                try:
                    cur.execute(
                        "SELECT COALESCE(SUM(total_amount),0) FROM invoices "
                        "WHERE created_at::date = CURRENT_DATE"
                    )
                    stats["today_collections"] = float(cur.fetchone()[0])
                except Exception:
                    stats["today_collections"] = 0.0

                # Pending bills
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM invoices "
                        "WHERE status IN ('pending','partial')"
                    )
                    stats["pending_bills"] = cur.fetchone()[0]
                except Exception:
                    stats["pending_bills"] = 0

                # Low stock medicines
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM pharmacy_stock "
                        "WHERE quantity <= min_quantity"
                    )
                    stats["low_stock_medicines"] = cur.fetchone()[0]
                except Exception:
                    stats["low_stock_medicines"] = 0

                # Lab tests pending
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM lab_orders WHERE status='PENDING'"
                    )
                    stats["lab_pending"] = cur.fetchone()[0]
                except Exception:
                    stats["lab_pending"] = 0

                # Follow-ups due today
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM prescriptions "
                        "WHERE follow_up_date = CURRENT_DATE"
                    )
                    stats["followup_today"] = cur.fetchone()[0]
                except Exception:
                    stats["followup_today"] = 0

                # Notifications sent today
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM notification_logs "
                        "WHERE created_at::date = CURRENT_DATE AND status='sent'"
                    )
                    stats["notifications_today"] = cur.fetchone()[0]
                except Exception:
                    stats["notifications_today"] = 0

                return stats
    except Exception as exc:
        print(f"⚠️  get_dashboard_enhanced_stats error: {exc}")
        return {}


def get_recent_activity(limit: int = 20) -> list:
    """
    Return recent activity feed across patients, prescriptions, lab, discharges.
    """
    events = []
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # New patient registrations
                cur.execute(
                    """
                    SELECT 'patient_registered' AS event_type,
                           full_name AS title,
                           'New patient registered' AS subtitle,
                           created_at
                    FROM patients
                    ORDER BY created_at DESC LIMIT 5
                    """
                )
                events += [_serialise(dict(r)) for r in cur.fetchall()]

                # Prescriptions created
                cur.execute(
                    """
                    SELECT 'prescription_created' AS event_type,
                           patient_name AS title,
                           CONCAT('Rx by Dr. ', doctor_name) AS subtitle,
                           created_at
                    FROM prescriptions
                    ORDER BY created_at DESC LIMIT 5
                    """
                )
                events += [_serialise(dict(r)) for r in cur.fetchall()]

                # Lab orders completed
                try:
                    cur.execute(
                        """
                        SELECT 'lab_result_uploaded' AS event_type,
                               patient_name AS title,
                               CONCAT('Lab: ', test_name) AS subtitle,
                               updated_at AS created_at
                        FROM lab_orders
                        WHERE status = 'COMPLETED'
                        ORDER BY updated_at DESC LIMIT 5
                        """
                    )
                    events += [_serialise(dict(r)) for r in cur.fetchall()]
                except Exception:
                    pass

                # IPD discharges
                try:
                    cur.execute(
                        """
                        SELECT 'discharge_completed' AS event_type,
                               patient_name AS title,
                               'Patient discharged' AS subtitle,
                               discharge_date AS created_at
                        FROM ipd_admissions
                        WHERE status = 'discharged'
                        ORDER BY discharge_date DESC LIMIT 5
                        """
                    )
                    events += [_serialise(dict(r)) for r in cur.fetchall()]
                except Exception:
                    pass

    except Exception as exc:
        print(f"⚠️  get_recent_activity error: {exc}")

    # Sort by created_at desc
    events.sort(key=lambda x: str(x.get("created_at", "") or ""), reverse=True)
    return events[:limit]


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
# EXPENSE MANAGEMENT MODULE
# ─────────────────────────────────────────────────────────────────────────────

# Standard expense categories for a hospital
EXPENSE_CATEGORIES = [
    "Rent & Premises",
    "Electricity & Power",
    "Water & Utilities",
    "Internet & Communication",
    "Medical Equipment",
    "Medicines & Consumables",
    "Staff Salaries",
    "Contract Staff",
    "Security",
    "Housekeeping",
    "Marketing & Advertising",
    "Insurance",
    "Maintenance & Repairs",
    "Administrative",
    "Legal & Compliance",
    "Lab Supplies",
    "Ambulance & Transport",
    "Other",
]


def add_expense(data: dict) -> dict:
    """Insert a new expense record. Returns {expense_id, status}."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hospital_expenses
                    (expense_date, category, sub_category, description,
                     amount, payment_mode, vendor, invoice_ref, recurring, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING expense_id
                """,
                (
                    data.get("expense_date") or date.today().isoformat(),
                    data.get("category", "Other"),
                    data.get("sub_category", ""),
                    data.get("description", ""),
                    float(data.get("amount", 0)),
                    data.get("payment_mode", "Cash"),
                    data.get("vendor", ""),
                    data.get("invoice_ref", ""),
                    bool(data.get("recurring", False)),
                    data.get("created_by", "admin"),
                ),
            )
            eid = cur.fetchone()[0]
            conn.commit()
    return {"expense_id": eid, "status": "saved"}


def get_expenses(period: str = "monthly", category: str = "") -> dict:
    """Return expense list + summary for a period."""
    today = date.today()
    if period == "daily":
        start, end = today, today
    elif period == "weekly":
        start = today - timedelta(days=6); end = today
    elif period == "yearly":
        start = today.replace(month=1, day=1); end = today
    else:  # monthly
        start = today.replace(day=1); end = today

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            params: list = [start, end]
            cat_filter = ""
            if category:
                cat_filter = " AND category = %s"
                params.append(category)

            cur.execute(
                f"""
                SELECT expense_id, expense_date, category, sub_category,
                       description, amount, payment_mode, vendor, invoice_ref, recurring
                FROM hospital_expenses
                WHERE expense_date BETWEEN %s AND %s{cat_filter}
                ORDER BY expense_date DESC, expense_id DESC
                """,
                params,
            )
            rows = [_float_row(dict(r)) for r in cur.fetchall()]

            # Summary by category
            cur.execute(
                f"""
                SELECT category,
                       SUM(amount) AS total,
                       COUNT(*)    AS count
                FROM hospital_expenses
                WHERE expense_date BETWEEN %s AND %s{cat_filter}
                GROUP BY category
                ORDER BY total DESC
                """,
                params,
            )
            by_cat = [_float_row(dict(r)) for r in cur.fetchall()]

            total = sum(r["total"] for r in by_cat)

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "expenses": rows,
        "by_category": by_cat,
        "total_expenses": round(total, 2),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_analytics_pl(period: str = "monthly") -> dict:
    """
    Full Profit & Loss analytics for management dashboard.
    Returns revenue, expenses, gross profit, net margin, MoM/YoY growth,
    department breakdown, staff cost ratio, and 12-month trend.
    """
    today = date.today()
    if period in ("daily", "today"):
        start = today;                    end = today
        prev_start = today - timedelta(days=1);  prev_end = today - timedelta(days=1)
        label = today.isoformat()
    elif period == "weekly":
        start = today - timedelta(days=6); end = today
        prev_start = today - timedelta(days=13); prev_end = today - timedelta(days=7)
        label = f"{start.isoformat()} to {end.isoformat()}"
    elif period == "yearly":
        start = today.replace(month=1, day=1); end = today
        prev_start = start.replace(year=start.year - 1)
        prev_end   = end.replace(year=end.year - 1)
        label = str(today.year)
    else:  # monthly
        start = today.replace(day=1); end = today
        if today.month == 1:
            prev_start = date(today.year - 1, 12, 1)
            prev_end   = date(today.year - 1, 12, 31)
        else:
            prev_start = date(today.year, today.month - 1, 1)
            import calendar as _cal
            prev_end = date(today.year, today.month - 1,
                            _cal.monthrange(today.year, today.month - 1)[1])
        label = today.strftime("%B %Y")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            def _rev(s, e):
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(net_amount),0) AS total_revenue,
                        COALESCE(SUM(CASE WHEN status='paid'   THEN net_amount ELSE 0 END),0) AS collected,
                        COALESCE(SUM(CASE WHEN status='unpaid' THEN net_amount ELSE 0 END),0) AS outstanding,
                        COUNT(*) AS invoices,
                        COALESCE(SUM(CASE WHEN bill_type='OPD'      THEN net_amount ELSE 0 END),0) AS opd,
                        COALESCE(SUM(CASE WHEN bill_type='IPD'      THEN net_amount ELSE 0 END),0) AS ipd,
                        COALESCE(SUM(CASE WHEN bill_type='PHARMACY' THEN net_amount ELSE 0 END),0) AS pharmacy,
                        COALESCE(SUM(CASE WHEN bill_type='LAB'      THEN net_amount ELSE 0 END),0) AS lab,
                        COALESCE(SUM(CASE WHEN bill_type='SURGERY'  THEN net_amount ELSE 0 END),0) AS surgery,
                        COALESCE(AVG(net_amount), 0) AS avg_bill
                    FROM billing WHERE DATE(created_at) BETWEEN %s AND %s
                    """, (s, e))
                return _float_row(dict(cur.fetchone()))

            def _exp(s, e):
                cur.execute(
                    """
                    SELECT COALESCE(SUM(amount),0) AS total,
                           COALESCE(SUM(CASE WHEN category='Staff Salaries'     THEN amount ELSE 0 END),0) AS salaries,
                           COALESCE(SUM(CASE WHEN category='Rent & Premises'    THEN amount ELSE 0 END),0) AS rent,
                           COALESCE(SUM(CASE WHEN category='Electricity & Power' THEN amount ELSE 0 END),0) AS electricity,
                           COALESCE(SUM(CASE WHEN category='Medical Equipment'  THEN amount ELSE 0 END),0) AS equipment,
                           COALESCE(SUM(CASE WHEN category='Medicines & Consumables' THEN amount ELSE 0 END),0) AS medicines,
                           COALESCE(SUM(CASE WHEN category='Marketing & Advertising' THEN amount ELSE 0 END),0) AS marketing,
                           COALESCE(SUM(CASE WHEN category='Maintenance & Repairs'   THEN amount ELSE 0 END),0) AS maintenance,
                           COALESCE(SUM(CASE WHEN category='Internet & Communication' THEN amount ELSE 0 END),0) AS internet,
                           COALESCE(SUM(CASE WHEN category='Water & Utilities'  THEN amount ELSE 0 END),0) AS water,
                           COALESCE(SUM(CASE WHEN category='Insurance'          THEN amount ELSE 0 END),0) AS insurance,
                           COALESCE(SUM(CASE WHEN category='Lab Supplies'       THEN amount ELSE 0 END),0) AS lab_supplies
                    FROM hospital_expenses WHERE expense_date BETWEEN %s AND %s
                    """, (s, e))
                return _float_row(dict(cur.fetchone()))

            # Current + previous period
            rev_cur  = _rev(start, end)
            rev_prev = _rev(prev_start, prev_end)
            exp_cur  = _exp(start, end)
            exp_prev = _exp(prev_start, prev_end)

            # 12-month rolling trend
            cur.execute(
                """
                SELECT TO_CHAR(DATE_TRUNC('month', created_at), 'Mon YYYY') AS month,
                       DATE_TRUNC('month', created_at) AS month_dt,
                       COALESCE(SUM(net_amount),0) AS revenue
                FROM billing
                WHERE created_at >= (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months')
                GROUP BY month_dt, month
                ORDER BY month_dt
                """)
            rev_trend = [_float_row(dict(r)) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT TO_CHAR(DATE_TRUNC('month', expense_date), 'Mon YYYY') AS month,
                       DATE_TRUNC('month', expense_date) AS month_dt,
                       COALESCE(SUM(amount),0) AS expenses
                FROM hospital_expenses
                WHERE expense_date >= (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months')
                GROUP BY month_dt, month
                ORDER BY month_dt
                """)
            exp_trend = [_float_row(dict(r)) for r in cur.fetchall()]

            # Staff headcount + total salary
            cur.execute("SELECT COUNT(*) AS cnt FROM doctors")
            doc_count = cur.fetchone()["cnt"]
            # Use staff_users (tenant table) — 'users' only exists in platform DB
            try:
                cur.execute("SELECT COUNT(*) AS cnt FROM staff_users WHERE is_active = TRUE")
                staff_count = cur.fetchone()["cnt"]
            except Exception:
                conn.rollback()
                staff_count = 0

            # Patient count this period
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM patients WHERE DATE(created_at) BETWEEN %s AND %s",
                (start, end))
            new_patients = cur.fetchone()["cnt"]

            # Appointments this period
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM appointments WHERE DATE(created_at) BETWEEN %s AND %s",
                (start, end))
            appointments = cur.fetchone()["cnt"]

            # Expense by category for chart
            cur.execute(
                """
                SELECT category, COALESCE(SUM(amount),0) AS total
                FROM hospital_expenses
                WHERE expense_date BETWEEN %s AND %s
                GROUP BY category ORDER BY total DESC
                """, (start, end))
            exp_by_cat = [_float_row(dict(r)) for r in cur.fetchall()]

    # ── Computed KPIs ───────────────────────────────────────────────────────
    total_rev  = rev_cur["total_revenue"]
    total_exp  = exp_cur["total"]
    gross_profit = total_rev - total_exp
    net_margin   = round(gross_profit / total_rev * 100, 1) if total_rev else 0

    prev_rev  = rev_prev["total_revenue"]
    prev_exp  = exp_prev["total"]
    rev_growth_pct = round((total_rev - prev_rev) / prev_rev * 100, 1) if prev_rev else 0
    exp_growth_pct = round((total_exp - prev_exp) / prev_exp * 100, 1) if prev_exp else 0
    profit_growth  = round(((gross_profit - (prev_rev - prev_exp)) / abs(prev_rev - prev_exp) * 100), 1) \
                     if (prev_rev - prev_exp) != 0 else 0

    salary_ratio   = round(exp_cur["salaries"] / total_rev * 100, 1) if total_rev else 0
    rev_per_patient = round(total_rev / new_patients, 2) if new_patients else 0

    # Merge trend lists into month-keyed dict
    trend_map: dict = {}
    for r in rev_trend:
        trend_map[r["month"]] = {"month": r["month"], "revenue": r["revenue"], "expenses": 0}
    for r in exp_trend:
        if r["month"] in trend_map:
            trend_map[r["month"]]["expenses"] = r["expenses"]
        else:
            trend_map[r["month"]] = {"month": r["month"], "revenue": 0, "expenses": r["expenses"]}
    trend_list = sorted(trend_map.values(), key=lambda x: x["month"])
    for t in trend_list:
        t["profit"] = round(t["revenue"] - t["expenses"], 2)

    # Forecasting: simple linear regression on last 3 months profit
    profits = [t["profit"] for t in trend_list[-3:]] if len(trend_list) >= 3 else []
    if len(profits) == 3:
        slope   = ((profits[2] - profits[0]) / 2)
        forecast_next = round(profits[-1] + slope, 2)
    else:
        forecast_next = gross_profit

    return {
        "period":        period,
        "label":         label,
        "start_date":    start.isoformat(),
        "end_date":      end.isoformat(),

        # Revenue
        "revenue": {
            "total":       round(total_rev, 2),
            "collected":   rev_cur["collected"],
            "outstanding": rev_cur["outstanding"],
            "invoices":    int(rev_cur["invoices"]),
            "avg_bill":    rev_cur["avg_bill"],
            "by_dept": {
                "OPD":      rev_cur["opd"],
                "IPD":      rev_cur["ipd"],
                "Pharmacy": rev_cur["pharmacy"],
                "Lab":      rev_cur["lab"],
                "Surgery":  rev_cur["surgery"],
            },
            "growth_pct": rev_growth_pct,
            "prev_total":  round(prev_rev, 2),
        },

        # Expenses
        "expenses": {
            "total":       round(total_exp, 2),
            "by_category": exp_by_cat,
            "salaries":    exp_cur["salaries"],
            "rent":        exp_cur["rent"],
            "electricity": exp_cur["electricity"],
            "equipment":   exp_cur["equipment"],
            "medicines":   exp_cur["medicines"],
            "marketing":   exp_cur["marketing"],
            "maintenance": exp_cur["maintenance"],
            "internet":    exp_cur["internet"],
            "water":       exp_cur["water"],
            "insurance":   exp_cur["insurance"],
            "lab_supplies": exp_cur["lab_supplies"],
            "growth_pct":  exp_growth_pct,
            "prev_total":  round(prev_exp, 2),
        },

        # Profit
        "profit": {
            "gross":        round(gross_profit, 2),
            "net_margin":   net_margin,
            "growth_pct":   profit_growth,
            "prev_gross":   round(prev_rev - prev_exp, 2),
            "forecast_next": forecast_next,
            "salary_ratio": salary_ratio,
        },

        # Operational
        "operational": {
            "staff_count":      staff_count,
            "doctor_count":     doc_count,
            "new_patients":     new_patients,
            "appointments":     appointments,
            "rev_per_patient":  rev_per_patient,
        },

        # Trend (12 months)
        "trend": trend_list,

        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

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

# ─────────────────────────────────────────────────────────────────────────────
# VISIT MANAGEMENT (patient_visits table)
# ─────────────────────────────────────────────────────────────────────────────

def create_visit(data: dict) -> dict:
    """
    Create a new OPD/IPD/ER visit for a patient.
    data: patient_id, visit_type, doctor_username, doctor_assigned,
          department, chief_complaint, notes
    """
    patient_id      = data.get("patient_id")
    visit_type      = (data.get("visit_type") or "OP").upper()[:2]
    doctor_username = (data.get("doctor_username") or "").strip()
    doctor_assigned = (data.get("doctor_assigned") or data.get("doctor_name") or "").strip()
    department      = (data.get("department") or "General").strip()
    chief_complaint = (data.get("chief_complaint") or "").strip()
    notes           = (data.get("notes") or "").strip()

    if not patient_id:
        return {"error": "patient_id required"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            from datetime import date as _date
            today_str = _date.today().strftime("%Y%m%d")
            cur.execute("SELECT COUNT(*) FROM op_tickets WHERE DATE(issued_at) = CURRENT_DATE")
            seq = (cur.fetchone()[0] or 0) + 1
            ticket_no = f"OP{today_str}{seq:03d}"

            cur.execute(
                """
                INSERT INTO patient_visits
                    (patient_id, visit_type, doctor_username, doctor_assigned,
                     department, chief_complaint, notes, status, op_ticket_no)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s)
                RETURNING visit_id, visit_date
                """,
                (patient_id, visit_type, doctor_username, doctor_assigned,
                 department, chief_complaint, notes, ticket_no)
            )
            row = cur.fetchone()
            visit_id   = row[0]
            visit_date = row[1]

            try:
                cur.execute(
                    "INSERT INTO op_tickets (ticket_no, patient_id, visit_id, "
                    "doctor_name, department) VALUES (%s,%s,%s,%s,%s)",
                    (ticket_no, patient_id, visit_id, doctor_assigned, department)
                )
            except Exception:
                pass

    return {
        "visit_id":   visit_id,
        "patient_id": patient_id,
        "ticket_no":  ticket_no,
        "visit_type": visit_type,
        "visit_date": visit_date.isoformat() if hasattr(visit_date, "isoformat") else str(visit_date),
        "doctor":     doctor_assigned,
        "status":     "active",
    }


def list_visits(patient_id: Optional[int] = None,
                doctor_username: Optional[str] = None,
                date_from: Optional[str] = None,
                limit: int = 50) -> list:
    """List visits filtered by patient/doctor/date, newest first."""
    conditions: list = []
    params: list = []

    if patient_id:
        conditions.append("v.patient_id = %s"); params.append(patient_id)
    if doctor_username:
        conditions.append("v.doctor_username = %s"); params.append(doctor_username)
    if date_from:
        conditions.append("v.visit_date >= %s"); params.append(date_from)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT v.visit_id, v.patient_id, p.full_name AS patient_name,
                       p.uhid, p.phone AS patient_phone,
                       v.visit_type, v.doctor_assigned, v.department,
                       v.visit_date, v.chief_complaint, v.diagnosis,
                       v.status, v.op_ticket_no
                FROM patient_visits v
                LEFT JOIN patients p ON p.id = v.patient_id
                {where}
                ORDER BY v.visit_date DESC LIMIT %s
                """,
                params
            )
            return [_serialise(dict(r)) for r in cur.fetchall()]


def get_visit_with_prescription(visit_id: int) -> dict:
    """Return visit + patient demographics + latest prescription with medicines."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT v.*, p.full_name AS patient_name, p.phone AS patient_phone,
                       p.uhid, p.gender, p.dob, p.blood_group, p.allergies
                FROM patient_visits v
                JOIN patients p ON p.id = v.patient_id
                WHERE v.visit_id = %s
                """,
                (visit_id,)
            )
            row = cur.fetchone()
            if not row:
                return {"error": "Visit not found"}
            result = _serialise(dict(row))

            cur.execute(
                """
                SELECT rx.id AS prescription_id, rx.diagnosis, rx.chief_complaint,
                       rx.bp, rx.pulse, rx.temperature, rx.spo2, rx.weight,
                       rx.diet_advice, rx.follow_up_days, rx.created_at,
                       COALESCE(JSON_AGG(
                           JSON_BUILD_OBJECT(
                               'medicine_name', pm.medicine_name,
                               'dose', pm.dose, 'frequency', pm.frequency,
                               'duration', pm.duration, 'route', pm.route
                           ) ORDER BY pm.sort_order
                       ) FILTER (WHERE pm.id IS NOT NULL), '[]'::json) AS medicines_list
                FROM prescriptions rx
                LEFT JOIN prescription_medicines pm ON pm.prescription_id = rx.id
                WHERE rx.visit_id = %s
                GROUP BY rx.id
                ORDER BY rx.created_at DESC LIMIT 1
                """,
                (visit_id,)
            )
            rx_row = cur.fetchone()
            result["prescription"] = _serialise(dict(rx_row)) if rx_row else None
            return result


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT TIMELINE  –  complete history on one screen (v6.1)
# ─────────────────────────────────────────────────────────────────────────────

def get_patient_timeline(patient_id: int) -> dict:
    """
    Return complete patient history on one screen:
    demographics | visits | prescriptions+medicines | lab orders | vitals | bills
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
            patient = cur.fetchone()
            if not patient:
                return {"error": "Patient not found"}
            patient = _serialise(dict(patient))

            # Visits
            cur.execute(
                """
                SELECT visit_id, visit_type, doctor_assigned, department,
                       TO_CHAR(visit_date,'YYYY-MM-DD') AS visit_date,
                       chief_complaint, diagnosis, notes, status, op_ticket_no
                FROM patient_visits WHERE patient_id = %s
                ORDER BY visit_date DESC LIMIT 30
                """,
                (patient_id,)
            )
            visits = [dict(r) for r in cur.fetchall()]

            # Prescriptions (by patient_id or phone)
            cur.execute(
                """
                SELECT rx.id AS prescription_id,
                       TO_CHAR(rx.created_at,'YYYY-MM-DD') AS date,
                       rx.doctor_name, rx.diagnosis, rx.chief_complaint,
                       rx.bp, rx.pulse, rx.temperature, rx.spo2, rx.weight,
                       rx.follow_up_days, rx.diet_advice,
                       COALESCE(JSON_AGG(
                           JSON_BUILD_OBJECT(
                               'medicine', pm.medicine_name, 'dose', pm.dose,
                               'frequency', pm.frequency, 'duration', pm.duration,
                               'route', pm.route
                           ) ORDER BY pm.sort_order
                       ) FILTER (WHERE pm.id IS NOT NULL), '[]'::json) AS medicines
                FROM prescriptions rx
                LEFT JOIN prescription_medicines pm ON pm.prescription_id = rx.id
                WHERE rx.patient_id = %s
                   OR rx.patient_phone = (SELECT phone FROM patients WHERE id = %s)
                GROUP BY rx.id
                ORDER BY rx.created_at DESC LIMIT 50
                """,
                (patient_id, patient_id)
            )
            prescriptions = [_serialise(dict(r)) for r in cur.fetchall()]
            # Deduplicate
            seen: set = set()
            prescs_deduped = []
            for p in prescriptions:
                rid = p.get("prescription_id")
                if rid not in seen:
                    seen.add(rid); prescs_deduped.append(p)

            # Lab orders
            cur.execute(
                """
                SELECT lo.id AS order_id,
                       TO_CHAR(lo.created_at,'YYYY-MM-DD') AS ordered_on,
                       lo.test_type, lo.test_name, lo.urgency, lo.status, lo.result_text
                FROM lab_orders lo
                WHERE lo.patient_id = %s
                   OR lo.patient_phone = (SELECT phone FROM patients WHERE id = %s)
                ORDER BY lo.created_at DESC LIMIT 50
                """,
                (patient_id, patient_id)
            )
            lab_orders = [_serialise(dict(r)) for r in cur.fetchall()]

            # Vitals
            vitals: list = []
            if patient.get("phone"):
                cur.execute(
                    "SELECT bp, pulse, temperature, spo2, weight, "
                    "TO_CHAR(recorded_at,'YYYY-MM-DD HH24:MI') AS recorded_at "
                    "FROM vitals WHERE patient_phone = %s "
                    "ORDER BY recorded_at DESC LIMIT 20",
                    (patient["phone"],)
                )
                vitals = [dict(r) for r in cur.fetchall()]

            # Bills
            bills: list = []
            if patient.get("phone"):
                cur.execute(
                    "SELECT id AS bill_id, bill_type, net_amount, status, "
                    "TO_CHAR(created_at,'YYYY-MM-DD') AS date "
                    "FROM billing WHERE patient_phone = %s "
                    "ORDER BY created_at DESC LIMIT 20",
                    (patient["phone"],)
                )
                bills = [_serialise(dict(r)) for r in cur.fetchall()]

    return {
        "patient":       patient,
        "visits":        visits,
        "prescriptions": prescs_deduped,
        "lab_orders":    lab_orders,
        "vitals":        vitals,
        "bills":         bills,
        "summary": {
            "total_visits":        len(visits),
            "total_prescriptions": len(prescs_deduped),
            "total_lab_orders":    len(lab_orders),
            "follow_up_pending":   sum(1 for v in visits if v.get("status") == "follow-up"),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALIASES FOR ROUTE COMPATIBILITY
# ─────────────────────────────────────────────────────────────────────────────

def search_patients(query: str, field: str = "auto") -> list:
    """Alias for search_patients_comprehensive."""
    return search_patients_comprehensive(query, field)


def create_lab_order(data: dict) -> dict:
    """Alias for order_lab_test."""
    return order_lab_test(data)


def update_lab_result(data: dict) -> dict:
    """Alias for record_lab_result."""
    return record_lab_result(data)


def admit_patient(data: dict) -> dict:
    """Admit patient to IPD (patient_admissions table)."""
    patient_name   = (data.get("patient_name") or "").strip()
    patient_phone  = (data.get("patient_phone") or "").strip()
    age            = str(data.get("age") or "")
    gender         = (data.get("gender") or "Unknown")
    ward_name      = (data.get("ward_name") or "General Male")
    bed_number     = (data.get("bed_number") or "")
    doctor         = (data.get("admitting_doctor") or data.get("doctor_name") or "")
    department     = (data.get("department") or "General")
    diagnosis      = (data.get("diagnosis") or "")
    notes          = (data.get("admission_notes") or data.get("notes") or "")
    created_by     = (data.get("created_by") or "reception")
    patient_id     = data.get("patient_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO patient_admissions
                    (patient_name, patient_phone, age, gender, ward_name,
                     bed_number, admitting_doctor, department, diagnosis,
                     admission_notes, status, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'admitted',%s)
                RETURNING id
                """,
                (patient_name, patient_phone, age, gender, ward_name,
                 bed_number, doctor, department, diagnosis, notes, created_by)
            )
            admission_id = cur.fetchone()[0]
            if patient_id:
                try:
                    cur.execute(
                        "UPDATE patient_admissions SET patient_id=%s WHERE id=%s",
                        (patient_id, admission_id)
                    )
                except Exception:
                    pass
    return {"admission_id": admission_id, "patient_name": patient_name,
            "ward_name": ward_name, "status": "admitted"}


def discharge_patient(data: dict) -> dict:
    """Discharge IPD patient and create discharge summary."""
    admission_id    = data.get("admission_id")
    if not admission_id:
        return {"error": "admission_id required"}
    final_diag      = (data.get("final_diagnosis") or "").strip()
    treatment       = (data.get("treatment_given") or "").strip()
    dc_meds         = (data.get("discharge_medicines") or "").strip()
    follow_up_date  = data.get("follow_up_date") or None
    diet_advice     = (data.get("diet_advice") or "").strip()
    follow_up_notes = (data.get("follow_up_notes") or "").strip()
    doctor_name     = (data.get("doctor_name") or "").strip()
    doctor_username = (data.get("doctor_username") or "").strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE patient_admissions SET status='discharged', "
                "discharge_date=CURRENT_TIMESTAMP WHERE id=%s RETURNING patient_name",
                (admission_id,)
            )
            row = cur.fetchone()
            if not row:
                return {"error": "Admission not found"}
            patient_name = row[0]
            cur.execute(
                """
                INSERT INTO discharge_summaries
                    (admission_id, patient_name, final_diagnosis, treatment_given,
                     discharge_medicines, follow_up_date, follow_up_notes,
                     diet_advice, doctor_name, doctor_username)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (admission_id, patient_name, final_diag, treatment,
                 dc_meds, follow_up_date, follow_up_notes,
                 diet_advice, doctor_name, doctor_username)
            )
            summary_id = cur.fetchone()[0]
    return {"discharge_summary_id": summary_id, "admission_id": admission_id,
            "patient_name": patient_name, "status": "discharged"}


def create_bill(data: dict) -> dict:
    """Create a billing record. Wraps create_invoice or inserts directly."""
    try:
        return create_invoice(data)
    except Exception:
        pass
    patient_name  = (data.get("patient_name") or "").strip()
    patient_phone = (data.get("patient_phone") or "").strip()
    bill_type     = (data.get("bill_type") or "OPD").upper()
    notes         = (data.get("notes") or "")
    created_by    = (data.get("created_by") or "system")
    total         = float(data.get("total_amount") or 0)
    net           = float(data.get("net_amount") or total)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO billing (patient_name,patient_phone,bill_type,"
                "total_amount,net_amount,notes,created_by,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'unpaid') RETURNING id",
                (patient_name, patient_phone, bill_type, total, net, notes, created_by)
            )
            bill_id = cur.fetchone()[0]
    return {"bill_id": bill_id, "patient_name": patient_name,
            "net_amount": net, "status": "unpaid"}


def get_bill_detail(bill_id: int) -> dict:
    """Get full bill with items and payments."""
    try:
        return get_invoice(bill_id)
    except Exception:
        pass
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM billing WHERE id = %s", (bill_id,))
            bill = cur.fetchone()
            if not bill:
                return {"error": "Bill not found"}
            bill = _serialise(dict(bill))
            cur.execute("SELECT * FROM bill_items WHERE bill_id=%s ORDER BY id", (bill_id,))
            bill["items"] = [_serialise(dict(r)) for r in cur.fetchall()]
            cur.execute("SELECT * FROM payments WHERE bill_id=%s ORDER BY paid_at", (bill_id,))
            bill["payments"] = [_serialise(dict(r)) for r in cur.fetchall()]
            return bill


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
