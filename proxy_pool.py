#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL Connection Pool with Stats Tracking
基于连接池的租户统计代理（更实用的方案）
"""

import asyncio
import hashlib
import json
import re
import yaml
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncpg
from asyncpg.pool import Pool
import aiofiles
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StatsConnection:
    """带统计功能的连接包装器"""
    
    def __init__(self, real_conn, tracker):
        self._conn = real_conn
        self._tracker = tracker
    
    async def execute(self, query, *args, **kwargs):
        """执行 SQL（无返回结果）"""
        start_time = asyncio.get_event_loop().time()
        result = await self._conn.execute(query, *args, **kwargs)
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # 异步统计（不阻塞）
        asyncio.create_task(
            self._tracker.track_query(query, execution_time, 0)
        )
        
        return result
    
    async def fetch(self, query, *args, **kwargs):
        """查询并返回所有结果"""
        start_time = asyncio.get_event_loop().time()
        result = await self._conn.fetch(query, *args, **kwargs)
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # 异步统计
        asyncio.create_task(
            self._tracker.track_query(query, execution_time, len(result))
        )
        
        return result
    
    async def fetchrow(self, query, *args, **kwargs):
        """查询并返回单行"""
        start_time = asyncio.get_event_loop().time()
        result = await self._conn.fetchrow(query, *args, **kwargs)
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # 异步统计
        asyncio.create_task(
            self._tracker.track_query(query, execution_time, 1 if result else 0)
        )
        
        return result
    
    async def fetchval(self, query, *args, **kwargs):
        """查询并返回单个值"""
        start_time = asyncio.get_event_loop().time()
        result = await self._conn.fetchval(query, *args, **kwargs)
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # 异步统计
        asyncio.create_task(
            self._tracker.track_query(query, execution_time, 1 if result else 0)
        )
        
        return result
    
    def __getattr__(self, name):
        """代理其他方法到真实连接"""
        return getattr(self._conn, name)


class TenantTracker:
    """租户流量追踪器"""
    
    def __init__(self, pool: Pool, log_file: str, enable_cache: bool = True):
        self.pool = pool
        self.log_file = log_file
        self.enable_cache = enable_cache
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.stats_queue = asyncio.Queue()
        self.running = False
        
    def extract_tenant_code(self, sql: str) -> Optional[str]:
        """从 SQL 中提取 tenant_code"""
        cleaned_sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
        cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL)
        
        patterns = [
            r"tenant_code\s*=\s*'([^']+)'",
            r"tenant_id\s*=\s*'([^']+)'",
            r"org_code\s*=\s*'([^']+)'",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_sql, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def calculate_sql_md5(self, sql: str) -> str:
        """计算 SQL MD5"""
        # 标准化流程：
        # 1. 转小写
        normalized = sql.lower()
        
        # 2. 移除注释
        normalized = re.sub(r'--.*?$', '', normalized, flags=re.MULTILINE)
        normalized = re.sub(r'/\*.*?\*/', '', normalized, flags=re.DOTALL)
        
        # 3. 统一引号为单引号
        normalized = re.sub(r'"([^"]*)"', r"'\1'", normalized)
        
        # 4. 移除操作符周围的空格（=, <, >, !=等）
        normalized = re.sub(r'\s*([=<>!]+)\s*', r'\1', normalized)
        
        # 5. 移除逗号后的多余空格
        normalized = re.sub(r',\s+', ',', normalized)
        
        # 6. 统一所有连续空白字符为单个空格
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # 7. 去除首尾空格
        normalized = normalized.strip()
        
        return hashlib.md5(normalized.encode()).hexdigest()
    
    async def get_explain_stats(self, sql: str) -> Optional[Dict[str, Any]]:
        """获取 EXPLAIN 统计"""
        if not self.enable_cache:
            return await self._do_explain(sql)
        
        sql_md5 = self.calculate_sql_md5(sql)
        
        # 检查缓存
        if sql_md5 in self.cache:
            stats = self.cache[sql_md5].copy()
            stats['from_cache'] = True
            return stats
        
        # 执行 EXPLAIN
        stats = await self._do_explain(sql)
        if stats:
            self.cache[sql_md5] = {k: v for k, v in stats.items() if k != 'from_cache'}
        
        return stats
    
    async def _do_explain(self, sql: str) -> Optional[Dict[str, Any]]:
        """执行 EXPLAIN"""
        try:
            async with self.pool.acquire() as conn:
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
                result = await conn.fetchval(explain_sql)
                
                # fetchval 返回的是 JSON 字符串，需要解析
                import json
                plan_data = json.loads(result) if isinstance(result, str) else result
                plan = plan_data[0]['Plan']
                
                return {
                    'total_cost': plan['Total Cost'],
                    'plan_rows': plan['Plan Rows'],
                    'plan_width': plan['Plan Width'],
                    'estimated_traffic': int(plan['Plan Rows'] * plan['Plan Width']),
                    'from_cache': False
                }
        except Exception as e:
            logger.debug(f"EXPLAIN 失败: {e}")
            return None
    
    async def track_query(self, sql: str, execution_time_ms: float, rows_returned: int):
        """追踪查询"""
        # 跳过内部查询
        if sql.strip().upper().startswith('EXPLAIN'):
            return
        
        # 提取租户
        tenant_code = self.extract_tenant_code(sql)
        
        # 获取 EXPLAIN 统计（异步，不阻塞）
        stats = await self.get_explain_stats(sql)
        
        # 加入队列
        await self.stats_queue.put({
            'timestamp': datetime.now().isoformat(),
            'tenant_code': tenant_code or 'UNKNOWN',
            'sql_length': len(sql),
            'sql_preview': sql[:100].replace('\n', ' '),
            'execution_time_ms': round(execution_time_ms, 2),
            'rows_returned': rows_returned,
            'total_cost': stats['total_cost'] if stats else None,
            'estimated_rows': stats['plan_rows'] if stats else None,
            'estimated_traffic_bytes': stats['estimated_traffic'] if stats else None,
            'estimated_traffic_mb': round(stats['estimated_traffic'] / 1024 / 1024, 2) if stats else None,
            'from_cache': stats['from_cache'] if stats else None
        })
    
    async def start_writer(self):
        """启动日志写入协程"""
        self.running = True
        buffer = []
        
        async def flush_buffer():
            if not buffer:
                return
            try:
                async with aiofiles.open(self.log_file, mode='a', encoding='utf-8') as f:
                    for entry in buffer:
                        await f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                logger.info(f"✓ 已写入 {len(buffer)} 条统计记录")
                buffer.clear()
            except Exception as e:
                logger.error(f"写入日志失败: {e}")
        
        while self.running:
            try:
                # 等待数据或超时
                entry = await asyncio.wait_for(self.stats_queue.get(), timeout=5.0)
                buffer.append(entry)
                
                # 每 10 条或队列空时刷新
                if len(buffer) >= 10 or self.stats_queue.empty():
                    await flush_buffer()
                    
            except asyncio.TimeoutError:
                # 超时也刷新
                await flush_buffer()
            except Exception as e:
                logger.error(f"写入协程错误: {e}")
        
        # 停止时刷新剩余数据
        await flush_buffer()
    
    async def stop_writer(self):
        """停止写入协程"""
        self.running = False


class ProxyConnectionPool:
    """带统计的连接池"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool: Optional[Pool] = None
        self.tracker: Optional[TenantTracker] = None
        self.writer_task = None
        
    async def initialize(self):
        """初始化连接池"""
        backend = self.config['backend']
        
        # 创建连接池
        self.pool = await asyncpg.create_pool(
            host=backend['host'],
            port=backend['port'],
            database=backend['database'],
            user=backend['user'],
            password=backend['password'],
            min_size=5,
            max_size=self.config['gateway']['max_connections']
        )
        
        # 创建追踪器
        self.tracker = TenantTracker(
            self.pool,
            self.config['logging']['log_file'],
            self.config['logging']['enable_cache']
        )
        
        # 启动写入协程
        self.writer_task = asyncio.create_task(self.tracker.start_writer())
        
        logger.info("✓ 连接池已初始化")
        logger.info(f"  后端: {backend['host']}:{backend['port']}/{backend['database']}")
        logger.info(f"  日志: {self.config['logging']['log_file']}")
        logger.info(f"  缓存: {'启用' if self.config['logging']['enable_cache'] else '禁用'}")
    
    @asynccontextmanager
    async def acquire(self):
        """获取连接"""
        async with self.pool.acquire() as conn:
            yield StatsConnection(conn, self.tracker)
    
    async def close(self):
        """关闭连接池"""
        logger.info("正在关闭连接池...")
        
        # 停止写入协程
        if self.tracker:
            await self.tracker.stop_writer()
        
        # 等待写入完成
        if self.writer_task:
            await self.writer_task
        
        # 关闭连接池
        if self.pool:
            await self.pool.close()
        
        logger.info("连接池已关闭")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'cache_size': len(self.tracker.cache) if self.tracker else 0,
            'queue_size': self.tracker.stats_queue.qsize() if self.tracker else 0,
            'pool_size': self.pool.get_size() if self.pool else 0,
            'pool_free': self.pool.get_idle_size() if self.pool else 0
        }


async def main():
    """示例使用"""
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 创建代理连接池
    proxy_pool = ProxyConnectionPool(config)
    await proxy_pool.initialize()
    
    logger.info("=" * 60)
    logger.info("🚀 PostgreSQL 代理已启动（应用层）")
    logger.info("💡 在你的应用中使用 proxy_pool.acquire() 获取连接")
    logger.info("=" * 60)
    
    try:
        # 示例查询
        logger.info("\n示例查询：")
        
        test_queries = [
            "SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 10",
            "SELECT COUNT(*) FROM users WHERE tenant_code = 'TENANT_001'",
            "SELECT * FROM products WHERE tenant_code = 'TENANT_002' LIMIT 5",
        ]
        
        for query in test_queries:
            logger.info(f"\n执行: {query[:50]}...")
            async with proxy_pool.acquire() as conn:
                try:
                    result = await conn.fetch(query)
                    logger.info(f"  -> 返回 {len(result)} 行")
                except Exception as e:
                    logger.error(f"  -> 错误: {e}")
            
            await asyncio.sleep(0.5)
        
        # 显示统计
        await asyncio.sleep(2)  # 等待统计写入
        stats = proxy_pool.get_stats()
        logger.info(f"\n📊 统计信息:")
        logger.info(f"  缓存大小: {stats['cache_size']}")
        logger.info(f"  队列大小: {stats['queue_size']}")
        logger.info(f"  连接池: {stats['pool_free']}/{stats['pool_size']}")
        
        logger.info("\n按 Ctrl+C 停止...")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("\n收到停止信号")
    finally:
        await proxy_pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见!")
