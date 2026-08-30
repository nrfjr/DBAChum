import time
from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)
from app.core.exceptions import AppError


SYSTEM_STAT_NAMES = (
    "CPU used by this session",
    "execute count",
    "session logical reads",
    "physical reads",
    "user commits",
    "user rollbacks",
    "redo size",
    "parse count (hard)",
)

RECENT_SQL_CANDIDATE_LIMIT = 50
CUMULATIVE_SQL_CANDIDATE_LIMIT = 20
SESSION_CANDIDATE_LIMIT = 25
WAIT_CANDIDATE_LIMIT = 20


async def _fetchone_optional(db, sql: str, warnings: list[str], label: str, params=None):
    try:
        return await db.fetchone(sql, params)
    except oracledb.Error as exc:
        warnings.append(f"{label} unavailable: {oracle_error_message(exc)}")
        return None


async def _fetchall_optional(db, sql: str, warnings: list[str], label: str, params=None):
    try:
        return await db.fetchall(sql, params)
    except oracledb.Error as exc:
        warnings.append(f"{label} unavailable: {oracle_error_message(exc)}")
        return []


def _sql_row(row) -> dict:
    return {
        "sql_id": row[0],
        "child_number": int(row[1] or 0),
        "plan_hash_value": int(row[2] or 0),
        "parsing_schema_name": row[3],
        "module": row[4],
        "cpu_time_us": int(row[5] or 0),
        "elapsed_time_us": int(row[6] or 0),
        "executions": int(row[7] or 0),
        "buffer_gets": int(row[8] or 0),
        "disk_reads": int(row[9] or 0),
        "rows_processed": int(row[10] or 0),
        "last_active_time": row[11],
        "sql_text": row[12],
    }


async def _collect_sql_candidates(db, warnings: list[str]) -> list[dict]:
    select_body = """
        SELECT
            sql_id,
            child_number,
            plan_hash_value,
            parsing_schema_name,
            module,
            cpu_time,
            elapsed_time,
            executions,
            buffer_gets,
            disk_reads,
            rows_processed,
            last_active_time,
            sql_text
        FROM v$sql
        WHERE sql_id IS NOT NULL
          AND parsing_schema_name IS NOT NULL
          AND (module IS NULL OR module <> 'DBAChum Collector')
    """

    recent_rows = await _fetchall_optional(
        db,
        f"""
        SELECT * FROM (
            {select_body}
            ORDER BY last_active_time DESC NULLS LAST
        ) WHERE ROWNUM <= :candidate_limit
        """,
        warnings,
        "Recent SQL telemetry",
        {"candidate_limit": RECENT_SQL_CANDIDATE_LIMIT},
    )

    cpu_rows = await _fetchall_optional(
        db,
        f"""
        SELECT * FROM (
            {select_body}
            ORDER BY cpu_time DESC
        ) WHERE ROWNUM <= :candidate_limit
        """,
        warnings,
        "Top SQL telemetry",
        {"candidate_limit": CUMULATIVE_SQL_CANDIDATE_LIMIT},
    )

    candidates: dict[tuple[str, int], dict] = {}
    for row in [*recent_rows, *cpu_rows]:
        item = _sql_row(row)
        key = (item["sql_id"], item["child_number"])
        candidates[key] = item
    return list(candidates.values())


async def _collect_session_candidates(db, warnings: list[str]) -> list[dict]:
    rows = await _fetchall_optional(
        db,
        """
        SELECT *
        FROM (
            SELECT
                s.sid,
                s.serial#,
                s.username,
                s.sql_id,
                s.status,
                s.module,
                s.machine,
                s.event,
                s.wait_class,
                s.last_call_et,
                s.blocking_session,
                NVL(cpu.value, 0) AS cpu_centiseconds
            FROM v$session s
            LEFT JOIN (
                SELECT ss.sid, ss.value
                FROM v$sesstat ss
                INNER JOIN v$statname sn
                    ON sn.statistic# = ss.statistic#
                WHERE sn.name = 'CPU used by this session'
            ) cpu
                ON cpu.sid = s.sid
            WHERE s.type = 'USER'
              AND (
                    s.status = 'ACTIVE'
                    OR s.blocking_session IS NOT NULL
                  )
              AND s.audsid <>
                  TO_NUMBER(SYS_CONTEXT('USERENV', 'SESSIONID'))
            ORDER BY NVL(cpu.value, 0) DESC
        )
        WHERE ROWNUM <= :session_limit
        """,
        warnings,
        "Session CPU telemetry",
        {"session_limit": SESSION_CANDIDATE_LIMIT},
    )

    return [
        {
            "sid": int(row[0]),
            "serial_number": int(row[1]),
            "username": row[2],
            "sql_id": row[3],
            "status": row[4],
            "module": row[5],
            "machine": row[6],
            "event": row[7],
            "wait_class": row[8],
            "active_seconds": int(row[9] or 0),
            "blocking_session": int(row[10]) if row[10] is not None else None,
            "cpu_centiseconds": int(row[11] or 0),
        }
        for row in rows
    ]


async def _collect_storage(db, warnings: list[str]) -> dict:
    tablespace_rows = await _fetchall_optional(
        db,
        """
        SELECT
            m.tablespace_name,
            t.contents,
            t.status,
            ROUND(m.used_space * t.block_size),
            ROUND(m.tablespace_size * t.block_size),
            ROUND(m.used_percent, 2)
        FROM dba_tablespace_usage_metrics m
        INNER JOIN dba_tablespaces t
            ON t.tablespace_name = m.tablespace_name
        ORDER BY m.used_percent DESC, m.tablespace_name
        """,
        warnings,
        "Tablespace telemetry",
    )

    tablespaces = [
        {
            "name": row[0],
            "contents": row[1],
            "status": row[2],
            "used_bytes": int(row[3] or 0),
            "capacity_bytes": int(row[4] or 0),
            "used_percent": float(row[5] or 0),
        }
        for row in tablespace_rows
    ]

    fra_row = await _fetchone_optional(
        db,
        """
        SELECT
            name,
            space_limit,
            space_used,
            space_reclaimable,
            number_of_files
        FROM v$recovery_file_dest
        """,
        warnings,
        "FRA telemetry",
    )
    fra = None
    if fra_row and fra_row[1]:
        limit_bytes = int(fra_row[1] or 0)
        used_bytes = int(fra_row[2] or 0)
        fra = {
            "destination": fra_row[0],
            "limit_bytes": limit_bytes,
            "used_bytes": used_bytes,
            "reclaimable_bytes": int(fra_row[3] or 0),
            "number_of_files": int(fra_row[4] or 0),
            "used_percent": (
                round(used_bytes / limit_bytes * 100, 2)
                if limit_bytes > 0
                else None
            ),
        }

    return {
        "tablespaces": tablespaces,
        "fra": fra,
    }


async def collect_oracle_telemetry(
    connection: dict,
    *,
    include_storage: bool = False,
) -> dict:
    """Collect one lightweight Oracle telemetry snapshot.

    This intentionally uses dynamic performance views and DBA tables only; it
    does not depend on AWR/ASH so the Phase 6 history remains license-neutral
    and compatible with the old Oracle estates DBAChum already supports.
    """
    collected_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        async with open_oracle_connection(connection) as db:
            # Tag the dedicated telemetry session so its own V$ queries do not
            # become "Top SQL" candidates in the history we are collecting.
            try:
                await db.execute(
                    "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(:module, :action); END;",
                    {
                        "module": "DBAChum Collector",
                        "action": "Phase 6 telemetry",
                    },
                )
            except oracledb.Error:
                pass

            started = time.perf_counter()
            await db.fetchone("SELECT 1 FROM dual")
            response_time_ms = round((time.perf_counter() - started) * 1000, 1)

            identity = await _fetchone_optional(
                db,
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
                    SYS_CONTEXT('USERENV', 'INSTANCE_NAME')
                FROM dual
                """,
                warnings,
                "Database identity",
            )

            session_summary = await _fetchone_optional(
                db,
                """
                SELECT
                    COUNT(*) AS total_sessions,
                    SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN blocking_session IS NOT NULL THEN 1 ELSE 0 END)
                FROM v$session
                WHERE type = 'USER'
                  AND audsid <>
                      TO_NUMBER(SYS_CONTEXT('USERENV', 'SESSIONID'))
                """,
                warnings,
                "Session summary",
            )

            uptime_row = await _fetchone_optional(
                db,
                """
                SELECT ROUND((SYSDATE - startup_time) * 86400)
                FROM v$instance
                """,
                warnings,
                "Database uptime",
            )

            stat_rows = await _fetchall_optional(
                db,
                """
                SELECT name, value
                FROM v$sysstat
                WHERE name IN (
                    'CPU used by this session',
                    'execute count',
                    'session logical reads',
                    'physical reads',
                    'user commits',
                    'user rollbacks',
                    'redo size',
                    'parse count (hard)'
                )
                """,
                warnings,
                "System statistics",
            )
            system_stats = {
                str(row[0]): int(row[1] or 0)
                for row in stat_rows
            }

            wait_rows = await _fetchall_optional(
                db,
                """
                SELECT *
                FROM (
                    SELECT event, total_waits, time_waited
                    FROM v$system_event
                    WHERE wait_class <> 'Idle'
                    ORDER BY time_waited DESC
                )
                WHERE ROWNUM <= :wait_limit
                """,
                warnings,
                "System waits",
                {"wait_limit": WAIT_CANDIDATE_LIMIT},
            )
            system_waits = [
                {
                    "event": row[0],
                    "total_waits": int(row[1] or 0),
                    "time_waited_centiseconds": int(row[2] or 0),
                }
                for row in wait_rows
            ]

            session_candidates = await _collect_session_candidates(db, warnings)
            sql_candidates = await _collect_sql_candidates(db, warnings)

            storage = None
            if include_storage:
                storage = await _collect_storage(db, warnings)

            return {
                "collected_at": collected_at,
                "status": "limited" if warnings else "online",
                "response_time_ms": response_time_ms,
                "active": int(session_summary[1] or 0) if session_summary else None,
                "connections": int(session_summary[0] or 0) if session_summary else None,
                "blocked": int(session_summary[2] or 0) if session_summary else None,
                "uptime_seconds": int(uptime_row[0] or 0) if uptime_row else None,
                "database_name": identity[0] if identity else None,
                "service_name": identity[1] if identity else None,
                "instance_name": identity[2] if identity else None,
                "version": db.version,
                "system_stats": system_stats,
                "system_waits": system_waits,
                "session_candidates": session_candidates,
                "sql_candidates": sql_candidates,
                "storage": storage,
                "warnings": warnings,
                "error": None,
            }

    except AppError as exc:
        return {
            "collected_at": collected_at,
            "status": "unreachable",
            "warnings": [],
            "error": exc.message,
            "system_stats": {},
            "system_waits": [],
            "session_candidates": [],
            "sql_candidates": [],
            "storage": None,
        }
    except oracledb.Error as exc:
        return {
            "collected_at": collected_at,
            "status": "unreachable",
            "warnings": [],
            "error": oracle_error_message(exc),
            "system_stats": {},
            "system_waits": [],
            "session_candidates": [],
            "sql_candidates": [],
            "storage": None,
        }
