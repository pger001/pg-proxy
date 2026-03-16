# Stop existing Python processes
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Start Flask
Write-Host "Starting Flask dashboard..."
cd "D:\vscode_mcp\pg_proxy"

$pythonPath = Get-Command python -ErrorAction Stop | Select-Object -ExpandProperty Source
& $pythonPath web_dashboard.py
