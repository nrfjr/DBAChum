import asyncio
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import open_sqlserver_connection, sqlserver_error_message
from app.core.exceptions import AppError


def _jobs_sync(connection: dict) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute(
                    """
                    SELECT CONVERT(varchar(36), j.job_id), j.name, j.enabled,
                           SUSER_SNAME(j.owner_sid),
                           h.run_status, h.run_date, h.run_time, h.message
                    FROM msdb.dbo.sysjobs j
                    LEFT JOIN msdb.dbo.sysjobhistory h
                      ON h.instance_id = (
                        SELECT MAX(h2.instance_id)
                        FROM msdb.dbo.sysjobhistory h2
                        WHERE h2.job_id = j.job_id AND h2.step_id = 0
                      )
                    ORDER BY j.name
                    """
                )
                rows = cursor.fetchall()
                status_map = {0: "FAILED", 1: "SUCCEEDED", 2: "RETRY", 3: "CANCELED", 4: "RUNNING"}
                items = []
                for row in rows:
                    run_date = int(row[5] or 0)
                    run_time = int(row[6] or 0)
                    last_run = None
                    if run_date:
                        try:
                            last_run = datetime.strptime(f"{run_date:08d}{run_time:06d}", "%Y%m%d%H%M%S")
                        except ValueError:
                            last_run = None
                    items.append({
                        "id": str(row[0]),
                        "name": str(row[1]),
                        "owner": None if row[3] is None else str(row[3]),
                        "enabled": bool(row[2]),
                        "status": status_map.get(row[4], "UNKNOWN") if row[4] is not None else "NEVER RUN",
                        "last_run": last_run,
                        "next_run": None,
                        "schedule": None,
                        "job_type": "SQL Server Agent",
                        "detail": None if row[7] is None else str(row[7]),
                        "can_run": True,
                        "can_enable_disable": True,
                    })
                return {"available": True, "items": items, "warnings": [], "checked_at": datetime.now(timezone.utc)}
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        return {
            "available": False,
            "items": [],
            "warnings": [f"SQL Server Agent jobs are unavailable. ({sqlserver_error_message(exc)})"],
            "checked_at": datetime.now(timezone.utc),
        }


async def get_sqlserver_jobs(connection: dict) -> dict:
    return await asyncio.to_thread(_jobs_sync, connection)


def _operate_sync(connection: dict, data) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute("SELECT name FROM msdb.dbo.sysjobs WHERE CONVERT(varchar(36), job_id) = ?", data.job_id)
                row = cursor.fetchone()
                if not row:
                    raise AppError("SQL Server Agent job was not found.", code="SQLSERVER_JOB_NOT_FOUND", status_code=404)
                name = str(row[0])
                if data.action.value == "run":
                    cursor.execute("EXEC msdb.dbo.sp_start_job @job_name = ?", name)
                    statement = "EXEC msdb.dbo.sp_start_job"
                else:
                    enabled = 1 if data.action.value == "enable" else 0
                    cursor.execute("EXEC msdb.dbo.sp_update_job @job_name = ?, @enabled = ?", name, enabled)
                    statement = "EXEC msdb.dbo.sp_update_job"
                return {"target": name, "statement": statement}
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="SQLSERVER_JOB_OPERATION_FAILED", status_code=400) from exc


async def sqlserver_job_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_operate_sync, connection, data)
