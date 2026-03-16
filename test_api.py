#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test API and check database"""

import asyncio
import asyncpg
import yaml
import json

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
    
    # Check if table exists and has data
    count = await conn.fetchval("SELECT COUNT(*) FROM public.tenant_stats")
    print(f"Total records in tenant_stats: {count}")
    
    # Get sample data
    sample = await conn.fetchrow("""
        SELECT * FROM public.tenant_stats LIMIT 1
    """)
    print(f"\nSample record:\n{json.dumps(dict(sample), indent=2, default=str)}")
    
    # Get summary
    summary = await conn.fetchrow("""
        SELECT
            COUNT(*) as total_queries,
            SUM(estimated_traffic_bytes) as total_traffic_bytes,
            SUM(execution_time_ms) as total_execution_time,
            AVG(execution_time_ms) as avg_execution_time,
            SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits
        FROM public.tenant_stats
    """)
    print(f"\nSummary:\n{json.dumps(dict(summary), indent=2, default=str)}")
    
    await conn.close()

asyncio.run(test())
