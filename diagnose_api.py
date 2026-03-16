#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API诊断脚本 - 检查各个API端点返回的数据格式
"""
import requests
import json
from datetime import datetime

API_BASE = "http://localhost:5000/api"

print("=" * 70)
print("Flask API 诊断报告")
print("=" * 70)
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"API Base: {API_BASE}\n")

# 测试的端点
endpoints = [
    ("summary", {}),
    ("tenant-ranking", {"limit": "5"}),
    ("slow-queries", {"limit": "5"}),
    ("high-traffic-queries", {"limit": "5"}),
    ("timeline", {"group_by": "hour", "days": "1"}),
    ("cache-stats", {})
]

for endpoint, params in endpoints:
    url = f"{API_BASE}/{endpoint}"
    print(f"\n{'─' * 70}")
    print(f"测试端点: {endpoint}")
    print(f"URL: {url}")
    if params:
        print(f"参数: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=5)
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ 成功")
            
            # 显示数据结构
            if isinstance(data, dict):
                print(f"返回类型: 字典对象")
                print(f"字段: {list(data.keys())}")
                print(f"数据示例:")
                for key, value in data.items():
                    if isinstance(value, (int, float, str, bool, type(None))):
                        print(f"  - {key}: {value} ({type(value).__name__})")
                    else:
                        print(f"  - {key}: {type(value).__name__}")
            elif isinstance(data, list):
                print(f"返回类型: 列表")
                print(f"数据条数: {len(data)}")
                if len(data) > 0:
                    print(f"第一条数据字段: {list(data[0].keys())}")
                    print(f"第一条数据:")
                    for key, value in data[0].items():
                        print(f"  - {key}: {value}")
        else:
            print(f"✗ HTTP错误")
            print(f"响应内容: {response.text[:200]}")
    
    except requests.exceptions.ConnectionError:
        print(f"✗ 连接失败 - Flask服务未运行或端口未监听")
    except requests.exceptions.Timeout:
        print(f"✗ 请求超时")
    except requests.exceptions.RequestException as e:
        print(f"✗ 请求错误: {str(e)}")
    except json.JSONDecodeError as e:
        print(f"✗ JSON解析错误: {str(e)}")
        print(f"响应内容: {response.text[:200]}")
    except Exception as e:
        print(f"✗ 未知错误: {str(e)}")

print(f"\n{'═' * 70}")
print("诊断完成")
print("=" * 70)
