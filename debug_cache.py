#!/usr/bin/env python3
"""调试 EXPLAIN 和 MD5 缓存"""

import asyncio
import asyncpg
import yaml
import hashlib
import re
from typing import Optional, Dict, Any


def calculate_sql_md5_v1(sql: str) -> str:
    """当前版本 - 已改进"""
    # 标准化流程：
    # 1. 转小写
    normalized = sql.lower()
    
    # 2. 移除注释
    normalized = re.sub(r'--.*?$', '', normalized, flags=re.MULTILINE)
    normalized = re.sub(r'/\*.*?\*/', '', normalized, flags=re.DOTALL)
    
    # 3. 统一引号为单引号
    normalized = re.sub(r'"([^"]*)"', r"'\1'", normalized)
    
    # 4. 移除操作符周围的空格（=, <, >, !=等)
    normalized = re.sub(r'\s*([=<>!]+)\s*', r'\1', normalized)
    
    # 5. 移除逗号后的多余空格
    normalized = re.sub(r',\s+', ',', normalized)
    
    # 6. 统一所有连续空白字符为单个空格
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # 7. 去除首尾空格
    normalized = normalized.strip()
    
    return hashlib.md5(normalized.encode()).hexdigest()


async def test_explain():
    """测试 EXPLAIN 功能"""
    print("\n" + "=" * 70)
    print("【测试 1】验证 EXPLAIN 功能")
    print("=" * 70)
    
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    backend = config['backend']
    
    # 连接数据库
    conn = await asyncpg.connect(
        host=backend['host'],
        port=backend['port'],
        database=backend['database'],
        user=backend['user'],
        password=backend['password']
    )
    
    print(f"✓ 已连接到 PostgreSQL")
    
    # 测试简单查询的 EXPLAIN
    sql = "SELECT * FROM public.orders WHERE tenant_code = 'TENANT_001' LIMIT 10"
    print(f"\n测试 SQL: {sql}")
    
    try:
        explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
        result = await conn.fetchval(explain_sql)
        
        print(f"\n✓ EXPLAIN 成功")
        print(f"结果类型: {type(result)}")
        
        # fetchval 返回的是 JSON 字符串
        import json
        plan_data = json.loads(result) if isinstance(result, str) else result
        plan = plan_data[0]['Plan']
        
        print(f"\n执行计划详情:")
        print(f"  Node Type: {plan.get('Node Type')}")
        print(f"  Total Cost: {plan.get('Total Cost')}")
        print(f"  Plan Rows: {plan.get('Plan Rows')}")
        print(f"  Plan Width: {plan.get('Plan Width')}")
        
        estimated_traffic = int(plan['Plan Rows'] * plan['Plan Width'])
        print(f"  预估流量: {estimated_traffic} bytes ({estimated_traffic / 1024:.2f} KB)")
        
    except Exception as e:
        print(f"\n✗ EXPLAIN 失败: {e}")
        import traceback
        traceback.print_exc()
    
    await conn.close()


async def test_md5_cache():
    """测试 MD5 缓存标准化"""
    print("\n" + "=" * 70)
    print("【测试 2】验证 MD5 标准化")
    print("=" * 70)
    
    test_cases = [
        (
            "SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 5",
            "SELECT  *  FROM  orders  WHERE  tenant_code='TENANT_001'  LIMIT  5"
        ),
        (
            'SELECT * FROM users WHERE email = "test@example.com"',
            "SELECT * FROM users WHERE email = 'test@example.com'"
        ),
        (
            "SELECT id, name FROM products WHERE status = ' active'",
            "SELECT   id  ,  name   FROM   products   WHERE   status='active'"
        ),
    ]
    
    print("\n改进后的标准化算法:")
    print("-" * 70)
    for i, (sql1, sql2) in enumerate(test_cases, 1):
        md5_1 = calculate_sql_md5_v1(sql1)
        md5_2 = calculate_sql_md5_v1(sql2)
        match = "✓ 匹配" if md5_1 == md5_2 else "✗ 不匹配"
        print(f"\n测试 {i}: {match}")
        print(f"  SQL1: {sql1}")
        print(f"  SQL2: {sql2}")
        print(f"  MD5-1: {md5_1}")
        print(f"  MD5-2: {md5_2}")


async def main():
    """主程序"""
    await test_md5_cache()
    await test_explain()


if __name__ == '__main__':
    asyncio.run(main())
