#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键解决方案: 杀死旧进程，备份并更新，然后启动 Flask
"""

import os
import sys
import subprocess
import time
import shutil

def banner(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def step(num, total, text):
    print(f"\n[{num}/{total}] {text}...")

def main():
    os.chdir(r'D:\vscode_mcp\pg_proxy')
    
    banner("🔧 Flask Dashboard 自动修复和启动")
    
    # Step 1: Kill old processes
    step(1, 4, "停止所有 Python 进程")
    try:
        subprocess.run('taskkill /IM python.exe /F', shell=True, 
                      capture_output=True, check=False)
        print("   ✓ 已清理旧进程")
        time.sleep(2)
    except:
        print("   ⚠️  无需清理")
    
    # Step 2: Backup and update
    step(2, 4, "更新 Flask 应用到最新版本")
    try:
        # Backup old version
        if os.path.exists('web_dashboard.py'):
            shutil.copy2('web_dashboard.py', 'web_dashboard_old.py')
            print("   ✓ 已备份旧版本")
        
        # Use new version
        if os.path.exists('web_dashboard_v2.py'):
            shutil.copy2('web_dashboard_v2.py', 'web_dashboard.py')
            print("   ✓ 已更新到新版本 (带启动检查)")
        else:
            print("   ⚠️  新版本不存在，使用现有版本")
    except Exception as e:
        print(f"   ⚠️  更新失败: {e}")
    
    # Step 3: Verify dependencies
    step(3, 4, "检查依赖")
    missing = []
    for module in ['flask', 'flask_cors', 'psycopg2', 'yaml']:
        try:
            __import__(module if module != 'yaml' else 'yaml')
            print(f"   ✓ {module}")
        except ImportError:
            print(f"   ✗ {module} 缺失")
            missing.append(module)
    
    if missing:
        print(f"\n   ❌ 缺少依赖: {', '.join(missing)}")
        print("   运行: pip install flask flask-cors psycopg2-binary pyyaml")
        input("\n按回车退出...")
        return False
    
    # Step 4: Launch Flask
    step(4, 4, "启动 Flask 服务")
    banner("🚀 正在启动...")
    
    try:
        # Run Flask (this will block)
        subprocess.run([sys.executable, 'web_dashboard.py'], check=True)
    except KeyboardInterrupt:
        print("\n\n停止服务...")
    except subprocess.CalledProcessError as e:
        print(f"\n\n❌ Flask 启动失败 (退出代码: {e.returncode})")
        print("\n可能的原因:")
        print("  1. 端口 5000 被占用")
        print("  2. 数据库连接失败")
        print("  3. config.yaml 配置错误")
        input("\n按回车退出...")
        return False
    
    return True

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n\n❌ 严重错误: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车退出...")
        sys.exit(1)
