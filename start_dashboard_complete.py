#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的仪表板启动脚本
1. 清理旧进程
2. 启动 Flask 服务
3. 验证服务正常
"""

import subprocess
import time
import sys
import os

print("="*60)
print("PostgreSQL Gateway 仪表板启动脚本")
print("="*60)

# 第1步：清理旧进程 
print("\n[1] 清理旧进程...")
try:
    # Windows 上杀死 Python 进程
    result = subprocess.run('taskkill /IM python.exe /F', shell=True, capture_output=True)
    print("已清理旧进程")
    time.sleep(2)
except Exception as e:
    print(f"警告: {e}")

# 第2步：启动 Flask
print("\n[2] 启动 Flask 服务...")
print("工作目录:", os.getcwd())

try:
    # 启动 Flask（使用相同的窗口）
    subprocess.Popen([sys.executable, 'web_dashboard.py'])
    print("Flask 应用已启动...")
    time.sleep(3)
    
    # 第3步：验证
    print("\n[3] 验证服务...")
    try:
        import requests
        response = requests.get('http://localhost:5000/api/summary', timeout=3)
        if response.status_code == 200:
            data = response.json()
            print("✓ API 连接成功!")
            print(f"  - 总查询数: {data.get('total_queries', 0):,}")
            print(f"  - 总流量: {data.get('total_traffic_mb', 0):.2f} MB")
            print(f"  - 缓存命中率: {data.get('cache_hit_rate', 0):.2f}%")
        else:
            print(f"✗ API 返回错误: {response.status_code}")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        sys.exit(1)
    
    # 第4步：访问指示
    print("\n" + "="*60)
    print("✓ 仪表板启动完成!")
    print("="*60)
    print("\n请在浏览器中访问:")
    print("  http://localhost:5000/")
    print("\n按 Ctrl+C 停止服务")
    print("="*60 + "\n")
    
    # 保持运行
    while True:
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\n\n停止服务...")
    sys.exit(0)
except Exception as e:
    print(f"\n错误: {e}")
    sys.exit(1)
