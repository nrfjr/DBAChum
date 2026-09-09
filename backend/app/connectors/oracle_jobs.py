from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


def _qualified_scheduler_name(job_id: str) -> tuple[str, str]:
    if not job_id.startswith("scheduler:"):
        raise AppError("Invalid Oracle Scheduler job identifier.", status_code=400)
    value = job_id.split(":", 1)[1]
    if "." not in value:
        raise AppError("Invalid Oracle Scheduler job identifier.", status_code=400)
    owner, name = value.split(".", 1)
    return owner, name


def _legacy_job_number(job_id: str) -> int:
    if not job_id.startswith("legacy:"):
        raise AppError("Invalid legacy Oracle job identifier.", status_code=400)
    try:
        return int(job_id.split(":", 1)[1])
    except ValueError as exc:
        raise AppError("Invalid legacy Oracle job identifier.", status_code=400) from exc


async def get_oracle_jobs(connection: dict) -> dict:
    warnings: list[str] = []
    try:
        async with open_oracle_connection(connection) as db:
            items: list[dict] = []
            try:
                rows = await db.fetchall(
                    """
                    SELECT owner, job_name, enabled, state, job_type,
                           repeat_interval, last_start_date, next_run_date,
                           run_count, failure_count
                    FROM all_scheduler_jobs
                    ORDER BY owner, job_name
                    """
                )
                for row in rows:
                    owner, name = str(row[0]), str(row[1])
                    items.append({
                        "id": f"scheduler:{owner}.{name}",
                        "name": name,
                        "owner": owner,
                        "enabled": str(row[2] or "FALSE").upper() == "TRUE",
                        "status": None if row[3] is None else str(row[3]),
                        "job_type": None if row[4] is None else str(row[4]),
                        "schedule": None if row[5] is None else str(row[5]),
                        "last_run": row[6],
                        "next_run": row[7],
                        "detail": f"Runs {row[8] or 0} · failures {row[9] or 0}",
                        "can_run": True,
                        "can_enable_disable": True,
                    })
            except oracledb.Error as exc:
                warnings.append(
                    "Oracle Scheduler metadata is unavailable; system is using legacy DBMS_JOB visibility where possible. "
                    f"({oracle_error_message(exc)})"
                )

            try:
                rows = await db.fetchall(
                    """
                    SELECT job, what, next_date, interval, broken, failures, last_date
                    FROM user_jobs
                    ORDER BY job
                    """
                )
                existing = {item["id"] for item in items}
                for row in rows:
                    job_number = int(row[0])
                    job_id = f"legacy:{job_number}"
                    if job_id in existing:
                        continue
                    items.append({
                        "id": job_id,
                        "name": f"DBMS_JOB {job_number}",
                        "owner": connection.get("username"),
                        "enabled": str(row[4] or "N").upper() != "Y",
                        "status": "BROKEN" if str(row[4] or "N").upper() == "Y" else "SCHEDULED",
                        "job_type": "DBMS_JOB",
                        "schedule": None if row[3] is None else str(row[3]),
                        "last_run": row[6],
                        "next_run": row[2],
                        "detail": None if row[1] is None else str(row[1]),
                        "can_run": True,
                        "can_enable_disable": True,
                    })
            except oracledb.Error as exc:
                if not items:
                    warnings.append(f"Legacy DBMS_JOB metadata is unavailable. ({oracle_error_message(exc)})")

            return {
                "available": bool(items) or not warnings,
                "items": items,
                "warnings": warnings,
                "checked_at": datetime.now(timezone.utc),
            }
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(oracle_error_message(exc), code="ORACLE_JOBS_FAILED", status_code=400) from exc


async def oracle_job_operation(connection: dict, data) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            if data.job_id.startswith("scheduler:"):
                owner, name = _qualified_scheduler_name(data.job_id)
                qualified = f'{owner}.{name}'
                if data.action.value == "run":
                    statement = "BEGIN DBMS_SCHEDULER.RUN_JOB(:job_name, use_current_session => FALSE); END;"
                    await db.execute(statement, {"job_name": qualified})
                elif data.action.value == "enable":
                    statement = "BEGIN DBMS_SCHEDULER.ENABLE(:job_name); END;"
                    await db.execute(statement, {"job_name": qualified})
                elif data.action.value == "disable":
                    statement = "BEGIN DBMS_SCHEDULER.DISABLE(:job_name, force => TRUE); END;"
                    await db.execute(statement, {"job_name": qualified})
                else:
                    raise AppError("Unsupported Oracle Scheduler operation.", status_code=400)
                await db.commit()
                return {"target": qualified, "statement": statement}

            job_number = _legacy_job_number(data.job_id)
            if data.action.value == "run":
                statement = "BEGIN DBMS_JOB.RUN(:job, TRUE); END;"
                await db.execute(statement, {"job": job_number})
            elif data.action.value in {"enable", "disable"}:
                broken_literal = "FALSE" if data.action.value == "enable" else "TRUE"
                statement = f"BEGIN DBMS_JOB.BROKEN(:job, {broken_literal}); END;"
                await db.execute(statement, {"job": job_number})
            else:
                raise AppError("Unsupported legacy Oracle job operation.", status_code=400)
            await db.commit()
            return {"target": str(job_number), "statement": statement}
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(oracle_error_message(exc), code="ORACLE_JOB_OPERATION_FAILED", status_code=400) from exc
