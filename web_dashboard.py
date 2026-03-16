#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Dashboard - Flask REST API Service for PostgreSQL Gateway
"""

from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import yaml
import json
import threading
import asyncio
import sys
import os
import urllib.request
from datetime import datetime

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ============================================================
# 后台自动采集（每 AUTO_COLLECT_INTERVAL_SEC 秒轮询一次）
# ============================================================
AUTO_COLLECT_INTERVAL_SEC = 60   # 可按需调整

_collect_lock = threading.Lock()        # 防止并发采集
_collect_status = {
    'running':       False,
    'last_run_at':   None,   # ISO string
    'last_result':   None,   # dict: {batches, fetched, success, failed}
    'last_error':    None,
    'total_runs':    0,
    'total_collected': 0,
}


# ============================================================
# 告警引擎
# ============================================================

def _load_alert_config() -> dict:
    """读取告警配置（defaults 兜底）"""
    config = yaml.safe_load(open('config.yaml', encoding='utf-8'))
    a = config.get('alerting') or {}
    return {
        'slow_query_threshold_ms':          float(a.get('slow_query_threshold_ms', 1000)),
        'high_frequency_threshold_per_min': int(a.get('high_frequency_threshold_per_min', 30)),
        'teams_webhook_url':                (a.get('teams_webhook_url') or '').strip(),
    }


def _ensure_alert_table(conn) -> None:
    """按需创建告警表（幂等）"""
    ddl_path = os.path.join(os.path.dirname(__file__), 'create_gateway_alert_log.sql')
    with open(ddl_path, encoding='utf-8') as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _ensure_collect_log_table(conn) -> None:
    """按需创建采集日志表（幂等）"""
    ddl = """
        CREATE TABLE IF NOT EXISTS public.gateway_collect_log (
            id              SERIAL PRIMARY KEY,
            collected_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            trigger_type    VARCHAR(20) NOT NULL DEFAULT 'auto',
            status          VARCHAR(20) NOT NULL,
            batches         INTEGER,
            fetched         INTEGER,
            success_count   INTEGER,
            failed_count    INTEGER,
            error_message   TEXT,
            duration_ms     INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_gateway_collect_log_at
            ON public.gateway_collect_log (collected_at DESC);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _insert_alert(conn, alert_type: str, alert_level: str, tenant_code,
                  dataset_id, request_log_id, request_id,
                  metric_value: float, threshold_value: float,
                  metric_unit: str, detail: str) -> int:
    """写入一条告警记录，返回新记录 id"""
    sql = """
        INSERT INTO public.gateway_alert_log
            (alert_type, alert_level, tenant_code, dataset_id,
             request_log_id, request_id,
             metric_value, threshold_value, metric_unit, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (alert_type, alert_level, tenant_code, dataset_id,
                          request_log_id, request_id,
                          metric_value, threshold_value, metric_unit, detail))
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id


def _send_teams_message(webhook_url: str, alerts: list) -> bool:
    """
    将多条告警批量发送到 Teams Incoming Webhook（Adaptive Card 格式）。
    alerts: list of dict with keys alert_type/tenant_code/detail/metric_value/metric_unit
    返回是否成功。
    """
    if not webhook_url or not alerts:
        return False

    slow   = [a for a in alerts if a['alert_type'] == 'SLOW_QUERY']
    high   = [a for a in alerts if a['alert_type'] == 'HIGH_FREQUENCY']

    lines = []
    if slow:
        lines.append(f"🐢 **慢查询告警** × {len(slow)} 条")
        for a in slow[:5]:
            lines.append(f"  • 租户 `{a['tenant_code']}` — {a['metric_value']:.0f} ms  ({a['detail'][:80]})")
        if len(slow) > 5:
            lines.append(f"  … 还有 {len(slow)-5} 条")
    if high:
        lines.append(f"🔥 **高频查询告警** × {len(high)} 条")
        for a in high[:5]:
            lines.append(f"  • 租户 `{a['tenant_code']}` — {a['metric_value']:.0f} 次/分钟  ({a['detail'][:80]})")
        if len(high) > 5:
            lines.append(f"  … 还有 {len(high)-5} 条")

    body_text = "\n".join(lines)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Teams Adaptive Card payload (simple MessageCard fallback compatible)
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000",
        "summary": f"MSPBots Gateway 告警 ({len(alerts)} 条)",
        "sections": [{
            "activityTitle": f"⚠️ MSPBots SQL Gateway 告警通知",
            "activitySubtitle": f"{ts}  共 {len(alerts)} 条告警",
            "activityText": body_text,
            "markdown": True
        }]
    }

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 202)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Teams 推送失败: %s", exc)
        return False


def _mark_alerts_notified(conn, alert_ids: list) -> None:
    if not alert_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.gateway_alert_log SET notified_teams=TRUE, notified_at=NOW() WHERE id = ANY(%s)",
            (alert_ids,)
        )
    conn.commit()


def _check_and_fire_alerts(config: dict) -> dict:
    """
    采集完成后检测告警：
    1. 慢查询：gateway_sql_resource_usage 中 execution_time_ms > threshold 的新增记录
    2. 高频查询：过去 1 分钟内 tenant_stats 中每租户查询次数超阈值
    将告警写库，并批量推送 Teams。
    返回 summary dict。
    """
    import logging
    logger = logging.getLogger(__name__)

    alert_cfg = _load_alert_config()
    slow_ms   = alert_cfg['slow_query_threshold_ms']
    hf_limit  = alert_cfg['high_frequency_threshold_per_min']
    webhook   = alert_cfg['teams_webhook_url']

    summary = {'slow_query': 0, 'high_frequency': 0, 'teams_sent': False}

    try:
        conn = get_db_connection()
        _ensure_alert_table(conn)

        new_alert_ids   = []
        new_alert_rows  = []

        # ── 1. 慢查询告警 ─────────────────────────────────────────
        # 仅检测最近 2 分钟内分析完成的、尚未告警的记录
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.request_log_id, u.request_id,
                       u.tenant_code, u.dataset_id,
                       u.execution_time_ms, u.sql_resolved
                FROM public.gateway_sql_resource_usage u
                WHERE u.execution_time_ms > %s
                  AND u.analyzed_at >= NOW() - INTERVAL '2 minutes'
                  AND NOT EXISTS (
                      SELECT 1 FROM public.gateway_alert_log al
                      WHERE al.alert_type = 'SLOW_QUERY'
                        AND al.request_log_id = u.request_log_id
                  )
                ORDER BY u.execution_time_ms DESC
                LIMIT 200
            """, (slow_ms,))
            slow_rows = cur.fetchall()

        for row in slow_rows:
            exec_ms = float(row['execution_time_ms'] or 0)
            sql_preview = (row['sql_resolved'] or '')[:120]
            detail = f"执行时间 {exec_ms:.0f}ms > 阈值 {slow_ms:.0f}ms，SQL: {sql_preview}"
            aid = _insert_alert(
                conn,
                alert_type='SLOW_QUERY', alert_level='WARNING',
                tenant_code=row['tenant_code'], dataset_id=row['dataset_id'],
                request_log_id=row['request_log_id'], request_id=row['request_id'],
                metric_value=exec_ms, threshold_value=slow_ms,
                metric_unit='ms', detail=detail
            )
            new_alert_ids.append(aid)
            new_alert_rows.append({'alert_type': 'SLOW_QUERY', 'tenant_code': row['tenant_code'],
                                   'metric_value': exec_ms, 'metric_unit': 'ms', 'detail': detail})
            summary['slow_query'] += 1

        # ── 2. 高频查询告警 ───────────────────────────────────────
        # 统计 tenant_stats 过去 1 分钟内每租户查询次数
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT tenant_code, COUNT(*) AS cnt
                FROM public.tenant_stats
                WHERE timestamp >= NOW() - INTERVAL '1 minute'
                GROUP BY tenant_code
                HAVING COUNT(*) > %s
            """, (hf_limit,))
            hf_rows = cur.fetchall()

        for row in hf_rows:
            cnt = int(row['cnt'])
            detail = f"租户 {row['tenant_code']} 1分钟内查询 {cnt} 次，超过阈值 {hf_limit} 次/分钟"
            # 同一租户同一分钟只插一次
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM public.gateway_alert_log
                    WHERE alert_type = 'HIGH_FREQUENCY'
                      AND tenant_code = %s
                      AND created_at >= NOW() - INTERVAL '1 minute'
                    LIMIT 1
                """, (row['tenant_code'],))
                already = cur.fetchone()
            if already:
                continue

            aid = _insert_alert(
                conn,
                alert_type='HIGH_FREQUENCY', alert_level='WARNING',
                tenant_code=row['tenant_code'], dataset_id=None,
                request_log_id=None, request_id=None,
                metric_value=cnt, threshold_value=hf_limit,
                metric_unit='count/min', detail=detail
            )
            new_alert_ids.append(aid)
            new_alert_rows.append({'alert_type': 'HIGH_FREQUENCY', 'tenant_code': row['tenant_code'],
                                   'metric_value': cnt, 'metric_unit': 'count/min', 'detail': detail})
            summary['high_frequency'] += 1

        # ── 3. Teams 推送 ────────────────────────────────────────
        if new_alert_rows and webhook:
            ok = _send_teams_message(webhook, new_alert_rows)
            if ok:
                _mark_alerts_notified(conn, new_alert_ids)
            summary['teams_sent'] = ok

        conn.close()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("告警检测异常: %s", exc)

    return summary


def _run_collect_sync(config: dict) -> dict:
    """阻塞式调用 asyncio 采集逻辑，返回 summary dict"""
    # 避免 Windows 上 asyncio 子循环警告
    if sys.platform == 'win32':
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.new_event_loop()

    async def _inner():
        # 延迟导入，避免启动时依赖问题
        sys.path.insert(0, os.path.dirname(__file__))
        from collect_gateway_sql_resource_usage import GatewaySqlResourceCollector
        collector = GatewaySqlResourceCollector(config)
        await collector.connect()
        try:
            await collector.ensure_usage_table()
            return await collector.run(
                batch_size=200,
                statuses=['SUCCESS', 'FAILED', 'TIMEOUT'],
                request_id=None,
                force=False,
                max_batches=0,
            )
        finally:
            await collector.close()

    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _do_collect(trigger_type: str = 'auto'):
    """单次采集，更新全局状态（线程安全）"""
    if not _collect_lock.acquire(blocking=False):
        return   # 上一次还没结束，跳过
    _start_time = datetime.now()
    _result = None
    _error  = None
    try:
        _collect_status['running'] = True
        config = yaml.safe_load(open('config.yaml', encoding='utf-8'))
        _result = _run_collect_sync(config)
        _collect_status['last_result']  = _result
        _collect_status['last_error']   = None
        _collect_status['total_runs']   += 1
        _collect_status['total_collected'] += _result.get('success', 0)
        _check_and_fire_alerts(config)   # 采集后触发告警检测
    except Exception as e:
        _error = str(e)
        _collect_status['last_error'] = _error
    finally:
        _collect_status['running']     = False
        _collect_status['last_run_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        _collect_lock.release()
        # 写采集日志到数据库
        try:
            duration_ms = int((datetime.now() - _start_time).total_seconds() * 1000)
            _log_conn = get_db_connection()
            _ensure_collect_log_table(_log_conn)
            with _log_conn.cursor() as _cur:
                _cur.execute("""
                    INSERT INTO public.gateway_collect_log
                        (trigger_type, status, batches, fetched, success_count, failed_count, error_message, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    trigger_type,
                    'FAILED' if _error else 'SUCCESS',
                    _result.get('batches', 0) if _result else None,
                    _result.get('fetched', 0) if _result else None,
                    _result.get('success', 0) if _result else None,
                    _result.get('failed', 0) if _result else None,
                    _error,
                    duration_ms,
                ))
                # 自动清理7天前旧日志
                _cur.execute("DELETE FROM public.gateway_collect_log WHERE collected_at < NOW() - INTERVAL '7 days'")
            _log_conn.commit()
            _log_conn.close()
        except Exception:
            pass


def _auto_collect_loop():
    """后台守护线程：定期触发采集"""
    import time
    while True:
        try:
            _do_collect()
        except Exception:
            pass
        time.sleep(AUTO_COLLECT_INTERVAL_SEC)


# 启动后台采集线程
_bg_thread = threading.Thread(target=_auto_collect_loop, daemon=True, name='auto-collector')
_bg_thread.start()

# Database configuration
def get_db_config():
    """Get database configuration"""
    config = yaml.safe_load(open('config.yaml', encoding='utf-8'))
    return config['backend']

def get_db_connection():
    """Create database connection"""
    db_config = get_db_config()
    return psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password'],
        cursor_factory=RealDictCursor
    )

def check_table_exists(cursor, table_name: str) -> bool:
    """Check whether table exists in public schema"""
    cursor.execute("SELECT to_regclass(%s) as table_ref", (f'public.{table_name}',))
    result = cursor.fetchone()
    return bool(result and result.get('table_ref'))

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Get statistics summary (from gateway_sql_resource_usage for accuracy)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify({
                'total_queries': 0, 'total_traffic_mb': 0.0,
                'total_execution_time_ms': 0.0, 'avg_execution_time_ms': 0.0,
                'avg_time_ms': 0.0, 'cache_hits': 0, 'cache_misses': 0, 'cache_hit_rate': 0.0
            })

        cursor.execute("""
            SELECT
                COUNT(*)                    AS total_queries,
                SUM(io_total_bytes)         AS total_io_bytes,
                SUM(execution_time_ms)      AS total_execution_time,
                AVG(execution_time_ms)      AS avg_execution_time
            FROM public.gateway_sql_resource_usage
        """)

        result = cursor.fetchone()

        # cache stats still come from tenant_stats (gateway_sql_resource_usage has no from_cache field)
        cursor.execute("""
            SELECT
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) AS cache_hits,
                COUNT(*) AS total_ts
            FROM public.tenant_stats
        """)
        cache_result = cursor.fetchone()
        cursor.close()
        conn.close()

        total_queries = int(result['total_queries'] or 0)
        cache_hits    = int(cache_result['cache_hits'] or 0)
        total_ts      = int(cache_result['total_ts'] or 1)

        return jsonify({
            'total_queries':          total_queries,
            'total_traffic_mb':       float((result['total_io_bytes'] or 0) / 1024 / 1024),
            'total_execution_time_ms': float(result['total_execution_time'] or 0),
            'avg_execution_time_ms':  float(result['avg_execution_time'] or 0),
            'avg_time_ms':            float(result['avg_execution_time'] or 0),
            'cache_hits':             cache_hits,
            'cache_misses':           total_ts - cache_hits,
            'cache_hit_rate':         float(cache_hits / total_ts * 100),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tenant-ranking', methods=['GET'])
def get_tenant_ranking():
    """Get tenant ranking by IO traffic from gateway_sql_resource_usage"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                tenant_code,
                COUNT(*)                                                AS query_count,
                COALESCE(SUM(io_total_bytes), 0)                        AS traffic_bytes,
                COALESCE(AVG(execution_time_ms) FILTER (WHERE execution_time_ms IS NOT NULL), 0) AS avg_time,
                COALESCE(SUM(rows) FILTER (WHERE rows IS NOT NULL), 0)  AS total_rows
            FROM public.gateway_sql_resource_usage
            GROUP BY tenant_code
            ORDER BY query_count DESC, traffic_bytes DESC NULLS LAST
            LIMIT 20
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx,
                'tenant_code': r['tenant_code'],
                'query_count': int(r['query_count']),
                'total_traffic_bytes': int(r['traffic_bytes'] or 0),
                'total_traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'avg_time_ms': float(r['avg_time'] or 0),
                'cache_hits': 0,
                'cache_rate': 0.0,
                'total_rows': int(r['total_rows'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/slow-queries', methods=['GET'])
def get_slow_queries():
    """Get slow queries from gateway_sql_resource_usage (by actual execution_time_ms)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COALESCE(execute_time, analyzed_at) AS timestamp,
                tenant_code,
                sql_resolved                        AS sql_preview,
                execution_time_ms,
                COALESCE(rows, 0)                   AS rows_returned,
                COALESCE(io_total_bytes, 0) / 1048576.0 AS estimated_traffic_mb
            FROM public.gateway_sql_resource_usage
            WHERE execution_time_ms IS NOT NULL
            ORDER BY execution_time_ms DESC
            LIMIT 10
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx,
                'timestamp': r['timestamp'].isoformat() if r['timestamp'] else None,
                'tenant_code': r['tenant_code'],
                'sql_preview': str(r['sql_preview'])[:80] if r['sql_preview'] else '',
                'execution_time_ms': float(r['execution_time_ms'] or 0),
                'rows_returned': int(r['rows_returned'] or 0),
                'traffic_mb': float(r['estimated_traffic_mb'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/high-traffic-queries', methods=['GET'])
def get_high_traffic_queries():
    """Get high-IO queries from gateway_sql_resource_usage (by io_total_bytes)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COALESCE(execute_time, analyzed_at)     AS timestamp,
                tenant_code,
                sql_resolved                            AS sql_preview,
                execution_time_ms,
                COALESCE(rows, 0)                       AS rows_returned,
                COALESCE(io_total_bytes, 0) / 1048576.0 AS estimated_traffic_mb,
                COALESCE(costs, 0)                      AS total_cost,
                COALESCE(plan_rows, 0)                  AS estimated_rows
            FROM public.gateway_sql_resource_usage
            ORDER BY io_total_bytes DESC NULLS LAST
            LIMIT 10
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx,
                'timestamp': r['timestamp'].isoformat() if r['timestamp'] else None,
                'tenant_code': r['tenant_code'],
                'sql_preview': str(r['sql_preview'])[:80] if r['sql_preview'] else '',
                'execution_time_ms': float(r['execution_time_ms'] or 0),
                'rows_returned': int(r['rows_returned'] or 0),
                'traffic_mb': float(r['estimated_traffic_mb'] or 0),
                'query_cost': float(r['total_cost'] or 0),
                'estimated_rows': int(r['estimated_rows'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/timeline', methods=['GET'])
def get_timeline():
    """Get time series data"""
    try:
        group_by = request.args.get('group_by', 'hour').strip().lower()
        days = max(1, min(int(request.args.get('days', 7)), 365))

        if group_by not in ('hour', 'day'):
            group_by = 'hour'

        trunc = "hour" if group_by == 'hour' else 'day'

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT
                DATE_TRUNC('{trunc}', COALESCE(execute_time, analyzed_at)) AS time_bucket,
                COUNT(*)                                                    AS query_count,
                COALESCE(SUM(io_total_bytes), 0)                           AS traffic_bytes,
                AVG(execution_time_ms)                                      AS avg_time,
                0                                                           AS cache_hits
            FROM public.gateway_sql_resource_usage
            WHERE COALESCE(execute_time, analyzed_at) IS NOT NULL
              AND COALESCE(execute_time, analyzed_at) >= NOW() - INTERVAL '{days} days'
            GROUP BY DATE_TRUNC('{trunc}', COALESCE(execute_time, analyzed_at))
            ORDER BY time_bucket
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for r in results:
            data.append({
                'time': r['time_bucket'].isoformat() if r['time_bucket'] else None,
                'timestamp': r['time_bucket'].isoformat() if r['time_bucket'] else None,
                'query_count': int(r['query_count']),
                'traffic_kb': float((r['traffic_bytes'] or 0) / 1024),
                'traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'avg_time_ms': float(r['avg_time'] or 0),
                'cache_hits': int(r['cache_hits'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache-stats', methods=['GET'])
def get_cache_stats():
    """Get cache statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                SUM(CASE WHEN from_cache THEN execution_time_ms ELSE 0 END) as cache_time_saved,
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as total_cache_hits,
                COUNT(*) as total_queries
            FROM public.tenant_stats
        """)
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'cache_hits': int(result['total_cache_hits'] or 0),
            'total_cache_hits': int(result['total_cache_hits'] or 0),
            'total_queries': int(result['total_queries'] or 0),
            'cache_hit_rate': float((result['total_cache_hits'] or 0) / (result['total_queries'] or 1) * 100),
            'saved_time_ms': float(result['cache_time_saved'] or 0),
            'time_saved_ms': float(result['cache_time_saved'] or 0)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resource-summary', methods=['GET'])
def get_resource_summary():
    """Get resource usage summary from gateway_sql_resource_usage"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify({
                'table_exists': False,
                'total_sql_count': 0,
                'total_tenants': 0,
                'total_io_mb': 0.0,
                'total_rows': 0,
                'total_cpu_ms': 0.0,
                'total_costs': 0.0,
                'avg_execution_time_ms': 0.0,
                'success_count': 0,
                'non_success_count': 0
            })

        cursor.execute("""
            SELECT
                COUNT(*) as total_sql_count,
                COUNT(DISTINCT tenant_code) as total_tenants,
                SUM(io_total_bytes) as total_io_bytes,
                SUM(rows) as total_rows,
                SUM(cpu_time_ms) as total_cpu_ms,
                SUM(costs) as total_costs,
                AVG(execution_time_ms) as avg_execution_time_ms,
                SUM(CASE WHEN execute_status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN execute_status <> 'SUCCESS' THEN 1 ELSE 0 END) as non_success_count
            FROM public.gateway_sql_resource_usage
        """)

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        return jsonify({
            'table_exists': True,
            'total_sql_count': int(result['total_sql_count'] or 0),
            'total_tenants': int(result['total_tenants'] or 0),
            'total_io_mb': float((result['total_io_bytes'] or 0) / 1024 / 1024),
            'total_rows': int(result['total_rows'] or 0),
            'total_cpu_ms': float(result['total_cpu_ms'] or 0),
            'total_costs': float(result['total_costs'] or 0),
            'avg_execution_time_ms': float(result['avg_execution_time_ms'] or 0),
            'success_count': int(result['success_count'] or 0),
            'non_success_count': int(result['non_success_count'] or 0)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resource-tenant-ranking', methods=['GET'])
def get_resource_tenant_ranking():
    """Get resource usage ranking by tenant"""
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 200))

        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify([])

        cursor.execute("""
            SELECT
                tenant_code,
                COUNT(*) as sql_count,
                SUM(io_total_bytes) as io_total_bytes,
                SUM(rows) as total_rows,
                SUM(cpu_time_ms) as total_cpu_ms,
                SUM(costs) as total_costs,
                AVG(execution_time_ms) as avg_execution_time_ms
            FROM public.gateway_sql_resource_usage
            GROUP BY tenant_code
            ORDER BY total_costs DESC NULLS LAST, io_total_bytes DESC NULLS LAST
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for idx, row in enumerate(rows, 1):
            data.append({
                'rank': idx,
                'tenant_code': row['tenant_code'],
                'sql_count': int(row['sql_count'] or 0),
                'io_total_bytes': int(row['io_total_bytes'] or 0),
                'io_total_mb': float((row['io_total_bytes'] or 0) / 1024 / 1024),
                'total_rows': int(row['total_rows'] or 0),
                'total_cpu_ms': float(row['total_cpu_ms'] or 0),
                'total_costs': float(row['total_costs'] or 0),
                'avg_execution_time_ms': float(row['avg_execution_time_ms'] or 0)
            })

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resource-status-breakdown', methods=['GET'])
def get_resource_status_breakdown():
    """Get execute_status distribution for pie chart"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify([])

        cursor.execute("""
            SELECT
                COALESCE(execute_status, 'UNKNOWN') AS execute_status,
                COUNT(*) AS cnt
            FROM public.gateway_sql_resource_usage
            GROUP BY execute_status
            ORDER BY cnt DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        total = sum(int(r['cnt']) for r in rows)
        return jsonify([{
            'status': r['execute_status'],
            'count': int(r['cnt']),
            'percentage': round(int(r['cnt']) / total * 100, 2) if total else 0
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/resource-recent', methods=['GET'])
def get_resource_recent():
    """Get recent resource usage records, supports ?status= filter, ?sort_by= sorting,
       and optional server-side pagination via ?page= & ?page_size="""
    try:
        # 分页模式：当传入 page 参数时启用；否则沿用旧的 limit 行为
        _page_str  = request.args.get('page', '').strip()
        paginated  = bool(_page_str)
        page       = max(1, int(_page_str or 1))
        page_size  = min(int(request.args.get('page_size', 20)), 200)
        limit      = max(1, min(int(request.args.get('limit', 20)), 200))
        status_filter = request.args.get('status', '').strip()
        sort_by = request.args.get('sort_by', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify([])

        allowed_sort = {
            'io':       'io_total_bytes DESC NULLS LAST',
            'cpu':      'cpu_time_ms DESC NULLS LAST',
            'rows':     'rows DESC NULLS LAST',
            'costs':    'costs DESC NULLS LAST',
            'exec_time':'analyzed_at DESC NULLS LAST',
        }
        order_clause = allowed_sort.get(sort_by, 'analyzed_at DESC NULLS LAST, request_log_id DESC')

        params = []
        where_clause = ''
        if status_filter:
            where_clause = 'WHERE execute_status = %s'
            params.append(status_filter)

        if paginated:
            # 获取总条数
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM public.gateway_sql_resource_usage {where_clause}", params)
            total = cursor.fetchone()['cnt']
            pages = (total + page_size - 1) // page_size if total > 0 else 1
            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT
                    request_id, tenant_code, dataset_id, execute_status,
                    rows, costs, cpu_time_ms, io_total_bytes,
                    execution_time_ms, create_time, execute_time, analyzed_at, error_message
                FROM public.gateway_sql_resource_usage
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
        else:
            cursor.execute(f"""
                SELECT
                    request_id, tenant_code, dataset_id, execute_status,
                    rows, costs, cpu_time_ms, io_total_bytes,
                    execution_time_ms, create_time, execute_time, analyzed_at, error_message
                FROM public.gateway_sql_resource_usage
                {where_clause}
                ORDER BY {order_clause}
                LIMIT %s
            """, params + [limit])

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        data = []
        for row in rows:
            data.append({
                'request_id': row['request_id'],
                'tenant_code': row['tenant_code'],
                'dataset_id': row['dataset_id'],
                'execute_status': row['execute_status'],
                'rows': int(row['rows'] or 0),
                'costs': float(row['costs'] or 0),
                'cpu_time_ms': float(row['cpu_time_ms'] or 0),
                'io_total_mb': float((row['io_total_bytes'] or 0) / 1024 / 1024),
                'execution_time_ms': float(row['execution_time_ms'] or 0),
                'create_time': row['create_time'].isoformat() if row['create_time'] else None,
                'execute_time': row['execute_time'].isoformat() if row['execute_time'] else None,
                'analyzed_at': row['analyzed_at'].isoformat() if row['analyzed_at'] else None,
                'error_message': row['error_message']
            })

        if paginated:
            return jsonify({'items': data, 'total': total, 'page': page, 'page_size': page_size, 'pages': pages})
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resource-collect-status', methods=['GET'])
def get_collect_status():
    """Return last auto-collection status"""
    return jsonify({
        'running':         _collect_status['running'],
        'last_run_at':     _collect_status['last_run_at'],
        'last_result':     _collect_status['last_result'],
        'last_error':      _collect_status['last_error'],
        'total_runs':      _collect_status['total_runs'],
        'total_collected': _collect_status['total_collected'],
        'interval_sec':    AUTO_COLLECT_INTERVAL_SEC,
    })


@app.route('/api/resource-collect-now', methods=['POST'])
def trigger_collect_now():
    """Manually trigger one collection round immediately (async, non-blocking)"""
    if _collect_status['running']:
        return jsonify({'queued': False, 'message': '采集任务正在运行中，请稍后再试'}), 202
    t = threading.Thread(target=lambda: _do_collect('manual'), daemon=True)
    t.start()
    return jsonify({'queued': True, 'message': '采集任务已触发，请稍后刷新页面查看结果'})


@app.route('/api/collect-logs', methods=['GET'])
def get_collect_logs():
    """Return collect log history (last 7 days, paginated)."""
    try:
        page      = max(1, int(request.args.get('page', 1)))
        page_size = min(int(request.args.get('page_size', 20)), 100)
        status    = request.args.get('status',  '').strip().upper() or None
        trigger   = request.args.get('trigger', '').strip().lower()  or None

        conn   = get_db_connection()
        cursor = conn.cursor()
        _ensure_collect_log_table(conn)

        # 仅查最近7天
        conditions = ["collected_at >= NOW() - INTERVAL '7 days'"]
        params     = []
        if status:
            conditions.append("status = %s")
            params.append(status)
        if trigger:
            conditions.append("trigger_type = %s")
            params.append(trigger)
        where = "WHERE " + " AND ".join(conditions)

        # 总条数
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM public.gateway_collect_log {where}", params)
        total = cursor.fetchone()['cnt']
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        # 分页查询
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT id, collected_at, trigger_type, status,
                   batches, fetched, success_count, failed_count,
                   error_message, duration_ms
            FROM public.gateway_collect_log
            {where}
            ORDER BY collected_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        items = []
        for r in rows:
            items.append({
                'id':            r['id'],
                'collected_at':  r['collected_at'].isoformat() if r['collected_at'] else None,
                'trigger_type':  r['trigger_type'],
                'status':        r['status'],
                'batches':       r['batches'],
                'fetched':       r['fetched'],
                'success_count': r['success_count'],
                'failed_count':  r['failed_count'],
                'error_message': r['error_message'],
                'duration_ms':   r['duration_ms'],
            })
        return jsonify({'items': items, 'total': total, 'page': page, 'page_size': page_size, 'pages': pages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/resource-billing-summary', methods=['GET'])
def get_resource_billing_summary():
    """Get resource billing summary with optional time window and grouping filters.

    Query params:
        tenant_code  – filter to a specific tenant (optional)
        dataset_id   – filter to a specific dataset (optional)
        start_date   – inclusive start date YYYY-MM-DD (default: 30 days ago)
        end_date     – inclusive end date  YYYY-MM-DD (default: today)
        granularity  – 'day' or 'month' (default: 'day')
    """
    try:
        from datetime import timedelta

        tenant_code = request.args.get('tenant_code', '').strip() or None
        dataset_id  = request.args.get('dataset_id',  '').strip() or None
        granularity = request.args.get('granularity', 'day').strip().lower()
        if granularity not in ('day', 'month'):
            granularity = 'day'

        today = datetime.now().date()
        default_start = today - timedelta(days=29)

        try:
            start_date = datetime.strptime(request.args.get('start_date', str(default_start)), '%Y-%m-%d').date()
        except ValueError:
            start_date = default_start
        try:
            end_date = datetime.strptime(request.args.get('end_date', str(today)), '%Y-%m-%d').date()
        except ValueError:
            end_date = today

        # Normalise: end_date cannot be before start_date
        if end_date < start_date:
            start_date, end_date = end_date, start_date

        conn = get_db_connection()
        cursor = conn.cursor()

        if not check_table_exists(cursor, 'gateway_sql_resource_usage'):
            cursor.close()
            conn.close()
            return jsonify({'table_exists': False, 'items': [], 'filters': {
                'tenant_code': tenant_code, 'dataset_id': dataset_id,
                'start_date': str(start_date), 'end_date': str(end_date),
                'granularity': granularity
            }})

        trunc_expr = "date_trunc('day',   analyzed_at)" if granularity == 'day' else "date_trunc('month', analyzed_at)"

        conditions = [
            "analyzed_at >= %s::date",
            "analyzed_at <  %s::date + INTERVAL '1 day'"
        ]
        params = [str(start_date), str(end_date)]

        if tenant_code:
            conditions.append("tenant_code = %s")
            params.append(tenant_code)
        if dataset_id:
            conditions.append("dataset_id = %s")
            params.append(dataset_id)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                tenant_code,
                dataset_id,
                {trunc_expr}::date            AS time_bucket,
                COUNT(*)                       AS sql_count,
                SUM(io_total_bytes)            AS total_io_bytes,
                SUM(rows)                      AS total_rows,
                SUM(cpu_time_ms)               AS total_cpu_ms,
                SUM(costs)                     AS total_costs,
                AVG(execution_time_ms)         AS avg_execution_time_ms,
                SUM(CASE WHEN execute_status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN execute_status != 'SUCCESS' THEN 1 ELSE 0 END) AS failed_count
            FROM public.gateway_sql_resource_usage
            WHERE {where_clause}
            GROUP BY tenant_code, dataset_id, {trunc_expr}
            ORDER BY time_bucket, tenant_code, dataset_id
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        items = []
        for row in rows:
            items.append({
                'tenant_code':          row['tenant_code'],
                'dataset_id':           row['dataset_id'],
                'time_bucket':          str(row['time_bucket']),
                'sql_count':            int(row['sql_count'] or 0),
                'total_io_bytes':       int(row['total_io_bytes'] or 0),
                'total_io_mb':          round(float((row['total_io_bytes'] or 0) / 1024 / 1024), 4),
                'total_rows':           int(row['total_rows'] or 0),
                'total_cpu_ms':         round(float(row['total_cpu_ms'] or 0), 4),
                'total_costs':          round(float(row['total_costs'] or 0), 4),
                'avg_execution_time_ms': round(float(row['avg_execution_time_ms'] or 0), 4),
                'success_count':        int(row['success_count'] or 0),
                'failed_count':         int(row['failed_count'] or 0),
            })

        return jsonify({
            'table_exists': True,
            'filters': {
                'tenant_code': tenant_code,
                'dataset_id':  dataset_id,
                'start_date':  str(start_date),
                'end_date':    str(end_date),
                'granularity': granularity
            },
            'items': items
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ----------------------------------------------------------------
# 告警 API
# ----------------------------------------------------------------

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """
    查询告警记录列表。
    参数:
      - limit       默认 50，最大 200
      - alert_type  SLOW_QUERY | HIGH_FREQUENCY，不填=全部
      - tenant_code 租户过滤
      - hours       查询最近 N 小时，默认 24
    """
    try:
        limit       = min(int(request.args.get('limit', 50)), 200)
        alert_type     = request.args.get('alert_type', '').strip() or None
        tenant_code    = request.args.get('tenant_code', '').strip() or None
        hours          = int(request.args.get('hours', 24))
        notified_teams = request.args.get('notified_teams', '').strip().lower()

        conn = get_db_connection()
        _ensure_alert_table(conn)

        filters = ["created_at >= NOW() - INTERVAL '%s hours'" ]
        params  = [hours]
        if alert_type:
            filters.append("alert_type = %s")
            params.append(alert_type)
        if tenant_code:
            filters.append("tenant_code = %s")
            params.append(tenant_code)
        if notified_teams == 'true':
            filters.append("notified_teams = TRUE")

        where = ' AND '.join(filters)
        sql = f"""
            SELECT id, alert_type, alert_level, tenant_code, dataset_id,
                   request_log_id, request_id,
                   metric_value, threshold_value, metric_unit,
                   detail, notified_teams,
                   to_char(notified_at, 'YYYY-MM-DD HH24:MI:SS') AS notified_at,
                   to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')  AS created_at
            FROM public.gateway_alert_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s
        """
        params.append(limit)

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()

        return jsonify({'alerts': [dict(r) for r in rows], 'total': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alert-stats', methods=['GET'])
def get_alert_stats():
    """
    告警统计摘要（最近 24 小时）。
    返回: 按类型汇总、按小时趋势。
    """
    try:
        conn = get_db_connection()
        _ensure_alert_table(conn)

        # --- 按类型汇总 ---
        with conn.cursor() as cur:
            cur.execute("""
                SELECT alert_type,
                       COUNT(*)                                           AS total,
                       COUNT(*) FILTER (WHERE notified_teams = TRUE)     AS teams_notified,
                       COUNT(DISTINCT tenant_code)                       AS tenant_count
                FROM public.gateway_alert_log
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY alert_type
                ORDER BY alert_type
            """)
            by_type = [dict(r) for r in cur.fetchall()]

        # --- 按小时趋势 (最近 24 小时) ---
        with conn.cursor() as cur:
            cur.execute("""
                SELECT to_char(date_trunc('hour', created_at), 'HH24:00') AS hour_label,
                       COUNT(*) FILTER (WHERE alert_type='SLOW_QUERY')      AS slow_query,
                       COUNT(*) FILTER (WHERE alert_type='HIGH_FREQUENCY')  AS high_frequency
                FROM public.gateway_alert_log
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY date_trunc('hour', created_at)
                ORDER BY date_trunc('hour', created_at)
            """)
            hourly = [dict(r) for r in cur.fetchall()]

        conn.close()

        return jsonify({
            'by_type': by_type,
            'hourly':  hourly,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dashboard.html')
def serve_dashboard():
    """Serve dashboard page"""
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return f"<p>Error loading dashboard: {e}</p>", 500

@app.route('/')
def index():
    """Redirect to dashboard"""
    return serve_dashboard()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Web Dashboard Started")
    print("="*60)
    print("Access: http://localhost:5000/")
    print("API Endpoints:")
    print("   - GET /api/summary")
    print("   - GET /api/tenant-ranking")
    print("   - GET /api/slow-queries")
    print("   - GET /api/high-traffic-queries")
    print("   - GET /api/timeline")
    print("   - GET /api/cache-stats")
    print("   - GET /api/resource-summary")
    print("   - GET /api/resource-tenant-ranking")
    print("   - GET /api/resource-recent")
    print("   - GET /api/resource-billing-summary")
    print("="*60 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False)
