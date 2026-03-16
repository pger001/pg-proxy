import psycopg2, psycopg2.extras, yaml
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["backend"]
conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["database"], user=cfg["user"], password=cfg["password"])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# tenant_stats 结构和数据量
cur.execute("SELECT COUNT(*) AS cnt FROM public.tenant_stats")
print("tenant_stats count:", cur.fetchone()["cnt"])

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='tenant_stats' ORDER BY ordinal_position")
print("tenant_stats columns:", [(r["column_name"], r["data_type"]) for r in cur.fetchall()])

cur.execute("SELECT * FROM public.tenant_stats LIMIT 3")
rows = cur.fetchall()
for r in rows:
    print("  row:", dict(r))

# gateway_sql_request_log 结构和数据量
cur.execute("SELECT COUNT(*) AS cnt FROM public.gateway_sql_request_log")
print("gateway_sql_request_log count:", cur.fetchone()["cnt"])
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='gateway_sql_request_log' ORDER BY ordinal_position")
print("gateway_sql_request_log columns:", [r["column_name"] for r in cur.fetchall()])

conn.close()



cur.execute("SELECT COUNT(*) AS cnt FROM public.gateway_sql_resource_usage")
print("resource_usage count:", cur.fetchone()["cnt"])

cur.execute("SELECT MIN(analyzed_at)::date AS mn, MAX(analyzed_at)::date AS mx FROM public.gateway_sql_resource_usage")
print("resource_usage date range:", dict(cur.fetchone()))

cur.execute("SELECT COUNT(*) AS cnt FROM public.gateway_collect_log")
print("collect_log count:", cur.fetchone()["cnt"])

cur.execute("SELECT COUNT(*) AS cnt FROM public.gateway_alert_log")
print("alert_log count:", cur.fetchone()["cnt"])

# 检测监控面板用的表
for table in ["gateway_request_logs", "pg_stat_statements"]:
    try:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} LIMIT 1")
        print(f"{table} count:", cur.fetchone()["cnt"])
    except Exception as e:
        print(f"{table}: ERROR - {e}")
        conn.rollback()

# 检测 summary 用的表字段
cur.execute("""
    SELECT execute_status, COUNT(*) AS cnt
    FROM public.gateway_sql_resource_usage
    GROUP BY execute_status
    LIMIT 10
""")
print("status breakdown:", [dict(r) for r in cur.fetchall()])

conn.close()
print("DONE")
