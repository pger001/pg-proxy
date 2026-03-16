# 🚀 仪表板启动指南

## 当前状态

您看到的"✗ 连接失败"是**正常的诊断**，表示浏览器中的页面无法与后端 Flask API 连接。

## 原因

Flask Web 服务可能：
1. ❌ 未启动
2. ❌ 已启动但响应缓慢或崩溃
3. ❌ 端口已被其他程序占用

## 解决方案

### 方法 1: 快速启动（推荐）

打开新的 PowerShell 窗口，运行：

```powershell
cd D:\vscode_mcp\pg_proxy
python quick_start.py
```

这个脚本会：
- ✓ 检查 Flask 是否运行
- ✓ 停止旧进程
- ✓ 启动新的 Flutter 服务
- ✓ 验证 API 连接
- ✓ 显示数据统计

### 方法 2: 直接启动

```powershell
cd D:\vscode_mcp\pg_proxy
python web_dashboard.py
```

然后在浏览器访问: http://localhost:5000/

### 方法 3: 清理并重启

```powershell
# 停止所有 Python 进程
taskkill /IM python.exe /F

# 等待 2 秒
Start-Sleep -Seconds 2

# 启动 Flask
cd D:\vscode_mcp\pg_proxy
python web_dashboard.py
```

## 已应用的改进

已更新 dashboard.html 以：
- ✓ 自动重试连接（最多 3 次）
- ✓ 在控制台显示详细的错误日志
- ✓ 显示重试计数
- ✓ 提供更清晰的状态消息

## 验证步骤

启动后，访问浏览器的开发者工具 (F12 → Console)：

1. 应该看到: "Dashboard loaded, attempting to connect to API..."
2. 应该看到: "Loading data from API: http://localhost:5000/api"
3. 如果成功: "✓ 已连接"
4. 如果失败: 查看具体的错误信息

## 测试 API 直接连接

```powershell
# 快速测试 API
python -c "import requests; print(requests.get('http://localhost:5000/api/summary').json())"
```

## 数据库状态

✓ 数据已成功导入到 PostgreSQL:
- 总记录数: 6,347
- 表名: public.tenant_stats
- 所有 API 端点都有数据

## 问题排查

### 如果看到 "✗ 连接失败"
1. 检查是否有 Python 进程运行: `tasklist | findstr python`
2. 检查端口 5000: `netstat -ano | findstr 5000`
3. 查看 Flask 日志输出（在启动的终端中）

### 如果 Flask 启动失败
- 检查是否安装了所有依赖: `pip show flask flask-cors psycopg2-binary pyyaml`
- 检查数据库连接: `python test_api.py`

### 如果 API 返回 500 错误
- 查看 Flask 终端中的错误信息
- 检查数据库配置: `cat config.yaml`
- 验证 PostgreSQL 连接: `python -c "import psycopg2; psycopg2.connect(host='localhost', user='dbtest1', password='xxx', database='test')"`

## 下一步

一旦 Flask 启动成功并且显示 "✓ 已连接"：

1. 页面会自动加载所有6个数据标签页
2. 每 30 秒自动刷新一次
3. 点击 "刷新数据" 按钮手动刷新

祝你使用愉快！🎉
