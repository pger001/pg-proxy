-- 示例 1: 简单查询
SELECT * FROM orders WHERE tenant_code = 'TENANT_001' AND status = 'active';

-- 示例 2: 包含 JOIN 的复杂查询
SELECT 
    o.order_id,
    o.amount,
    c.customer_name,
    p.product_name
FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN products p ON o.product_id = p.id
WHERE o.tenant_code = 'TENANT_002'
  AND o.created_at >= '2026-01-01'
ORDER BY o.amount DESC
LIMIT 1000;

-- 示例 3: 多层 CTE（适合测试 500 行长 SQL 场景）
WITH RECURSIVE tenant_hierarchy AS (
    -- 基础层：直接子组织
    SELECT 
        org_id,
        parent_org_id,
        org_name,
        1 as level
    FROM organizations
    WHERE tenant_code = 'TENANT_003'
      AND parent_org_id IS NULL
    
    UNION ALL
    
    -- 递归层：所有子孙组织
    SELECT 
        o.org_id,
        o.parent_org_id,
        o.org_name,
        th.level + 1
    FROM organizations o
    INNER JOIN tenant_hierarchy th ON o.parent_org_id = th.org_id
    WHERE o.tenant_code = 'TENANT_003'
),
org_users AS (
    SELECT 
        ou.org_id,
        ou.user_id,
        u.username,
        u.email,
        u.created_at
    FROM org_users ou
    JOIN users u ON ou.user_id = u.id
    WHERE ou.tenant_code = 'TENANT_003'
      AND u.status = 'active'
),
user_orders AS (
    SELECT 
        ou.org_id,
        ou.user_id,
        o.order_id,
        o.amount,
        o.created_at as order_date
    FROM org_users ou
    JOIN orders o ON ou.user_id = o.user_id
    WHERE o.tenant_code = 'TENANT_003'
      AND o.status IN ('completed', 'shipped')
      AND o.created_at >= CURRENT_DATE - INTERVAL '90 days'
),
org_stats AS (
    SELECT 
        th.org_id,
        th.org_name,
        th.level,
        COUNT(DISTINCT ou.user_id) as user_count,
        COUNT(uo.order_id) as order_count,
        COALESCE(SUM(uo.amount), 0) as total_amount,
        COALESCE(AVG(uo.amount), 0) as avg_order_amount
    FROM tenant_hierarchy th
    LEFT JOIN org_users ou ON th.org_id = ou.org_id
    LEFT JOIN user_orders uo ON ou.user_id = uo.user_id
    GROUP BY th.org_id, th.org_name, th.level
),
ranked_orgs AS (
    SELECT 
        org_id,
        org_name,
        level,
        user_count,
        order_count,
        total_amount,
        avg_order_amount,
        ROW_NUMBER() OVER (PARTITION BY level ORDER BY total_amount DESC) as rank_in_level,
        PERCENT_RANK() OVER (ORDER BY total_amount) as percentile
    FROM org_stats
    WHERE user_count > 0
)
SELECT 
    ro.org_id,
    ro.org_name,
    ro.level,
    ro.user_count,
    ro.order_count,
    ROUND(ro.total_amount::numeric, 2) as total_amount,
    ROUND(ro.avg_order_amount::numeric, 2) as avg_order_amount,
    ro.rank_in_level,
    ROUND(ro.percentile::numeric, 4) as percentile,
    CASE 
        WHEN ro.percentile >= 0.9 THEN 'Top 10%'
        WHEN ro.percentile >= 0.75 THEN 'Top 25%'
        WHEN ro.percentile >= 0.5 THEN 'Top 50%'
        ELSE 'Bottom 50%'
    END as performance_tier
FROM ranked_orgs ro
WHERE ro.rank_in_level <= 20
ORDER BY ro.level, ro.rank_in_level;

-- 示例 4: 包含子查询和窗口函数
SELECT 
    t.tenant_code,
    t.order_date,
    t.daily_revenue,
    t.daily_orders,
    AVG(t.daily_revenue) OVER (
        PARTITION BY t.tenant_code 
        ORDER BY t.order_date 
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) as moving_avg_7day,
    SUM(t.daily_orders) OVER (
        PARTITION BY t.tenant_code 
        ORDER BY t.order_date 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as cumulative_orders
FROM (
    SELECT 
        tenant_code,
        DATE(created_at) as order_date,
        SUM(amount) as daily_revenue,
        COUNT(*) as daily_orders
    FROM orders
    WHERE tenant_code = 'TENANT_004'
      AND created_at >= CURRENT_DATE - INTERVAL '180 days'
    GROUP BY tenant_code, DATE(created_at)
) t
ORDER BY t.order_date DESC;
