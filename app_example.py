#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例应用：使用带统计的 PostgreSQL 代理连接池
"""

import asyncio
import yaml
from proxy_pool import ProxyConnectionPool
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TenantApplication:
    """示例多租户应用"""
    
    def __init__(self, proxy_pool: ProxyConnectionPool):
        self.pool = proxy_pool
    
    async def get_tenant_orders(self, tenant_code: str, limit: int = 100):
        """获取租户订单"""
        async with self.pool.acquire() as conn:
            query = f"""
                SELECT order_id, amount, status, created_at
                FROM orders
                WHERE tenant_code = '{tenant_code}'
                ORDER BY created_at DESC
                LIMIT {limit}
            """
            return await conn.fetch(query)
    
    async def get_tenant_stats(self, tenant_code: str):
        """获取租户统计"""
        async with self.pool.acquire() as conn:
            query = f"""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(amount) as total_amount,
                    AVG(amount) as avg_amount
                FROM orders
                WHERE tenant_code = '{tenant_code}'
                  AND status = 'completed'
            """
            return await conn.fetchrow(query)
    
    async def complex_tenant_query(self, tenant_code: str):
        """复杂的多层 CTE 查询"""
        async with self.pool.acquire() as conn:
            query = f"""
                WITH tenant_orders AS (
                    SELECT 
                        order_id,
                        user_id,
                        amount,
                        status,
                        created_at
                    FROM orders
                    WHERE tenant_code = '{tenant_code}'
                      AND created_at >= CURRENT_DATE - INTERVAL '30 days'
                ),
                user_aggregates AS (
                    SELECT 
                        user_id,
                        COUNT(*) as order_count,
                        SUM(amount) as total_spent,
                        AVG(amount) as avg_order_value
                    FROM tenant_orders
                    GROUP BY user_id
                ),
                top_users AS (
                    SELECT 
                        user_id,
                        order_count,
                        total_spent,
                        ROW_NUMBER() OVER (ORDER BY total_spent DESC) as rank
                    FROM user_aggregates
                )
                SELECT 
                    u.username,
                    tu.order_count,
                    tu.total_spent,
                    tu.rank
                FROM top_users tu
                JOIN users u ON tu.user_id = u.id
                WHERE tu.rank <= 20
                ORDER BY tu.rank
            """
            return await conn.fetch(query)


async def simulate_workload(app: TenantApplication):
    """模拟工作负载"""
    tenants = ['TENANT_001', 'TENANT_002', 'TENANT_003']
    
    logger.info("开始模拟工作负载...")
    
    tasks = []
    for tenant in tenants:
        # 每个租户执行多种查询
        tasks.append(app.get_tenant_orders(tenant, limit=50))
        tasks.append(app.get_tenant_stats(tenant))
        tasks.append(app.complex_tenant_query(tenant))
    
    # 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = len(results) - success_count
    
    logger.info(f"工作负载完成: {success_count} 成功, {error_count} 失败")
    
    return results


async def main():
    """主程序"""
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 初始化代理连接池
    proxy_pool = ProxyConnectionPool(config)
    await proxy_pool.initialize()
    
    # 创建应用
    app = TenantApplication(proxy_pool)
    
    logger.info("=" * 60)
    logger.info("🚀 示例应用已启动")
    logger.info("=" * 60)
    
    try:
        # 运行示例查询
        logger.info("\n📝 示例 1: 获取租户订单")
        try:
            orders = await app.get_tenant_orders('TENANT_001', limit=10)
            logger.info(f"  -> 找到 {len(orders)} 条订单")
        except Exception as e:
            logger.error(f"  -> 错误: {e}")
        
        await asyncio.sleep(1)
        
        logger.info("\n📊 示例 2: 获取租户统计")
        try:
            stats = await app.get_tenant_stats('TENANT_001')
            if stats:
                logger.info(f"  -> 订单总数: {stats['total_orders']}")
                logger.info(f"  -> 总金额: {stats['total_amount']}")
        except Exception as e:
            logger.error(f"  -> 错误: {e}")
        
        await asyncio.sleep(1)
        
        logger.info("\n🔥 示例 3: 复杂 CTE 查询")
        try:
            top_users = await app.complex_tenant_query('TENANT_001')
            logger.info(f"  -> 找到 {len(top_users)} 个顶级用户")
        except Exception as e:
            logger.error(f"  -> 错误: {e}")
        
        await asyncio.sleep(1)
        
        logger.info("\n💪 示例 4: 模拟并发工作负载")
        await simulate_workload(app)
        
        # 等待统计写入
        await asyncio.sleep(2)
        
        # 显示统计
        stats_info = proxy_pool.get_stats()
        logger.info("\n" + "=" * 60)
        logger.info("📊 代理统计信息")
        logger.info("=" * 60)
        logger.info(f"EXPLAIN 缓存大小: {stats_info['cache_size']}")
        logger.info(f"待写入队列: {stats_info['queue_size']}")
        logger.info(f"连接池状态: {stats_info['pool_free']} 空闲 / {stats_info['pool_size']} 总数")
        logger.info(f"\n✓ 所有统计已写入: {config['logging']['log_file']}")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n收到中断信号")
    finally:
        await proxy_pool.close()
        logger.info("应用已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见!")
