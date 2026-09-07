import asyncio
import re
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import open_sqlserver_connection, probe_sqlserver_identity, sqlserver_error_message
from app.core.exceptions import AppError


_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")


def _hex(value) -> str | None:
    if value is None:
        return None
    try:
        return bytes(value).hex().upper()
    except Exception:
        text = str(value)
        return text[2:] if text.lower().startswith("0x") else text


def _diagnostics(item: dict) -> list[str]:
    notes: list[str] = []
    executions = max(int(item.get("executions") or 0), 1)
    elapsed = float(item.get("elapsed_seconds") or 0)
    logical = int(item.get("logical_reads") or 0)
    physical = int(item.get("physical_reads") or 0)
    if elapsed / executions >= 2:
        notes.append(f"Average elapsed time is {elapsed / executions:.2f}s per execution; inspect the cached plan and waits.")
    if logical / executions >= 100_000:
        notes.append(f"High logical reads per execution ({logical // executions:,}); inspect scans, joins, and predicate selectivity.")
    if physical / executions >= 10_000:
        notes.append(f"High physical reads per execution ({physical // executions:,}); review access path and memory pressure.")
    if not notes:
        notes.append("No obvious metric-level red flag. Review the cached plan, estimates, indexes, and parameter sensitivity before changing anything.")
    return notes


def _top_sql_sync(connection: dict, limit: int) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            if not identity.capabilities.get("dm_exec"):
                return {
                    "source": "SQL Server legacy mode",
                    "available": False,
                    "items": [],
                    "warnings": ["Top SQL requires SQL Server 2005+ dynamic management views. Legacy SQL Server activity remains available from the Activity tab."],
                    "checked_at": datetime.now(timezone.utc),
                }
            cursor = db.cursor()
            try:
                database_name = (connection.get("database") or "").strip()
                where = "WHERE (st.dbid = DB_ID() OR st.dbid IS NULL)" if database_name else ""
                cursor.execute(
                    f"""
                    SELECT TOP {int(limit)}
                        qs.plan_handle,
                        qs.sql_handle,
                        qs.statement_start_offset,
                        qs.statement_end_offset,
                        qs.execution_count,
                        qs.total_elapsed_time,
                        qs.total_worker_time,
                        qs.total_logical_reads,
                        qs.total_physical_reads,
                        qs.last_execution_time,
                        SUBSTRING(
                            st.text,
                            (qs.statement_start_offset / 2) + 1,
                            ((CASE qs.statement_end_offset
                                WHEN -1 THEN DATALENGTH(st.text)
                                ELSE qs.statement_end_offset
                              END - qs.statement_start_offset) / 2) + 1
                        ) AS statement_text
                    FROM sys.dm_exec_query_stats AS qs
                    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
                    {where}
                    ORDER BY qs.total_elapsed_time DESC
                    """
                )
                items = []
                for index, row in enumerate(cursor.fetchall()):
                    plan_handle = _hex(row[0])
                    sql_handle = _hex(row[1])
                    item = {
                        "key": f"{plan_handle or sql_handle or index}:{int(row[2] or 0)}",
                        "plan_handle": plan_handle,
                        "sql_handle": sql_handle,
                        "statement_start_offset": int(row[2] or 0),
                        "statement_end_offset": int(row[3] or -1),
                        "executions": int(row[4] or 0),
                        "elapsed_seconds": float(row[5] or 0) / 1_000_000,
                        "cpu_seconds": float(row[6] or 0) / 1_000_000,
                        "logical_reads": int(row[7] or 0),
                        "physical_reads": int(row[8] or 0),
                        "last_active_at": row[9],
                        "sql_text": row[10],
                    }
                    item["diagnostics"] = _diagnostics(item)
                    items.append(item)
                return {
                    "source": "SQL Server sys.dm_exec_query_stats ordered by total elapsed time",
                    "available": True,
                    "items": items,
                    "warnings": [],
                    "checked_at": datetime.now(timezone.utc),
                }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_TOP_SQL_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_top_sql(connection: dict, limit: int) -> dict:
    return await asyncio.to_thread(_top_sql_sync, connection, limit)


def _plan_sync(connection: dict, data) -> dict:
    handle = (data.plan_handle or "").strip()
    if handle.lower().startswith("0x"):
        handle = handle[2:]
    if not handle or len(handle) % 2 or not _HEX_RE.fullmatch(handle):
        raise AppError(
            "SQL Server plan lookup requires a valid cached plan handle.",
            code="SQLSERVER_PLAN_HANDLE_INVALID",
            status_code=400,
        )
    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            if not identity.capabilities.get("dm_exec"):
                raise AppError(
                    "Cached plan lookup requires SQL Server 2005+ dynamic management views.",
                    code="SQLSERVER_PLAN_UNAVAILABLE_LEGACY",
                    status_code=400,
                )
            cursor = db.cursor()
            try:
                cursor.execute(f"SELECT query_plan FROM sys.dm_exec_query_plan(0x{handle})")
                row = cursor.fetchone()
                plan_text = None if not row or row[0] is None else str(row[0])
                if not plan_text:
                    raise AppError(
                        "The cached SQL Server plan is no longer available.",
                        code="SQLSERVER_PLAN_NOT_FOUND",
                        status_code=404,
                    )
                diagnostics = []
                upper = plan_text.upper()
                if "TABLE SCAN" in upper:
                    diagnostics.append("The cached plan contains a table scan; verify whether the scan is expected and whether useful indexes/selectivity are available.")
                if "INDEX SCAN" in upper:
                    diagnostics.append("The cached plan contains one or more index scans; compare rows read versus rows returned before adding indexes.")
                if "SPILL" in upper or "SPILLTO" in upper:
                    diagnostics.append("The cached plan indicates a spill/worktable condition; review memory grant estimates and cardinality.")
                if "MISSINGINDEX" in upper:
                    diagnostics.append("SQL Server included a missing-index hint in the plan. Treat it as a candidate only; compare with existing indexes and write cost.")
                if not diagnostics:
                    diagnostics.append("Review estimated versus actual cardinality, join choices, scans/seeks, memory grants, and parameter sensitivity before applying changes.")
                return {
                    "source": "SQL Server cached SHOWPLAN XML",
                    "available": True,
                    "plan_text": plan_text,
                    "steps": [],
                    "diagnostics": diagnostics,
                    "warnings": [],
                    "checked_at": datetime.now(timezone.utc),
                }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_PLAN_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_sql_plan(connection: dict, data) -> dict:
    return await asyncio.to_thread(_plan_sync, connection, data)
