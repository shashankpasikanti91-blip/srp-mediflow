import psycopg2, psycopg2.extras
conn = psycopg2.connect(host='localhost', port=5432, dbname='hospital_ai', user='postgres', password='postgres')
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print('TABLES:', tables)
for t in ['registrations', 'patient_visits', 'op_tickets', 'attendance', 'doctor_attendance', 'doctors']:
    if t in tables:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        print(f'{t} rows:', cur.fetchone()[0])
    else:
        print(f'{t}: NOT FOUND')
conn.close()
