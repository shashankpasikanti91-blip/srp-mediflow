import psycopg2
conn = psycopg2.connect(host='localhost', port=5434, dbname='hospital_ai',
                        user='ats_user', password='ats_password', connect_timeout=5)
cur = conn.cursor()
cur.execute("SELECT username, role FROM staff_users WHERE role='founder' OR username='founder' LIMIT 5")
rows = cur.fetchall()
print('Founder accounts:', rows)
cur.execute("SELECT username, role FROM staff_users LIMIT 15")
print('All staff:', cur.fetchall())
conn.close()
