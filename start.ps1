# PostgreSQL Gateway 启动脚本
# 使用方法: .\start.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  PostgreSQL Gateway Launcher" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[X] Python not found. Please install Python 3.7+." -ForegroundColor Red
    exit 1
}

$pythonVersion = python --version
Write-Host "[OK] $pythonVersion" -ForegroundColor Green

# 检查依赖
Write-Host ""
Write-Host "Checking dependencies..." -ForegroundColor Yellow

$requiredModules = @('asyncpg', 'aiofiles', 'yaml', 'fastapi', 'uvicorn')
$missingModules = @()

foreach ($module in $requiredModules) {
    $result = python -c "import $module" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missingModules += $module
    }
}

if ($missingModules.Count -gt 0) {
    Write-Host "[!] Missing modules: $($missingModules -join ', ')" -ForegroundColor Yellow
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
}

Write-Host "[OK] All dependencies installed" -ForegroundColor Green

# 检查配置文件
if (-not (Test-Path "config.yaml")) {
    Write-Host "[X] config.yaml not found!" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] config.yaml found" -ForegroundColor Green

# 显示菜单
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Select Mode:" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "1. Run Traffic Stats Demo (demo_traffic_stats.py) - RECOMMENDED"
Write-Host "2. Run Example Application (app_example.py)"
Write-Host "3. Run Web API Server (api_example.py)"
Write-Host "4. Run TCP Gateway (pg_gateway.py) - Experimental"
Write-Host "5. Visualize Stats Report (visualize_stats.py)"
Write-Host "6. Exit"
Write-Host ""

$choice = Read-Host "Enter your choice (1-6)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Starting Traffic Stats Demo..." -ForegroundColor Green
        Write-Host "This will create test data and demonstrate traffic statistics" -ForegroundColor Yellow
        python demo_traffic_stats.py
    }
    "2" {
        Write-Host ""
        Write-Host "Starting Example Application..." -ForegroundColor Green
        python app_example.py
    }
    "3" {
        Write-Host ""
        Write-Host "Starting Web API Server..." -ForegroundColor Green
        Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
        python api_example.py
    }
    "4" {
        Write-Host ""
        Write-Host "Starting TCP Gateway (Experimental)..." -ForegroundColor Yellow
        python pg_gateway.py
    }
    "5" {
        Write-Host ""
        Write-Host "Visualizing Stats Report..." -ForegroundColor Cyan
        python visualize_stats.py -f tenant_stats.log -m all
    }
    "6" {
        Write-Host "Goodbye!" -ForegroundColor Cyan
        exit 0
    }
    default {
        Write-Host "Invalid choice!" -ForegroundColor Red
        exit 1
    }
}
