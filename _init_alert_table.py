import psycopg2, pathlib, sys
ddl = pathlib.Path('create_gateway_alert_log.sql').read_text('utf-8')
conn = psycopg2.connect(host='localhost', port=5432, dbname='test', user='dbtest1', password='dbtest1')
cur = conn.cursor()
cur.execute(ddl)
conn.commit()
cur.execute('SELECT COUNT(*) FROM public.gateway_alert_log')
print('Table OK, rows:', cur.fetchone()[0])
conn.close()
