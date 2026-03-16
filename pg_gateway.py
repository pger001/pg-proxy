#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL Gateway - 租户流量统计代理
客户端 -> Gateway (15432) -> PostgreSQL (5432)
"""

import asyncio
import hashlib
import json
import re
import yaml
from datetime import datetime
from typing import Optional, Dict, Any
import asyncpg
from asyncpg import Connection
import aiofiles
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TenantStatsTracker:
    """租户统计追踪器"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.stats_buffer = []  # 批量写入缓冲区
        
    def extract_tenant_code(self, sql: str) -> Optional[str]:
        """从 SQL 中提取 tenant_code"""
        cleaned_sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
        cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL)
        
        patterns = [
            r"tenant_code\s*=\s*'([^']+)'",
            r"tenant_code\s*=\s*\"([^\"]+)\"",
            r"tenant_code\s+IN\s*\(\s*'([^']+)'",
            r"tenant_code::text\s*=\s*'([^']+)'",
            r"tenant_id\s*=\s*'([^']+)'",
            r"org_code\s*=\s*'([^']+)'",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_sql, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def calculate_sql_md5(self, sql: str) -> str:
        """计算 SQL 的 MD5"""
        normalized_sql = re.sub(r'\s+', ' ', sql.strip()).lower()
        return hashlib.md5(normalized_sql.encode('utf-8')).hexdigest()
    
    async def get_explain_stats(self, conn: Connection, sql: str) -> Optional[Dict[str, Any]]:
        """获取执行计划统计（带缓存）"""
        sql_md5 = self.calculate_sql_md5(sql)
        
        # 检查缓存
        if sql_md5 in self.cache:
            stats = self.cache[sql_md5].copy()
            stats['from_cache'] = True
            return stats
        
        try:
            # 执行 EXPLAIN（不影响主查询）
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            result = await conn.fetchval(explain_sql)
            
            plan = result[0]['Plan']
            stats = {
                'total_cost': plan['Total Cost'],
                'plan_rows': plan['Plan Rows'],
                'plan_width': plan['Plan Width'],
                'estimated_traffic': int(plan['Plan Rows'] * plan['Plan Width']),
                'from_cache': False
            }
            
            # 存入缓存
            self.cache[sql_md5] = {k: v for k, v in stats.items() if k != 'from_cache'}
            
            return stats
            
        except Exception as e:
            logger.warning(f"EXPLAIN 失败: {e}")
            return None
    
    async def record_stats(self, tenant_code: str, sql: str, stats: Optional[Dict[str, Any]], 
                          execution_time_ms: float, rows_returned: int):
        """记录统计信息"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'tenant_code': tenant_code or 'UNKNOWN',
            'sql_length': len(sql),
            'sql_preview': sql[:100].replace('\n', ' '),
            'execution_time_ms': round(execution_time_ms, 2),
            'rows_returned': rows_returned,
        }
        
        if stats:
            log_entry.update({
                'total_cost': stats['total_cost'],
                'estimated_rows': stats['plan_rows'],
                'estimated_traffic_bytes': stats['estimated_traffic'],
                'estimated_traffic_mb': round(stats['estimated_traffic'] / 1024 / 1024, 2),
                'from_cache': stats['from_cache']
            })
        
        # 添加到缓冲区
        self.stats_buffer.append(log_entry)
        
        # 每 10 条刷新一次
        if len(self.stats_buffer) >= 10:
            await self.flush_buffer()
    
    async def flush_buffer(self):
        """刷新缓冲区到文件"""
        if not self.stats_buffer:
            return
        
        try:
            async with aiofiles.open(self.log_file, mode='a', encoding='utf-8') as f:
                for entry in self.stats_buffer:
                    await f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            logger.info(f"已写入 {len(self.stats_buffer)} 条统计记录")
            self.stats_buffer.clear()
            
        except Exception as e:
            logger.error(f"写入日志失败: {e}")


class PostgreSQLGateway:
    """PostgreSQL Gateway 主类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.gateway_host = config['gateway']['listen_host']
        self.gateway_port = config['gateway']['listen_port']
        self.backend_config = config['backend']
        self.max_connections = config['gateway']['max_connections']
        
        # 创建统计追踪器
        self.tracker = TenantStatsTracker(config['logging']['log_file'])
        
        # 连接池（每个客户端连接持有一个后端连接）
        self.active_connections = 0
        
    async def create_backend_connection(self) -> Connection:
        """创建到后端 PostgreSQL 的连接"""
        return await asyncpg.connect(
            host=self.backend_config['host'],
            port=self.backend_config['port'],
            database=self.backend_config['database'],
            user=self.backend_config['user'],
            password=self.backend_config['password']
        )
    
    async def handle_query(self, backend_conn: Connection, sql: str) -> tuple:
        """处理查询请求"""
        start_time = asyncio.get_event_loop().time()
        
        # 1. 提取 tenant_code
        tenant_code = self.tracker.extract_tenant_code(sql)
        
        # 2. 异步获取 EXPLAIN（不阻塞主查询）
        stats_task = None
        if tenant_code:
            stats_task = asyncio.create_task(
                self.tracker.get_explain_stats(backend_conn, sql)
            )
        
        # 3. 执行实际查询
        try:
            result = await backend_conn.fetch(sql)
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # 4. 等待 EXPLAIN 完成（如果有）
            stats = None
            if stats_task:
                try:
                    stats = await asyncio.wait_for(stats_task, timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning("EXPLAIN 超时")
            
            # 5. 记录统计
            await self.tracker.record_stats(
                tenant_code, sql, stats, execution_time, len(result)
            )
            
            return result, None
            
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            return None, str(e)
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理客户端连接"""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"新连接来自: {client_addr}")
        
        if self.active_connections >= self.max_connections:
            logger.warning(f"连接数已达上限 ({self.max_connections})")
            writer.close()
            await writer.wait_closed()
            return
        
        self.active_connections += 1
        backend_conn = None
        
        try:
            # 创建后端连接
            backend_conn = await self.create_backend_connection()
            logger.info(f"为 {client_addr} 创建后端连接成功")
            
            # 简化的命令循环（实际生产需要完整的 PostgreSQL 协议解析）
            # 这里使用简化的文本协议模拟
            writer.write(b"PostgreSQL Gateway Ready\n")
            await writer.drain()
            
            while True:
                # 读取客户端 SQL（简化版，实际需要解析二进制协议）
                data = await reader.readline()
                if not data:
                    break
                
                sql = data.decode('utf-8').strip()
                if not sql:
                    continue
                
                logger.info(f"[{client_addr}] SQL: {sql[:50]}...")
                
                # 处理特殊命令
                if sql.upper() == 'QUIT' or sql.upper() == 'EXIT':
                    writer.write(b"Bye\n")
                    await writer.drain()
                    break
                
                if sql.upper() == 'STATS':
                    # 返回统计信息
                    stats_info = f"Cache Size: {len(self.tracker.cache)}\n"
                    writer.write(stats_info.encode('utf-8'))
                    await writer.drain()
                    continue
                
                # 执行查询
                result, error = await self.handle_query(backend_conn, sql)
                
                if error:
                    writer.write(f"ERROR: {error}\n".encode('utf-8'))
                else:
                    # 返回结果（简化版）
                    response = f"OK: {len(result)} rows\n"
                    for row in result[:5]:  # 只返回前 5 行
                        response += f"{dict(row)}\n"
                    if len(result) > 5:
                        response += f"... and {len(result) - 5} more rows\n"
                    
                    writer.write(response.encode('utf-8'))
                
                await writer.drain()
                
        except Exception as e:
            logger.error(f"处理客户端 {client_addr} 时出错: {e}")
        finally:
            self.active_connections -= 1
            if backend_conn:
                await backend_conn.close()
            writer.close()
            await writer.wait_closed()
            logger.info(f"连接 {client_addr} 已关闭")
    
    async def start(self):
        """启动 Gateway"""
        server = await asyncio.start_server(
            self.handle_client,
            self.gateway_host,
            self.gateway_port
        )
        
        addr = server.sockets[0].getsockname()
        logger.info(f"🚀 PostgreSQL Gateway 已启动")
        logger.info(f"📡 监听地址: {addr[0]}:{addr[1]}")
        logger.info(f"🔗 后端数据库: {self.backend_config['host']}:{self.backend_config['port']}")
        logger.info(f"📊 日志文件: {self.tracker.log_file}")
        logger.info(f"🔢 最大连接数: {self.max_connections}")
        logger.info("=" * 60)
        
        async with server:
            await server.serve_forever()


async def main():
    """主入口"""
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 创建并启动 Gateway
    gateway = PostgreSQLGateway(config)
    
    try:
        await gateway.start()
    except KeyboardInterrupt:
        logger.info("\n正在关闭 Gateway...")
        # 刷新缓冲区
        await gateway.tracker.flush_buffer()
        logger.info("Gateway 已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见!")
