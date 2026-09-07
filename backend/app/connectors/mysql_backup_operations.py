import shlex

from app.core.exceptions import AppError
from app.core.security import decrypt_secret
from app.services.database_remote import run_database_remote_script


def _shell_single(value: str) -> str:
    return shlex.quote(str(value))


def _cnf_value(value: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise AppError(
            "Stored MySQL backup credentials contain a newline and cannot be written to a temporary client option file.",
            code="MYSQL_BACKUP_CREDENTIAL_FORMAT_UNSUPPORTED",
            status_code=400,
        )
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def mysql_backup_operation(database, connection: dict, data) -> dict:
    encrypted = connection.get("password_encrypted")
    if not encrypted:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    database_name = (connection.get("database") or "").strip()
    if not database_name:
        raise AppError(
            "MySQL/MariaDB dump requires a database name on the connection.",
            code="MYSQL_BACKUP_DATABASE_REQUIRED",
            status_code=400,
        )

    destination = (data.destination or "~/dbachum-backups").strip()
    password = decrypt_secret(encrypted)
    script = f"""set -e
umask 077
out_dir={_shell_single(destination)}
case \"$out_dir\" in '~/'*) out_dir=\"$HOME/${{out_dir#~/}}\" ;; esac
mkdir -p \"$out_dir\"
dump_bin=$(command -v mysqldump 2>/dev/null || command -v mariadb-dump 2>/dev/null || true)
[ -n "$dump_bin" ] || {{ echo 'mysqldump/mariadb-dump executable not found on the linked server.' >&2; exit 127; }}
command -v gzip >/dev/null 2>&1 || {{ echo 'gzip executable not found on the linked server.' >&2; exit 127; }}
cnf=$(mktemp)
trap 'rm -f \"$cnf\"' EXIT
cat >\"$cnf\" <<'DBACHUM_CNF'
[client]
user={_cnf_value(connection['username'])}
password={_cnf_value(password)}
host={_cnf_value(connection['host'])}
port={int(connection['port'])}
DBACHUM_CNF
stamp=$(date +%Y%m%d_%H%M%S)
out=\"$out_dir/{database_name}_${{stamp}}.sql.gz\"
mysqldump --defaults-extra-file=\"$cnf\" --single-transaction --routines --events --triggers {_shell_single(database_name)} | gzip >\"$out\"
printf 'DBACHUM_BACKUP_PATH=%s\\n' \"$out\"
"""
    result = await run_database_remote_script(
        database,
        connection,
        server_id=data.server_id,
        script=script,
    )
    path = None
    for line in result["stdout"].splitlines():
        if line.startswith("DBACHUM_BACKUP_PATH="):
            path = line.split("=", 1)[1]
    return {
        "target": database_name,
        "backup_type": "mysqldump",
        "destination": path or destination,
        "server_id": result["server_id"],
        "server_name": result["server_name"],
        "exit_status": result["exit_status"],
        "output_tail": result["stdout"][-4000:],
        "error_tail": result["stderr"][-4000:],
        "statement": "mysqldump via linked SSH server",
    }
