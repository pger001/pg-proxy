package main

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
)

// ExplainResult 执行计划结果
type ExplainResult struct {
	TotalCost        float64 `json:"total_cost"`
	PlanRows         int64   `json:"plan_rows"`
	PlanWidth        int     `json:"plan_width"`
	EstimatedTraffic int64   `json:"estimated_traffic"`
	FromCache        bool    `json:"from_cache"`
}

// StatsLog 统计日志结构
type StatsLog struct {
	Timestamp            string  `json:"timestamp"`
	TenantCode           string  `json:"tenant_code"`
	TotalCost            float64 `json:"total_cost"`
	PlanRows             int64   `json:"plan_rows"`
	PlanWidth            int     `json:"plan_width"`
	EstimatedTrafficByte int64   `json:"estimated_traffic_bytes"`
	EstimatedTrafficMB   float64 `json:"estimated_traffic_mb"`
	FromCache            bool    `json:"from_cache"`
}

// TenantStatsCollector PostgreSQL 租户统计收集器
type TenantStatsCollector struct {
	connString string
	logFile    string
	cache      map[string]*ExplainResult
	cacheMu    sync.RWMutex
	logMu      sync.Mutex
}

// NewTenantStatsCollector 创建新的收集器
func NewTenantStatsCollector(connString, logFile string) *TenantStatsCollector {
	return &TenantStatsCollector{
		connString: connString,
		logFile:    logFile,
		cache:      make(map[string]*ExplainResult),
	}
}

// ExtractTenantCode 从 SQL 中提取 tenant_code
func (c *TenantStatsCollector) ExtractTenantCode(sql string) (string, error) {
	// 移除注释
	sql = regexp.MustCompile(`--.*?$`).ReplaceAllString(sql, "")
	sql = regexp.MustCompile(`(?s)/\*.*?\*/`).ReplaceAllString(sql, "")

	// 多种模式匹配
	patterns := []string{
		`tenant_code\s*=\s*'([^']+)'`,
		`tenant_code\s*=\s*"([^"]+)"`,
		`tenant_code\s+IN\s*\(\s*'([^']+)'`,
		`tenant_code::text\s*=\s*'([^']+)'`,
	}

	for _, pattern := range patterns {
		re := regexp.MustCompile(`(?i)` + pattern)
		if matches := re.FindStringSubmatch(sql); matches != nil {
			return matches[1], nil
		}
	}

	return "", fmt.Errorf("无法从 SQL 中提取 tenant_code")
}

// CalculateSQLMD5 计算 SQL 的 MD5 哈希值
func (c *TenantStatsCollector) CalculateSQLMD5(sql string) string {
	// 标准化 SQL
	normalized := strings.ToLower(strings.TrimSpace(sql))
	normalized = regexp.MustCompile(`\s+`).ReplaceAllString(normalized, " ")

	// 计算 MD5
	hash := md5.Sum([]byte(normalized))
	return hex.EncodeToString(hash[:])
}

// GetExplainResult 获取执行计划（带缓存）
func (c *TenantStatsCollector) GetExplainResult(ctx context.Context, sql string) (*ExplainResult, error) {
	sqlMD5 := c.CalculateSQLMD5(sql)

	// 检查缓存
	c.cacheMu.RLock()
	if cached, ok := c.cache[sqlMD5]; ok {
		c.cacheMu.RUnlock()
		result := *cached
		result.FromCache = true
		return &result, nil
	}
	c.cacheMu.RUnlock()

	// 执行 EXPLAIN
	conn, err := pgx.Connect(ctx, c.connString)
	if err != nil {
		return nil, fmt.Errorf("数据库连接失败: %w", err)
	}
	defer conn.Close(ctx)

	explainSQL := fmt.Sprintf("EXPLAIN (FORMAT JSON) %s", sql)
	var jsonResult string
	err = conn.QueryRow(ctx, explainSQL).Scan(&jsonResult)
	if err != nil {
		return nil, fmt.Errorf("EXPLAIN 执行失败: %w", err)
	}

	// 解析 JSON
	var explainData []map[string]interface{}
	if err := json.Unmarshal([]byte(jsonResult), &explainData); err != nil {
		return nil, fmt.Errorf("JSON 解析失败: %w", err)
	}

	plan := explainData[0]["Plan"].(map[string]interface{})
	totalCost := plan["Total Cost"].(float64)
	planRows := int64(plan["Plan Rows"].(float64))
	planWidth := int(plan["Plan Width"].(float64))
	estimatedTraffic := planRows * int64(planWidth)

	result := &ExplainResult{
		TotalCost:        totalCost,
		PlanRows:         planRows,
		PlanWidth:        planWidth,
		EstimatedTraffic: estimatedTraffic,
		FromCache:        false,
	}

	// 存入缓存
	c.cacheMu.Lock()
	c.cache[sqlMD5] = &ExplainResult{
		TotalCost:        totalCost,
		PlanRows:         planRows,
		PlanWidth:        planWidth,
		EstimatedTraffic: estimatedTraffic,
	}
	c.cacheMu.Unlock()

	return result, nil
}

// WriteStatsAsync 异步写入统计结果
func (c *TenantStatsCollector) WriteStatsAsync(tenantCode string, stats *ExplainResult) error {
	c.logMu.Lock()
	defer c.logMu.Unlock()

	logEntry := StatsLog{
		Timestamp:            time.Now().Format("2006-01-02 15:04:05"),
		TenantCode:           tenantCode,
		TotalCost:            stats.TotalCost,
		PlanRows:             stats.PlanRows,
		PlanWidth:            stats.PlanWidth,
		EstimatedTrafficByte: stats.EstimatedTraffic,
		EstimatedTrafficMB:   float64(stats.EstimatedTraffic) / 1024 / 1024,
		FromCache:            stats.FromCache,
	}

	jsonData, err := json.Marshal(logEntry)
	if err != nil {
		return fmt.Errorf("JSON 序列化失败: %w", err)
	}

	f, err := os.OpenFile(c.logFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("打开日志文件失败: %w", err)
	}
	defer f.Close()

	if _, err := f.Write(append(jsonData, '\n')); err != nil {
		return fmt.Errorf("写入日志失败: %w", err)
	}

	return nil
}

// AnalyzeSQL 完整分析流程
func (c *TenantStatsCollector) AnalyzeSQL(ctx context.Context, sql string) (map[string]interface{}, error) {
	// 1. 提取 tenant_code
	tenantCode, err := c.ExtractTenantCode(sql)
	if err != nil {
		return nil, err
	}

	// 2. 获取执行计划
	stats, err := c.GetExplainResult(ctx, sql)
	if err != nil {
		return nil, err
	}

	// 3. 异步写入日志
	go func() {
		if err := c.WriteStatsAsync(tenantCode, stats); err != nil {
			log.Printf("写入日志失败: %v", err)
		}
	}()

	// 4. 返回结果
	return map[string]interface{}{
		"tenant_code":        tenantCode,
		"total_cost":         stats.TotalCost,
		"plan_rows":          stats.PlanRows,
		"plan_width":         stats.PlanWidth,
		"estimated_traffic":  stats.EstimatedTraffic,
		"from_cache":         stats.FromCache,
	}, nil
}

// ClearCache 清空缓存
func (c *TenantStatsCollector) ClearCache() {
	c.cacheMu.Lock()
	defer c.cacheMu.Unlock()
	c.cache = make(map[string]*ExplainResult)
}

// GetCacheSize 获取缓存大小
func (c *TenantStatsCollector) GetCacheSize() int {
	c.cacheMu.RLock()
	defer c.cacheMu.RUnlock()
	return len(c.cache)
}

func main() {
	// 数据库连接字符串
	connString := "postgres://postgres:postgres@localhost:5432/testdb"

	// 创建收集器
	collector := NewTenantStatsCollector(connString, "tenant_stats.log")

	// 示例 SQL
	testSQL := `
	WITH tenant_orders AS (
		SELECT 
			order_id,
			user_id,
			amount,
			created_at
		FROM orders
		WHERE tenant_code = 'TENANT_001'
		  AND status = 'completed'
	),
	user_stats AS (
		SELECT 
			user_id,
			COUNT(*) as order_count,
			SUM(amount) as total_amount
		FROM tenant_orders
		GROUP BY user_id
	)
	SELECT * FROM user_stats;
	`

	ctx := context.Background()

	// 第一次分析
	fmt.Println("=== 第一次分析 ===")
	result1, err := collector.AnalyzeSQL(ctx, testSQL)
	if err != nil {
		log.Fatalf("分析失败: %v", err)
	}
	printResult(result1)
	fmt.Printf("当前缓存大小: %d\n\n", collector.GetCacheSize())

	// 第二次分析（从缓存获取）
	time.Sleep(100 * time.Millisecond) // 等待异步写入完成
	fmt.Println("=== 第二次分析（相同 SQL）===")
	result2, err := collector.AnalyzeSQL(ctx, testSQL)
	if err != nil {
		log.Fatalf("分析失败: %v", err)
	}
	printResult(result2)
	fmt.Printf("当前缓存大小: %d\n", collector.GetCacheSize())

	fmt.Printf("\n✓ 统计结果已写入 %s\n", collector.logFile)
}

func printResult(result map[string]interface{}) {
	fmt.Printf("租户: %s\n", result["tenant_code"])
	fmt.Printf("代价: %.2f\n", result["total_cost"])
	fmt.Printf("预估行数: %d\n", result["plan_rows"])
	fmt.Printf("行宽: %d\n", result["plan_width"])
	traffic := result["estimated_traffic"].(int64)
	fmt.Printf("预估流量: %d bytes (%.2f MB)\n", traffic, float64(traffic)/1024/1024)
	fmt.Printf("来自缓存: %v\n", result["from_cache"])
}
