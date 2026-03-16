@echo off
chcp 65001 >nul
echo ========================================
echo 重启Flask服务
echo ========================================

echo.
echo [1/3] 停止所有Python进程...
taskkill /IM python.exe /F 2>nul
if %errorlevel% equ 0 (
    echo   ✓ Python进程已停止
) else (
    echo   - 没有运行的Python进程
)

timeout /t 2 /nobreak >nul

echo.
echo [2/3] 启动Flask服务...
start "Flask Dashboard" python web_dashboard.py

timeout /t 3 /nobreak >nul

echo.
echo [3/3] 检查服务状态...
netstat -ano | findstr ":5000" >nul
if %errorlevel% equ 0 (
    echo   ✓ Flask正在监听端口5000
    echo.
    echo ========================================
    echo ✓ 服务启动成功！
    echo ========================================
    echo.
    echo 请在浏览器访问: http://localhost:5000/
    echo.
    echo 提示: 刷新浏览器页面查看修复效果
    echo       状态应该从 "✗ 连接失败" 变为 "✓ 已连接"
) else (
    echo   ✗ 端口5000未监听，启动可能失败
    echo.
    echo 请检查Flask窗口的错误信息
)

echo.
pause
