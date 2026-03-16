$endpoints = @(
    "/api/summary",
    "/api/tenant-ranking?limit=5",
    "/api/slow-queries?limit=5",
    "/api/high-traffic-queries?limit=5",
    "/api/timeline?group_by=hour&days=1",
    "/api/cache-stats"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "测试所有API端点" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allSuccess = $true

foreach ($endpoint in $endpoints) {
    $url = "http://localhost:5000$endpoint"
    Write-Host "测试: $endpoint" -ForegroundColor Yellow
    
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        
        if ($response.StatusCode -eq 200) {
            Write-Host "  ✓ 状态: 200 OK" -ForegroundColor Green
            
            $data = $response.Content | ConvertFrom-Json
            
            if ($data -is [Array]) {
                Write-Host "  ✓ 返回: 数组 ($($data.Count) 条)" -ForegroundColor Green
                
                if ($endpoint -like "*timeline*" -and $data.Count -gt 0) {
                    $first = $data[0]
                    if ($first.time -and $first.traffic_kb -and $first.query_count) {
                        Write-Host "  ✓ 字段: time, traffic_kb, query_count 都存在" -ForegroundColor Green
                    } else {
                        Write-Host "  ✗ 字段缺失!" -ForegroundColor Red
                        $allSuccess = $false
                    }
                }
            } else {
                Write-Host "  ✓ 返回: 对象" -ForegroundColor Green
            }
        } else {
            Write-Host "  ✗ 状态: $($response.StatusCode)" -ForegroundColor Red
            $allSuccess = $false
        }
    }
    catch {
        Write-Host "  ✗ 错误: $($_.Exception.Message)" -ForegroundColor Red
        $allSuccess = $false
    }
    
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
if ($allSuccess) {
    Write-Host "✓✓✓ 所有API测试通过!" -ForegroundColor Green
    Write-Host ""
    Write-Host "请刷新浏览器 (Ctrl+Shift+R) 查看结果" -ForegroundColor Yellow
} else {
    Write-Host "✗ 部分API测试失败" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan
