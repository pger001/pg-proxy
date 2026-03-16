#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 gateway_sql_request_log 采集每条 SQL 的资源消耗，并落库到 gateway_sql_resource_usage。

核心能力：
1. 自动将 sql_content 中的 {tenant_code}/{dataset_id}/{request_id} 变量替换为当前行值。
2. 使用 EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) 采集 rows/cost/io/memory 等指标。
3. 采集结果按 request_log_id 幂等写入，便于后续按租户计费。
"""

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import yaml


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


BLOCK_SIZE_BYTES = 8192
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

BLOCK_KEYS = [
    "Shared Hit Blocks",
    "Shared Read Blocks",
    "Shared Dirtied Blocks",
    "Shared Written Blocks",
    "Local Hit Blocks",
    "Local Read Blocks",
    "Local Dirtied Blocks",
    "Local Written Blocks",
    "Temp Read Blocks",
    "Temp Written Blocks",
]

MEMORY_KEYS = [
    "Peak Memory Usage",
    "Memory Usage",
]


class GatewaySqlResourceCollector:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        backend = self.config["backend"]
        self.conn = await asyncpg.connect(
            host=backend["host"],
            port=backend["port"],
            database=backend["database"],
            user=backend["user"],
            password=backend["password"],
        )
        logger.info("✓ 已连接 PostgreSQL")

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            logger.info("✓ 已关闭 PostgreSQL 连接")

    async def execute_sql_file(self, file_name: str) -> None:
        ddl_file = Path(__file__).with_name(file_name)
        if not ddl_file.exists():
            raise FileNotFoundError(f"未找到 SQL 文件: {ddl_file}")

        ddl_sql = ddl_file.read_text(encoding="utf-8")
        await self.conn.execute(ddl_sql)

    async def ensure_usage_table(self) -> None:
        await self.execute_sql_file("create_gateway_sql_resource_usage.sql")
        logger.info("✓ 资源消耗表 gateway_sql_resource_usage 已创建/已存在")

    async def ensure_source_table(self, init_source_table: bool) -> None:
        exists = await self.conn.fetchval(
            "SELECT to_regclass('public.gateway_sql_request_log')"
        )
        if exists:
            logger.info("✓ 源表 gateway_sql_request_log 已存在")
            return

        if not init_source_table:
            raise RuntimeError(
                "源表 public.gateway_sql_request_log 不存在。"
                "可先执行 create_gateway_sql_request_log.sql，"
                "或运行脚本时加 --init-source-table 自动初始化。"
            )

        await self.execute_sql_file("create_gateway_sql_request_log.sql")
        logger.info("✓ 已自动创建源表 gateway_sql_request_log")

    async def fetch_pending_requests(
        self,
        batch_size: int,
        statuses: List[str],
        request_id: Optional[str],
        force: bool,
        last_id: int,
    ) -> List[asyncpg.Record]:
        sql = """
        SELECT
            l.id,
            l.request_id,
            l.tenant_code,
            l.dataset_id,
            l.sql_content,
            l.create_time,
            l.execute_time,
            l.execute_status
        FROM public.gateway_sql_request_log l
        WHERE l.execute_status = ANY($1::varchar[])
          AND ($2::varchar IS NULL OR l.request_id = $2)
                    AND l.id > $4
          AND (
              $3::boolean
              OR NOT EXISTS (
                  SELECT 1
                  FROM public.gateway_sql_resource_usage u
                  WHERE u.request_log_id = l.id
              )
          )
        ORDER BY l.id
        LIMIT $5
        """
        return await self.conn.fetch(sql, statuses, request_id, force, last_id, batch_size)

    @staticmethod
    def resolve_sql_template(sql_template: str, values: Dict[str, Any]) -> str:
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            value = values.get(key)
            if value is None:
                return match.group(0)
            return str(value)

        return PLACEHOLDER_PATTERN.sub(replacer, sql_template)

    @staticmethod
    def normalize_sql(sql_text: str) -> str:
        sql_text = (sql_text or "").strip()
        if not sql_text:
            raise ValueError("sql_content 为空")

        # 去掉尾部分号，避免 EXPLAIN 拼接后出现空语句
        sql_text = re.sub(r";\s*$", "", sql_text)

        # 当前实现仅支持单语句，避免多语句误执行
        if ";" in sql_text:
            raise ValueError("sql_content 含多条 SQL 语句，当前仅支持单语句采集")

        return sql_text

    async def explain_analyze(self, sql_text: str) -> Tuple[Dict[str, Any], Any]:
        sql_text = self.normalize_sql(sql_text)

        # 用事务包裹并回滚，避免 ANALYZE 对 DML 产生持久副作用
        tx = self.conn.transaction()
        await tx.start()
        try:
            explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql_text}"
            raw_plan = await self.conn.fetchval(explain_sql)
        finally:
            await tx.rollback()

        if isinstance(raw_plan, str):
            plan_payload = json.loads(raw_plan)
        else:
            plan_payload = raw_plan

        if not isinstance(plan_payload, list) or not plan_payload:
            raise ValueError("EXPLAIN 返回格式异常，期望 JSON 数组")

        top = plan_payload[0]
        plan = top.get("Plan")
        if not isinstance(plan, dict):
            raise ValueError("EXPLAIN JSON 中缺少 Plan 节点")

        aggregated = self.aggregate_plan_metrics(plan)

        planning_time_ms = float(top.get("Planning Time") or 0.0)
        execution_time_ms = float(top.get("Execution Time") or 0.0)

        actual_rows = int(plan.get("Actual Rows") or 0)
        total_cost = float(plan.get("Total Cost") or 0.0)
        plan_rows = int(plan.get("Plan Rows") or 0)
        plan_width = int(plan.get("Plan Width") or 0)

        io_read_blocks = (
            aggregated["Shared Read Blocks"]
            + aggregated["Local Read Blocks"]
            + aggregated["Temp Read Blocks"]
        )
        io_write_blocks = (
            aggregated["Shared Written Blocks"]
            + aggregated["Local Written Blocks"]
            + aggregated["Temp Written Blocks"]
        )

        io_read_bytes = io_read_blocks * BLOCK_SIZE_BYTES
        io_write_bytes = io_write_blocks * BLOCK_SIZE_BYTES
        io_total_bytes = io_read_bytes + io_write_bytes

        peak_memory_kb = aggregated["peak_memory_kb"] if aggregated["peak_memory_kb"] > 0 else None
        memory_estimated_kb = (
            float(actual_rows * plan_width) / 1024.0 if actual_rows > 0 and plan_width > 0 else None
        )

        metrics = {
            "planning_time_ms": planning_time_ms,
            "execution_time_ms": execution_time_ms,
            # PostgreSQL EXPLAIN 没有直接 CPU 指标，这里采用执行时间近似
            "cpu_time_ms": execution_time_ms if execution_time_ms > 0 else None,
            "rows": actual_rows,
            "costs": total_cost,
            "plan_rows": plan_rows,
            "plan_width": plan_width,
            "shared_hit_blocks": aggregated["Shared Hit Blocks"],
            "shared_read_blocks": aggregated["Shared Read Blocks"],
            "shared_dirtied_blocks": aggregated["Shared Dirtied Blocks"],
            "shared_written_blocks": aggregated["Shared Written Blocks"],
            "local_hit_blocks": aggregated["Local Hit Blocks"],
            "local_read_blocks": aggregated["Local Read Blocks"],
            "local_dirtied_blocks": aggregated["Local Dirtied Blocks"],
            "local_written_blocks": aggregated["Local Written Blocks"],
            "temp_read_blocks": aggregated["Temp Read Blocks"],
            "temp_written_blocks": aggregated["Temp Written Blocks"],
            "io_read_bytes": io_read_bytes,
            "io_write_bytes": io_write_bytes,
            "io_total_bytes": io_total_bytes,
            "peak_memory_kb": peak_memory_kb,
            "memory_estimated_kb": memory_estimated_kb,
        }

        return metrics, plan_payload

    def aggregate_plan_metrics(self, root: Dict[str, Any]) -> Dict[str, Any]:
        aggregated: Dict[str, Any] = {key: 0 for key in BLOCK_KEYS}
        aggregated["peak_memory_kb"] = 0.0

        def walk(node: Dict[str, Any]) -> None:
            for block_key in BLOCK_KEYS:
                aggregated[block_key] += int(node.get(block_key) or 0)

            for mem_key in MEMORY_KEYS:
                if mem_key in node and node[mem_key] is not None:
                    aggregated["peak_memory_kb"] = max(
                        aggregated["peak_memory_kb"],
                        float(node[mem_key]),
                    )

            for child in node.get("Plans") or []:
                if isinstance(child, dict):
                    walk(child)

        walk(root)
        return aggregated

    async def upsert_usage_row(
        self,
        request_row: asyncpg.Record,
        sql_resolved: str,
        metrics: Dict[str, Any],
        error_message: Optional[str],
        plan_payload: Optional[Any],
    ) -> None:
        insert_sql = """
        INSERT INTO public.gateway_sql_resource_usage (
            request_log_id, request_id, tenant_code, dataset_id,
            create_time, execute_time, execute_status,
            sql_template, sql_resolved,
            planning_time_ms, execution_time_ms, cpu_time_ms,
            rows, costs, plan_rows, plan_width,
            shared_hit_blocks, shared_read_blocks, shared_dirtied_blocks, shared_written_blocks,
            local_hit_blocks, local_read_blocks, local_dirtied_blocks, local_written_blocks,
            temp_read_blocks, temp_written_blocks,
            io_read_bytes, io_write_bytes, io_total_bytes,
            peak_memory_kb, memory_estimated_kb,
            error_message, plan_json
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7,
            $8, $9,
            $10, $11, $12,
            $13, $14, $15, $16,
            $17, $18, $19, $20,
            $21, $22, $23, $24,
            $25, $26,
            $27, $28, $29,
            $30, $31,
            $32, $33::jsonb
        )
        ON CONFLICT (request_log_id) DO UPDATE
        SET
            request_id = EXCLUDED.request_id,
            tenant_code = EXCLUDED.tenant_code,
            dataset_id = EXCLUDED.dataset_id,
            create_time = EXCLUDED.create_time,
            execute_time = EXCLUDED.execute_time,
            execute_status = EXCLUDED.execute_status,
            sql_template = EXCLUDED.sql_template,
            sql_resolved = EXCLUDED.sql_resolved,
            analyzed_at = CURRENT_TIMESTAMP(3),
            planning_time_ms = EXCLUDED.planning_time_ms,
            execution_time_ms = EXCLUDED.execution_time_ms,
            cpu_time_ms = EXCLUDED.cpu_time_ms,
            rows = EXCLUDED.rows,
            costs = EXCLUDED.costs,
            plan_rows = EXCLUDED.plan_rows,
            plan_width = EXCLUDED.plan_width,
            shared_hit_blocks = EXCLUDED.shared_hit_blocks,
            shared_read_blocks = EXCLUDED.shared_read_blocks,
            shared_dirtied_blocks = EXCLUDED.shared_dirtied_blocks,
            shared_written_blocks = EXCLUDED.shared_written_blocks,
            local_hit_blocks = EXCLUDED.local_hit_blocks,
            local_read_blocks = EXCLUDED.local_read_blocks,
            local_dirtied_blocks = EXCLUDED.local_dirtied_blocks,
            local_written_blocks = EXCLUDED.local_written_blocks,
            temp_read_blocks = EXCLUDED.temp_read_blocks,
            temp_written_blocks = EXCLUDED.temp_written_blocks,
            io_read_bytes = EXCLUDED.io_read_bytes,
            io_write_bytes = EXCLUDED.io_write_bytes,
            io_total_bytes = EXCLUDED.io_total_bytes,
            peak_memory_kb = EXCLUDED.peak_memory_kb,
            memory_estimated_kb = EXCLUDED.memory_estimated_kb,
            error_message = EXCLUDED.error_message,
            plan_json = EXCLUDED.plan_json
        """

        plan_json_str = json.dumps(plan_payload, ensure_ascii=False) if plan_payload is not None else None

        await self.conn.execute(
            insert_sql,
            request_row["id"],
            request_row["request_id"],
            request_row["tenant_code"],
            request_row["dataset_id"],
            request_row["create_time"],
            request_row["execute_time"],
            request_row["execute_status"],
            request_row["sql_content"],
            sql_resolved,
            metrics.get("planning_time_ms"),
            metrics.get("execution_time_ms"),
            metrics.get("cpu_time_ms"),
            metrics.get("rows"),
            metrics.get("costs"),
            metrics.get("plan_rows"),
            metrics.get("plan_width"),
            metrics.get("shared_hit_blocks"),
            metrics.get("shared_read_blocks"),
            metrics.get("shared_dirtied_blocks"),
            metrics.get("shared_written_blocks"),
            metrics.get("local_hit_blocks"),
            metrics.get("local_read_blocks"),
            metrics.get("local_dirtied_blocks"),
            metrics.get("local_written_blocks"),
            metrics.get("temp_read_blocks"),
            metrics.get("temp_written_blocks"),
            metrics.get("io_read_bytes"),
            metrics.get("io_write_bytes"),
            metrics.get("io_total_bytes"),
            metrics.get("peak_memory_kb"),
            metrics.get("memory_estimated_kb"),
            error_message,
            plan_json_str,
        )

    async def process_one(self, row: asyncpg.Record) -> Tuple[bool, Optional[str]]:
        replace_values = {
            "tenant_code": row["tenant_code"],
            "dataset_id": row["dataset_id"],
            "request_id": row["request_id"],
        }

        sql_resolved = self.resolve_sql_template(row["sql_content"], replace_values)

        metrics: Dict[str, Any] = {}
        error_message: Optional[str] = None
        plan_payload: Optional[Any] = None

        try:
            metrics, plan_payload = await self.explain_analyze(sql_resolved)
            ok = True
        except Exception as exc:
            ok = False
            error_message = str(exc)

        await self.upsert_usage_row(
            request_row=row,
            sql_resolved=sql_resolved,
            metrics=metrics,
            error_message=error_message,
            plan_payload=plan_payload,
        )

        return ok, error_message

    async def run(
        self,
        batch_size: int,
        statuses: List[str],
        request_id: Optional[str],
        force: bool,
        max_batches: int,
    ) -> Dict[str, int]:
        summary = {
            "batches": 0,
            "fetched": 0,
            "success": 0,
            "failed": 0,
        }
        last_id = 0

        while True:
            if max_batches > 0 and summary["batches"] >= max_batches:
                break

            rows = await self.fetch_pending_requests(
                batch_size=batch_size,
                statuses=statuses,
                request_id=request_id,
                force=force,
                last_id=last_id,
            )

            if not rows:
                break

            summary["batches"] += 1
            summary["fetched"] += len(rows)
            last_id = rows[-1]["id"]

            for row in rows:
                ok, err = await self.process_one(row)
                if ok:
                    summary["success"] += 1
                else:
                    summary["failed"] += 1
                    logger.warning(
                        "request_log_id=%s explain失败: %s",
                        row["id"],
                        err,
                    )

            logger.info(
                "批次 %s 完成: 本批 %s 条, 累计成功 %s, 失败 %s",
                summary["batches"],
                len(rows),
                summary["success"],
                summary["failed"],
            )

        return summary


def parse_statuses(status_text: str) -> List[str]:
    values = [x.strip().upper() for x in status_text.split(",") if x.strip()]
    allowed = {"INIT", "SUCCESS", "FAILED", "TIMEOUT"}
    invalid = [x for x in values if x not in allowed]
    if invalid:
        raise ValueError(f"非法状态值: {invalid}, 允许值: {sorted(allowed)}")
    if not values:
        raise ValueError("status 不能为空")
    return values


async def main() -> None:
    parser = argparse.ArgumentParser(description="采集 gateway_sql_request_log 的资源消耗并落表")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径，默认 config.yaml")
    parser.add_argument("--batch-size", type=int, default=200, help="每批处理条数，默认 200")
    parser.add_argument(
        "--status",
        default="SUCCESS,FAILED,TIMEOUT",
        help="处理哪些 execute_status，逗号分隔；默认 SUCCESS,FAILED,TIMEOUT",
    )
    parser.add_argument("--request-id", default=None, help="仅处理指定 request_id")
    parser.add_argument("--force", action="store_true", help="强制重算（忽略已采集记录）")
    parser.add_argument("--max-batches", type=int, default=0, help="最多处理批次数，0 表示不限制")
    parser.add_argument(
        "--init-source-table",
        action="store_true",
        help="若源表 gateway_sql_request_log 不存在则自动创建",
    )

    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    statuses = parse_statuses(args.status)

    collector = GatewaySqlResourceCollector(config)
    try:
        await collector.connect()
        await collector.ensure_source_table(init_source_table=args.init_source_table)
        await collector.ensure_usage_table()

        summary = await collector.run(
            batch_size=args.batch_size,
            statuses=statuses,
            request_id=args.request_id,
            force=args.force,
            max_batches=args.max_batches,
        )

        print("\n" + "=" * 70)
        print("gateway_sql_resource_usage 采集完成")
        print("=" * 70)
        print(f"批次数:       {summary['batches']}")
        print(f"读取总数:     {summary['fetched']}")
        print(f"采集成功:     {summary['success']}")
        print(f"采集失败:     {summary['failed']}")
        print("=" * 70 + "\n")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
