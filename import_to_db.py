#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 tenant_stats.log 数据导入到 PostgreSQL 数据库
"""

import json
import asyncpg
import yaml
from pathlib import Path
import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LogImporter:
    """日志导入器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.conn = None
    
    async def connect(self):
        """连接数据库"""
        backend = self.config['backend']
        self.conn = await asyncpg.connect(
            host=backend['host'],
            port=backend['port'],
            database=backend['database'],
            user=backend['user'],
            password=backend['password']
        )
        logger.info("✓ 已连接到 PostgreSQL")
    
    async def create_table(self):
        """创建统计表"""
        create_sql = """
        SET search_path TO public;
        
        CREATE TABLE IF NOT EXISTS tenant_stats (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            tenant_code VARCHAR(100),
            sql_length INTEGER,
            sql_preview TEXT,
            execution_time_ms FLOAT,
            rows_returned INTEGER,
            total_cost FLOAT,
            estimated_rows INTEGER,
            estimated_traffic_bytes INTEGER,
            estimated_traffic_mb FLOAT,
            from_cache BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT idx_timestamp_tenant UNIQUE (timestamp, tenant_code)
        );
        
        CREATE INDEX IF NOT EXISTS idx_tenant_code ON public.tenant_stats(tenant_code);
        CREATE INDEX IF NOT EXISTS idx_timestamp ON public.tenant_stats(timestamp);
        CREATE INDEX IF NOT EXISTS idx_execution_time ON public.tenant_stats(execution_time_ms);
        CREATE INDEX IF NOT EXISTS idx_traffic ON public.tenant_stats(estimated_traffic_bytes);
        """
        
        try:
            await self.conn.execute(create_sql)
            logger.info("✓ 表 tenant_stats 已创建/已存在")
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            raise
    
    async def import_logs(self, log_file: str, skip_existing: bool = True):
        """导入日志文件"""
        if not Path(log_file).exists():
            logger.error(f"日志文件不存在: {log_file}")
            return 0
        
        imported_count = 0
        skipped_count = 0
        
        with open(log_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    record = json.loads(line)
                    
                    # 解析时间戳 - 先做这个，然后在后续使用
                    timestamp_str = record.get('timestamp')
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except:
                            timestamp = datetime.now()
                    else:
                        timestamp = datetime.now()
                    
                    # 检查是否已存在（如果启用跳过）
                    if skip_existing:
                        existing = await self.conn.fetchval(
                            "SELECT id FROM public.tenant_stats WHERE timestamp = $1 AND tenant_code = $2",
                            timestamp,
                            record.get('tenant_code', 'UNKNOWN')
                        )
                        if existing:
                            skipped_count += 1
                            continue
                    
                    # 插入记录
                    insert_sql = """
                    INSERT INTO public.tenant_stats (
                        timestamp, tenant_code, sql_length, sql_preview,
                        execution_time_ms, rows_returned, total_cost,
                        estimated_rows, estimated_traffic_bytes, estimated_traffic_mb,
                        from_cache
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (timestamp, tenant_code) DO NOTHING
                    """
                    
                    await self.conn.execute(
                        insert_sql,
                        timestamp,
                        record.get('tenant_code', 'UNKNOWN'),
                        record.get('sql_length'),
                        record.get('sql_preview'),
                        record.get('execution_time_ms'),
                        record.get('rows_returned'),
                        record.get('total_cost'),
                        record.get('estimated_rows'),
                        record.get('estimated_traffic_bytes'),
                        record.get('estimated_traffic_mb'),
                        record.get('from_cache', False)
                    )
                    
                    imported_count += 1
                    
                    if imported_count % 1000 == 0:
                        logger.info(f"已导入 {imported_count} 条记录...")
                
                except json.JSONDecodeError as e:
                    logger.warning(f"第 {line_num} 行 JSON 解析错误: {e}")
                except Exception as e:
                    logger.error(f"第 {line_num} 行导入失败: {e}")
        
        logger.info(f"✓ 导入完成: {imported_count} 条新记录，{skipped_count} 条重复记录")
        return imported_count
    
    async def get_stats_summary(self) -> dict:
        """获取统计摘要"""
        result = await self.conn.fetchrow("""
            SELECT
                COUNT(*) as total_queries,
                SUM(estimated_traffic_bytes) as total_traffic_bytes,
                SUM(execution_time_ms) as total_time_ms,
                SUM(rows_returned) as total_rows,
                AVG(execution_time_ms) as avg_time_ms,
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits,
                COUNT(*) - SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_misses
            FROM public.tenant_stats
        """)
        
        return {
            'total_queries': result['total_queries'] or 0,
            'total_traffic_bytes': result['total_traffic_bytes'] or 0,
            'total_traffic_mb': (result['total_traffic_bytes'] or 0) / 1024 / 1024,
            'total_time_ms': result['total_time_ms'] or 0,
            'total_rows': result['total_rows'] or 0,
            'avg_time_ms': result['avg_time_ms'] or 0,
            'cache_hits': result['cache_hits'] or 0,
            'cache_misses': result['cache_misses'] or 0
        }
    
    async def close(self):
        """关闭连接"""
        if self.conn:
            await self.conn.close()
            logger.info("✓ 数据库连接已关闭")


async def main():
    """主函数"""
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    importer = LogImporter(config)
    
    try:
        # 连接数据库
        await importer.connect()
        
        # 创建表
        await importer.create_table()
        
        # 导入日志
        log_file = config['logging']['log_file']
        imported = await importer.import_logs(log_file)
        
        # 显示统计
        print("\n" + "=" * 60)
        stats = await importer.get_stats_summary()
        print("📊 数据库统计摘要")
        print("=" * 60)
        print(f"总查询数:     {stats['total_queries']:,}")
        print(f"总流量:       {stats['total_traffic_bytes']:,} bytes ({stats['total_traffic_mb']:.2f} MB)")
        print(f"总执行时间:   {stats['total_time_ms']:.2f} ms")
        print(f"平均执行时间: {stats['avg_time_ms']:.2f} ms")
        print(f"缓存命中:     {stats['cache_hits']:,}")
        print(f"缓存未命中:   {stats['cache_misses']:,}")
        print("=" * 60 + "\n")
        
        if imported > 0:
            print(f"✓ 本次导入了 {imported} 条新记录到 tenant_stats 表")
        else:
            print("✓ 所有记录已经在数据库中")
        
    except Exception as e:
        logger.error(f"导入失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await importer.close()


if __name__ == '__main__':
    asyncio.run(main())
