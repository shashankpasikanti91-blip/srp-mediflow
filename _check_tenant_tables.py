import psycopg2
dbs = ['srp_sai_care','srp_city_medical','srp_apollo_warangal','srp_green_cross']
for db in dbs:
    try:
        conn = psycopg2.connect(host='localhost',port=5432,dbname=db,user='ats_user',password='ats_password',connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        tables = [r[0] for r in cur.fetchall()]
        print(f'{db}: {tables or "EMPTY"}')
        cur.close(); conn.close()
    except Exception as e:
        print(f'{db} FAIL: {e}')
