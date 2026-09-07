from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


def _diagnostics(item: dict) -> list[str]:
    notes: list[str] = []
    executions = max(int(item.get("executions") or 0), 1)
    elapsed = float(item.get("elapsed_seconds") or 0)
    logical = int(item.get("logical_reads") or 0)
    physical = int(item.get("physical_reads") or 0)
    rows = int(item.get("rows_processed") or 0)

    if elapsed / executions >= 2:
        notes.append(f"Average elapsed time is {elapsed / executions:.2f}s per execution; inspect the execution plan and waits.")
    if logical / executions >= 100_000:
        notes.append(f"High buffer gets per execution ({logical // executions:,}); check join order, access paths, and selectivity.")
    if physical / executions >= 10_000:
        notes.append(f"High physical reads per execution ({physical // executions:,}); review full scans, cache pressure, and indexing.")
    if rows == 0 and logical >= 100_000:
        notes.append("The statement consumes substantial logical I/O while returning few/no rows; review predicates and indexes.")
    if not notes:
        notes.append("No obvious metric-level red flag. Use the cursor plan and object statistics before changing SQL or indexes.")
    return notes


async def get_oracle_top_sql(connection: dict, limit: int) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            rows = await db.fetchall(
                """
                SELECT * FROM (
                    SELECT
                        sql_id,
                        child_number,
                        plan_hash_value,
                        parsing_schema_name,
                        executions,
                        elapsed_time,
                        cpu_time,
                        buffer_gets,
                        disk_reads,
                        rows_processed,
                        sql_text,
                        last_active_time
                    FROM v$sql
                    WHERE sql_id IS NOT NULL
                      AND sql_text IS NOT NULL
                    ORDER BY elapsed_time DESC
                )
                WHERE ROWNUM <= :limit
                """,
                {"limit": limit},
            )
            items = []
            for row in rows:
                item = {
                    "key": f"{row[0]}:{int(row[1] or 0)}",
                    "sql_id": row[0],
                    "child_number": int(row[1] or 0),
                    "plan_hash_value": int(row[2] or 0) if row[2] is not None else None,
                    "schema_name": row[3],
                    "executions": int(row[4] or 0),
                    "elapsed_seconds": float(row[5] or 0) / 1_000_000,
                    "cpu_seconds": float(row[6] or 0) / 1_000_000,
                    "logical_reads": int(row[7] or 0),
                    "physical_reads": int(row[8] or 0),
                    "rows_processed": int(row[9] or 0),
                    "sql_text": row[10],
                    "last_active_at": row[11],
                }
                item["diagnostics"] = _diagnostics(item)
                items.append(item)
            return {
                "source": "Oracle v$sql ordered by total elapsed time",
                "available": True,
                "items": items,
                "warnings": [],
                "checked_at": datetime.now(timezone.utc),
            }
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_TOP_SQL_FAILED",
            status_code=400,
        ) from exc


def _plan_diagnostics(steps: list[dict]) -> list[str]:
    notes: list[str] = []
    for step in steps:
        operation = str(step.get("operation") or "").upper()
        options = str(step.get("options") or "").upper()
        object_name = step.get("object_name") or "object"
        if operation == "TABLE ACCESS" and "FULL" in options:
            notes.append(f"Full table scan on {object_name}; verify whether the scan is expected for the result size and predicates.")
        if operation == "INDEX" and "SKIP SCAN" in options:
            notes.append(f"Index skip scan on {object_name}; a better leading column or composite index may reduce work.")
        if operation in {"SORT", "HASH JOIN"} and float(step.get("bytes") or 0) >= 100 * 1024 * 1024:
            notes.append(f"Large {operation.lower()} estimate ({int(step.get('bytes') or 0):,} bytes); verify cardinality and PGA/workarea pressure.")
    if not notes:
        notes.append("Review estimated cardinality versus actual workload, predicate selectivity, and object statistics before applying changes.")
    return list(dict.fromkeys(notes))


async def get_oracle_sql_plan(connection: dict, data) -> dict:
    if not data.sql_id:
        raise AppError(
            "Oracle plan lookup requires sql_id.",
            code="ORACLE_PLAN_SQL_ID_REQUIRED",
            status_code=400,
        )
    child = int(data.child_number or 0)
    try:
        async with open_oracle_connection(connection) as db:
            rows = await db.fetchall(
                """
                SELECT
                    id,
                    parent_id,
                    operation,
                    options,
                    object_owner,
                    object_name,
                    cost,
                    cardinality,
                    bytes,
                    access_predicates,
                    filter_predicates
                FROM v$sql_plan
                WHERE sql_id = :sql_id
                  AND child_number = :child_number
                ORDER BY id
                """,
                {"sql_id": data.sql_id, "child_number": child},
            )
            steps = [
                {
                    "id": int(row[0]) if row[0] is not None else None,
                    "parent_id": int(row[1]) if row[1] is not None else None,
                    "operation": row[2],
                    "options": row[3],
                    "object_owner": row[4],
                    "object_name": row[5],
                    "cost": float(row[6]) if row[6] is not None else None,
                    "cardinality": float(row[7]) if row[7] is not None else None,
                    "bytes": float(row[8]) if row[8] is not None else None,
                    "access_predicates": row[9],
                    "filter_predicates": row[10],
                }
                for row in rows
            ]
            if not steps:
                raise AppError(
                    "No cached cursor plan was found for this SQL ID/child number.",
                    code="ORACLE_PLAN_NOT_FOUND",
                    status_code=404,
                )
            return {
                "source": "Oracle v$sql_plan cached cursor plan",
                "available": True,
                "steps": steps,
                "diagnostics": _plan_diagnostics(steps),
                "warnings": ["This is the cached cursor plan. DBAChum does not invoke DBMS_SQLTUNE or consume Tuning Pack features automatically."],
                "checked_at": datetime.now(timezone.utc),
            }
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_PLAN_FAILED",
            status_code=400,
        ) from exc
