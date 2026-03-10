"""Seed dummy records for demo/testing: IPD, Surgery, Lab, Billing, Pharmacy + Notification settings"""
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, database='hospital_ai',
                        user='ats_user', password='ats_password')
cur = conn.cursor()

# ── 1. Notification settings (pre-fill Telegram) ──────────────────────────
try:
    cur.execute("""
        INSERT INTO notification_settings
            (tenant_slug, active_provider, telegram_bot_token, telegram_chat_id,
             notify_on_appointment, notify_on_prescription, notify_on_lab_result,
             notify_on_discharge, daily_summary_enabled)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_slug) DO UPDATE SET
            active_provider       = EXCLUDED.active_provider,
            telegram_bot_token    = EXCLUDED.telegram_bot_token,
            telegram_chat_id      = EXCLUDED.telegram_chat_id,
            notify_on_appointment = EXCLUDED.notify_on_appointment,
            notify_on_prescription= EXCLUDED.notify_on_prescription,
            notify_on_lab_result  = EXCLUDED.notify_on_lab_result,
            notify_on_discharge   = EXCLUDED.notify_on_discharge,
            daily_summary_enabled = EXCLUDED.daily_summary_enabled
    """, ('star_hospital', 'telegram',
          '8535042281:AAG6koMQ17LVJPigw8TNzJq5fAGZNEYObkE', '7144152487',
          True, True, True, True, True))
    print("✅ Notification settings saved (Telegram token + chat ID)")
except Exception as e:
    conn.rollback()
    print(f"⚠️  Notification settings: {e}. Trying without ON CONFLICT...")
    try:
        cur.execute("""
            INSERT INTO notification_settings
                (tenant_slug, active_provider, telegram_bot_token, telegram_chat_id,
                 notify_on_appointment, notify_on_prescription, notify_on_lab_result,
                 notify_on_discharge, daily_summary_enabled)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, ('star_hospital', 'telegram',
              '8535042281:AAG6koMQ17LVJPigw8TNzJq5fAGZNEYObkE', '7144152487',
              True, True, True, True, True))
        print("✅ Notification settings inserted")
    except Exception as e2:
        conn.rollback()
        print(f"❌ Notification settings failed: {e2}")

# ── 2. IPD admission ──────────────────────────────────────────────────────
try:
    cur.execute("""
        INSERT INTO patient_admissions
            (patient_name, patient_phone, ward_name, bed_number,
             admitting_doctor, diagnosis, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, ('Demo Patient Narsimha', '9876543210', 'General Ward', 'B-12',
          'Dr. K. Ramyanadh', 'Typhoid Fever with Dehydration', 'admitted'))
    ipd_id = cur.fetchone()[0]
    print(f"✅ IPD admission id={ipd_id}")
except Exception as e:
    conn.rollback()
    print(f"⚠️  IPD: {e}")

# ── 3. Surgery record ─────────────────────────────────────────────────────
try:
    cur.execute("""
        INSERT INTO surgeries
            (patient_name, patient_phone, surgery_type, anesthesia_type,
             operation_date, estimated_cost, negotiated_cost, operation_notes,
             status, surgeon_name)
        VALUES (%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s) RETURNING id
    """, ('Demo Patient Lakshmi', '9876543211',
          'Appendectomy', 'General Anaesthesia',
          18000, 14500,
          'Pre-op: nil by mouth 6hrs. Post-op: IV antibiotics 5 days.',
          'scheduled', 'Dr. B. Ramachandra Nayak'))
    sur_id = cur.fetchone()[0]
    print(f"✅ Surgery id={sur_id}")
except Exception as e:
    conn.rollback()
    print(f"⚠️  Surgery: {e}")

# ── 4. Pharmacy — medicine + stock ───────────────────────────────────────
try:
    cur.execute("SELECT id FROM medicines WHERE medicine_name='Paracetamol 500mg' LIMIT 1")
    row = cur.fetchone()
    if row:
        med_id = row[0]
        print(f"   Medicine already exists id={med_id}")
    else:
        cur.execute("""INSERT INTO medicines (medicine_name, generic_name, category, unit)
                       VALUES (%s,%s,%s,%s) RETURNING id""",
                   ('Paracetamol 500mg', 'Paracetamol', 'Analgesic', 'Tablet'))
        med_id = cur.fetchone()[0]
        print(f"   Created medicine id={med_id}")

    # Add stock batch
    try:
        cur.execute("""
            INSERT INTO medicine_inventory
                (medicine_id, batch_number, expiry_date, quantity,
                 purchase_price, sell_price, supplier, min_quantity)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (med_id, 'BATCH-2026-P01', '2027-12-31', 500,
              2.50, 5.00, 'Apollo Pharmaceuticals', 50))
        inv_id = cur.fetchone()[0]
        print(f"✅ Pharmacy stock id={inv_id}")
    except Exception as e2:
        conn.rollback()
        print(f"   Stock insert (may be dup): {e2}")

    # Add a second medicine
    cur.execute("SELECT id FROM medicines WHERE medicine_name='Cetirizine 10mg' LIMIT 1")
    if not cur.fetchone():
        cur.execute("""INSERT INTO medicines (medicine_name, generic_name, category, unit)
                       VALUES (%s,%s,%s,%s)""",
                   ('Cetirizine 10mg', 'Cetirizine', 'Antihistamine', 'Tablet'))
    cur.execute("SELECT id FROM medicines WHERE medicine_name='Cetirizine 10mg' LIMIT 1")
    cet_id = cur.fetchone()[0]
    try:
        cur.execute("""
            INSERT INTO medicine_inventory
                (medicine_id, batch_number, expiry_date, quantity,
                 purchase_price, sell_price, supplier, min_quantity)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (cet_id, 'BATCH-2026-C01', '2027-06-30', 200,
              3.00, 8.00, 'Sun Pharma', 30))
        print(f"✅ Added Cetirizine stock")
    except Exception:
        conn.rollback()

except Exception as e:
    conn.rollback()
    print(f"⚠️  Pharmacy: {e}")

# ── 5. Lab order (COMPLETED with result) ─────────────────────────────────
try:
    cur.execute("""
        INSERT INTO lab_orders
            (patient_name, patient_phone, test_type, test_name,
             doctor_username, status, result_text, result_value, unit, reference_range)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, ('Demo Patient Narsimha', '9876543210', 'LAB', 'Complete Blood Count (CBC)',
          'star_hospital_doctor', 'COMPLETED',
          'RBC: 4.5 M/uL  WBC: 8200/uL  Platelets: 210K/uL  Hb: 13.2 g/dL  '
          'PCV: 39%  MCV: 88fL  MCH: 29.2pg  MCHC: 33g/dL — All values within normal range.',
          '13.2', 'g/dL', 'Male: 13.0–17.0 | Female: 12.0–16.0'))
    lab_id = cur.fetchone()[0]
    print(f"✅ Lab order (COMPLETED) id={lab_id}")
except Exception as e:
    conn.rollback()
    print(f"⚠️  Lab order: {e}")

# Also add a PENDING lab order
try:
    cur.execute("""
        INSERT INTO lab_orders
            (patient_name, patient_phone, test_type, test_name,
             doctor_username, status)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, ('Demo Patient Lakshmi', '9876543211', 'LAB', 'Random Blood Sugar (RBS)',
          'star_hospital_doctor', 'PENDING'))
    lab2_id = cur.fetchone()[0]
    print(f"✅ Lab order (PENDING) id={lab2_id}")
except Exception as e:
    conn.rollback()
    print(f"⚠️  Lab order PENDING: {e}")

# ── 6. Billing ────────────────────────────────────────────────────────────
try:
    cur.execute("""
        INSERT INTO invoices
            (patient_name, patient_phone, bill_type,
             consultation_fee, lab_charges, pharmacy_charges,
             imaging_charges, misc_charges,
             total_amount, discount, net_amount, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, ('Demo Patient Narsimha', '9876543210', 'OPD',
          500, 800, 250, 0, 100,
          1650, 100, 1550, 'unpaid'))
    bill_id = cur.fetchone()[0]
    print(f"✅ Bill id={bill_id}")
except Exception as e:
    conn.rollback()
    print(f"⚠️  Billing: {e}")

conn.commit()
conn.close()
print("\n✅ All seed records committed!")
