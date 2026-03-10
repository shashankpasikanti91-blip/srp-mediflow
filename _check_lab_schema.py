import psycopg2, json
conn = psycopg2.connect(host="localhost", port=5434, dbname="hospital_ai", user="ats_user", password="ats_password")
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='lab_orders' ORDER BY ordinal_position")
cols = cur.fetchall()
print("LAB_ORDERS COLUMNS:", [c[0] for c in cols])
cur.execute("SELECT * FROM lab_orders LIMIT 3")
rows = cur.fetchall()
print("SAMPLE ROWS:", rows)

# Check doctors table columns
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='doctors' ORDER BY ordinal_position")
dcols = cur.fetchall()
print("DOCTORS COLUMNS:", [c[0] for c in dcols])

cur.close(); conn.close()
print("DONE")
