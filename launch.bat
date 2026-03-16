@echo off
cls
echo ============================================================
echo Flask Dashboard Launcher
echo ============================================================
echo.

echo [1/3] Stopping old Python processes...
taskkill /IM python.exe /F 2>nul
timeout /t 2 >nul

echo [2/3] Updating Flask application...
copy /Y web_dashboard_v2.py web_dashboard.py >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to update web_dashboard.py
    pause
    exit /b 1
)

echo [3/3] Starting Flask service...
echo.
python web_dashboard.py

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: Flask failed to start
    echo ============================================================
    echo.
    echo Check the error messages above.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
