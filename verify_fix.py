#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证时间线API修复
"""
import requests
import json

API_URL = "http://localhost:5000/api/timeline?group_by=hour&days=1"

print("=" * 60)
print("验证时间线API字段修复")
print("=" * 60)
print(f"请求: {API_URL}\n")

try:
    response = requests.get(API_URL, timeout=5)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ HTTP 200 - 成功")
        print(f"✓ 返回 {len(data)} 条数据\n")
        
        if len(data) > 0:
            first_item = data[0]
            print("第一条数据字段检查:")
            print(f"  - 'time' 字段: {'✓ 存在' if 'time' in first_item else '✗ 缺失'}")
            print(f"  - 'traffic_kb' 字段: {'✓ 存在' if 'traffic_kb' in first_item else '✗ 缺失'}")
            print(f"  - 'query_count' 字段: {'✓ 存在' if 'query_count' in first_item else '✗ 缺失'}")
            
            print("\n数据示例:")
            if 'time' in first_item:
                print(f"  time: {first_item['time']}")
            if 'traffic_kb' in first_item:
                print(f"  traffic_kb: {first_item['traffic_kb']:.2f} KB")
            if 'query_count' in first_item:
                print(f"  query_count: {first_item['query_count']}")
            
            # 验证字段是否符合前端期望
            required_fields = ['time', 'traffic_kb', 'query_count']
            missing_fields = [f for f in required_fields if f not in first_item]
            
            if not missing_fields:
                print("\n" + "=" * 60)
                print("✓✓✓ 所有字段正确！前端应该能正常显示")
                print("=" * 60)
            else:
                print(f"\n✗ 缺少字段: {missing_fields}")
                print("前端仍会显示连接失败")
    else:
        print(f"✗ HTTP {response.status_code}")
        print(f"错误: {response.text}")

except requests.exceptions.ConnectionError:
    print("✗ 连接失败 - Flask服务未运行")
    print("\n请先运行: restart_flask.bat")
except Exception as e:
    print(f"✗ 错误: {str(e)}")
