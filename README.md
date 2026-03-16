# PostgreSQL Gateway - 租户流量统计系统

> 一个透明的 PostgreSQL 代理层，自动统计多租户应用的流量和查询性能

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 12+](https://img.shields.io/badge/postgresql-12+-blue.svg)](https://www.postgresql.org/)
[![asyncpg](https://img.shields.io/badge/asyncpg-latest-green.svg)](https://github.com/MagicStack/asyncpg)

## ⚡ 5分钟快速开始

### 使用示例（只需 3 步）

```python
import asyncio
import yaml
from proxy_pool import ProxyConnectionPool

async def main():
    # 1. 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 2. 初始化连接池
    pool = ProxyConnectionPool(config)
    await pool.initialize()
    
    # 3. 执行查询 - 自动统计租户流量！
    async with pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT * FROM orders 
            WHERE tenant_code = 'TENANT_001' 
            LIMIT 10
        """)
        print(f"找到 {len(result)} 条订单")
    
    await pool.close()

asyncio.run(main())
```

### 立即运行示例

```bash
# 最简单的示例
python simple_example.py

# 完整功能演示
python demo_traffic_stats.py

# 查看统计报告
python visualize_stats.py
```

**详细指南**: 查看 [QUICK_START.md](QUICK_START.md) 了解更多用法

---

## 📖 项目介绍

一个用于分析 PostgreSQL 多租户系统的代理工具，能够从复杂 SQL（包括多层 CTE）中提取租户信息，获取执行计划，计算预估流量，并异步记录统计结果。

## 🚀 功能特性

- ✅ **智能租户提取**：使用正则表达式从 SQL 中自动提取 `tenant_code`
- ✅ **执行计划分析**：调用 `EXPLAIN (FORMAT JSON)` 获取精确的查询计划
- ✅ **流量预估**：计算 `预估流量 = Plan Rows × Plan Width`
- ✅ **MD5 缓存机制**：针对长 SQL（如 500 行）避免重复 EXPLAIN
- ✅ **异步日志写入**：使用 `asyncio` + `aiofiles` 提升性能
- ✅ **支持复杂查询**：完美处理多层 CTE、递归查询、窗口函数等

## 📋 环境要求

- Python 3.7+
- PostgreSQL 9.5+
- 必需的 Python 包（见 `requirements.txt`）

## 🔧 安装

### 1. 克隆或下载项目

```bash
cd d:\vscode_mcp\pg_proxy
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install psycopg2-binary aiofiles pyyaml
```

### 3. 配置数据库

编辑 `config.yaml`，填入你的 PostgreSQL 连接信息：

```yaml
database:
  host: localhost
  port: 5432
  database: your_database
  user: postgres
  password: your_password
```

## 💻 使用方法

### 基本用法

```python
import asyncio
from tenant_stats import TenantStatsCollector

async def main():
    # 数据库配置
    db_config = {
        'host': 'localhost',
        'port': '5432',
        'database': 'testdb',
        'user': 'postgres',
        'password': 'postgres'
    }
    
    # 创建收集器
    collector = TenantStatsCollector(db_config, log_file='tenant_stats.log')
    
    # 分析 SQL
    sql = """
    SELECT * FROM orders 
    WHERE tenant_code = 'TENANT_001' 
      AND status = 'completed'
    """
    
    result = await collector.analyze_sql(sql)
    print(f"租户: {result['tenant_code']}")
    print(f"代价: {result['total_cost']}")
    print(f"预估流量: {result['estimated_traffic']} bytes")

asyncio.run(main())
```

### 直接运行示例

```bash
python tenant_stats.py
```

### 批量处理 SQL 文件

```python
import asyncio
from tenant_stats import TenantStatsCollector

async def batch_analyze():
    db_config = {...}  # 你的配置
    collector = TenantStatsCollector(db_config)
    
    # 读取 SQL 文件
    with open('example_sql.sql', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 按分号分割为多个 SQL
    sql_statements = [s.strip() + ';' for s in content.split(';') if s.strip()]
    
    for i, sql in enumerate(sql_statements):
        try:
            result = await collector.analyze_sql(sql)
            print(f"[{i+1}] 租户: {result['tenant_code']}, "
                  f"流量: {result['estimated_traffic']/1024/1024:.2f} MB, "
                  f"缓存: {result['from_cache']}")
        except Exception as e:
            print(f"[{i+1}] 错误: {e}")

asyncio.run(batch_analyze())
```

## 📊 输出格式

日志文件（`tenant_stats.log`）为 JSONL 格式，每行一条记录：

```json
{
  "timestamp": "2026-03-10 14:30:15",
  "tenant_code": "TENANT_001",
  "total_cost": 1542.34,
  "plan_rows": 50000,
  "plan_width": 128,
  "estimated_traffic_bytes": 6400000,
  "estimated_traffic_mb": 6.1,
  "from_cache": false
}
```

## 🎯 核心功能说明

### 1. 正则提取 tenant_code

支持以下模式：

- `WHERE tenant_code = 'xxx'`
- `WHERE tenant_code IN ('xxx')`
- `AND tenant_code = 'xxx'`
- `tenant_code::text = 'xxx'`

### 2. MD5 缓存机制

```python
# 相同 SQL 第一次执行：从数据库获取 EXPLAIN
result1 = await collector.analyze_sql(long_sql)  # from_cache = False

# 相同 SQL 第二次执行：从缓存读取
result2 = await collector.analyze_sql(long_sql)  # from_cache = True
```

缓存键：SQL 标准化后的 MD5 哈希值（忽略空格、换行、大小写）

### 3. 执行计划提取

从 `EXPLAIN (FORMAT JSON)` 返回的 JSON 中提取：

- **Total Cost**：查询总代价
- **Plan Rows**：预估返回行数
- **Plan Width**：每行平均宽度（字节）
- **Estimated Traffic** = Plan Rows × Plan Width （字节）

### 4. 异步日志写入

使用 `aiofiles` 异步写入，避免阻塞主线程：

```python
await collector.write_stats_async(tenant_code, stats)
```

## 🔍 示例场景

### 场景 1：DBA 日常巡检

```python
# 监控 TOP 10 慢查询的租户流量
slow_queries = get_slow_queries_from_pg_stat_statements()
for sql in slow_queries:
    result = await collector.analyze_sql(sql)
    if result['estimated_traffic'] > 100 * 1024 * 1024:  # > 100 MB
        alert(f"租户 {result['tenant_code']} 查询流量过大")
```

### 场景 2：租户账单计算

```python
# 统计每个租户本月的累计流量
monthly_stats = {}
for sql in get_tenant_queries_this_month():
    result = await collector.analyze_sql(sql)
    tenant = result['tenant_code']
    monthly_stats[tenant] = monthly_stats.get(tenant, 0) + result['estimated_traffic']

# 生成账单
for tenant, traffic in monthly_stats.items():
    cost = calculate_cost(traffic)
    print(f"{tenant}: {traffic/1024/1024/1024:.2f} GB -> ${cost}")
```

### 场景 3：SQL 优化建议

```python
result = await collector.analyze_sql(complex_sql)
if result['total_cost'] > 10000:
    suggest_optimization(result['tenant_code'], complex_sql)
```

## 🛠️ API 参考

### `TenantStatsCollector`

#### 初始化

```python
collector = TenantStatsCollector(
    db_config={
        'host': 'localhost',
        'port': '5432',
        'database': 'testdb',
        'user': 'postgres',
        'password': 'postgres'
    },
    log_file='tenant_stats.log'
)
```

#### 方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `extract_tenant_code(sql)` | 提取租户代码 | `str` 或 `None` |
| `calculate_sql_md5(sql)` | 计算 SQL 的 MD5 | `str` (32位16进制) |
| `get_explain_result(sql)` | 获取执行计划（带缓存） | `Dict[str, Any]` |
| `analyze_sql(sql)` | 完整分析流程（异步） | `Dict[str, Any]` |
| `write_stats_async(tenant, stats)` | 异步写入日志 | `None` |
| `clear_cache()` | 清空缓存 | `None` |
| `get_cache_size()` | 获取缓存大小 | `int` |

## ⚠️ 注意事项

1. **EXPLAIN 权限**：确保数据库用户有执行 `EXPLAIN` 的权限
2. **长 SQL 处理**：500+ 行的 SQL 会自动使用 MD5 缓存，无需额外配置
3. **并发安全**：当前实现为单线程安全，多进程场景需考虑缓存共享（可使用 Redis）
4. **日志轮转**：生产环境建议配置日志轮转（logrotate）
5. **性能影响**：`EXPLAIN` 不会实际执行 SQL，对数据库影响极小

## 📝 测试

运行内置测试：

```bash
python tenant_stats.py
```

预期输出：

```
=== 第一次分析 ===
租户: TENANT_001
代价: 1542.34
预估行数: 50000
行宽: 128
预估流量: 6400000 bytes (6.10 MB)
来自缓存: False
当前缓存大小: 1

=== 第二次分析（相同 SQL）===
租户: TENANT_001
代价: 1542.34
预估流量: 6400000 bytes
来自缓存: True
当前缓存大小: 1

✓ 统计结果已写入 tenant_stats.log
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

---

**Made for DBAs with ❤️**
