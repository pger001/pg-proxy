#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 租户统计工具
功能：提取 SQL 中的 tenant_code，分析执行计划，计算预估流量并异步记录
"""

import re
import hashlib
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import aiofiles


class TenantStatsCollector:
    """PostgreSQL 租户统计收集器"""
    
    def __init__(self, db_config: Dict[str, str], log_file: str = "tenant_stats.log"):
        """
        初始化收集器
        
        Args:
            db_config: 数据库连接配置 {host, port, database, user, password}
            log_file: 日志文件路径
        """
        self.db_config = db_config
        self.log_file = log_file
        self.cache: Dict[str, Dict[str, Any]] = {}  # MD5 -> explain result cache
        
    def extract_tenant_code(self, sql: str) -> Optional[str]:
        """
        从 SQL 中提取 tenant_code
        
        支持多种模式：
        - WHERE tenant_code = 'xxx'
        - WHERE tenant_code IN ('xxx')
        - AND tenant_code = 'xxx'
        - tenant_code::text = 'xxx'
        
        Args:
            sql: SQL 语句
            
        Returns:
            tenant_code 值，如果未找到则返回 None
        """
        # 移除注释和换行，便于匹配
        cleaned_sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
        cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL)
        
        # 多种模式匹配
        patterns = [
            r"tenant_code\s*=\s*'([^']+)'",
            r"tenant_code\s*=\s*\"([^\"]+)\"",
            r"tenant_code\s+IN\s*\(\s*'([^']+)'",
            r"tenant_code::text\s*=\s*'([^']+)'",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_sql, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def calculate_sql_md5(self, sql: str) -> str:
        """
        计算 SQL 的 MD5 哈希值
        
        Args:
            sql: SQL 语句
            
        Returns:
            MD5 哈希值（32位16进制字符串）
        """
        # 标准化 SQL：移除多余空格、换行，转小写
        normalized_sql = re.sub(r'\s+', ' ', sql.strip()).lower()
        return hashlib.md5(normalized_sql.encode('utf-8')).hexdigest()
    
    def get_explain_result(self, sql: str) -> Dict[str, Any]:
        """
        获取 SQL 的执行计划（支持 MD5 缓存）
        
        Args:
            sql: SQL 语句
            
        Returns:
            包含执行计划信息的字典
            {
                'total_cost': float,
                'plan_rows': int,
                'plan_width': int,
                'estimated_traffic': int,  # bytes
                'from_cache': bool
            }
        """
        sql_md5 = self.calculate_sql_md5(sql)
        
        # 检查缓存
        if sql_md5 in self.cache:
            result = self.cache[sql_md5].copy()
            result['from_cache'] = True
            return result
        
        # 执行 EXPLAIN
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # 执行 EXPLAIN (FORMAT JSON)
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            cursor.execute(explain_sql)
            explain_result = cursor.fetchone()[0]
            
            # 解析结果
            plan = explain_result[0]['Plan']
            total_cost = plan['Total Cost']
            plan_rows = plan['Plan Rows']
            plan_width = plan['Plan Width']
            estimated_traffic = plan_rows * plan_width
            
            result = {
                'total_cost': total_cost,
                'plan_rows': plan_rows,
                'plan_width': plan_width,
                'estimated_traffic': estimated_traffic,
                'from_cache': False
            }
            
            # 存入缓存
            self.cache[sql_md5] = {
                'total_cost': total_cost,
                'plan_rows': plan_rows,
                'plan_width': plan_width,
                'estimated_traffic': estimated_traffic
            }
            
            return result
            
        except Exception as e:
            raise Exception(f"EXPLAIN 执行失败: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    async def write_stats_async(self, tenant_code: str, stats: Dict[str, Any]):
        """
        异步写入统计结果到日志文件
        
        Args:
            tenant_code: 租户代码
            stats: 统计信息字典
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = {
            'timestamp': timestamp,
            'tenant_code': tenant_code,
            'total_cost': stats['total_cost'],
            'plan_rows': stats['plan_rows'],
            'plan_width': stats['plan_width'],
            'estimated_traffic_bytes': stats['estimated_traffic'],
            'estimated_traffic_mb': round(stats['estimated_traffic'] / 1024 / 1024, 2),
            'from_cache': stats['from_cache']
        }
        
        async with aiofiles.open(self.log_file, mode='a', encoding='utf-8') as f:
            await f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    async def analyze_sql(self, sql: str) -> Dict[str, Any]:
        """
        完整分析流程：提取租户、获取执行计划、写入日志
        
        Args:
            sql: SQL 语句
            
        Returns:
            分析结果字典
        """
        # 1. 提取 tenant_code
        tenant_code = self.extract_tenant_code(sql)
        if not tenant_code:
            raise ValueError("无法从 SQL 中提取 tenant_code")
        
        # 2. 获取执行计划
        stats = self.get_explain_result(sql)
        
        # 3. 异步写入日志
        await self.write_stats_async(tenant_code, stats)
        
        # 4. 返回结果
        return {
            'tenant_code': tenant_code,
            **stats
        }
    
    def clear_cache(self):
        """清空 MD5 缓存"""
        self.cache.clear()
    
    def get_cache_size(self) -> int:
        """获取当前缓存大小"""
        return len(self.cache)


async def main():
    """示例使用"""
    
    # 数据库配置
    db_config = {
        'host': 'localhost',
        'port': '5432',
        'database': 'testdb',
        'user': 'postgres',
        'password': 'postgres'
    }
    
    # 创建收集器
    collector = TenantStatsCollector(db_config, log_file='tenant_stats.log')
    
    # 示例 SQL（包含多层 CTE）
    test_sql = """
    WITH tenant_orders AS (
        SELECT 
            order_id,
            user_id,
            amount,
            created_at
        FROM orders
        WHERE tenant_code = 'TENANT_001'
          AND status = 'completed'
    ),
    user_stats AS (
        SELECT 
            user_id,
            COUNT(*) as order_count,
            SUM(amount) as total_amount
        FROM tenant_orders
        GROUP BY user_id
    ),
    ranked_users AS (
        SELECT 
            user_id,
            order_count,
            total_amount,
            ROW_NUMBER() OVER (ORDER BY total_amount DESC) as rank
        FROM user_stats
    )
    SELECT 
        u.user_id,
        u.username,
        r.order_count,
        r.total_amount,
        r.rank
    FROM ranked_users r
    JOIN users u ON r.user_id = u.id
    WHERE r.rank <= 100
    ORDER BY r.rank;
    """
    
    try:
        # 第一次分析（从数据库获取）
        print("=== 第一次分析 ===")
        result1 = await collector.analyze_sql(test_sql)
        print(f"租户: {result1['tenant_code']}")
        print(f"代价: {result1['total_cost']}")
        print(f"预估行数: {result1['plan_rows']}")
        print(f"行宽: {result1['plan_width']}")
        print(f"预估流量: {result1['estimated_traffic']} bytes ({result1['estimated_traffic']/1024/1024:.2f} MB)")
        print(f"来自缓存: {result1['from_cache']}")
        print(f"当前缓存大小: {collector.get_cache_size()}\n")
        
        # 第二次分析（从缓存获取）
        print("=== 第二次分析（相同 SQL）===")
        result2 = await collector.analyze_sql(test_sql)
        print(f"租户: {result2['tenant_code']}")
        print(f"代价: {result2['total_cost']}")
        print(f"预估流量: {result2['estimated_traffic']} bytes")
        print(f"来自缓存: {result2['from_cache']}")
        print(f"当前缓存大小: {collector.get_cache_size()}\n")
        
        print(f"✓ 统计结果已写入 {collector.log_file}")
        
    except Exception as e:
        print(f"✗ 错误: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
