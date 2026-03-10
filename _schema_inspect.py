import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='srp_platform_db', user='ats_user', password='ats_password')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients' ORDER BY ordinal_position")
print('clients columns:', [r[0] for r in cur.fetchall()])
cur.execute("SELECT * FROM clients")
rows = cur.fetchall()
print(f'Total rows: {len(rows)}')
for r in rows:
    print('ROW:', r)
conn.close()
