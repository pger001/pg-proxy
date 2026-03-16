# 🚨 紧急修复：连接失败

## 问题
页面显示: **✗ 连接失败** (红色按钮)

## 原因
Flask Web 服务没有运行 (Exit Code: 1 = 启动失败)

## 解决方案 (3 选 1)

### 🥇 方案 1: 一键修复 (最简单)

```powershell
cd D:\vscode_mcp\pg_proxy
python fix_and_start.py
```

### 🥈 方案 2: 批处理文件

双击运行: `launch.bat`

### 🥉 方案 3: 手动修复

```powershell
# 停止旧进程
taskkill /IM python.exe /F

# 等待 2 秒
Start-Sleep -Seconds 2

# 启动服务
cd D:\vscode_mcp\pg_proxy
python web_dashboard.py
```

## 验证成功

看到这个输出:
```
============================================================
🚀 Dashboard Ready!
============================================================
📊 Access: http://localhost:5000/
```

然后打开浏览器: http://localhost:5000/

应该显示: **✓ 已连接** (绿色按钮)

## 如果仍然失败

可能原因:
1. **端口被占用**: 运行 `netstat -ano | findstr 5000` 检查
2. **依赖缺失**: 运行 `pip install psycopg2-binary`
3. **数据库问题**: 检查 PostgreSQL 是否运行

详细诊断: 运行 `python diagnose_flask.py`

---

**快速提示**: 直接运行 `python fix_and_start.py` 会自动处理所有问题！✨
