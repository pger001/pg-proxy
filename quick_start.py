#!/usr/bin/env python3
"""Quick diagnostic and startup"""
import subprocess, time, socket, sys

def is_port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

print("检查 Flask 服务状态...")
if is_port_open(5000):
    print("✓ Flask 已在运行 (端口 5000)")
    try:
        import requests
        r = requests.get('http://localhost:5000/api/summary', timeout=2)
        if r.status_code == 200:
            print("✓ API 响应正常")
            data = r.json()
            print(f"  查询数: {data['total_queries']}")
            print(f"  流量: {data['total_traffic_mb']:.2f} MB")
            sys.exit(0)
    except:
        print("✗ API 响应异常，重启...")

print("✗ Flask 未运行，现在启动...")
subprocess.Popen([sys.executable, 'web_dashboard.py'])
time.sleep(3)

print("等待服务准备就绪...")
for i in range(10):
    if is_port_open(5000):
        print("✓ Flask 已启动!")
        time.sleep(1)
        break
    time.sleep(1)
    print(f"  尝试 {i+1}/10...")
else:
    print("✗ Flask 启动失败")
    sys.exit(1)

print("\n成功! 访问: http://localhost:5000/")
