@echo off
REM Kill any existing Python processes on port 5000
cls
echo Checking for Flask services...
tasklist | findstr "python"
echo.
echo Stopping all Python processes...
taskkill /IM python.exe /F 2>nul

timeout /t 2

echo.
echo Starting Flask Web Dashboard...
cd /d D:\vscode_mcp\pg_proxy
python web_dashboard.py

pause
