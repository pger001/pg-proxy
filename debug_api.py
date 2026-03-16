#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug API errors"""

import asyncio
import asyncpg
import yaml
from datetime import datetime

async def test():
    config = yaml.safe_load(open('config.yaml', encoding='utf-8'))
    backend = config['backend']
    
    conn = await asyncpg.connect(
        host=backend['host'],
        port=backend['port'],
        database=backend['database'],
        user=backend['user'],
        password=backend['password']
    )
    
    # Test summary query
    print("Testing summary query...")
    try:
        result = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_queries,
                SUM(estimated_traffic_bytes) as total_traffic_bytes,
                SUM(execution_time_ms) as total_execution_time,
                AVG(execution_time_ms) as avg_execution_time,
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits,
                COUNT(*) - SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_misses
            FROM public.tenant_stats
        """)
        print(f"Summary query result: {dict(result)}")
    except Exception as e:
        print(f"Error in summary query: {e}")
    
    # Test tenant ranking query
    print("\nTesting tenant ranking query...")
    try:
        results = await conn.fetch("""
            SELECT
                tenant_code,
                COUNT(*) as query_count,
                SUM(estimated_traffic_bytes) as traffic_bytes,
                AVG(execution_time_ms) as avg_time,
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits,
                SUM(rows_returned) as total_rows
            FROM public.tenant_stats
            GROUP BY tenant_code
            ORDER BY traffic_bytes DESC
            LIMIT 20
        """)
        print(f"Tenant ranking query result (first 2 rows):")
        for r in results[:2]:
            print(f"  {dict(r)}")
    except Exception as e:
        print(f"Error in tenant ranking query: {e}")
    
    await conn.close()

asyncio.run(test())
