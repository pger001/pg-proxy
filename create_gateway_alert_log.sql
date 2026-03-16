-- ============================================================
-- 告警记录表：gateway_alert_log
-- 存储慢查询超时告警 和 租户高频查询告警
-- ============================================================
CREATE TABLE IF NOT EXISTS public.gateway_alert_log (
    id               SERIAL PRIMARY KEY,
    alert_type       VARCHAR(30)   NOT NULL,   -- SLOW_QUERY | HIGH_FREQUENCY
    alert_level      VARCHAR(10)   NOT NULL DEFAULT 'WARNING',  -- INFO | WARNING | CRITICAL
    tenant_code      VARCHAR(100),
    dataset_id       VARCHAR(200),
    request_log_id   BIGINT,                   -- 关联 gateway_sql_request_log.id（慢查询时填）
    request_id       VARCHAR(200),
    metric_value     NUMERIC(18,4),            -- 触发告警的指标值（ms 或 次/分钟）
    threshold_value  NUMERIC(18,4),            -- 告警阈值
    metric_unit      VARCHAR(30),              -- ms | count/min
    detail           TEXT,                     -- 告警详情描述
    notified_teams   BOOLEAN       NOT NULL DEFAULT FALSE,  -- 是否已推送 Teams
    notified_at      TIMESTAMPTZ,              -- 推送时间
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_gateway_alert_log_created_at
    ON public.gateway_alert_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gateway_alert_log_alert_type
    ON public.gateway_alert_log (alert_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gateway_alert_log_tenant
    ON public.gateway_alert_log (tenant_code, created_at DESC);

COMMENT ON TABLE  public.gateway_alert_log IS '查询告警记录：慢查询超时 & 租户高频查询';
COMMENT ON COLUMN public.gateway_alert_log.alert_type     IS '告警类型：SLOW_QUERY=慢查询超时, HIGH_FREQUENCY=高频查询';
COMMENT ON COLUMN public.gateway_alert_log.metric_value   IS '实际采集的指标数值';
COMMENT ON COLUMN public.gateway_alert_log.threshold_value IS '触发告警的阈值';
COMMENT ON COLUMN public.gateway_alert_log.notified_teams IS '是否已通过 Teams Webhook 发送通知';
