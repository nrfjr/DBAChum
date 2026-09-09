import shlex

from app.core.exceptions import AppError
from app.services.database_remote import run_database_remote_script


def _rman_environment(connection: dict, oracle_sid: str | None) -> str:
    sid = (oracle_sid or "").strip()
    if not sid and connection.get("oracle_identifier_type") == "sid":
        sid = str(connection.get("oracle_identifier") or "").strip()
    sid_export = f"export ORACLE_SID={shlex.quote(sid)}\n" if sid else ""
    return f"""set -e
[ -r \"$HOME/.profile\" ] && . \"$HOME/.profile\" >/dev/null 2>&1 || true
[ -r \"$HOME/.bash_profile\" ] && . \"$HOME/.bash_profile\" >/dev/null 2>&1 || true
{sid_export}if [ -n \"${{ORACLE_SID:-}}\" ] && ! command -v rman >/dev/null 2>&1; then
  if [ -r /usr/local/bin/oraenv ]; then ORAENV_ASK=NO . /usr/local/bin/oraenv >/dev/null 2>&1 || true; fi
  if ! command -v rman >/dev/null 2>&1 && [ -r /usr/bin/oraenv ]; then ORAENV_ASK=NO . /usr/bin/oraenv >/dev/null 2>&1 || true; fi
fi
command -v rman >/dev/null 2>&1 || {{ echo 'RMAN executable not found in the linked SSH environment.' >&2; exit 127; }}
"""


def _format(destination: str | None, suffix: str = "%d_%T_%U.bkp") -> str:
    if not destination:
        return ""
    path = destination.rstrip("/") + "/" + suffix
    escaped = path.replace("'", "''")
    return f" FORMAT '{escaped}'"


async def oracle_rman_backup(database, connection: dict, data) -> dict:
    action = data.action.value
    fmt = _format(data.destination)
    commands: list[str] = []
    if action == "full":
        commands.append(f"BACKUP DATABASE{fmt};")
    elif action == "archivelog":
        commands.append(f"BACKUP ARCHIVELOG ALL{fmt};")
    elif action == "database_plus_archivelog":
        if data.destination:

            commands.append("SQL 'ALTER SYSTEM ARCHIVE LOG CURRENT';")
            commands.append(f"BACKUP ARCHIVELOG ALL{fmt};")
            commands.append(f"BACKUP DATABASE{fmt};")
            commands.append("SQL 'ALTER SYSTEM ARCHIVE LOG CURRENT';")
            commands.append(f"BACKUP ARCHIVELOG ALL{fmt};")
        else:
            commands.append("BACKUP DATABASE PLUS ARCHIVELOG;")
    else:
        raise AppError(
            "Oracle RMAN supports full, archivelog, or database_plus_archivelog from this DBAChum action.",
            code="ORACLE_BACKUP_TYPE_UNSUPPORTED",
            status_code=400,
        )

    if data.cleanup_archivelogs_after:
        days = int(data.archivelog_retention_days)
        commands.append("CROSSCHECK ARCHIVELOG ALL;")
        commands.append("DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;")
        commands.append(
            f"DELETE NOPROMPT ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-{days}' BACKED UP 1 TIMES TO DEVICE TYPE DISK;"
        )

    rman_block = "\n".join(commands)
    script = _rman_environment(connection, data.oracle_sid) + f"""
rman target / <<'DBACHUM_RMAN'
{rman_block}
EXIT;
DBACHUM_RMAN
"""
    result = await run_database_remote_script(
        database,
        connection,
        server_id=data.server_id,
        script=script,
    )
    return {
        "target": connection.get("oracle_identifier") or connection.get("name"),
        "backup_type": action,
        "destination": data.destination or "RMAN configured destination",
        "server_id": result["server_id"],
        "server_name": result["server_name"],
        "exit_status": result["exit_status"],
        "output_tail": result["stdout"][-16000:],
        "error_tail": result["stderr"][-8000:],
        "statement": "RMAN backup block",
    }


async def oracle_rman_maintenance(database, connection: dict, data) -> dict:
    if data.action.value == "delete_archivelogs":
        days = int(data.older_than_days or 1)
        backup_clause = (
            f" BACKED UP {int(data.backed_up_times)} TIMES TO DEVICE TYPE DISK"
            if int(data.backed_up_times) > 0
            else ""
        )
        commands = [
            "CROSSCHECK ARCHIVELOG ALL;",
            "DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;",
            f"DELETE NOPROMPT ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-{days}'{backup_clause};",
        ]
        target = f"archivelogs older than {days} day(s)"
    elif data.action.value == "delete_obsolete":
        commands = [
            "CROSSCHECK BACKUP;",
            "DELETE NOPROMPT EXPIRED BACKUP;",
            "DELETE NOPROMPT OBSOLETE;",
        ]
        target = "RMAN obsolete backups"
    else:
        raise AppError("Unsupported Oracle maintenance operation.", status_code=400)

    script = _rman_environment(connection, data.oracle_sid) + f"""
rman target / <<'DBACHUM_RMAN'
{chr(10).join(commands)}
EXIT;
DBACHUM_RMAN
"""
    result = await run_database_remote_script(
        database,
        connection,
        server_id=data.server_id,
        script=script,
    )
    return {
        "target": target,
        "server_id": result["server_id"],
        "server_name": result["server_name"],
        "exit_status": result["exit_status"],
        "output_tail": result["stdout"][-16000:],
        "error_tail": result["stderr"][-8000:],
        "statement": "RMAN maintenance block",
    }
