"""Debug why schema fails for a tenant DB"""
import psycopg2, re

with open('srp_mediflow_schema.sql', encoding='utf-8') as f:
    sql = f.read()

# Count statements
stmts = [s.strip() for s in re.split(r';\s*\n', sql) if s.strip() and not s.strip().startswith('--')]
print(f"Total statements parsed from schema: {len(stmts)}")
for i, s in enumerate(stmts[:5]):
    print(f"  stmt[{i}]: {s[:80]}")

conn = psycopg2.connect(host='localhost',port=5432,dbname='srp_sai_care',user='ats_user',password='ats_password')
conn.autocommit = False
cur = conn.cursor()

print("\nRunning statements against srp_sai_care:")
for i, stmt in enumerate(stmts):
    stmt = stmt.rstrip(';').strip()
    if not stmt:
        continue
    try:
        cur.execute(stmt)
        conn.commit()
        print(f"  [{i}] OK: {stmt[:60]}")
    except Exception as e:
        conn.rollback()
        print(f"  [{i}] FAIL: {stmt[:60]}")
        print(f"       ERR: {str(e).split(chr(10))[0][:120]}")

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTables after provision: {tables}")
cur.close(); conn.close()
