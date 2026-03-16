#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向 gateway_sql_request_log 插入 10 条测试数据
"""
import psycopg2
import yaml
from datetime import datetime, timedelta

cfg = yaml.safe_load(open('config.yaml', encoding='utf-8'))['backend']
conn = psycopg2.connect(
    host=cfg['host'], port=cfg['port'],
    database=cfg['database'], user=cfg['user'], password=cfg['password']
)
cur = conn.cursor()

now = datetime.now()

rows = [
    # (request_id, tenant_code, dataset_id, sql_content, execute_status, create_offset_min, execute_offset_min)
    ('REQ_TEST_001', 'TENANT_A', 'DS_SALES',
     "SELECT tenant_code, COUNT(*) AS cnt FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' GROUP BY tenant_code",
     'SUCCESS', -60, -59),

    ('REQ_TEST_002', 'TENANT_B', 'DS_ORDER',
     "SELECT * FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' ORDER BY execution_time_ms DESC LIMIT 10",
     'SUCCESS', -55, -54),

    ('REQ_TEST_003', 'TENANT_A', 'DS_REPORT',
     "SELECT dataset_id, SUM(estimated_traffic_bytes) AS total_bytes FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' GROUP BY dataset_id",
     'SUCCESS', -50, -49),

    ('REQ_TEST_004', 'TENANT_C', 'DS_SALES',
     "SELECT AVG(execution_time_ms) AS avg_ms, MAX(execution_time_ms) AS max_ms FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' AND dataset_id = '{dataset_id}'",
     'SUCCESS', -45, -44),

    ('REQ_TEST_005', 'TENANT_B', 'DS_LOG',
     "SELECT tenant_code, dataset_id, execution_time_ms FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' AND execution_time_ms > 100 LIMIT 5",
     'FAILED', -40, -39),

    ('REQ_TEST_006', 'TENANT_D', 'DS_ORDER',
     "SELECT COUNT(*) AS total, SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) AS cache_hits FROM public.tenant_stats WHERE tenant_code = '{tenant_code}'",
     'SUCCESS', -35, -34),

    ('REQ_TEST_007', 'TENANT_C', 'DS_REPORT',
     "SELECT * FROM public.tenant_stats WHERE dataset_id = '{dataset_id}' ORDER BY create_time DESC LIMIT 20",
     'SUCCESS', -30, -29),

    ('REQ_TEST_008', 'TENANT_A', 'DS_ORDER',
     "SELECT tenant_code, COUNT(*) AS sql_cnt, AVG(execution_time_ms) AS avg_exec FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' GROUP BY tenant_code",
     'TIMEOUT', -25, None),

    ('REQ_TEST_009', 'TENANT_D', 'DS_SALES',
     "SELECT estimated_traffic_bytes / 1024.0 AS traffic_kb FROM public.tenant_stats WHERE request_id = '{request_id}' LIMIT 1",
     'SUCCESS', -20, -19),

    ('REQ_TEST_010', 'TENANT_B', 'DS_REPORT',
     "SELECT tenant_code, dataset_id, execution_time_ms, from_cache FROM public.tenant_stats WHERE tenant_code = '{tenant_code}' AND dataset_id = '{dataset_id}' LIMIT 50",
     'SUCCESS', -10, -9),
]

inserted = 0
skipped  = 0

for (req_id, tenant, dataset, sql, status, c_off, e_off) in rows:
    create_time  = now + timedelta(minutes=c_off)
    execute_time = (now + timedelta(minutes=e_off)) if e_off is not None else None

    cur.execute("""
        INSERT INTO public.gateway_sql_request_log
          (request_id, tenant_code, dataset_id, sql_content, create_time, execute_time, execute_status)
        SELECT %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM public.gateway_sql_request_log WHERE request_id = %s
        )
    """, (req_id, tenant, dataset, sql, create_time, execute_time, status, req_id))

    if cur.rowcount:
        inserted += 1
        print(f"  ✓ {req_id}  [{tenant}]  {status}")
    else:
        skipped += 1
        print(f"  - {req_id}  已存在，跳过")

conn.commit()
conn.close()

print(f"\n完成: 新插入 {inserted} 条，跳过 {skipped} 条")
print("下一步: 点击 Dashboard「立即采集」按钮或等待自动采集（60s）")
