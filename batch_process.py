#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理工具：从文件读取 SQL 并批量分析
"""

import asyncio
import argparse
import yaml
from pathlib import Path
from tenant_stats import TenantStatsCollector


def parse_sql_file(file_path: str) -> list:
    """
    解析 SQL 文件，分割为独立的语句
    
    Args:
        file_path: SQL 文件路径
        
    Returns:
        SQL 语句列表
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 按分号分割，过滤空语句和注释
    statements = []
    for stmt in content.split(';'):
        stmt = stmt.strip()
        if stmt and not stmt.startswith('--'):
            statements.append(stmt + ';')
    
    return statements


async def batch_process(sql_file: str, config_file: str = 'config.yaml'):
    """
    批量处理 SQL 文件
    
    Args:
        sql_file: SQL 文件路径
        config_file: 配置文件路径
    """
    # 加载配置
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    db_config = config['database']
    log_file = config['logging']['log_file']
    
    # 创建收集器
    collector = TenantStatsCollector(db_config, log_file)
    
    # 解析 SQL 文件
    print(f"📂 正在读取 SQL 文件: {sql_file}")
    statements = parse_sql_file(sql_file)
    print(f"✓ 已解析 {len(statements)} 条 SQL 语句\n")
    
    # 批量分析
    success_count = 0
    error_count = 0
    total_traffic = 0
    
    for i, sql in enumerate(statements, 1):
        try:
            result = await collector.analyze_sql(sql)
            
            traffic_mb = result['estimated_traffic'] / 1024 / 1024
            total_traffic += result['estimated_traffic']
            
            cache_flag = "🔄" if result['from_cache'] else "🆕"
            print(f"[{i}/{len(statements)}] {cache_flag} "
                  f"租户: {result['tenant_code']:15} | "
                  f"代价: {result['total_cost']:10.2f} | "
                  f"流量: {traffic_mb:8.2f} MB | "
                  f"行数: {result['plan_rows']:,}")
            
            success_count += 1
            
        except Exception as e:
            print(f"[{i}/{len(statements)}] ❌ 错误: {str(e)[:50]}...")
            error_count += 1
        
        # 避免过快请求
        await asyncio.sleep(0.1)
    
    # 统计汇总
    print("\n" + "=" * 80)
    print("📊 处理统计")
    print("=" * 80)
    print(f"✓ 成功: {success_count} 条")
    print(f"✗ 失败: {error_count} 条")
    print(f"📦 缓存大小: {collector.get_cache_size()}")
    print(f"💾 总流量: {total_traffic / 1024 / 1024:.2f} MB ({total_traffic / 1024 / 1024 / 1024:.2f} GB)")
    print(f"📝 日志文件: {log_file}")
    print("=" * 80)


async def interactive_mode(config_file: str = 'config.yaml'):
    """
    交互模式：逐条输入 SQL 进行分析
    
    Args:
        config_file: 配置文件路径
    """
    # 加载配置
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    db_config = config['database']
    log_file = config['logging']['log_file']
    
    # 创建收集器
    collector = TenantStatsCollector(db_config, log_file)
    
    print("\n" + "=" * 80)
    print("🔧 PostgreSQL 租户统计工具 - 交互模式")
    print("=" * 80)
    print("输入 SQL 语句进行分析（输入 'exit' 或 'quit' 退出）")
    print("输入 'cache' 查看缓存状态")
    print("输入 'clear' 清空缓存")
    print("=" * 80 + "\n")
    
    while True:
        try:
            # 多行输入
            print("请输入 SQL（按两次 Enter 结束）:")
            lines = []
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
            
            sql = '\n'.join(lines).strip()
            
            if not sql:
                continue
            
            # 特殊命令
            if sql.lower() in ['exit', 'quit']:
                print("\n👋 再见！")
                break
            elif sql.lower() == 'cache':
                print(f"📦 当前缓存大小: {collector.get_cache_size()}\n")
                continue
            elif sql.lower() == 'clear':
                collector.clear_cache()
                print("✓ 缓存已清空\n")
                continue
            
            # 分析 SQL
            result = await collector.analyze_sql(sql)
            
            print("\n" + "-" * 80)
            print(f"🎯 分析结果")
            print("-" * 80)
            print(f"租户代码:     {result['tenant_code']}")
            print(f"查询代价:     {result['total_cost']:.2f}")
            print(f"预估行数:     {result['plan_rows']:,}")
            print(f"行宽 (字节):  {result['plan_width']}")
            print(f"预估流量:     {result['estimated_traffic']:,} bytes "
                  f"({result['estimated_traffic']/1024/1024:.2f} MB)")
            print(f"来自缓存:     {'是' if result['from_cache'] else '否'}")
            print("-" * 80 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}\n")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description='PostgreSQL 租户统计工具 - 批量处理'
    )
    parser.add_argument(
        '-f', '--file',
        help='SQL 文件路径'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='配置文件路径（默认: config.yaml）'
    )
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='交互模式'
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        # 交互模式
        asyncio.run(interactive_mode(args.config))
    elif args.file:
        # 批量处理模式
        asyncio.run(batch_process(args.file, args.config))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
