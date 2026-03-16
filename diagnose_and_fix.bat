@echo off
chcp 65001 >nul
cls

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║         Flask Dashboard 完整诊断与修复工具                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

echo [步骤 1/5] 检查Python进程...
echo ────────────────────────────────────────────────────────────────
tasklist | findstr python.exe >nul
if %errorlevel% equ 0 (
    echo ✓ 发现运行中的Python进程
    echo   正在停止旧进程...
    taskkill /IM python.exe /F >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo   ✓ 进程已清理
) else (
    echo - 没有运行的Python进程
)

echo.
echo [步骤 2/5] 启动Flask服务...
echo ────────────────────────────────────────────────────────────────
start "Flask Dashboard Service" /MIN python web_dashboard.py
timeout /t 4 /nobreak >nul

echo.
echo [步骤 3/5] 检查服务状态...
echo ────────────────────────────────────────────────────────────────
netstat -ano | findstr ":5000.*LISTENING" >nul
if %errorlevel% equ 0 (
    echo ✓ Flask服务正在监听端口5000
) else (
    echo ✗ 警告: 端口5000未监听
    echo   请检查Flask窗口的错误信息
    pause
    exit /b 1
)

echo.
echo [步骤 4/5] 测试API端点...
echo ────────────────────────────────────────────────────────────────
python test_all_apis.py
if %errorlevel% neq 0 (
    echo.
    echo ✗ API测试失败!
    pause
    exit /b 1
)

echo.
echo [步骤 5/5] 打开浏览器诊断页面...
echo ────────────────────────────────────────────────────────────────
timeout /t 2 /nobreak >nul
start http://localhost:5000/diagnose.html

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                     诊断完成                                 ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo 已在浏览器中打开诊断页面: http://localhost:5000/diagnose.html
echo.
echo 诊断页面将自动测试所有API并显示详细结果
echo.
echo 如果所有测试通过，请:
echo   1. 访问 http://localhost:5000/
echo   2. 按 Ctrl+Shift+R 强制刷新清除缓存
echo   3. 查看状态指示器是否显示 "✓ 已连接" (绿色)
echo.
echo 如果仍然失败，请:
echo   1. 在浏览器按 F12 打开开发者工具
echo   2. 切换到 "控制台" (Console) 标签
echo   3. 截图错误信息发送给技术支持
echo.
pause
