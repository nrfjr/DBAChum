import asyncio
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import _close_mysql_resource, mysql_connect_kwargs
from app.core.exceptions import AppError


def _qident(value: str) -> str:
    return "`" + str(value).replace("`", "``") + "`"


def _jobs_sync(connection: dict) -> dict:
    db = cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        schema = connection.get("database")
        sql = """
            SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, EVENT_TYPE,
                   INTERVAL_VALUE, INTERVAL_FIELD, EXECUTE_AT, STARTS, ENDS,
                   LAST_EXECUTED
            FROM information_schema.EVENTS
        """
        params = None
        if schema:
            sql += " WHERE EVENT_SCHEMA = %s"
            params = (schema,)
        sql += " ORDER BY EVENT_SCHEMA, EVENT_NAME"
        cursor.execute(sql, params)
        items = []
        for row in cursor.fetchall():
            owner, name = str(row[0]), str(row[1])
            event_type = None if row[3] is None else str(row[3])
            if event_type == "RECURRING":
                schedule = f"EVERY {row[4]} {row[5]}" if row[4] is not None else None
            else:
                schedule = f"AT {row[6]}" if row[6] is not None else None
            items.append({
                "id": f"{owner}.{name}",
                "name": name,
                "owner": owner,
                "enabled": str(row[2] or "").upper() == "ENABLED",
                "status": None if row[2] is None else str(row[2]),
                "schedule": schedule,
                "last_run": row[9],
                "next_run": row[7] if event_type == "RECURRING" else row[6],
                "job_type": "Event Scheduler",
                "detail": f"Ends {row[8]}" if row[8] is not None else None,
                "can_run": False,
                "can_enable_disable": True,
            })
        return {"available": True, "items": items, "warnings": [], "checked_at": datetime.now(timezone.utc)}
    except MySQLError as exc:
        return {"available": False, "items": [], "warnings": [f"MySQL/MariaDB Event Scheduler metadata is unavailable. ({exc})"], "checked_at": datetime.now(timezone.utc)}
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def get_mysql_jobs(connection: dict) -> dict:
    return await asyncio.to_thread(_jobs_sync, connection)


def _operate_sync(connection: dict, data) -> dict:
    if data.action.value == "run":
        raise AppError("MySQL/MariaDB events do not expose a safe generic Run Now operation.", code="MYSQL_EVENT_RUN_UNSUPPORTED", status_code=400)
    if "." not in data.job_id:
        raise AppError("Invalid MySQL/MariaDB event identifier.", status_code=400)
    schema, name = data.job_id.split(".", 1)
    db = cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        state = "ENABLE" if data.action.value == "enable" else "DISABLE"
        statement = f"ALTER EVENT {_qident(schema)}.{_qident(name)} {state}"
        cursor.execute(statement)
        return {"target": data.job_id, "statement": statement}
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_EVENT_OPERATION_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_job_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_operate_sync, connection, data)
