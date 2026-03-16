#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import sys

BASE_URL = "http://localhost:5000"

print("=" * 60)
print("测试所有API端点")
print("=" * 60)

endpoints = [
    ("/api/summary", "摘要统计"),
    ("/api/tenant-ranking?limit=5", "租户排行"),
    ("/api/slow-queries?limit=5", "慢查询"),
    ("/api/high-traffic-queries?limit=5", "高流量查询"),
    ("/api/timeline?group_by=hour&days=1", "时间线"),
    ("/api/cache-stats", "缓存统计"),
    ("/api/resource-summary", "资源总览"),
    ("/api/resource-tenant-ranking?limit=5", "资源租户排行"),
    ("/api/resource-recent?limit=5", "最近资源明细"),
    ("/api/resource-billing-summary?granularity=day", "计费口径汇总(按天)"),
    ("/api/resource-billing-summary?granularity=month&tenant_code=TENANT_001", "计费口径汇总(按月+租户)"),
    ("/api/resource-collect-status", "采集状态"),
]

all_success = True

for endpoint, name in endpoints:
    url = BASE_URL + endpoint
    print(f"\n测试: {name}")
    print(f"  URL: {endpoint}")
    
    try:
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            print(f"  ✓ 状态: 200 OK")
            data = response.json()
            
            # 检查timeline特殊字段
            if "timeline" in endpoint:
                if isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    has_time = 'time' in first
                    has_traffic_kb = 'traffic_kb' in first
                    has_query_count = 'query_count' in first
                    
                    print(f"  ✓ 返回 {len(data)} 条数据")
                    print(f"  {'✓' if has_time else '✗'} 'time' 字段: {first.get('time', 'N/A')[:19]}")
                    print(f"  {'✓' if has_traffic_kb else '✗'} 'traffic_kb' 字段: {first.get('traffic_kb', 'N/A')}")
                    print(f"  {'✓' if has_query_count else '✗'} 'query_count' 字段: {first.get('query_count', 'N/A')}")
                    
                    if not (has_time and has_traffic_kb and has_query_count):
                        print("  ✗ 字段不完整，前端会失败!")
                        all_success = False
            elif "resource-summary" in endpoint:
                required = ['table_exists', 'total_sql_count', 'total_io_mb', 'total_costs']
                missing = [k for k in required if k not in data]
                if missing:
                    print(f"  ✗ 缺少字段: {missing}")
                    all_success = False
                else:
                    print(f"  ✓ table_exists: {data.get('table_exists')}")
                    print(f"  ✓ total_sql_count: {data.get('total_sql_count')}")
            elif "resource-tenant-ranking" in endpoint:
                if isinstance(data, list):
                    print(f"  ✓ 返回 {len(data)} 条数据")
                    if len(data) > 0:
                        first = data[0]
                        required = ['tenant_code', 'sql_count', 'io_total_mb', 'total_costs']
                        missing = [k for k in required if k not in first]
                        if missing:
                            print(f"  ✗ 缺少字段: {missing}")
                            all_success = False
                else:
                    print("  ✗ 期望返回数组")
                    all_success = False
            elif "resource-recent" in endpoint:
                if isinstance(data, list):
                    print(f"  ✓ 返回 {len(data)} 条数据")
                    if len(data) > 0:
                        first = data[0]
                        required = ['request_id', 'tenant_code', 'execute_status', 'costs']
                        missing = [k for k in required if k not in first]
                        if missing:
                            print(f"  ✗ 缺少字段: {missing}")
                            all_success = False
                else:
                    print("  ✗ 期望返回数组")
                    all_success = False
            elif "resource-billing-summary" in endpoint:
                required = ['table_exists', 'filters', 'items']
                missing = [k for k in required if k not in data]
                if missing:
                    print(f"  ✗ 缺少字段: {missing}")
                    all_success = False
                else:
                    items = data.get('items', [])
                    print(f"  ✓ table_exists: {data.get('table_exists')}  items: {len(items)}")
                    filters = data.get('filters', {})
                    print(f"  ✓ filters: start={filters.get('start_date')}  end={filters.get('end_date')}  granularity={filters.get('granularity')}")
                    if items:
                        first = items[0]
                        req_fields = ['tenant_code', 'dataset_id', 'time_bucket', 'sql_count', 'total_costs']
                        miss2 = [k for k in req_fields if k not in first]
                        if miss2:
                            print(f"  ✗ items缺少字段: {miss2}")
                            all_success = False
            elif "resource-collect-status" in endpoint:
                required = ['running', 'last_run_at', 'interval_sec', 'total_collected']
                missing = [k for k in required if k not in data]
                if missing:
                    print(f"  ✗ 缺少字段: {missing}")
                    all_success = False
                else:
                    print(f"  ✓ running={data['running']}  total_collected={data['total_collected']}  interval={data['interval_sec']}s")
            elif isinstance(data, list):
                print(f"  ✓ 返回 {len(data)} 条数据")
            else:
                print(f"  ✓ 返回对象数据")
        else:
            print(f"  ✗ HTTP {response.status_code}")
            all_success = False
            
    except requests.exceptions.ConnectionError:
        print(f"  ✗ 连接失败 - 服务未运行")
        all_success = False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        all_success = False

print("\n" + "=" * 60)
if all_success:
    print("✓✓✓ 所有API测试通过!")
    print("\n下一步:")
    print("1. 打开浏览器访问 http://localhost:5000/")
    print("2. 按 Ctrl+Shift+R 强制刷新")
    print("3. 查看状态是否显示 '✓ 已连接' (绿色)")
    print("4. 如果还是失败，按F12打开控制台查看JavaScript错误")
else:
    print("✗ 部分API测试失败")
    sys.exit(1)
print("=" * 60)
