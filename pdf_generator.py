"""
pdf_generator.py — SRP MediFlow PDF Document Generator
=======================================================
Generates printable PDFs for:
  1. OPD Prescription
  2. IPD Discharge Summary
  3. Pharmacy Bill
  4. Hospital Invoice

Uses ReportLab (pure-Python PDF library).
Install: pip install reportlab

Falls back to a plain-text HTML receipt if ReportLab is not installed.

Public API
----------
    generate_opd_pdf(visit_data: dict)  -> bytes
    generate_discharge_pdf(adm_data: dict) -> bytes
    generate_pharmacy_bill_pdf(sale_data: dict) -> bytes
    generate_invoice_pdf(invoice_data: dict) -> bytes

Each function returns raw PDF bytes. The caller is responsible for
setting the Content-Type to 'application/pdf' and sending the bytes.

All functions accept a single dict (enriched by hms_db queries) and
fall back gracefully when optional fields are missing.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any

# ── Try to import ReportLab ────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.platypus.flowables import HRFlowable
    from io import BytesIO
    _RL = True
except ImportError:
    _RL = False

# ── Brand colours ─────────────────────────────────────────────────────────────
_BRAND_PURPLE = HexColor('#667eea') if _RL else None
_BRAND_GREEN  = HexColor('#00b896') if _RL else None
_BRAND_DARK   = HexColor('#1a1d27') if _RL else None
_LIGHT_GREY   = HexColor('#f4f6fa') if _RL else None
_MID_GREY     = HexColor('#8892a4') if _RL else None
_TEXT_DARK    = HexColor('#1a202c') if _RL else None

W, H = A4 if _RL else (595, 842)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now().strftime('%d %b %Y  %H:%M')


def _safe(val: Any, default: str = '—') -> str:
    if val is None or val == '':
        return default
    return str(val)


def _fallback_html(title: str, rows: list[tuple[str, str]], hospital: str = '') -> bytes:
    """Return a minimal HTML receipt when ReportLab is not installed."""
    lines = [
        f'<html><head><meta charset="UTF-8"><title>{title}</title>',
        '<style>body{font-family:Arial,sans-serif;max-width:700px;margin:40px auto;}',
        'h1{color:#667eea;}table{width:100%;border-collapse:collapse;}',
        'td{padding:8px;border-bottom:1px solid #eee;}b{color:#444;}</style></head><body>',
        f'<h1>🏥 {hospital or "SRP MediFlow"}</h1>',
        f'<h2>{title}</h2>',
        f'<p style="color:#888;">Generated: {_now_str()}</p><hr>',
        '<table>',
    ]
    for k, v in rows:
        lines.append(f'<tr><td><b>{k}</b></td><td>{v}</td></tr>')
    lines.append('</table>')
    lines.append('<hr><p style="color:#aaa;font-size:12px;">Powered by SRP AI Labs · SRP MediFlow</p>')
    lines.append('</body></html>')
    return '\n'.join(lines).encode('utf-8')


# ── ReportLab helpers ─────────────────────────────────────────────────────────

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle('BrandTitle',
        fontName='Helvetica-Bold', fontSize=18, textColor=_BRAND_PURPLE,
        leading=24, alignment=TA_LEFT))
    s.add(ParagraphStyle('SubTitle',
        fontName='Helvetica', fontSize=10, textColor=_MID_GREY,
        leading=14, alignment=TA_LEFT))
    s.add(ParagraphStyle('SectionHead',
        fontName='Helvetica-Bold', fontSize=11, textColor=_TEXT_DARK,
        leading=16, spaceAfter=4))
    s.add(ParagraphStyle('BodySmall',
        fontName='Helvetica', fontSize=9, textColor=_TEXT_DARK, leading=13))
    s.add(ParagraphStyle('BodySmallGrey',
        fontName='Helvetica', fontSize=9, textColor=_MID_GREY, leading=13))
    s.add(ParagraphStyle('Bold9',
        fontName='Helvetica-Bold', fontSize=9, textColor=_TEXT_DARK, leading=13))
    s.add(ParagraphStyle('Footer',
        fontName='Helvetica', fontSize=7.5, textColor=_MID_GREY,
        leading=11, alignment=TA_CENTER))
    return s


def _header_block(story, hospital_name: str, document_title: str, s):
    """Add branded header to PDF story."""
    story.append(Paragraph(f'🏥  {hospital_name}', s['BrandTitle']))
    story.append(Paragraph('Powered by SRP MediFlow · SRP AI Labs', s['SubTitle']))
    story.append(HRFlowable(width='100%', thickness=1.5, color=_BRAND_PURPLE,
                             spaceAfter=6, spaceBefore=4))
    story.append(Paragraph(document_title, ParagraphStyle(
        'DocTitle', fontName='Helvetica-Bold', fontSize=14,
        textColor=_BRAND_GREEN, leading=18, spaceAfter=2)))
    story.append(Paragraph(f'Printed: {_now_str()}', s['BodySmallGrey']))
    story.append(Spacer(1, 8*mm))


def _kv_table(pairs: list[tuple[str, str]]) -> Table:
    """Two-column key-value info table."""
    data = [[Paragraph(f'<b>{k}</b>', ParagraphStyle(
                'K', fontName='Helvetica-Bold', fontSize=9, textColor=_MID_GREY)),
             Paragraph(str(v), ParagraphStyle(
                'V', fontName='Helvetica', fontSize=9, textColor=_TEXT_DARK))]
            for k, v in pairs]
    t = Table(data, colWidths=[45*mm, 100*mm])
    t.setStyle(TableStyle([
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',  (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0,0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _items_table(headers: list[str], rows: list[list], col_widths=None) -> Table:
    """Formatted data table with purple header row."""
    s = _styles()
    header_row = [Paragraph(f'<b>{h}</b>', ParagraphStyle(
        'TH', fontName='Helvetica-Bold', fontSize=8.5,
        textColor=white, leading=12))
        for h in headers]
    body_rows = [[Paragraph(_safe(cell), ParagraphStyle(
        'TD', fontName='Helvetica', fontSize=8.5,
        textColor=_TEXT_DARK, leading=12)) for cell in row]
        for row in rows]
    all_rows = [header_row] + body_rows
    t = Table(all_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0),  _BRAND_PURPLE),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [white, _LIGHT_GREY]),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('GRID',         (0, 0), (-1, -1), 0.3, HexColor('#dce1ea')),
        ('LINEBELOW',    (0, 0), (-1, 0),  1.2, _BRAND_PURPLE),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _footer(story, s):
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=_MID_GREY,
                             spaceBefore=0, spaceAfter=4))
    story.append(Paragraph(
        'This is a computer-generated document and does not require a signature. '
        '© SRP AI Labs · SRP MediFlow HMS',
        s['Footer']))


# ══════════════════════════════════════════════════════════════════════════════
# 1. OPD PRESCRIPTION PDF
# ══════════════════════════════════════════════════════════════════════════════

def generate_opd_pdf(visit_data: dict) -> bytes:
    """
    Generate OPD Prescription PDF.

    Expected keys in visit_data:
        hospital_name, patient_name, patient_id, uhid, age, gender, phone,
        visit_date, doctor_name, doctor_dept, chief_complaint, diagnosis,
        notes, op_ticket_no, prescriptions (list of dicts with
        medicine_name, dosage, frequency, duration, instructions, quantity),
        vitals (dict: bp, pulse, temp, spo2, weight)
    """
    hospital   = _safe(visit_data.get('hospital_name'), 'Hospital')
    p_name     = _safe(visit_data.get('patient_name'))
    p_id       = _safe(visit_data.get('patient_id'))
    uhid       = _safe(visit_data.get('uhid'))
    age        = _safe(visit_data.get('age'))
    gender     = _safe(visit_data.get('gender'))
    phone      = _safe(visit_data.get('phone'))
    visit_date = _safe(visit_data.get('visit_date'))
    doctor     = _safe(visit_data.get('doctor_name'))
    dept       = _safe(visit_data.get('doctor_dept'))
    complaint  = _safe(visit_data.get('chief_complaint'))
    diagnosis  = _safe(visit_data.get('diagnosis'))
    notes      = _safe(visit_data.get('notes'))
    ticket     = _safe(visit_data.get('op_ticket_no'))
    prescriptions = visit_data.get('prescriptions') or []
    vitals     = visit_data.get('vitals') or {}

    if not _RL:
        rows = [
            ('Patient', p_name), ('UHID', uhid), ('Age/Gender', f'{age} / {gender}'),
            ('Phone', phone), ('OPD Ticket', ticket), ('Visit Date', visit_date),
            ('Doctor', doctor), ('Department', dept),
            ('Chief Complaint', complaint), ('Diagnosis', diagnosis),
            ('Notes', notes),
        ]
        for i, rx in enumerate(prescriptions, 1):
            rows.append((f'Rx {i}', f"{rx.get('medicine_name','')} | {rx.get('dosage','')} | {rx.get('frequency','')} | {rx.get('duration','')}"))
        return _fallback_html('OPD Prescription', rows, hospital)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=15*mm, bottomMargin=15*mm)
    s = _styles()
    story = []

    _header_block(story, hospital, 'OPD Prescription', s)

    # Patient info
    story.append(Paragraph('Patient Information', s['SectionHead']))
    story.append(_kv_table([
        ('Patient Name', p_name),
        ('UHID',         uhid),
        ('Patient ID',   p_id),
        ('Age / Gender', f'{age} / {gender}'),
        ('Phone',        phone),
        ('OPD Ticket',   ticket),
        ('Visit Date',   visit_date),
        ('Doctor',       f'{doctor}' + (f'  [{dept}]' if dept != '—' else '')),
    ]))
    story.append(Spacer(1, 6*mm))

    # Vitals
    if vitals:
        story.append(Paragraph('Vitals', s['SectionHead']))
        vrow = [(k.replace('_',' ').title(), _safe(v))
                for k, v in vitals.items() if v not in (None, '', '—')]
        if vrow:
            story.append(_kv_table(vrow))
            story.append(Spacer(1, 6*mm))

    # Complaint & Diagnosis
    story.append(Paragraph('Clinical Notes', s['SectionHead']))
    story.append(_kv_table([
        ('Chief Complaint', complaint),
        ('Diagnosis',       diagnosis),
        ('Notes',           notes),
    ]))
    story.append(Spacer(1, 6*mm))

    # Prescriptions
    story.append(Paragraph('Prescription (Rx)', s['SectionHead']))
    if prescriptions:
        rx_rows = [
            [str(i),
             rx.get('medicine_name', ''),
             rx.get('dosage', ''),
             rx.get('frequency', ''),
             rx.get('duration', ''),
             str(rx.get('quantity', '')),
             rx.get('instructions', '')]
            for i, rx in enumerate(prescriptions, 1)
        ]
        story.append(_items_table(
            ['#', 'Medicine', 'Dosage', 'Frequency', 'Duration', 'Qty', 'Instructions'],
            rx_rows,
            col_widths=[8*mm, 40*mm, 25*mm, 22*mm, 20*mm, 12*mm, 36*mm]))
    else:
        story.append(Paragraph('No prescription recorded for this visit.', s['BodySmallGrey']))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(
        'Doctor Signature: ____________________________   Date: _______________',
        s['BodySmall']))

    _footer(story, s)
    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 2. IPD DISCHARGE SUMMARY PDF
# ══════════════════════════════════════════════════════════════════════════════

def generate_discharge_pdf(adm_data: dict) -> bytes:
    """
    Generate IPD Discharge Summary PDF.

    Expected keys in adm_data:
        hospital_name, patient_name, uhid, age, gender, phone, blood_group,
        admission_date, discharge_date, ward_name, bed_number,
        admitting_doctor, attending_doctor,
        admission_diagnosis, final_diagnosis, comorbidities,
        treatment_summary, discharge_condition,
        advice_on_discharge, follow_up_date,
        discharge_medications (list of dicts: medicine_name, dosage, frequency, duration),
        discharge_summary_text,
        total_bill_amount,
        investigations (list of dicts: test_name, result_value, reference_range, unit)
    """
    hospital = _safe(adm_data.get('hospital_name'), 'Hospital')
    p_name   = _safe(adm_data.get('patient_name'))
    uhid     = _safe(adm_data.get('uhid'))
    age      = _safe(adm_data.get('age'))
    gender   = _safe(adm_data.get('gender'))
    phone    = _safe(adm_data.get('phone'))
    bg       = _safe(adm_data.get('blood_group'))
    adm_dt   = _safe(adm_data.get('admission_date'))
    dis_dt   = _safe(adm_data.get('discharge_date'))
    ward     = _safe(adm_data.get('ward_name'))
    bed      = _safe(adm_data.get('bed_number'))
    adm_doc  = _safe(adm_data.get('admitting_doctor'))
    att_doc  = _safe(adm_data.get('attending_doctor'))
    adm_dx   = _safe(adm_data.get('admission_diagnosis'))
    fin_dx   = _safe(adm_data.get('final_diagnosis'))
    comorbid = _safe(adm_data.get('comorbidities'))
    treatment= _safe(adm_data.get('treatment_summary'))
    condition= _safe(adm_data.get('discharge_condition'))
    advice   = _safe(adm_data.get('advice_on_discharge'))
    follow   = _safe(adm_data.get('follow_up_date'))
    summary  = _safe(adm_data.get('discharge_summary_text'))
    bill_amt = _safe(adm_data.get('total_bill_amount'))
    meds     = adm_data.get('discharge_medications') or []
    invests  = adm_data.get('investigations') or []

    if not _RL:
        rows = [
            ('Patient', p_name), ('UHID', uhid), ('Age/Gender', f'{age}/{gender}'),
            ('Blood Group', bg), ('Admission', adm_dt), ('Discharge', dis_dt),
            ('Ward/Bed', f'{ward} / {bed}'), ('Admitting Doctor', adm_doc),
            ('Admitting Diagnosis', adm_dx), ('Final Diagnosis', fin_dx),
            ('Treatment', treatment), ('Condition at Discharge', condition),
            ('Advice', advice), ('Follow-Up', follow), ('Bill Amount', bill_amt),
        ]
        return _fallback_html('IPD Discharge Summary', rows, hospital)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=15*mm, bottomMargin=15*mm)
    s = _styles()
    story = []

    _header_block(story, hospital, 'IPD Discharge Summary', s)

    story.append(Paragraph('Patient Details', s['SectionHead']))
    story.append(_kv_table([
        ('Patient Name', p_name), ('UHID', uhid),
        ('Age / Gender', f'{age} / {gender}'), ('Blood Group', bg), ('Phone', phone),
        ('Admission Date', adm_dt), ('Discharge Date', dis_dt),
        ('Ward', ward), ('Bed No.', bed),
        ('Admitting Doctor', adm_doc), ('Attending Doctor', att_doc),
    ]))
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph('Diagnosis', s['SectionHead']))
    story.append(_kv_table([
        ('Admission Diagnosis', adm_dx),
        ('Final Diagnosis', fin_dx),
        ('Comorbidities', comorbid),
    ]))
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph('Treatment & Clinical Summary', s['SectionHead']))
    story.append(Paragraph(treatment if treatment != '—' else 'Not recorded.',
                            s['BodySmall']))
    if summary != '—':
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(summary, s['BodySmall']))
    story.append(Spacer(1, 5*mm))

    if invests:
        story.append(Paragraph('Investigations', s['SectionHead']))
        inv_rows = [[r.get('test_name',''), r.get('result_value',''),
                     r.get('reference_range',''), r.get('unit','')]
                    for r in invests]
        story.append(_items_table(
            ['Test Name', 'Result', 'Reference Range', 'Unit'],
            inv_rows,
            col_widths=[55*mm, 45*mm, 45*mm, 20*mm]))
        story.append(Spacer(1, 5*mm))

    story.append(Paragraph('Discharge Instructions', s['SectionHead']))
    story.append(_kv_table([
        ('Condition at Discharge', condition),
        ('Advice on Discharge', advice),
        ('Follow-Up Date', follow),
    ]))
    story.append(Spacer(1, 5*mm))

    if meds:
        story.append(Paragraph('Discharge Medications', s['SectionHead']))
        med_rows = [[m.get('medicine_name',''), m.get('dosage',''),
                     m.get('frequency',''), m.get('duration','')]
                    for m in meds]
        story.append(_items_table(
            ['Medicine', 'Dosage', 'Frequency', 'Duration'],
            med_rows,
            col_widths=[65*mm, 40*mm, 35*mm, 25*mm]))
        story.append(Spacer(1, 5*mm))

    story.append(Paragraph('Billing', s['SectionHead']))
    story.append(_kv_table([('Total Bill Amount', f'₹ {bill_amt}')]))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph(
        'Doctor Signature: ____________________________   Date: _______________',
        s['BodySmall']))

    _footer(story, s)
    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 3. PHARMACY BILL PDF
# ══════════════════════════════════════════════════════════════════════════════

def generate_pharmacy_bill_pdf(sale_data: dict) -> bytes:
    """
    Generate Pharmacy Bill / Cash Memo PDF.

    Expected keys in sale_data:
        hospital_name, bill_no, sale_date, patient_name, patient_phone,
        cashier, items (list of dicts: medicine_name, batch_no, expiry_date,
        qty, unit_price, gst_pct, amount), subtotal, gst_total, total,
        payment_mode
    """
    hospital  = _safe(sale_data.get('hospital_name'), 'Hospital')
    bill_no   = _safe(sale_data.get('bill_no'))
    sale_date = _safe(sale_data.get('sale_date'))
    p_name    = _safe(sale_data.get('patient_name'))
    p_phone   = _safe(sale_data.get('patient_phone'))
    cashier   = _safe(sale_data.get('cashier'))
    items     = sale_data.get('items') or []
    subtotal  = _safe(sale_data.get('subtotal', '0'))
    gst_tot   = _safe(sale_data.get('gst_total', '0'))
    total     = _safe(sale_data.get('total', '0'))
    pay_mode  = _safe(sale_data.get('payment_mode'))

    if not _RL:
        rows = [
            ('Bill No', bill_no), ('Date', sale_date), ('Patient', p_name),
            ('Phone', p_phone), ('Cashier', cashier), ('Payment', pay_mode),
        ]
        for i, it in enumerate(items, 1):
            rows.append((f'Item {i}',
                f"{it.get('medicine_name','')} x{it.get('qty',1)} = ₹{it.get('amount',0)}"))
        rows += [('Subtotal', f'₹{subtotal}'), ('GST', f'₹{gst_tot}'), ('TOTAL', f'₹{total}')]
        return _fallback_html('Pharmacy Bill', rows, hospital)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=15*mm, bottomMargin=15*mm)
    s = _styles()
    story = []

    _header_block(story, hospital, f'Pharmacy Bill / Cash Memo — #{bill_no}', s)

    story.append(_kv_table([
        ('Bill No', bill_no), ('Date', sale_date),
        ('Patient', p_name),  ('Phone', p_phone),
        ('Cashier', cashier), ('Payment Mode', pay_mode),
    ]))
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph('Item Details', s['SectionHead']))
    if items:
        item_rows = [
            [str(i), it.get('medicine_name',''), it.get('batch_no',''),
             _safe(it.get('expiry_date')), str(it.get('qty','')),
             f"₹{it.get('unit_price','')}", f"{it.get('gst_pct','0')}%",
             f"₹{it.get('amount','')}"]
            for i, it in enumerate(items, 1)
        ]
        story.append(_items_table(
            ['#', 'Medicine', 'Batch No', 'Expiry', 'Qty', 'Unit Price', 'GST%', 'Amount'],
            item_rows,
            col_widths=[7*mm, 50*mm, 22*mm, 18*mm, 10*mm, 18*mm, 12*mm, 18*mm]))
    else:
        story.append(Paragraph('No items on this bill.', s['BodySmallGrey']))

    story.append(Spacer(1, 5*mm))

    # Totals
    totals_data = [
        [Paragraph('<b>Subtotal</b>', s['Bold9']), Paragraph(f'₹ {subtotal}', s['BodySmall'])],
        [Paragraph('<b>GST</b>',      s['Bold9']), Paragraph(f'₹ {gst_tot}',  s['BodySmall'])],
        [Paragraph('<b>TOTAL</b>',    ParagraphStyle('TOT', fontName='Helvetica-Bold',
                                         fontSize=11, textColor=_BRAND_GREEN)),
         Paragraph(f'₹ {total}',      ParagraphStyle('TOTV', fontName='Helvetica-Bold',
                                         fontSize=11, textColor=_BRAND_GREEN))],
    ]
    t = Table(totals_data, colWidths=[120*mm, 40*mm])
    t.setStyle(TableStyle([
        ('ALIGN',      (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('LINEABOVE',  (0, 2), (-1, 2), 1, _BRAND_PURPLE),
    ]))
    story.append(t)

    _footer(story, s)
    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 4. HOSPITAL INVOICE PDF
# ══════════════════════════════════════════════════════════════════════════════

def generate_invoice_pdf(invoice_data: dict) -> bytes:
    """
    Generate Hospital Invoice PDF (OPD / IPD / Mixed).

    Expected keys in invoice_data:
        hospital_name, hospital_address, hospital_phone, hospital_gstin,
        invoice_no, invoice_date, due_date, bill_type,
        patient_name, patient_id, uhid, patient_phone, patient_address,
        doctor_name, items (list of dicts: description, category, qty,
        unit_price, discount, gst_pct, amount),
        subtotal, discount_total, gst_total, net_amount,
        payment_status, payment_mode, notes
    """
    hospital  = _safe(invoice_data.get('hospital_name'), 'Hospital')
    h_addr    = _safe(invoice_data.get('hospital_address'))
    h_phone   = _safe(invoice_data.get('hospital_phone'))
    h_gstin   = _safe(invoice_data.get('hospital_gstin'))
    inv_no    = _safe(invoice_data.get('invoice_no'))
    inv_date  = _safe(invoice_data.get('invoice_date'))
    due_date  = _safe(invoice_data.get('due_date'))
    bill_type = _safe(invoice_data.get('bill_type'))
    p_name    = _safe(invoice_data.get('patient_name'))
    p_id      = _safe(invoice_data.get('patient_id'))
    uhid      = _safe(invoice_data.get('uhid'))
    p_phone   = _safe(invoice_data.get('patient_phone'))
    p_addr    = _safe(invoice_data.get('patient_address'))
    doctor    = _safe(invoice_data.get('doctor_name'))
    items     = invoice_data.get('items') or []
    subtotal  = _safe(invoice_data.get('subtotal', '0'))
    disc_tot  = _safe(invoice_data.get('discount_total', '0'))
    gst_tot   = _safe(invoice_data.get('gst_total', '0'))
    net_amt   = _safe(invoice_data.get('net_amount', '0'))
    pay_stat  = _safe(invoice_data.get('payment_status', 'PENDING'))
    pay_mode  = _safe(invoice_data.get('payment_mode'))
    notes     = _safe(invoice_data.get('notes'))

    if not _RL:
        rows = [
            ('Invoice No', inv_no), ('Date', inv_date), ('Type', bill_type),
            ('Patient', p_name), ('UHID', uhid), ('Doctor', doctor),
            ('Subtotal', f'₹{subtotal}'), ('Discount', f'₹{disc_tot}'),
            ('GST', f'₹{gst_tot}'), ('NET AMOUNT', f'₹{net_amt}'),
            ('Payment Status', pay_stat),
        ]
        return _fallback_html(f'Invoice #{inv_no}', rows, hospital)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=15*mm, bottomMargin=15*mm)
    s = _styles()
    story = []

    _header_block(story, hospital, f'Tax Invoice — {bill_type}', s)

    # Hospital & Invoice meta side-by-side
    left_data  = [['Hospital Details', 'Invoice Details']]
    left_style = TableStyle([
        ('FONTNAME', (0,0),(-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0),(-1,0), 10),
        ('TEXTCOLOR',(0,0),(-1,0), _BRAND_PURPLE),
        ('TOPPADDING',(0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1),2),
        ('VALIGN',  (0,0),(-1,-1),'TOP'),
    ])
    meta_t = Table([
        [
            Paragraph(f'<b>{hospital}</b><br/>{h_addr}<br/>Ph: {h_phone}<br/>GSTIN: {h_gstin}',
                      s['BodySmall']),
            Paragraph(f'<b>Invoice No:</b> {inv_no}<br/>'
                      f'<b>Date:</b> {inv_date}<br/>'
                      f'<b>Due Date:</b> {due_date}<br/>'
                      f'<b>Status:</b> <font color="#00b896">{pay_stat}</font>',
                      s['BodySmall']),
        ]
    ], colWidths=[85*mm, 75*mm])
    meta_t.setStyle(TableStyle([
        ('VALIGN', (0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),0),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph('Bill To', s['SectionHead']))
    story.append(_kv_table([
        ('Patient Name', p_name), ('UHID', uhid), ('Patient ID', p_id),
        ('Phone', p_phone), ('Address', p_addr), ('Doctor', doctor),
    ]))
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph('Services & Charges', s['SectionHead']))
    if items:
        item_rows = [
            [str(i), it.get('description',''), it.get('category',''),
             str(it.get('qty',1)), f"₹{it.get('unit_price','')}",
             f"{it.get('discount','0')}%", f"{it.get('gst_pct','0')}%",
             f"₹{it.get('amount','')}"]
            for i, it in enumerate(items, 1)
        ]
        story.append(_items_table(
            ['#', 'Description', 'Category', 'Qty', 'Unit Price', 'Disc.', 'GST%', 'Amount'],
            item_rows,
            col_widths=[7*mm, 52*mm, 24*mm, 10*mm, 20*mm, 12*mm, 12*mm, 18*mm]))
    else:
        story.append(Paragraph('No line items.', s['BodySmallGrey']))

    story.append(Spacer(1, 5*mm))

    # Totals block
    totals = [
        ('Subtotal',         f'₹ {subtotal}'),
        ('Discount (-)',     f'₹ {disc_tot}'),
        ('GST (+)',          f'₹ {gst_tot}'),
    ]
    tot_rows = [[Paragraph(f'<b>{k}</b>', s['Bold9']),
                 Paragraph(v, s['BodySmall'])] for k, v in totals]
    tot_rows.append([
        Paragraph('<b>NET AMOUNT</b>', ParagraphStyle('NA', fontName='Helvetica-Bold',
                  fontSize=12, textColor=_BRAND_GREEN)),
        Paragraph(f'₹ {net_amt}', ParagraphStyle('NAV', fontName='Helvetica-Bold',
                  fontSize=12, textColor=_BRAND_GREEN)),
    ])
    t = Table(tot_rows, colWidths=[120*mm, 40*mm])
    t.setStyle(TableStyle([
        ('ALIGN',        (1,0),(1,-1),'RIGHT'),
        ('TOPPADDING',   (0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LINEABOVE',    (0,-1),(-1,-1),1,_BRAND_PURPLE),
    ]))
    story.append(t)

    if pay_mode != '—' or notes != '—':
        story.append(Spacer(1, 4*mm))
        story.append(_kv_table([
            ('Payment Mode', pay_mode),
            ('Notes', notes),
        ]))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(
        'Authorised Signatory: ____________________________   Seal / Stamp',
        s['BodySmall']))

    _footer(story, s)
    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT-TYPE helper
# ══════════════════════════════════════════════════════════════════════════════

def content_type() -> str:
    """Return correct MIME type depending on output format."""
    return 'application/pdf' if _RL else 'text/html; charset=utf-8'


def is_real_pdf() -> bool:
    """Return True if ReportLab is available (real PDF output)."""
    return _RL
