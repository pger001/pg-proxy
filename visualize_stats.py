#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流量统计可视化工具
读取日志文件并生成统计报告
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any
import argparse


class StatsVisualizer:
    """统计可视化"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.stats = []
        
    def load_stats(self) -> bool:
        """加载统计数据"""
        if not Path(self.log_file).exists():
            print(f"❌ 日志文件不存在: {self.log_file}")
            return False
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    self.stats.append(entry)
                except json.JSONDecodeError:
                    continue
        
        print(f"✓ 已加载 {len(self.stats)} 条统计记录\n")
        return True
    
    def show_summary(self):
        """显示总体概览"""
        print("=" * 80)
        print(" " * 30 + "总体概览")
        print("=" * 80)
        
        if not self.stats:
            print("没有统计数据")
            return
        
        total_queries = len(self.stats)
        total_traffic = sum(s.get('estimated_traffic_bytes', 0) or 0 for s in self.stats)
        total_time = sum(s.get('execution_time_ms', 0) for s in self.stats)
        total_rows = sum(s.get('rows_returned', 0) for s in self.stats)
        
        cache_hits = sum(1 for s in self.stats if s.get('from_cache'))
        cache_misses = total_queries - cache_hits
        
        print(f"查询总数:     {total_queries:,}")
        print(f"总流量:       {total_traffic:,} bytes ({total_traffic/1024/1024:.2f} MB)")
        print(f"总执行时间:   {total_time:.2f} ms")
        print(f"总返回行数:   {total_rows:,}")
        print(f"平均执行时间: {total_time/total_queries:.2f} ms")
        print(f"缓存命中:     {cache_hits} ({cache_hits/total_queries*100:.1f}%)")
        print(f"缓存未命中:   {cache_misses} ({cache_misses/total_queries*100:.1f}%)")
        print()
    
    def show_tenant_ranking(self):
        """显示租户排行"""
        print("=" * 80)
        print(" " * 30 + "租户流量排行")
        print("=" * 80)
        
        tenant_stats = defaultdict(lambda: {
            'query_count': 0,
            'total_traffic': 0,
            'total_time': 0,
            'total_rows': 0,
            'avg_time': 0
        })
        
        for entry in self.stats:
            tenant = entry.get('tenant_code', 'UNKNOWN')
            tenant_stats[tenant]['query_count'] += 1
            tenant_stats[tenant]['total_traffic'] += entry.get('estimated_traffic_bytes', 0) or 0
            tenant_stats[tenant]['total_time'] += entry.get('execution_time_ms', 0)
            tenant_stats[tenant]['total_rows'] += entry.get('rows_returned', 0)
        
        # 计算平均值
        for tenant, data in tenant_stats.items():
            if data['query_count'] > 0:
                data['avg_time'] = data['total_time'] / data['query_count']
        
        # 按流量排序
        sorted_tenants = sorted(
            tenant_stats.items(),
            key=lambda x: x[1]['total_traffic'],
            reverse=True
        )
        
        print(f"{'排名':<6} {'租户':<15} {'查询数':<10} {'流量(MB)':<12} {'平均时间(ms)':<15} {'总行数':<10}")
        print("-" * 80)
        
        for rank, (tenant, data) in enumerate(sorted_tenants, 1):
            traffic_mb = data['total_traffic'] / 1024 / 1024
            print(f"{rank:<6} {tenant:<15} {data['query_count']:<10} {traffic_mb:<12.2f} {data['avg_time']:<15.2f} {data['total_rows']:<10}")
        
        print()
    
    def show_slow_queries(self, top_n: int = 10):
        """显示慢查询"""
        print("=" * 80)
        print(f" " * 30 + f"TOP {top_n} 慢查询")
        print("=" * 80)
        
        # 按执行时间排序
        sorted_stats = sorted(
            self.stats,
            key=lambda x: x.get('execution_time_ms', 0),
            reverse=True
        )[:top_n]
        
        for rank, entry in enumerate(sorted_stats, 1):
            print(f"\n【第 {rank} 名】")
            print(f"租户:     {entry.get('tenant_code')}")
            print(f"时间:     {entry.get('timestamp')}")
            print(f"执行时间: {entry.get('execution_time_ms', 0):.2f} ms")
            print(f"返回行数: {entry.get('rows_returned', 0):,}")
            if entry.get('estimated_traffic_mb'):
                print(f"预估流量: {entry.get('estimated_traffic_mb', 0):.2f} MB")
            print(f"SQL:      {entry.get('sql_preview')}")
        
        print()
    
    def show_high_traffic_queries(self, top_n: int = 10):
        """显示高流量查询"""
        print("=" * 80)
        print(f" " * 30 + f"TOP {top_n} 高流量查询")
        print("=" * 80)
        
        # 过滤有流量数据的记录
        traffic_stats = [s for s in self.stats if s.get('estimated_traffic_bytes')]
        
        # 按流量排序
        sorted_stats = sorted(
            traffic_stats,
            key=lambda x: x.get('estimated_traffic_bytes', 0),
            reverse=True
        )[:top_n]
        
        for rank, entry in enumerate(sorted_stats, 1):
            print(f"\n【第 {rank} 名】")
            print(f"租户:     {entry.get('tenant_code')}")
            print(f"时间:     {entry.get('timestamp')}")
            print(f"预估流量: {entry.get('estimated_traffic_mb', 0):.2f} MB ({entry.get('estimated_traffic_bytes', 0):,} bytes)")
            print(f"查询代价: {entry.get('total_cost', 0):.2f}")
            print(f"预估行数: {entry.get('estimated_rows', 0):,}")
            print(f"执行时间: {entry.get('execution_time_ms', 0):.2f} ms")
            print(f"SQL:      {entry.get('sql_preview')}")
        
        print()
    
    def show_timeline(self, group_by: str = 'minute'):
        """显示时间线统计"""
        print("=" * 80)
        print(f" " * 30 + f"时间线统计 (按{group_by})")
        print("=" * 80)
        
        timeline = defaultdict(lambda: {'count': 0, 'traffic': 0})
        
        for entry in self.stats:
            timestamp_str = entry.get('timestamp')
            if not timestamp_str:
                continue
            
            try:
                dt = datetime.fromisoformat(timestamp_str)
                
                if group_by == 'hour':
                    key = dt.strftime('%Y-%m-%d %H:00')
                elif group_by == 'minute':
                    key = dt.strftime('%Y-%m-%d %H:%M')
                else:
                    key = dt.strftime('%Y-%m-%d')
                
                timeline[key]['count'] += 1
                timeline[key]['traffic'] += entry.get('estimated_traffic_bytes', 0) or 0
            except:
                continue
        
        # 排序
        sorted_timeline = sorted(timeline.items())
        
        print(f"{'时间':<20} {'查询数':<10} {'流量(KB)':<12} {'可视化'}")
        print("-" * 80)
        
        max_count = max(t[1]['count'] for t in sorted_timeline) if sorted_timeline else 1
        
        for time_key, data in sorted_timeline:
            traffic_kb = data['traffic'] / 1024
            bar_len = int(data['count'] / max_count * 40)
            bar = '█' * bar_len
            print(f"{time_key:<20} {data['count']:<10} {traffic_kb:<12.2f} {bar}")
        
        print()
    
    def show_cache_stats(self):
        """显示缓存统计"""
        print("=" * 80)
        print(" " * 30 + "缓存效果分析")
        print("=" * 80)
        
        cache_hits = [s for s in self.stats if s.get('from_cache')]
        cache_misses = [s for s in self.stats if not s.get('from_cache')]
        
        if not cache_hits and not cache_misses:
            print("没有缓存数据")
            return
        
        total = len(self.stats)
        hit_rate = len(cache_hits) / total * 100 if total > 0 else 0
        
        print(f"缓存命中:   {len(cache_hits)} ({hit_rate:.1f}%)")
        print(f"缓存未命中: {len(cache_misses)} ({100-hit_rate:.1f}%)")
        print()
        
        # 缓存节省的时间（假设 EXPLAIN 平均 15ms）
        saved_time = len(cache_hits) * 15
        print(f"预计节省时间: ~{saved_time} ms ({saved_time/1000:.2f} 秒)")
        print()


def main():
    parser = argparse.ArgumentParser(description='流量统计可视化工具')
    parser.add_argument('-f', '--file', default='tenant_stats.log', help='日志文件路径')
    parser.add_argument('-m', '--mode', choices=['all', 'summary', 'tenant', 'slow', 'traffic', 'timeline', 'cache'],
                       default='all', help='显示模式')
    parser.add_argument('-n', '--top', type=int, default=10, help='显示前 N 条')
    parser.add_argument('-g', '--group', choices=['hour', 'minute', 'day'], default='minute',
                       help='时间线分组方式')
    
    args = parser.parse_args()
    
    visualizer = StatsVisualizer(args.file)
    
    if not visualizer.load_stats():
        return
    
    if args.mode in ['all', 'summary']:
        visualizer.show_summary()
    
    if args.mode in ['all', 'tenant']:
        visualizer.show_tenant_ranking()
    
    if args.mode in ['all', 'slow']:
        visualizer.show_slow_queries(args.top)
    
    if args.mode in ['all', 'traffic']:
        visualizer.show_high_traffic_queries(args.top)
    
    if args.mode in ['all', 'timeline']:
        visualizer.show_timeline(args.group)
    
    if args.mode in ['all', 'cache']:
        visualizer.show_cache_stats()


if __name__ == "__main__":
    main()
