from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


logger = logging.getLogger(__name__)
LONG_RUNNING_SECONDS = 300
AGENT_JOB_LIMIT = 100


def _duration_seconds(run_duration: object) -> int | None:
    if run_duration is None:
        return None
    try:
        value = int(run_duration)
    except (TypeError, ValueError):
        return None

    hours = value // 10000
    minutes = (value % 10000) // 100
    seconds = value % 100
    return hours * 3600 + minutes * 60 + seconds


def _agent_datetime(run_date: object, run_time: object) -> datetime | None:
    try:
        date_value = int(run_date or 0)
        time_value = int(run_time or 0)
    except (TypeError, ValueError):
        return None

    if date_value <= 0:
        return None

    year = date_value // 10000
    month = (date_value % 10000) // 100
    day = date_value % 100
    hour = time_value // 10000
    minute = (time_value % 10000) // 100
    second = time_value % 100

    try:
        # SQL Agent stores these fields in SQL Server local time and does not
        # persist a timezone offset. Keep the datetime naive rather than
        # inventing UTC; the API/UI labels it as server-local time.
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _agent_status(value: object) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return "never_run"
    return {
        0: "failed",
        1: "succeeded",
        2: "retry",
        3: "canceled",
        4: "in_progress",
    }.get(code, "unknown")


def _database_state(cursor, identity, warnings: list[str]) -> dict:
    try:
        if identity.capabilities["database_state_catalog"]:
            cursor.execute(
                """
                SELECT
                    name,
                    state_desc,
                    recovery_model_desc,
                    user_access_desc,
                    is_read_only,
                    is_auto_close_on,
                    is_auto_shrink_on,
                    log_reuse_wait_desc,
                    page_verify_option_desc,
                    compatibility_level
                FROM sys.databases
                WHERE name = DB_NAME()
                """
            )
            row = cursor.fetchone()
        else:
            cursor.execute(
                """
                SELECT
                    name,
                    CAST(DATABASEPROPERTYEX(name, 'Status') AS varchar(60)),
                    CAST(DATABASEPROPERTYEX(name, 'Recovery') AS varchar(60)),
                    CAST(DATABASEPROPERTYEX(name, 'UserAccess') AS varchar(60)),
                    CAST(DATABASEPROPERTYEX(name, 'IsReadOnly') AS int),
                    CAST(DATABASEPROPERTYEX(name, 'IsAutoClose') AS int),
                    CAST(DATABASEPROPERTYEX(name, 'IsAutoShrink') AS int),
                    NULL,
                    NULL,
                    cmptlevel
                FROM master.dbo.sysdatabases
                WHERE name = DB_NAME()
                """
            )
            row = cursor.fetchone()

        if not row:
            return {}

        return {
            "name": row[0],
            "state": row[1],
            "recovery_model": row[2],
            "user_access": row[3],
            "read_only": bool(row[4]) if row[4] is not None else None,
            "auto_close": bool(row[5]) if row[5] is not None else None,
            "auto_shrink": bool(row[6]) if row[6] is not None else None,
            "log_reuse_wait": row[7],
            "page_verify": row[8],
            "compatibility_level": int(row[9]) if row[9] is not None else None,
        }
    except Exception as exc:
        logger.warning("SQL Server database-state monitoring unavailable: %s", exc)
        warnings.append("Database state/details unavailable for this login/version.")
        return {}


def _log_space(cursor, database_name: str | None, warnings: list[str]) -> dict:
    if not database_name:
        return {}

    try:
        cursor.execute("DBCC SQLPERF(LOGSPACE)")
        rows = cursor.fetchall()
        target = next(
            (row for row in rows if str(row[0]).lower() == database_name.lower()),
            None,
        )
        if not target:
            warnings.append("Transaction-log usage was not returned for this database.")
            return {}

        size_mb = float(target[1]) if target[1] is not None else None
        used_percent = float(target[2]) if target[2] is not None else None
        size_bytes = int(size_mb * 1024 * 1024) if size_mb is not None else None
        used_bytes = (
            int(size_bytes * used_percent / 100)
            if size_bytes is not None and used_percent is not None
            else None
        )
        free_bytes = (
            max(size_bytes - used_bytes, 0)
            if size_bytes is not None and used_bytes is not None
            else None
        )
        return {
            "size_bytes": size_bytes,
            "used_bytes": used_bytes,
            "free_bytes": free_bytes,
            "used_percent": round(used_percent, 2) if used_percent is not None else None,
            "status_code": int(target[3]) if len(target) > 3 and target[3] is not None else None,
        }
    except Exception as exc:
        logger.warning("SQL Server transaction-log monitoring unavailable: %s", exc)
        warnings.append(
            "Transaction-log usage unavailable for this login/version."
        )
        return {}


def _workload(cursor, identity, warnings: list[str]) -> dict:
    try:
        if identity.capabilities["dm_exec"]:
            try:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        SUM(CASE WHEN r.blocking_session_id <> 0 THEN 1 ELSE 0 END),
                        SUM(CASE WHEN r.total_elapsed_time >= {LONG_RUNNING_SECONDS * 1000} THEN 1 ELSE 0 END),
                        MAX(r.total_elapsed_time)
                    FROM sys.dm_exec_requests r
                    INNER JOIN sys.dm_exec_sessions s
                        ON s.session_id = r.session_id
                    WHERE s.is_user_process = 1
                      AND r.session_id <> @@SPID
                      AND r.database_id = DB_ID()
                    """
                )
                row = cursor.fetchone()
            except Exception as exc:
                warnings.append(
                    "Modern workload DMVs are unavailable for this login; "
                    "DBAChum fell back to sysprocesses. "
                    f"({sqlserver_error_message(exc)})"
                )
                cursor.execute(
                    f"""
                    SELECT
                        SUM(CASE
                            WHEN status NOT IN ('sleeping', 'background', 'dormant')
                            THEN 1 ELSE 0 END),
                        SUM(CASE WHEN blocked <> 0 THEN 1 ELSE 0 END),
                        SUM(CASE
                            WHEN status NOT IN ('sleeping', 'background', 'dormant')
                             AND DATEDIFF(SECOND, last_batch, GETDATE()) >= {LONG_RUNNING_SECONDS}
                            THEN 1 ELSE 0 END),
                        MAX(CASE
                            WHEN status NOT IN ('sleeping', 'background', 'dormant')
                            THEN DATEDIFF(SECOND, last_batch, GETDATE()) * 1000
                            ELSE 0 END)
                    FROM master.dbo.sysprocesses
                    WHERE spid <> @@SPID
                      AND spid > 50
                      AND dbid = DB_ID()
                    """
                )
                row = cursor.fetchone()
        else:
            cursor.execute(
                f"""
                SELECT
                    SUM(CASE
                        WHEN status NOT IN ('sleeping', 'background', 'dormant')
                        THEN 1 ELSE 0 END),
                    SUM(CASE WHEN blocked <> 0 THEN 1 ELSE 0 END),
                    SUM(CASE
                        WHEN status NOT IN ('sleeping', 'background', 'dormant')
                         AND DATEDIFF(SECOND, last_batch, GETDATE()) >= {LONG_RUNNING_SECONDS}
                        THEN 1 ELSE 0 END),
                    MAX(CASE
                        WHEN status NOT IN ('sleeping', 'background', 'dormant')
                        THEN DATEDIFF(SECOND, last_batch, GETDATE()) * 1000
                        ELSE 0 END)
                FROM master.dbo.sysprocesses
                WHERE spid <> @@SPID
                  AND spid > 50
                  AND dbid = DB_ID()
                """
            )
            row = cursor.fetchone()

        return {
            "active": int(row[0] or 0) if row else 0,
            "blocked": int(row[1] or 0) if row else 0,
            "long_running": int(row[2] or 0) if row else 0,
            "longest_request_ms": int(row[3] or 0) if row and row[3] is not None else None,
            "long_running_threshold_seconds": LONG_RUNNING_SECONDS,
        }
    except Exception as exc:
        logger.warning("SQL Server workload-health monitoring unavailable: %s", exc)
        warnings.append("Blocking/long-running health summary unavailable for this login/version.")
        return {
            "active": None,
            "blocked": None,
            "long_running": None,
            "longest_request_ms": None,
            "long_running_threshold_seconds": LONG_RUNNING_SECONDS,
        }


def _tempdb(cursor, current_database: str | None, warnings: list[str]) -> dict:
    files: list[dict] = []
    original = current_database or "master"
    escaped_original = original.replace("]", "]]")

    try:
        cursor.execute("USE tempdb")
        cursor.execute(
            """
            SELECT
                name,
                filename,
                CASE WHEN groupid = 0 THEN 'LOG' ELSE 'ROWS' END,
                CAST(size AS bigint) * 8192,
                CASE
                    WHEN FILEPROPERTY(name, 'SpaceUsed') IS NULL THEN NULL
                    ELSE CAST(FILEPROPERTY(name, 'SpaceUsed') AS bigint) * 8192
                END
            FROM dbo.sysfiles
            ORDER BY groupid, fileid
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            allocated = int(row[3] or 0)
            used = int(row[4]) if row[4] is not None else None
            files.append(
                {
                    "name": row[0],
                    "physical_name": row[1],
                    "file_type": row[2],
                    "allocated_bytes": allocated,
                    "used_bytes": used,
                    "free_bytes": max(allocated - used, 0) if used is not None else None,
                    "used_percent": (
                        round(used / allocated * 100, 2)
                        if used is not None and allocated > 0
                        else None
                    ),
                }
            )
    except Exception as exc:
        logger.warning("SQL Server tempdb monitoring unavailable: %s", exc)
        warnings.append("tempdb file usage unavailable for this login/version.")
    finally:
        try:
            cursor.execute(f"USE [{escaped_original}]")
        except Exception:
            # The connection is short-lived; failing to restore the context is
            # harmless and should not hide telemetry that was already collected.
            pass

    row_files = [item for item in files if item["file_type"] == "ROWS"]
    allocated = sum(int(item["allocated_bytes"] or 0) for item in row_files)
    used_values = [item["used_bytes"] for item in row_files if item["used_bytes"] is not None]
    used = sum(int(value or 0) for value in used_values) if used_values else None
    used_percent = (
        round(used / allocated * 100, 2)
        if used is not None and allocated > 0
        else None
    )

    return {
        "allocated_bytes": allocated if row_files else None,
        "used_bytes": used,
        "free_bytes": max(allocated - used, 0) if used is not None else None,
        "used_percent": used_percent,
        "files": files,
    }


def _running_agent_job_ids(cursor, warnings: list[str]) -> set[str]:
    try:
        cursor.execute(
            """
            SELECT CAST(job_id AS varchar(36))
            FROM msdb.dbo.sysjobactivity
            WHERE session_id = (
                SELECT MAX(session_id)
                FROM msdb.dbo.sysjobactivity
            )
              AND start_execution_date IS NOT NULL
              AND stop_execution_date IS NULL
            """
        )
        return {str(row[0]).lower() for row in cursor.fetchall() if row[0] is not None}
    except Exception as exc:
        logger.debug("SQL Agent current activity unavailable: %s", exc)
        warnings.append("Current SQL Agent running-state visibility is unavailable.")
        return set()


def _agent_jobs(cursor, identity, warnings: list[str]) -> dict:
    try:
        cursor.execute(
            f"""
            SELECT TOP {AGENT_JOB_LIMIT}
                CAST(j.job_id AS varchar(36)),
                j.name,
                j.enabled,
                SUSER_SNAME(j.owner_sid),
                j.description,
                h.run_status,
                h.run_date,
                h.run_time,
                h.run_duration,
                h.message
            FROM msdb.dbo.sysjobs j
            LEFT JOIN msdb.dbo.sysjobhistory h
              ON h.instance_id = (
                    SELECT MAX(h2.instance_id)
                    FROM msdb.dbo.sysjobhistory h2
                    WHERE h2.job_id = j.job_id
                      AND h2.step_id = 0
                 )
            ORDER BY j.name
            """
        )
        rows = cursor.fetchall()
    except Exception as exc:
        logger.warning("SQL Agent monitoring unavailable: %s", exc)
        warnings.append(
            "SQL Agent jobs unavailable; msdb permissions or SQL Server Agent may limit visibility."
        )
        return {
            "available": False,
            "jobs": [],
            "enabled_jobs": None,
            "failed_jobs": None,
            "running_jobs": None,
        }

    running_ids = (
        _running_agent_job_ids(cursor, warnings)
        if identity.capabilities["sql_agent_activity"]
        else set()
    )
    if not identity.capabilities["sql_agent_activity"]:
        warnings.append(
            "SQL Server 2000 mode shows completed SQL Agent history; current running-job state is unavailable."
        )

    jobs: list[dict] = []
    for row in rows:
        job_id = str(row[0]) if row[0] is not None else ""
        enabled = bool(row[2])
        status = _agent_status(row[5])
        if job_id.lower() in running_ids:
            status = "in_progress"
        jobs.append(
            {
                "job_id": job_id,
                "name": row[1],
                "enabled": enabled,
                "owner": row[3],
                "description": row[4],
                "last_status": status,
                "last_run_at": _agent_datetime(row[6], row[7]),
                "last_duration_seconds": _duration_seconds(row[8]),
                "last_message": row[9],
                "running": job_id.lower() in running_ids,
            }
        )

    enabled_jobs = [item for item in jobs if item["enabled"]]
    failed_jobs = [
        item
        for item in enabled_jobs
        if item["last_status"] in {"failed", "canceled"}
    ]
    running_jobs = [item for item in enabled_jobs if item["running"]]

    if len(rows) >= AGENT_JOB_LIMIT:
        warnings.append(
            f"SQL Agent list is capped at {AGENT_JOB_LIMIT} jobs for this view."
        )

    return {
        "available": True,
        "jobs": jobs,
        "enabled_jobs": len(enabled_jobs),
        "failed_jobs": len(failed_jobs),
        "running_jobs": len(running_jobs),
    }


def _get_sqlserver_health_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                database = _database_state(cursor, identity, warnings)
                log = _log_space(cursor, identity.database_name, warnings)
                workload = _workload(cursor, identity, warnings)
                tempdb = _tempdb(cursor, identity.database_name, warnings)
                agent = _agent_jobs(cursor, identity, warnings)
            finally:
                cursor.close()

            return {
                "available": True,
                "database_name": identity.database_name,
                "generation": identity.version.generation,
                "database": database,
                "transaction_log": log,
                "workload": workload,
                "tempdb": tempdb,
                "agent": agent,
                "warnings": warnings,
                "checked_at": checked_at,
            }
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_HEALTH_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_health(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_health_sync, connection)
