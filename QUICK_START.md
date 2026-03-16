# PostgreSQL Gateway 快速开始指南

## 🎯 5分钟快速集成

### 步骤 1: 基础使用

最简单的使用方式：

```python
import asyncio
import yaml
from proxy_pool import ProxyConnectionPool

async def main():
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 初始化代理连接池
    pool = ProxyConnectionPool(config)
    await pool.initialize()
    
    try:
        # 执行查询 - 自动统计租户流量
        async with pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT * FROM orders 
                WHERE tenant_code = 'TENANT_001' 
                LIMIT 10
            """)
            print(f"找到 {len(result)} 条订单")
    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(main())
```

### 步骤 2: 在现有应用中集成

替换现有的 `asyncpg.create_pool()`：

**原始代码：**
```python
# 旧代码
pool = await asyncpg.create_pool(
    host='localhost',
    port=5432,
    database='test',
    user='dbtest1',
    password='password'
)
async with pool.acquire() as conn:
    result = await conn.fetch("SELECT * FROM orders")
```

**替换为：**
```python
# 新代码 - 带流量统计
pool = ProxyConnectionPool(config)
await pool.initialize()

# 使用方式完全相同！
async with pool.acquire() as conn:
    result = await conn.fetch("SELECT * FROM orders")
# 查询会自动记录到 tenant_stats.log
```

### 步骤 3: 配置租户识别规则

编辑 `config.yaml`，支持你的租户字段：

```yaml
backend:
  host: localhost
  port: 5432
  database: your_db
  user: your_user
  password: your_password

gateway:
  host: 0.0.0.0
  port: 15432
  max_connections: 100

logging:
  log_file: tenant_stats.log
  enable_cache: true
```

### 步骤 4: 分析统计数据

```bash
# 方法 1: 使用可视化工具
python visualize_stats.py

# 方法 2: 使用 jq 命令行分析
cat tenant_stats.log | jq -r '.tenant_code' | sort | uniq -c
cat tenant_stats.log | jq 'select(.estimated_traffic_mb > 1)'

# 方法 3: Python 直接读取
import json
with open('tenant_stats.log') as f:
    for line in f:
        record = json.loads(line)
        print(f"{record['tenant_code']}: {record['estimated_traffic_mb']} MB")
```

## 📊 实时查看统计

运行示例应用后查看结果：

```bash
# 运行示例
python app_example.py

# 实时监控日志
tail -f tenant_stats.log | jq .

# 查看统计报告
python visualize_stats.py
```

## 🔧 高级功能

### 1. 自定义租户提取规则

修改 `proxy_pool.py` 中的 `extract_tenant_code()` 方法：

```python
def extract_tenant_code(self, sql: str) -> Optional[str]:
    patterns = [
        r"tenant_code\s*=\s*'([^']+)'",
        r"company_id\s*=\s*'([^']+)'",  # 添加你的字段
        r"org_id\s*=\s*'([^']+)'",      # 添加更多模式
    ]
    for pattern in patterns:
        match = re.search(pattern, sql, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
```

### 2. 禁用/启用 EXPLAIN 缓存

在 `config.yaml` 中：

```yaml
logging:
  enable_cache: false  # 禁用缓存，每次都执行 EXPLAIN
```

### 3. 调整批量写入参数

修改 `proxy_pool.py` 中的 `start_writer()` 方法：

```python
# 每 10 条或 5 秒刷新
if len(buffer) >= 10 or self.stats_queue.empty():
    await flush_buffer()
```

改为：

```python
# 每 50 条或 10 秒刷新（适合高并发场景）
if len(buffer) >= 50 or self.stats_queue.empty():
    await flush_buffer()
```

## 📈 性能特性

- ✅ **零性能开销** - 异步统计，不阻塞查询
- ✅ **智能缓存** - EXPLAIN 结果缓存，减少数据库负载
- ✅ **批量写入** - 队列缓冲，减少磁盘 I/O
- ✅ **连接池管理** - 自动管理连接，支持高并发

## 🎯 典型使用场景

### 场景 1: Multi-tenant SaaS
```python
async def get_customer_data(customer_id: str):
    async with pool.acquire() as conn:
        # tenant_code 自动识别
        return await conn.fetch(f"""
            SELECT * FROM data 
            WHERE tenant_code = '{customer_id}'
        """)
```

### 场景 2: 流量监控
```bash
# 每小时生成报告
*/60 * * * * python visualize_stats.py > /var/log/tenant_report.txt
```

### 场景 3: 费用计算
```python
import json

def calculate_monthly_cost(tenant_code: str):
    total_traffic = 0
    with open('tenant_stats.log') as f:
        for line in f:
            record = json.loads(line)
            if record['tenant_code'] == tenant_code:
                total_traffic += record.get('estimated_traffic_bytes', 0)
    
    # 按流量计费: $0.10/GB
    cost = (total_traffic / 1024 / 1024 / 1024) * 0.10
    return cost
```

## 🚀 生产环境部署

### 1. 日志轮转

```bash
# 使用 logrotate
cat > /etc/logrotate.d/tenant_stats << EOF
/path/to/tenant_stats.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 app app
}
EOF
```

### 2. 监控告警

```python
# 监控高流量租户
def check_high_traffic_tenants():
    import json
    from collections import defaultdict
    
    tenant_traffic = defaultdict(int)
    with open('tenant_stats.log') as f:
        for line in f:
            record = json.loads(line)
            tenant_traffic[record['tenant_code']] += record.get('estimated_traffic_mb', 0)
    
    for tenant, traffic in tenant_traffic.items():
        if traffic > 1000:  # 超过 1GB
            send_alert(f"租户 {tenant} 流量异常: {traffic} MB")
```

### 3. 性能优化

```yaml
# config.yaml - 生产环境配置
gateway:
  max_connections: 200  # 根据服务器资源调整
  
logging:
  enable_cache: true    # 启用缓存减少负载
  log_file: /var/log/tenant_stats.log
```

## 📚 完整 API 参考

### ProxyConnectionPool

```python
class ProxyConnectionPool:
    async def initialize()              # 初始化连接池
    async def acquire() -> StatsConnection  # 获取连接
    async def close()                   # 关闭连接池
    def get_stats() -> Dict             # 获取统计信息
```

### StatsConnection (透明代理)

支持所有 asyncpg.Connection 方法：
- `fetch(query)` - 返回多行
- `fetchrow(query)` - 返回单行
- `fetchval(query)` - 返回单值
- `execute(query)` - 执行命令

## 🎓 更多示例

参考项目中的示例文件：

- `app_example.py` - 基础应用示例
- `api_example.py` - FastAPI Web 服务示例
- `demo_traffic_stats.py` - 完整功能演示
- `visualize_stats.py` - 数据可视化工具

## 💡 常见问题

**Q: 如何只统计特定表的查询？**
```python
# 修改 track_query() 方法
async def track_query(self, sql: str, ...):
    if 'FROM orders' not in sql.lower():
        return  # 跳过非 orders 表的查询
    # ... 继续统计
```

**Q: 日志文件太大怎么办？**
- 使用 logrotate 自动归档
- 定期分析后清理: `> tenant_stats.log`
- 导入数据库长期存储

**Q: 支持其他数据库吗？**
- 目前仅支持 PostgreSQL
- 原理可扩展到 MySQL (需要适配 EXPLAIN 格式)

---

🎉 **开始使用吧！**

有问题查看文档：
- README_GATEWAY.md - 架构说明
- DEMO_GUIDE.md - 演示指南
- PROJECT_SUMMARY.md - 项目总结
