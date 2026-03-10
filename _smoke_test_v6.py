"""Smoke test for v6.0 features — run with C:/Python314/python.exe _smoke_test_v6.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

errors = []

# 1. DB connection + migration tables/columns
try:
    import db
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prescriptions")
            rx_count = cur.fetchone()[0]
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='prescriptions' "
                "AND column_name IN ('chief_complaint','bp','pulse','spo2','follow_up_days') "
                "ORDER BY column_name"
            )
            cols = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' "
                "AND table_name IN ('prescription_medicines','notification_settings','notification_logs','notification_templates') "
                "ORDER BY table_name"
            )
            new_tables = [r[0] for r in cur.fetchall()]
    print(f"[OK] DB connection — prescriptions row count: {rx_count}")
    if len(cols) == 5:
        print(f"[OK] Migration columns present: {cols}")
    else:
        errors.append(f"[FAIL] Expected 5 new columns, got: {cols}")
    if len(new_tables) == 4:
        print(f"[OK] Migration tables present: {new_tables}")
    else:
        errors.append(f"[FAIL] Expected 4 new tables, got: {new_tables}")
except Exception as e:
    errors.append(f"[FAIL] DB check: {e}")

# 2. Notification providers
try:
    from notifications.telegram_provider import TelegramProvider
    from notifications.whatsapp_provider import WhatsAppProvider
    from notifications.service import NotificationService
    tg = TelegramProvider("dummy_token", "dummy_chat")
    wa = WhatsAppProvider(None)
    assert tg.is_configured() == True,  "TelegramProvider.is_configured() should be True with token+chat"
    assert wa.is_configured() == False, "WhatsAppProvider.is_configured() should be False with empty config"
    print("[OK] TelegramProvider configured=True, WhatsAppProvider configured=False")
    print("[OK] NotificationService imported")
except Exception as e:
    errors.append(f"[FAIL] Notifications: {e}")

# 3. hms_db functions
try:
    import hms_db
    needed = [
        "create_full_prescription", "get_full_prescription", "get_prescriptions_by_visit",
        "get_notification_settings", "save_notification_settings",
        "get_dashboard_enhanced_stats", "get_recent_activity"
    ]
    missing = [f for f in needed if not hasattr(hms_db, f)]
    if missing:
        errors.append(f"[FAIL] hms_db missing: {missing}")
    else:
        print(f"[OK] hms_db — all {len(needed)} required functions present")
except Exception as e:
    errors.append(f"[FAIL] hms_db import: {e}")

# 4. PDF generator
try:
    import pdf_generator
    assert hasattr(pdf_generator, "generate_digital_prescription_pdf")
    print("[OK] pdf_generator.generate_digital_prescription_pdf present")
except Exception as e:
    errors.append(f"[FAIL] pdf_generator: {e}")

# 5. Server imports
try:
    import importlib.util, types
    # Just check the file compiles
    spec = importlib.util.spec_from_file_location("srv", os.path.join(os.path.dirname(__file__), "srp_mediflow_server.py"))
    mod = types.ModuleType("srv")
    # We only do compile check, not full exec (would start server)
    with open(os.path.join(os.path.dirname(__file__), "srp_mediflow_server.py"), encoding="utf-8") as f:
        source = f.read()
    compile(source, "srp_mediflow_server.py", "exec")
    print("[OK] srp_mediflow_server.py compiles without errors")
except Exception as e:
    errors.append(f"[FAIL] server compile: {e}")

print()
if errors:
    print("=== FAILURES ===")
    for err in errors:
        print(err)
    sys.exit(1)
else:
    print("=== ALL v6.0 SMOKE TESTS PASSED ===")
