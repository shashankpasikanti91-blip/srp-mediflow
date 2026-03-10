import psycopg2, psycopg2.extras
conn = psycopg2.connect(host='localhost',port=5432,dbname='hospital_ai',user='postgres',password='postgres')
cur = conn.cursor()
for t in ['prescription_items','prescriptions','medicines','appointments','registrations']:
    cur.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (t,))
    cols = cur.fetchall()
    if cols:
        print(f'\n{t}:')
        for c in cols: print(f'  {c[0]} ({c[1]})')
    else:
        print(f'\n{t}: NOT FOUND')
conn.close()
