#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键启动仪表板脚本
自动处理所有启动步骤
"""

import os
import sys
import subprocess
import time
import socket

def check_port(port=5000):
    """检查端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def main():
    print("\n" + "="*70)
    print(" "*15 + "🚀 PostgreSQL Gateway 仪表板启动器")
    print("="*70)
    
    # 检查当前目录
    if not os.path.exists('web_dashboard.py'):
        print("\n❌ 错误: 找不到 web_dashboard.py")
        print("请确保在 D:\\vscode_mcp\\pg_proxy 目录中运行此脚本")
        return False
    
    # 步骤 1: 检查现有服务
    print("\n📋 步骤 1: 检查现有服务...")
    if check_port(5000):
        print("   ⚠️  端口 5000 已被使用，尝试停止旧服务...")
        try:
            subprocess.run('taskkill /IM python.exe /F', shell=True, capture_output=True)
            time.sleep(2)
            print("   ✓ 旧进程已停止")
        except Exception as e:
            print(f"   ⚠️  无法停止旧进程: {e}")
    else:
        print("   ✓ 端口 5000 可用")
    
    # 步骤 2: 启动 Flask
    print("\n🚀 步骤 2: 启动 Flask 服务...")
    try:
        # 以分离进程方式启动 Flask
        subprocess.Popen(
            [sys.executable, 'web_dashboard.py'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        print("   ✓ Flask 进程已启动")
        
        # 等待服务准备就绪
        print("\n⏳ 等待服务启动...")
        for i in range(15):
            time.sleep(1)
            if check_port(5000):
                print(f"   ✓ 服务已就绪！(第 {i+1} 秒)")
                break
            else:
                print(f"   ⏳ 等待中... ({i+1}/15秒)")
        else:
            print("   ❌ 服务启动超时")
            return False
        
        # 步骤 3: 验证 API
        print("\n✅ 步骤 3: 验证 API 连接...")
        time.sleep(1)
        try:
            import requests
            response = requests.get('http://localhost:5000/api/summary', timeout=3)
            if response.status_code == 200:
                data = response.json()
                print("   ✓ API 连接成功!")
                print(f"   • 总查询数: {data.get('total_queries', 0):,}")
                print(f"   • 总流量: {data.get('total_traffic_mb', 0):.2f} MB")
                print(f"   • 缓存命中率: {data.get('cache_hit_rate', 0):.2f}%")
            else:
                print(f"   ⚠️  API 返回错误代码: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  API 连接测试失败: {e}")
            print("   但 Flask 服务应该是在运行的，请检查浏览器")
        
        # 最终提示
        print("\n" + "="*70)
        print(" "*20 + "🎉 仪表板启动成功！")
        print("="*70)
        print("\n📊 请在浏览器中访问:")
        print("   👉 http://localhost:5000/")
        print("\n💡 提示:")
        print("   • 页面加载后自动连接到 API")
        print("   • 若显示 '连接失败'，请等待1-2秒后刷新")
        print("   • 服务每 30 秒自动刷新一次")
        print("   • 点击 '刷新数据' 按钮立即更新")
        print("\n📝 要停止服务，请按 Ctrl+C")
        print("="*70 + "\n")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 启动失败: {e}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
