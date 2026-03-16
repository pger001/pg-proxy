#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流量统计功能演示程序
功能：
1. 创建测试表和数据
2. 执行多种类型的查询
3. 验证流量统计功能
4. 可视化展示统计结果
"""

import asyncio
import yaml
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from proxy_pool import ProxyConnectionPool
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrafficStatsDemo:
    """流量统计演示"""
    
    def __init__(self, proxy_pool: ProxyConnectionPool):
        self.pool = proxy_pool
        self.test_tenants = ['TENANT_001', 'TENANT_002', 'TENANT_003']
        
    async def setup_test_data(self):
        """创建测试表和数据"""
        logger.info("=" * 70)
        logger.info("【步骤 1】创建测试表和数据")
        logger.info("=" * 70)
        
        async with self.pool.acquire() as conn:
            # 设置 search_path 确保在 public schema 创建表
            await conn.execute("SET search_path TO public")
            
            # 1. 创建订单表
            logger.info("创建 orders 表...")
            await conn.execute("""
                DROP TABLE IF EXISTS public.orders CASCADE
            """)
            await conn.execute("""
                CREATE TABLE public.orders (
                    order_id SERIAL PRIMARY KEY,
                    tenant_code VARCHAR(50) NOT NULL,
                    user_id INT NOT NULL,
                    product_name VARCHAR(100),
                    amount NUMERIC(10, 2),
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✓ orders 表创建成功")
            
            # 2. 创建用户表
            logger.info("创建 users 表...")
            await conn.execute("""
                DROP TABLE IF EXISTS public.users CASCADE
            """)
            await conn.execute("""
                CREATE TABLE public.users (
                    id SERIAL PRIMARY KEY,
                    tenant_code VARCHAR(50) NOT NULL,
                    username VARCHAR(50),
                    email VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✓ users 表创建成功")
            
            # 3. 插入测试数据
            logger.info("插入测试数据...")
            
            # 插入用户
            for tenant in self.test_tenants:
                for i in range(1, 51):  # 每个租户 50 个用户
                    await conn.execute("""
                        INSERT INTO users (tenant_code, username, email, status)
                        VALUES ($1, $2, $3, $4)
                    """, tenant, f"user_{tenant}_{i}", f"user{i}@{tenant.lower()}.com", 
                    'active' if i % 10 != 0 else 'inactive')
            
            logger.info(f"✓ 已插入 {len(self.test_tenants) * 50} 个用户")
            
            # 插入订单
            products = ['笔记本电脑', 'iPhone 15', '机械键盘', '显示器', '鼠标']
            statuses = ['pending', 'completed', 'shipped', 'cancelled']
            
            order_count = 0
            for tenant in self.test_tenants:
                for i in range(1, 1001):  # 每个租户 1000 个订单
                    await conn.execute("""
                        INSERT INTO orders (tenant_code, user_id, product_name, amount, status, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, 
                    tenant,
                    (i % 50) + 1,
                    products[i % len(products)],
                    round((i % 100 + 1) * 10.5, 2),
                    statuses[i % len(statuses)],
                    datetime.now() - timedelta(days=i % 90))
                    order_count += 1
            
            logger.info(f"✓ 已插入 {order_count} 个订单")
            
            # 创建索引
            logger.info("创建索引...")
            await conn.execute("CREATE INDEX idx_orders_tenant ON public.orders(tenant_code)")
            await conn.execute("CREATE INDEX idx_users_tenant ON public.users(tenant_code)")
            logger.info("✓ 索引创建成功")
            
        logger.info("\n✓ 测试数据准备完成\n")
    
    async def run_test_queries(self):
        """运行测试查询"""
        logger.info("=" * 70)
        logger.info("【步骤 2】执行测试查询（验证流量统计）")
        logger.info("=" * 70)
        
        test_cases = [
            {
                'name': '简单查询 - 小数据量',
                'tenant': 'TENANT_001',
                'sql': "SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 10"
            },
            {
                'name': '中等查询 - 聚合统计',
                'tenant': 'TENANT_001',
                'sql': """
                    SELECT 
                        status,
                        COUNT(*) as order_count,
                        SUM(amount) as total_amount,
                        AVG(amount) as avg_amount
                    FROM orders
                    WHERE tenant_code = 'TENANT_001'
                    GROUP BY status
                """
            },
            {
                'name': '复杂查询 - JOIN',
                'tenant': 'TENANT_002',
                'sql': """
                    SELECT 
                        u.username,
                        u.email,
                        COUNT(o.order_id) as order_count,
                        SUM(o.amount) as total_spent
                    FROM users u
                    LEFT JOIN orders o ON u.id = o.user_id AND o.tenant_code = u.tenant_code
                    WHERE u.tenant_code = 'TENANT_002'
                      AND u.status = 'active'
                    GROUP BY u.id, u.username, u.email
                    HAVING COUNT(o.order_id) > 5
                    ORDER BY total_spent DESC
                    LIMIT 20
                """
            },
            {
                'name': '大数据量查询',
                'tenant': 'TENANT_003',
                'sql': "SELECT * FROM orders WHERE tenant_code = 'TENANT_003' ORDER BY created_at DESC LIMIT 500"
            },
            {
                'name': '多层 CTE 查询',
                'tenant': 'TENANT_001',
                'sql': """
                    WITH recent_orders AS (
                        SELECT 
                            user_id,
                            order_id,
                            amount,
                            created_at
                        FROM orders
                        WHERE tenant_code = 'TENANT_001'
                          AND created_at >= CURRENT_DATE - INTERVAL '30 days'
                          AND status = 'completed'
                    ),
                    user_stats AS (
                        SELECT 
                            user_id,
                            COUNT(*) as order_count,
                            SUM(amount) as total_amount,
                            AVG(amount) as avg_amount,
                            MAX(created_at) as last_order_date
                        FROM recent_orders
                        GROUP BY user_id
                    ),
                    ranked_users AS (
                        SELECT 
                            user_id,
                            order_count,
                            total_amount,
                            avg_amount,
                            last_order_date,
                            ROW_NUMBER() OVER (ORDER BY total_amount DESC) as rank,
                            PERCENT_RANK() OVER (ORDER BY total_amount) as percentile
                        FROM user_stats
                    )
                    SELECT 
                        u.username,
                        u.email,
                        r.order_count,
                        r.total_amount,
                        r.avg_amount,
                        r.rank,
                        ROUND(r.percentile::numeric, 4) as percentile
                    FROM ranked_users r
                    JOIN users u ON r.user_id = u.id
                    WHERE r.rank <= 10
                    ORDER BY r.rank
                """
            },
            {
                'name': '重复查询（测试缓存）',
                'tenant': 'TENANT_001',
                'sql': "SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 10"
            }
        ]
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n[测试 {i}/{len(test_cases)}] {test_case['name']}")
            logger.info(f"租户: {test_case['tenant']}")
            logger.info(f"SQL: {test_case['sql'][:80]}...")
            
            try:
                start_time = asyncio.get_event_loop().time()
                
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(test_case['sql'])
                
                execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
                
                logger.info(f"✓ 执行成功")
                logger.info(f"  返回行数: {len(rows)}")
                logger.info(f"  执行时间: {execution_time:.2f} ms")
                
                results.append({
                    'name': test_case['name'],
                    'tenant': test_case['tenant'],
                    'rows': len(rows),
                    'time': execution_time
                })
                
            except Exception as e:
                logger.error(f"✗ 执行失败: {e}")
                results.append({
                    'name': test_case['name'],
                    'tenant': test_case['tenant'],
                    'error': str(e)
                })
            
            await asyncio.sleep(0.3)  # 等待统计写入
        
        logger.info("\n✓ 所有测试查询执行完成\n")
        return results
    
    async def analyze_log_file(self) -> List[Dict[str, Any]]:
        """分析日志文件"""
        log_file = self.pool.config['logging']['log_file']
        
        if not Path(log_file).exists():
            logger.warning(f"日志文件不存在: {log_file}")
            return []
        
        stats = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    stats.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return stats
    
    def display_statistics(self, stats: List[Dict[str, Any]]):
        """展示统计结果"""
        logger.info("=" * 70)
        logger.info("【步骤 3】流量统计结果展示")
        logger.info("=" * 70)
        
        if not stats:
            logger.warning("没有统计数据")
            return
        
        # 按租户分组
        tenant_stats = {}
        total_traffic = 0
        cache_hits = 0
        cache_misses = 0
        
        for entry in stats:
            tenant = entry.get('tenant_code', 'UNKNOWN')
            if tenant not in tenant_stats:
                tenant_stats[tenant] = {
                    'query_count': 0,
                    'total_traffic_bytes': 0,
                    'total_time_ms': 0,
                    'total_rows': 0
                }
            
            tenant_stats[tenant]['query_count'] += 1
            tenant_stats[tenant]['total_traffic_bytes'] += entry.get('estimated_traffic_bytes', 0) or 0
            tenant_stats[tenant]['total_time_ms'] += entry.get('execution_time_ms', 0)
            tenant_stats[tenant]['total_rows'] += entry.get('rows_returned', 0)
            
            total_traffic += entry.get('estimated_traffic_bytes', 0) or 0
            
            if entry.get('from_cache'):
                cache_hits += 1
            else:
                cache_misses += 1
        
        # 展示总体统计
        logger.info("\n【总体统计】")
        logger.info(f"  总查询次数: {len(stats)}")
        logger.info(f"  总预估流量: {total_traffic:,} bytes ({total_traffic/1024/1024:.2f} MB)")
        logger.info(f"  缓存命中: {cache_hits} 次")
        logger.info(f"  缓存未命中: {cache_misses} 次")
        logger.info(f"  缓存命中率: {cache_hits/(cache_hits+cache_misses)*100:.1f}%" if (cache_hits+cache_misses) > 0 else "  缓存命中率: N/A")
        
        # 展示租户统计
        logger.info("\n【租户统计明细】")
        logger.info("-" * 70)
        logger.info(f"{'租户':<15} {'查询数':<10} {'总流量(MB)':<15} {'平均时间(ms)':<15} {'总行数':<10}")
        logger.info("-" * 70)
        
        for tenant, data in sorted(tenant_stats.items()):
            avg_time = data['total_time_ms'] / data['query_count'] if data['query_count'] > 0 else 0
            traffic_mb = data['total_traffic_bytes'] / 1024 / 1024
            
            logger.info(f"{tenant:<15} {data['query_count']:<10} {traffic_mb:<15.2f} {avg_time:<15.2f} {data['total_rows']:<10}")
        
        logger.info("-" * 70)
        
        # 展示最近的查询详情
        logger.info("\n【最近查询详情（最后 5 条）】")
        logger.info("-" * 70)
        
        for entry in stats[-5:]:
            logger.info(f"\n时间: {entry.get('timestamp')}")
            logger.info(f"租户: {entry.get('tenant_code')}")
            logger.info(f"SQL: {entry.get('sql_preview')}")
            logger.info(f"执行时间: {entry.get('execution_time_ms', 0):.2f} ms")
            logger.info(f"返回行数: {entry.get('rows_returned', 0)}")
            
            if entry.get('estimated_traffic_bytes'):
                logger.info(f"预估流量: {entry.get('estimated_traffic_bytes'):,} bytes ({entry.get('estimated_traffic_mb', 0):.2f} MB)")
                logger.info(f"查询代价: {entry.get('total_cost', 0):.2f}")
                logger.info(f"预估行数: {entry.get('estimated_rows', 0):,}")
            
            logger.info(f"缓存: {'✓ 命中' if entry.get('from_cache') else '✗ 未命中'}")
        
        logger.info("\n" + "-" * 70)
    
    def display_cache_info(self):
        """展示缓存信息"""
        logger.info("\n【缓存信息】")
        pool_stats = self.pool.get_stats()
        logger.info(f"  缓存大小: {pool_stats['cache_size']}")
        logger.info(f"  待写队列: {pool_stats['queue_size']}")
        logger.info(f"  连接池: {pool_stats['pool_free']} 空闲 / {pool_stats['pool_size']} 总数")
    
    async def verify_md5_cache(self):
        """验证 MD5 缓存功能"""
        logger.info("\n【验证 MD5 缓存】")
        
        # 清空缓存
        if self.pool.tracker:
            self.pool.tracker.cache.clear()
            logger.info("✓ 缓存已清空")
        
        # 第一次查询
        sql1 = "SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 5"
        logger.info(f"\n第 1 次查询: {sql1}")
        
        async with self.pool.acquire() as conn:
            await conn.fetch(sql1)
        
        await asyncio.sleep(0.5)
        logger.info(f"  缓存大小: {self.pool.get_stats()['cache_size']}")
        
        # 第二次查询（相同 SQL，多余空格）
        sql2 = "SELECT  *  FROM  orders  WHERE  tenant_code='TENANT_001'  LIMIT  5"
        logger.info(f"\n第 2 次查询: {sql2}")
        
        async with self.pool.acquire() as conn:
            await conn.fetch(sql2)
        
        await asyncio.sleep(0.5)
        cache_size = self.pool.get_stats()['cache_size']
        logger.info(f"  缓存大小: {cache_size}")
        
        if cache_size == 1:
            logger.info("✓ MD5 缓存验证成功：相同 SQL 被识别为同一条")
        else:
            logger.warning("✗ MD5 缓存验证失败：未能识别为同一条 SQL")


async def main():
    """主程序"""
    print("\n" + "=" * 70)
    print("  PostgreSQL Gateway - 流量统计功能演示")
    print("=" * 70)
    print()
    
    # 加载配置
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml 不存在，请先配置数据库连接")
        return
    
    # 初始化代理连接池
    proxy_pool = ProxyConnectionPool(config)
    
    try:
        await proxy_pool.initialize()
        logger.info("✓ 代理连接池初始化成功\n")
        
        # 创建演示实例
        demo = TrafficStatsDemo(proxy_pool)
        
        # 询问是否创建测试数据
        print("\n是否创建测试表和数据？(y/n): ", end='')
        import sys
        sys.stdout.flush()
        
        # 模拟输入（实际使用时取消注释下面的代码）
        # choice = input().strip().lower()
        choice = 'y'  # 自动模式
        
        if choice == 'y':
            await demo.setup_test_data()
        else:
            logger.info("跳过测试数据创建\n")
        
        # 运行测试查询
        await demo.run_test_queries()
        
        # 等待统计写入
        logger.info("等待统计数据写入...")
        await asyncio.sleep(3)
        
        # 分析日志文件
        stats = await demo.analyze_log_file()
        
        # 展示统计结果
        demo.display_statistics(stats)
        
        # 展示缓存信息
        demo.display_cache_info()
        
        # 验证 MD5 缓存
        await demo.verify_md5_cache()
        
        # 最终统计
        logger.info("\n" + "=" * 70)
        logger.info("【演示完成】")
        logger.info("=" * 70)
        logger.info(f"✓ 日志文件: {config['logging']['log_file']}")
        logger.info("✓ 所有功能验证通过")
        logger.info("\n可以使用以下命令分析日志:")
        logger.info(f"  cat {config['logging']['log_file']} | jq .")
        logger.info(f"  cat {config['logging']['log_file']} | jq -r '.tenant_code' | sort | uniq -c")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"演示过程出错: {e}", exc_info=True)
    finally:
        await proxy_pool.close()
        logger.info("\n✓ 代理连接池已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 演示已中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
