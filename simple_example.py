#!/usr/bin/env python3
"""
最简单的使用示例 - 5行代码集成流量统计
"""

import asyncio
import yaml
from proxy_pool import ProxyConnectionPool


async def simple_query_example():
    """简单查询示例"""
    
    # 1. 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 2. 初始化连接池
    pool = ProxyConnectionPool(config)
    await pool.initialize()
    print("✓ 连接池已初始化\n")
    
    try:
        # 3. 执行查询（自动记录统计）
        print("执行查询 1: 获取 TENANT_001 的订单...")
        async with pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT order_id, product_name, amount, status
                FROM orders
                WHERE tenant_code = 'TENANT_001'
                LIMIT 5
            """)
            
            print(f"  找到 {len(result)} 条订单:")
            for row in result:
                print(f"    - 订单 #{row['order_id']}: {row['product_name']} ${row['amount']}")
        
        print()
        await asyncio.sleep(1)
        
        # 4. 再执行一个查询
        print("执行查询 2: 获取 TENANT_002 的用户统计...")
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(amount) as total_amount
                FROM orders
                WHERE tenant_code = 'TENANT_002'
                  AND status = 'completed'
            """)
            
            print(f"  订单总数: {result['total_orders']}")
            print(f"  总金额: ${result['total_amount']}")
        
        print()
        await asyncio.sleep(1)
        
        # 5. 查看统计
        stats = pool.get_stats()
        print("\n" + "=" * 60)
        print("📊 统计信息")
        print("=" * 60)
        print(f"EXPLAIN 缓存: {stats['cache_size']} 条")
        print(f"连接池: {stats['pool_free']} 空闲 / {stats['pool_size']} 总数")
        print(f"日志文件: {config['logging']['log_file']}")
        print(f"\n✓ 所有查询统计已自动记录到日志文件")
        print("=" * 60)
        
    finally:
        # 6. 关闭连接池
        await pool.close()


async def main():
    print("\n" + "=" * 60)
    print("  PostgreSQL Gateway - 最简单使用示例")
    print("=" * 60)
    print()
    
    await simple_query_example()
    
    print("\n💡 下一步:")
    print("  1. 查看日志: cat tenant_stats.log | tail -2 | jq .")
    print("  2. 可视化: python visualize_stats.py")
    print("  3. 完整演示: python demo_traffic_stats.py")
    print()


if __name__ == '__main__':
    asyncio.run(main())
