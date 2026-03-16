# 数据库存储 + Web 仪表板使用指南

本指南说明如何将 `tenant_stats.log` 日志数据存储到 PostgreSQL 数据库，并通过网页仪表板可视化展示。

---

## 🎯 三个新工具

### 1. **import_to_db.py** - 日志导入工具
将 `tenant_stats.log` 中的统计数据导入到 PostgreSQL 数据库

### 2. **web_dashboard.py** - Web API 服务
提供 REST API，为前端仪表板供数据

### 3. **dashboard.html** - Web 仪表板
交互式网页，实时展示统计数据和图表

---

## 📦 安装依赖

```bash
pip install -r requirements_web.txt
```

或手动安装：
```bash
pip install asyncpg Flask Flask-CORS PyYAML
```

---

## 🚀 使用步骤

### 步骤 1: 导入日志数据到数据库

```bash
python import_to_db.py
```

**输出示例：**
```
✓ 已连接到 PostgreSQL
✓ 表 tenant_stats 已创建/已存在
已导入 6,347 条新记录，0 条重复记录
✓ 导入完成

📊 数据库统计摘要
============================================================
总查询数:     6,347
总流量:       31,294 bytes (0.03 MB)
总执行时间:   6,403 ms
平均执行时间: 1.01 ms
缓存命中:     4
缓存未命中:   6,343
============================================================

✓ 本次导入了 6,347 条新记录到 tenant_stats 表
```

---

### 步骤 2: 启动 Web API 服务

```bash
python web_dashboard.py
```

**输出示例：**
```
✓ 数据库连接池已初始化
✓ API 服务已启动
 * Running on http://0.0.0.0:5000
```

---

### 步骤 3: 打开仪表板

在浏览器中打开：
```
http://localhost:5000/dashboard.html
```

**或者使用 VS Code 的 Live Server:**
```
右键 dashboard.html → Open with Live Server
```

---

## 📊 Web 仪表板功能

### 🎨 主界面

页面分为 6 个主要选项卡：

#### 1️⃣ **概览 (Overview)**
- 📈 时间线统计图表（查询数和流量趋势）
- 🥧 租户分布饼图
- ⚡ 执行时间分布

#### 2️⃣ **租户排行 (Tenant Ranking)**
- 按流量从高到低排序
- 显示每个租户的查询数、流量、平均执行时间
- 可视化流量柱状图

```
排名  租户          查询数  流量(MB)  平均时间(ms)
1    TENANT_001   20     0.02     8.50
2    TENANT_003   5      0.01     10.45
```

#### 3️⃣ **慢查询 (Slow Queries)**
- TOP 10 执行时间最长的查询
- 显示租户、执行时间、返回行数、SQL 预览

```
排名  租户      执行时间   返回行数  SQL 预览
1    UNKNOWN  46.13 ms  0        CREATE TABLE...
2    TENANT_003 37.92 ms 20      WITH tenant_orders AS...
```

#### 4️⃣ **高流量 (High Traffic)**
- TOP 10 流量最高的查询
- 显示预估流量、查询代价、预估行数

```
排名  租户       流量      查询代价  SQL 预览
1    TENANT_003 0.01 MB  32.06    SELECT * FROM orders...
```

#### 5️⃣ **时间线 (Timeline)**
- 7 天内的查询数和流量趋势
- 双轴图表：左轴为查询数，右轴为流量

#### 6️⃣ **缓存分析 (Cache)**
- 缓存命中率饼图
- 预计节省的执行时间

---

## 📡 REST API 端点

API 服务提供的端点（基础 URL: `http://localhost:5000/api`）：

### GET `/summary`
获取总体统计摘要

**响应示例：**
```json
{
  "total_queries": 6347,
  "total_traffic_bytes": 31294,
  "total_traffic_mb": 0.03,
  "total_time_ms": 6403.25,
  "avg_time_ms": 1.01,
  "cache_hits": 4,
  "cache_misses": 6343,
  "cache_hit_rate": 0.1
}
```

---

### GET `/tenant-ranking?limit=20`
获取租户流量排行

**参数：** `limit` (默认 20)

**响应示例：**
```json
[
  {
    "rank": 1,
    "tenant_code": "TENANT_001",
    "query_count": 20,
    "total_traffic_bytes": 31294,
    "total_traffic_mb": 0.02,
    "avg_time_ms": 8.50,
    "total_rows": 200
  }
]
```

---

### GET `/slow-queries?limit=10`
获取慢查询

**参数：** `limit` (默认 10)

**响应示例：**
```json
[
  {
    "rank": 1,
    "timestamp": "2026-03-10T11:40:09",
    "tenant_code": "UNKNOWN",
    "execution_time_ms": 46.13,
    "rows_returned": 0,
    "traffic_bytes": 0,
    "sql_preview": "CREATE TABLE public.orders..."
  }
]
```

---

### GET `/high-traffic-queries?limit=10`
获取高流量查询

**参数：** `limit` (默认 10)

---

### GET `/timeline?group_by=hour&days=7`
获取时间线统计

**参数：**
- `group_by`: `hour`, `day` (默认 `hour`)
- `days`: 天数 (默认 7)

**响应示例：**
```json
[
  {
    "time": "2026-03-10 11:00:00",
    "query_count": 100,
    "traffic_kb": 50.0,
    "traffic_bytes": 51200
  }
]
```

---

### GET `/cache-stats`
获取缓存统计

**响应示例：**
```json
{
  "total_queries": 6347,
  "cache_hits": 4,
  "cache_misses": 6343,
  "hit_rate": 0.1,
  "saved_time_ms": 60,
  "saved_time_seconds": 0.06
}
```

---

## 💡 实际使用场景

### 场景 1: 定期导入数据

```bash
# 创建定时任务（Windows 任务计划）或 Linux cron
# 每小时导入一次日志

# Windows PowerShell 脚本
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "ImportTenantStats" -Action (New-ScheduledTaskAction -Execute "python" -Argument "import_to_db.py") -Trigger $trigger
```

### 场景 2: 生成报告

创建一个脚本定期从数据库生成报告：

```python
import asyncpg
import asyncio

async def generate_report():
    conn = await asyncpg.connect('postgresql://user:password@localhost/test')
    
    # 获取昨天的统计
    stats = await conn.fetchrow("""
        SELECT COUNT(*) as queries, SUM(estimated_traffic_bytes) as traffic
        FROM tenant_stats
        WHERE DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day'
    """)
    
    print(f"昨天统计: {stats['queries']} 查询, {stats['traffic']/1024/1024:.2f} MB 流量")
    
    await conn.close()

asyncio.run(generate_report())
```

### 场景 3: 监控告警

```python
# 监控高流量租户并发送告警
async def check_high_traffic():
    conn = await asyncpg.connect('...')
    
    tenants = await conn.fetch("""
        SELECT tenant_code, SUM(estimated_traffic_bytes) as traffic
        FROM tenant_stats
        WHERE timestamp > now() - interval '1 hour'
        GROUP BY tenant_code
        HAVING SUM(estimated_traffic_bytes) > 100000000  -- 100MB
    """)
    
    for tenant in tenants:
        alert(f"租户 {tenant['tenant_code']} 1小时流量 {tenant['traffic']/1024/1024:.0f}MB")
```

---

## 🔍 数据库表结构

```sql
CREATE TABLE tenant_stats (
    id SERIAL PRIMARY KEY,                          -- 自增 ID
    timestamp TIMESTAMP NOT NULL,                   -- 查询时间戳
    tenant_code VARCHAR(100),                       -- 租户代码
    sql_length INTEGER,                             -- SQL 长度
    sql_preview TEXT,                               -- SQL 预览
    execution_time_ms FLOAT,                        -- 执行时间（毫秒）
    rows_returned INTEGER,                          -- 返回行数
    total_cost FLOAT,                               -- 查询代价
    estimated_rows INTEGER,                         -- 预估行数
    estimated_traffic_bytes INTEGER,                -- 预估流量（字节）
    estimated_traffic_mb FLOAT,                     -- 预估流量（MB）
    from_cache BOOLEAN,                             -- 是否来自缓存
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 数据库创建时间
);

CREATE INDEX idx_tenant_code ON tenant_stats(tenant_code);
CREATE INDEX idx_timestamp ON tenant_stats(timestamp);
CREATE INDEX idx_execution_time ON tenant_stats(execution_time_ms);
CREATE INDEX idx_traffic ON tenant_stats(estimated_traffic_bytes);
```

---

## 🛠️ 故障排查

### 问题 1: Web 服务无法启动

```
ERROR: Address already in use
```

**解决方法：**
```bash
# 查找占用 5000 端口的进程
netstat -ano | findstr :5000

# 杀死进程（Windows）
taskkill /PID <PID> /F
```

### 问题 2: 仪表板数据加载失败

检查浏览器控制台（F12）查看 CORS 错误。确保 Web 服务正在运行。

### 问题 3: 数据库连接失败

检查 `config.yaml` 中的数据库凭据和连接信息。

---

## 📈 性能优化

### 1. 添加更多索引

```sql
-- 针对常见查询优化
CREATE INDEX idx_tenant_time ON tenant_stats(tenant_code, timestamp);
CREATE INDEX idx_traffic_time ON tenant_stats(timestamp, estimated_traffic_bytes);
```

### 2. 数据归档

```sql
-- 归档旧数据到归档表
CREATE TABLE tenant_stats_archive AS 
SELECT * FROM tenant_stats 
WHERE timestamp < now() - interval '90 days';

DELETE FROM tenant_stats WHERE timestamp < now() - interval '90 days';
```

### 3. 定期清理

```bash
# 定期清理日志文件，保持最近 30 天
find . -name "tenant_stats*.log" -mtime +30 -delete
```

---

## 🎓 使用工作流

### 完整的工作流程：

```
1. 应用运行
   ↓
2. 自动生成 tenant_stats.log
   ↓
3. 定期运行 import_to_db.py（每小时/每天）
   ↓
4. 启动 web_dashboard.py
   ↓
5. 打开浏览器查看 dashboard.html
   ↓
6. 实时监控和分析多租户流量
```

---

## 📚 相关文件

| 文件 | 说明 |
|------|------|
| `import_to_db.py` | 日志导入工具 |
| `web_dashboard.py` | Web API 服务 |
| `dashboard.html` | 前端仪表板 |
| `requirements_web.txt` | Python 依赖 |

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements_web.txt

# 2. 导入日志数据
python import_to_db.py

# 3. 启动 Web 服务
python web_dashboard.py

# 4. 打开浏览器
# 访问：http://localhost:5000/dashboard.html
```

---

🎉 **现在你有了一个完整的多租户流量分析系统！**
