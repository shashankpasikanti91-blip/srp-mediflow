import psycopg2

for dbname in ['hospital_ai', 'srp_platform_db']:
    print(f"\n{'='*50}")
    print(f"DATABASE: {dbname}")
    print('='*50)
    try:
        conn = psycopg2.connect(host='localhost', port=5432, dbname=dbname, user='ats_user', password='ats_password')
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = [r[0] for r in cur.fetchall()]
        print("Tables:", tables)
        for t in tables:
            # Check each table for phone-like columns
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}' AND column_name ILIKE '%%phone%%' OR table_name='{t}' AND column_name ILIKE '%%mobile%%' OR table_name='{t}' AND column_name ILIKE '%%contact%%'")
            cols = [r[0] for r in cur.fetchall()]
            if cols:
                print(f"\n  TABLE {t} has cols: {cols}")
                cur.execute(f"SELECT {','.join(cols)} FROM {t} LIMIT 5")
                for r in cur.fetchall():
                    print(f"    {r}")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")

