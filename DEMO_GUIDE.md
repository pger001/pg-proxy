# 流量统计功能测试指南

## 🚀 快速开始

### 方法 1: 使用启动菜单（推荐）

```bash
.\start.ps1
```

选择 **选项 1: Run Traffic Stats Demo** 即可自动完成全部测试。

### 方法 2: 直接运行

```bash
python demo_traffic_stats.py
```

## 📋 演示程序功能

`demo_traffic_stats.py` 会自动执行以下步骤：

### ✅ 步骤 1: 创建测试数据

- 创建 `orders` 和 `users` 表
- 插入 3 个租户的测试数据
  - 每个租户 50 个用户
  - 每个租户 1000 个订单
  - 总计 3000 条订单记录

### ✅ 步骤 2: 执行测试查询

运行 6 种类型的查询：

1. **简单查询** - 小数据量（LIMIT 10）
2. **聚合查询** - GROUP BY + 统计函数
3. **复杂 JOIN** - 多表关联 + 过滤 + 排序
4. **大数据量查询** - 返回 500 行
5. **多层 CTE** - 3 层 CTE + 窗口函数
6. **重复查询** - 测试 MD5 缓存

每个查询都会：
- ✓ 自动提取 tenant_code
- ✓ 异步执行 EXPLAIN 获取流量预估
- ✓ 记录到日志文件
- ✓ 利用 MD5 缓存避免重复 EXPLAIN

### ✅ 步骤 3: 统计结果展示

自动分析日志文件并展示：

- **总体统计**: 查询次数、总流量、缓存命中率
- **租户明细**: 每个租户的查询数、流量、平均时间
- **最近查询**: 最后 5 条查询的详细信息
- **缓存验证**: MD5 缓存功能验证

## 📊 预期输出示例

```
======================================================================
  PostgreSQL Gateway - 流量统计功能演示
======================================================================

2026-03-10 15:30:45 - INFO - ✓ 代理连接池初始化成功

======================================================================
【步骤 1】创建测试表和数据
======================================================================
2026-03-10 15:30:46 - INFO - 创建 orders 表...
2026-03-10 15:30:46 - INFO - ✓ orders 表创建成功
2026-03-10 15:30:46 - INFO - 创建 users 表...
2026-03-10 15:30:46 - INFO - ✓ users 表创建成功
2026-03-10 15:30:46 - INFO - 插入测试数据...
2026-03-10 15:30:50 - INFO - ✓ 已插入 150 个用户
2026-03-10 15:31:10 - INFO - ✓ 已插入 3000 个订单
2026-03-10 15:31:10 - INFO - ✓ 测试数据准备完成

======================================================================
【步骤 2】执行测试查询（验证流量统计）
======================================================================

[测试 1/6] 简单查询 - 小数据量
租户: TENANT_001
SQL: SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 10...
2026-03-10 15:31:11 - INFO - ✓ 执行成功
  返回行数: 10
  执行时间: 8.45 ms

[测试 2/6] 聚合查询
租户: TENANT_001
SQL: SELECT status, COUNT(*) as order_count...
2026-03-10 15:31:12 - INFO - ✓ 执行成功
  返回行数: 4
  执行时间: 15.23 ms

...

======================================================================
【步骤 3】流量统计结果展示
======================================================================

【总体统计】
  总查询次数: 6
  总预估流量: 1,234,567 bytes (1.18 MB)
  缓存命中: 1 次
  缓存未命中: 5 次
  缓存命中率: 16.7%

【租户统计明细】
----------------------------------------------------------------------
租户             查询数      总流量(MB)      平均时间(ms)    总行数
----------------------------------------------------------------------
TENANT_001       4           0.75            12.34           534
TENANT_002       1           0.32            18.56           20
TENANT_003       1           0.11            9.87            500
----------------------------------------------------------------------

【最近查询详情（最后 5 条）】
----------------------------------------------------------------------

时间: 2026-03-10T15:31:15.123456
租户: TENANT_001
SQL: WITH recent_orders AS ( SELECT user_id, order_id, amount, created_at FROM orders WHERE te...
执行时间: 23.45 ms
返回行数: 10
预估流量: 320,000 bytes (0.31 MB)
查询代价: 1542.34
预估行数: 5000
缓存: ✗ 未命中

...

【验证 MD5 缓存】
✓ 缓存已清空

第 1 次查询: SELECT * FROM orders WHERE tenant_code = 'TENANT_001' LIMIT 5
  缓存大小: 1

第 2 次查询: SELECT  *  FROM  orders  WHERE  tenant_code='TENANT_001'  LIMIT  5
  缓存大小: 1
✓ MD5 缓存验证成功：相同 SQL 被识别为同一条

======================================================================
【演示完成】
======================================================================
✓ 日志文件: tenant_stats.log
✓ 所有功能验证通过

可以使用以下命令分析日志:
  cat tenant_stats.log | jq .
  cat tenant_stats.log | jq -r '.tenant_code' | sort | uniq -c
======================================================================
```

## 📈 统计报告可视化

执行完演示后，可以查看详细报告：

```bash
# 查看完整报告
python visualize_stats.py

# 只看租户排行
python visualize_stats.py -m tenant

# 只看慢查询 TOP 5
python visualize_stats.py -m slow -n 5

# 只看高流量查询
python visualize_stats.py -m traffic

# 查看时间线（按小时）
python visualize_stats.py -m timeline -g hour

# 查看缓存统计
python visualize_stats.py -m cache
```

### 报告示例

```
================================================================================
                              租户流量排行
================================================================================
排名   租户             查询数      流量(MB)     平均时间(ms)    总行数
--------------------------------------------------------------------------------
1      TENANT_001       15          2.45         14.23           1234
2      TENANT_002       8           1.32         11.56           567
3      TENANT_003       6           0.87         9.78            345

================================================================================
                              TOP 5 高流量查询
================================================================================

【第 1 名】
租户:     TENANT_001
时间:     2026-03-10T15:31:15.123456
预估流量: 0.95 MB (999,424 bytes)
查询代价: 2340.56
预估行数: 15,600
执行时间: 45.67 ms
SQL:      SELECT * FROM orders WHERE tenant_code = 'TENANT_001' ORDER BY created_at DESC LIMIT 500

...

================================================================================
                              缓存效果分析
================================================================================
缓存命中:   5 (25.0%)
缓存未命中: 15 (75.0%)

预计节省时间: ~75 ms (0.08 秒)
```

## 🎯 验证要点

### ✅ 1. 租户识别

检查日志文件，确认 `tenant_code` 被正确提取：

```bash
cat tenant_stats.log | jq -r '.tenant_code' | sort | uniq
```

预期输出：
```
TENANT_001
TENANT_002
TENANT_003
```

### ✅ 2. 流量统计

检查是否包含预估流量数据：

```bash
cat tenant_stats.log | jq 'select(.estimated_traffic_mb != null)'
```

应该能看到 `estimated_traffic_bytes`、`total_cost`、`plan_rows` 等字段。

### ✅ 3. MD5 缓存

检查缓存命中情况：

```bash
cat tenant_stats.log | jq 'select(.from_cache == true)'
```

重复的查询应该显示 `"from_cache": true`。

### ✅ 4. 性能影响

对比带缓存和不带缓存的执行时间：

```bash
# 缓存未命中的查询
cat tenant_stats.log | jq 'select(.from_cache == false) | .execution_time_ms'

# 缓存命中的查询
cat tenant_stats.log | jq 'select(.from_cache == true) | .execution_time_ms'
```

缓存命中的查询应该更快（节省 EXPLAIN 时间）。

## 🔧 自定义测试

如果你想测试自己的 SQL：

```python
# 修改 demo_traffic_stats.py 中的 test_cases
test_cases = [
    {
        'name': '你的测试名称',
        'tenant': 'YOUR_TENANT',
        'sql': "你的 SQL 语句"
    }
]
```

或者直接在应用中使用：

```python
from proxy_pool import ProxyConnectionPool
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

proxy_pool = ProxyConnectionPool(config)
await proxy_pool.initialize()

# 执行查询（自动统计）
async with proxy_pool.acquire() as conn:
    result = await conn.fetch("你的 SQL")

# 等待统计写入
await asyncio.sleep(1)

# 查看统计
stats = proxy_pool.get_stats()
print(stats)
```

## ⚙️ 配置说明

演示程序使用 `config.yaml` 中的配置：

```yaml
backend:
  host: localhost      # ← 修改为你的数据库地址
  port: 5432
  database: test       # ← 修改为你的数据库名
  user: dbtest1        # ← 修改为你的用户名
  password: dbtest1    # ← 修改为你的密码

logging:
  log_file: tenant_stats.log
  enable_cache: true   # ← 启用 MD5 缓存
```

## 🚨 常见问题

### Q: 演示程序无法连接数据库？

A: 检查 `config.yaml` 中的数据库配置是否正确。

### Q: 没有看到预估流量数据？

A: 确保数据库用户有 `EXPLAIN` 权限：

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dbtest1;
```

### Q: 日志文件在哪里？

A: 默认在 `tenant_stats.log`，可在 `config.yaml` 中修改。

### Q: 如何清空测试数据？

A: 重新运行演示程序会自动清空旧数据（DROP TABLE）。

或者手动执行：

```sql
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS users CASCADE;
```

## 📚 相关文档

- [README_GATEWAY.md](README_GATEWAY.md) - 完整使用指南
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - 项目架构说明
- [proxy_pool.py](proxy_pool.py) - 核心代码

---

**开始验证流量统计功能吧！** 🚀
