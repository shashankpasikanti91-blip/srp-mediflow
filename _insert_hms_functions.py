"""Insert new functions into hms_db.py before the HELPERS section"""
import re

with open('hms_db.py', encoding='utf-8') as f:
    content = f.read()

NEW_FUNCTIONS = '''

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
                       TO_CHAR(visit_date,\'YYYY-MM-DD\') AS visit_date,
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
                       TO_CHAR(rx.created_at,\'YYYY-MM-DD\') AS date,
                       rx.doctor_name, rx.diagnosis, rx.chief_complaint,
                       rx.bp, rx.pulse, rx.temperature, rx.spo2, rx.weight,
                       rx.follow_up_days, rx.diet_advice,
                       COALESCE(JSON_AGG(
                           JSON_BUILD_OBJECT(
                               \'medicine\', pm.medicine_name, \'dose\', pm.dose,
                               \'frequency\', pm.frequency, \'duration\', pm.duration,
                               \'route\', pm.route
                           ) ORDER BY pm.sort_order
                       ) FILTER (WHERE pm.id IS NOT NULL), \'[]\'::json) AS medicines
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
                       TO_CHAR(lo.created_at,\'YYYY-MM-DD\') AS ordered_on,
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
                    "TO_CHAR(recorded_at,\'YYYY-MM-DD HH24:MI\') AS recorded_at "
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
                    "TO_CHAR(created_at,\'YYYY-MM-DD\') AS date "
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
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,\'admitted\',%s)
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
                "UPDATE patient_admissions SET status=\'discharged\', "
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
                "VALUES (%s,%s,%s,%s,%s,%s,%s,\'unpaid\') RETURNING id",
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

'''

# Find the HELPERS section and insert before it
# We target the line from repr output
TARGET = '\n# \u2500\u2500\u2500'  # The ─── pattern with unicode
idx = content.rfind('# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nHELPERS')
print(f'idx of HELPERS block: {idx}')

# Find it by searching for "# HELPERS\n"
import re
m = re.search(r'\n# HELPERS\n', content)
if m:
    insert_pos = m.start()
    content = content[:insert_pos] + NEW_FUNCTIONS + content[insert_pos:]
    with open('hms_db.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Inserted {len(NEW_FUNCTIONS)} chars of new functions')
else:
    print('ERROR: Could not find HELPERS section')
    import sys; sys.exit(1)
