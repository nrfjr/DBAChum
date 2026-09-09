import asyncio
import re
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import _close_mysql_resource, mysql_connect_kwargs
from app.core.exceptions import AppError


_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE | re.DOTALL)


def _diagnostics(item: dict) -> list[str]:
    notes: list[str] = []
    executions = max(int(item.get("executions") or 0), 1)
    elapsed = float(item.get("elapsed_seconds") or 0)
    examined = int(item.get("rows_examined") or 0)
    sent = int(item.get("rows_sent") or 0)
    if elapsed / executions >= 2:
        notes.append(f"Average digest time is {elapsed / executions:.2f}s per execution; capture a representative statement and run EXPLAIN.")
    if int(item.get("no_index_used") or 0) > 0:
        notes.append("Performance Schema reports executions with no index used; verify predicates and index coverage.")
    if int(item.get("no_good_index_used") or 0) > 0:
        notes.append("Performance Schema reports executions with no good index used; inspect EXPLAIN and existing composite indexes.")
    if sent >= 0 and examined > max(sent * 100, 100_000):
        notes.append(f"Rows examined ({examined:,}) are much higher than rows sent ({sent:,}); review filtering and index selectivity.")
    if int(item.get("temp_disk_tables") or 0) > 0:
        notes.append("This digest created on-disk temporary tables; review GROUP BY/ORDER BY shape, temp limits, and indexing.")
    if not notes:
        notes.append("No obvious digest-level red flag. Capture the real SQL with literals/binds and use EXPLAIN before changing indexes.")
    return notes


def _top_sql_sync(connection: dict, limit: int) -> dict:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        has_last_seen = True
        try:
            cursor.execute(
                f"""
                SELECT
                    DIGEST,
                    DIGEST_TEXT,
                    COUNT_STAR,
                    SUM_TIMER_WAIT,
                    SUM_ROWS_EXAMINED,
                    SUM_ROWS_SENT,
                    SUM_CREATED_TMP_DISK_TABLES,
                    SUM_NO_INDEX_USED,
                    SUM_NO_GOOD_INDEX_USED,
                    FIRST_SEEN,
                    LAST_SEEN
                FROM performance_schema.events_statements_summary_by_digest
                WHERE DIGEST IS NOT NULL
                  AND (SCHEMA_NAME = DATABASE() OR DATABASE() IS NULL)
                ORDER BY SUM_TIMER_WAIT DESC
                LIMIT {int(limit)}
                """
            )
            rows = cursor.fetchall()
        except MySQLError:
            has_last_seen = False
            try:
                cursor.execute(
                    f"""
                    SELECT
                        DIGEST,
                        DIGEST_TEXT,
                        COUNT_STAR,
                        SUM_TIMER_WAIT,
                        SUM_ROWS_EXAMINED,
                        SUM_ROWS_SENT,
                        SUM_CREATED_TMP_DISK_TABLES,
                        SUM_NO_INDEX_USED,
                        SUM_NO_GOOD_INDEX_USED
                    FROM performance_schema.events_statements_summary_by_digest
                    WHERE DIGEST IS NOT NULL
                      AND (SCHEMA_NAME = DATABASE() OR DATABASE() IS NULL)
                    ORDER BY SUM_TIMER_WAIT DESC
                    LIMIT {int(limit)}
                    """
                )
                rows = cursor.fetchall()
            except MySQLError as exc:
                return {
                    "source": "MySQL/MariaDB Performance Schema",
                    "available": False,
                    "items": [],
                    "warnings": ["Top SQL requires Performance Schema statement digests on this server."],
                    "checked_at": datetime.now(timezone.utc),
                }

        items = []
        for row in rows:
            item = {
                "key": str(row[0]),
                "digest": str(row[0]),
                "sql_text": row[1],
                "normalized_sql": True,
                "executions": int(row[2] or 0),
                "elapsed_seconds": float(row[3] or 0) / 1_000_000_000_000,
                "rows_examined": int(row[4] or 0),
                "rows_sent": int(row[5] or 0),
                "temp_disk_tables": int(row[6] or 0),
                "no_index_used": int(row[7] or 0),
                "no_good_index_used": int(row[8] or 0),
                "last_active_at": row[10] if has_last_seen else None,
            }
            item["diagnostics"] = _diagnostics(item)
            items.append(item)
        return {
            "source": "MySQL/MariaDB Performance Schema statement digests",
            "available": True,
            "items": items,
            "warnings": ["Digest SQL is normalized and may contain placeholders; use a representative real SELECT for EXPLAIN."],
            "checked_at": datetime.now(timezone.utc),
        }
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_TOP_SQL_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def get_mysql_top_sql(connection: dict, limit: int) -> dict:
    return await asyncio.to_thread(_top_sql_sync, connection, limit)


def _plan_sync(connection: dict, data) -> dict:
    sql_text = (data.sql_text or "").strip()
    if not sql_text or not _SELECT_RE.match(sql_text):
        raise AppError(
            "MySQL/MariaDB EXPLAIN accepts SELECT/WITH statements only.",
            code="MYSQL_EXPLAIN_SELECT_REQUIRED",
            status_code=400,
        )

    stripped = sql_text.rstrip().rstrip(";")
    if ";" in stripped:
        raise AppError(
            "Explain one SQL statement at a time.",
            code="MYSQL_EXPLAIN_MULTISTATEMENT_REJECTED",
            status_code=400,
        )

    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        cursor.execute("EXPLAIN " + stripped)
        columns = [description[0] for description in cursor.description or []]
        rows = cursor.fetchall()
        steps = []
        diagnostics: list[str] = []
        for index, row in enumerate(rows):
            record = dict(zip(columns, row))
            access = str(record.get("type") or "").upper()
            extra_text = str(record.get("Extra") or record.get("extra") or "")
            table = record.get("table") or record.get("TABLE")
            rows_est = record.get("rows") or record.get("ROWS")
            steps.append(
                {
                    "id": int(record.get("id") or index + 1),
                    "operation": access or "ACCESS",
                    "object_name": None if table is None else str(table),
                    "cardinality": float(rows_est) if rows_est is not None else None,
                    "extra": {str(key): None if value is None else str(value) for key, value in record.items()},
                }
            )
            if access == "ALL":
                diagnostics.append(f"Full scan on {table or 'table'}; verify predicates and candidate indexes.")
            if "Using temporary" in extra_text:
                diagnostics.append(f"{table or 'This step'} uses a temporary table; inspect GROUP BY/ORDER BY and index coverage.")
            if "Using filesort" in extra_text:
                diagnostics.append(f"{table or 'This step'} uses filesort; verify ordering/grouping indexes and result size.")
        if not diagnostics:
            diagnostics.append("Review access type, possible_keys/key, estimated rows, filtering, temporary tables, and filesort before changing indexes.")
        return {
            "source": "MySQL/MariaDB EXPLAIN (statement not executed)",
            "available": True,
            "steps": steps,
            "diagnostics": list(dict.fromkeys(diagnostics)),
            "warnings": [],
            "checked_at": datetime.now(timezone.utc),
        }
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_EXPLAIN_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def get_mysql_sql_plan(connection: dict, data) -> dict:
    return await asyncio.to_thread(_plan_sync, connection, data)
