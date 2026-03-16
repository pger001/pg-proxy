#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web API 示例：使用 FastAPI + 代理连接池
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import yaml
from proxy_pool import ProxyConnectionPool
from contextlib import asynccontextmanager
import uvicorn

# 全局代理连接池
proxy_pool: Optional[ProxyConnectionPool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期管理"""
    global proxy_pool
    
    # 启动时初始化
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    proxy_pool = ProxyConnectionPool(config)
    await proxy_pool.initialize()
    print("✓ 代理连接池已初始化")
    
    yield
    
    # 关闭时清理
    await proxy_pool.close()
    print("✓ 代理连接池已关闭")


app = FastAPI(
    title="Tenant Stats API",
    description="带租户流量统计的 PostgreSQL API",
    lifespan=lifespan
)


class Order(BaseModel):
    order_id: int
    amount: float
    status: str
    created_at: str


class TenantStats(BaseModel):
    tenant_code: str
    total_orders: int
    total_amount: float
    avg_amount: float


@app.get("/")
async def root():
    """健康检查"""
    stats = proxy_pool.get_stats()
    return {
        "status": "running",
        "proxy_stats": stats
    }


@app.get("/tenants/{tenant_code}/orders", response_model=List[Order])
async def get_tenant_orders(
    tenant_code: str,
    limit: int = Query(default=100, le=1000)
):
    """获取租户订单"""
    async with proxy_pool.acquire() as conn:
        try:
            query = f"""
                SELECT order_id, amount, status, created_at::text
                FROM orders
                WHERE tenant_code = '{tenant_code}'
                ORDER BY created_at DESC
                LIMIT {limit}
            """
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/tenants/{tenant_code}/stats", response_model=TenantStats)
async def get_tenant_stats(tenant_code: str):
    """获取租户统计"""
    async with proxy_pool.acquire() as conn:
        try:
            query = f"""
                SELECT 
                    '{tenant_code}' as tenant_code,
                    COUNT(*) as total_orders,
                    COALESCE(SUM(amount), 0) as total_amount,
                    COALESCE(AVG(amount), 0) as avg_amount
                FROM orders
                WHERE tenant_code = '{tenant_code}'
                  AND status = 'completed'
            """
            row = await conn.fetchrow(query)
            if not row:
                raise HTTPException(status_code=404, detail="Tenant not found")
            return dict(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_proxy_stats():
    """获取代理统计"""
    return proxy_pool.get_stats()


@app.post("/admin/clear-cache")
async def clear_cache():
    """清空 EXPLAIN 缓存"""
    if proxy_pool and proxy_pool.tracker:
        proxy_pool.tracker.cache.clear()
        return {"message": "Cache cleared", "cache_size": 0}
    return {"error": "Tracker not initialized"}


if __name__ == "__main__":
    print("🚀 启动 Web API 服务器...")
    print("📡 访问 http://localhost:8000/docs 查看 API 文档")
    uvicorn.run(app, host="0.0.0.0", port=8000)
