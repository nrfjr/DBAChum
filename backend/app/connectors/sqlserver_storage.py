import asyncio
from datetime import datetime, timezone

import mssql_python

from app.connectors.sqlserver_sessions import (
    _connect_kwargs,
)
from app.core.exceptions import AppError


def _get_sqlserver_storage_sync(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **_connect_kwargs(connection),
        ) as sql_connection:

            cursor = sql_connection.cursor()

            cursor.execute(
                """
                SELECT
                    DB_NAME(),

                    name,
                    physical_name,
                    type_desc,

                    CAST(size AS bigint) * 8192,

                    CASE
                        WHEN FILEPROPERTY(
                            name,
                            'SpaceUsed'
                        ) IS NULL
                        THEN NULL
                        ELSE
                            CAST(
                                FILEPROPERTY(
                                    name,
                                    'SpaceUsed'
                                )
                                AS bigint
                            ) * 8192
                    END

                FROM sys.database_files

                ORDER BY
                    type_desc,
                    file_id
                """
            )

            rows = cursor.fetchall()

            files = []

            allocated_total = 0
            used_total = 0
            have_used = False

            database_name = None

            for row in rows:
                database_name = row[0]

                allocated = int(row[4] or 0)

                used = (
                    int(row[5])
                    if row[5] is not None
                    else None
                )

                free = (
                    max(allocated - used, 0)
                    if used is not None
                    else None
                )

                percent = (
                    round(
                        used / allocated * 100,
                        2,
                    )
                    if used is not None
                    and allocated > 0
                    else None
                )

                allocated_total += allocated

                if used is not None:
                    used_total += used
                    have_used = True

                files.append(
                    {
                        "name": row[1],
                        "physical_name": row[2],
                        "file_type": row[3],

                        "allocated_bytes":
                            allocated,

                        "used_bytes": used,
                        "free_bytes": free,
                        "used_percent": percent,
                    }
                )

            return {
                "available": True,

                "database_name":
                    database_name,

                "allocated_bytes":
                    allocated_total,

                "used_bytes":
                    used_total
                    if have_used
                    else None,

                "files": files,
                "warnings": [],

                "checked_at": checked_at,
            }

    except mssql_python.Error as exc:
        raise AppError(
            str(exc),
            code="SQLSERVER_STORAGE_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_storage(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _get_sqlserver_storage_sync,
        connection,
    )