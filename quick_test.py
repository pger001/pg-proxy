import requests
import json

API_BASE = "http://localhost:5000/api"

print("=" * 60)
print("Flask Dashboard API 测试结果")
print("=" * 60)

# 测试所有端点
endpoints = [
    ("summary", {}),
    ("tenant-ranking", {"limit": 5}),
    ("slow-queries", {"limit": 5}),
    ("high-traffic-queries", {"limit": 5}),
    ("timeline", {"group_by": "hour", "days": 1}),
    ("cache-stats", {})
]

for endpoint, params in endpoints:
    url = f"{API_BASE}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=5)
        status = "✓" if response.status_code == 200 else "✗"
        print(f"\n{status} {endpoint}: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if endpoint == "summary":
                print(f"  - 总查询数: {data.get('total_queries', 0):,}")
                print(f"  - 总流量: {data.get('total_traffic_mb', 0):.3f} MB")
                print(f"  - 缓存命中率: {data.get('cache_hit_rate', 0):.2f}%")
                print(f"  - 平均执行时间: {data.get('avg_execution_time', 0):.2f} ms")
                print(f"  - 租户总数: {data.get('total_tenants', 0):,}")
            
            elif endpoint == "tenant-ranking":
                print(f"  - 返回租户数: {len(data)}")
                if len(data) > 0:
                    print(f"  - Top 1: tenant_id={data[0].get('tenant_id')}, queries={data[0].get('total_queries', 0):,}")
            
            elif endpoint == "slow-queries":
                print(f"  - 慢查询数: {len(data)}")
                if len(data) > 0:
                    print(f"  - 最慢查询: {data[0].get('avg_time', 0):.2f} ms")
            
            elif endpoint == "high-traffic-queries":
                print(f"  - 高流量查询数: {len(data)}")
                if len(data) > 0:
                    print(f"  - 最大流量: {data[0].get('total_traffic_mb', 0):.3f} MB")
            
            elif endpoint == "timeline":
                print(f"  - 时间点数量: {len(data)}")
            
            elif endpoint == "cache-stats":
                print(f"  - 总命中数: {data.get('total_cache_hits', 0):,}")
                print(f"  - 总未命中数: {data.get('total_cache_misses', 0):,}")
    
    except Exception as e:
        print(f"\n✗ {endpoint}: 错误 - {str(e)}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
