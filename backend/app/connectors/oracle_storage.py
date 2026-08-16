from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)


async def get_oracle_storage(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    tablespaces = []
    fra = None

    warnings: list[str] = []

    tablespaces_available = True
    fra_available = True

    async with open_oracle_connection(
        connection
    ) as oracle_connection:

        try:
            rows = await oracle_connection.fetchall(
                """
                SELECT
                    m.tablespace_name,
                    t.contents,
                    t.status,

                    ROUND(
                        m.used_space
                        * t.block_size
                    ),

                    ROUND(
                        m.tablespace_size
                        * t.block_size
                    ),

                    ROUND(
                        m.used_percent,
                        2
                    )

                FROM dba_tablespace_usage_metrics m

                INNER JOIN dba_tablespaces t
                    ON t.tablespace_name =
                       m.tablespace_name

                ORDER BY
                    m.used_percent DESC,
                    m.tablespace_name
                """
            )

            tablespaces = [
                {
                    "name": row[0],
                    "contents": row[1],
                    "status": row[2],
                    "used_bytes":
                        int(row[3] or 0),
                    "capacity_bytes":
                        int(row[4] or 0),
                    "used_percent":
                        float(row[5] or 0),
                }
                for row in rows
            ]

        except oracledb.Error as exc:
            tablespaces_available = False

            warnings.append(
                "Tablespace information unavailable: "
                + oracle_error_message(exc)
            )

        try:
            row = await oracle_connection.fetchone(
                """
                SELECT
                    name,
                    space_limit,
                    space_used,
                    space_reclaimable,
                    number_of_files

                FROM v$recovery_file_dest
                """
            )

            if row and row[1]:
                limit_bytes = int(
                    row[1] or 0
                )

                used_bytes = int(
                    row[2] or 0
                )

                used_percent = (
                    round(
                        used_bytes
                        / limit_bytes
                        * 100,
                        2,
                    )
                    if limit_bytes > 0
                    else None
                )

                fra = {
                    "destination": row[0],
                    "limit_bytes":
                        limit_bytes,
                    "used_bytes":
                        used_bytes,
                    "reclaimable_bytes":
                        int(row[3] or 0),
                    "number_of_files":
                        int(row[4] or 0),
                    "used_percent":
                        used_percent,
                }

            else:
                fra_available = False

        except oracledb.Error as exc:
            fra_available = False

            warnings.append(
                "FRA information unavailable: "
                + oracle_error_message(exc)
            )

    return {
        "tablespaces_available":
            tablespaces_available,

        "fra_available":
            fra_available,

        "tablespaces":
            tablespaces,

        "fra":
            fra,

        "warnings":
            warnings,

        "checked_at":
            checked_at,
    }