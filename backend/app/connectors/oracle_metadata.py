import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError
from app.connectors.oracle_provisioning import normalize_oracle_identifier


async def list_oracle_schemas(connection: dict) -> list[dict]:
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            rows = await oracle_connection.fetchall(
                """
                SELECT username
                FROM all_users
                ORDER BY username
                """
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_SCHEMA_METADATA_FAILED",
                status_code=400,
            ) from exc

    return [{"name": row[0]} for row in rows]


async def list_oracle_tables(connection: dict, owner: str) -> list[dict]:
    owner = normalize_oracle_identifier(owner, field_name="Schema")

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            rows = await oracle_connection.fetchall(
                """
                SELECT owner, table_name
                FROM all_tables
                WHERE owner = :owner
                ORDER BY table_name
                """,
                {"owner": owner},
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_TABLE_METADATA_FAILED",
                status_code=400,
            ) from exc

    return [
        {"owner": row[0], "name": row[1]}
        for row in rows
    ]


async def list_oracle_columns(
    connection: dict,
    owner: str,
    table_name: str,
) -> list[dict]:
    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            rows = await oracle_connection.fetchall(
                """
                SELECT
                    column_name,
                    data_type,
                    data_length,
                    nullable,
                    data_default,
                    column_id
                FROM all_tab_columns
                WHERE owner = :owner
                  AND table_name = :table_name
                ORDER BY column_id
                """,
                {"owner": owner, "table_name": table_name},
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_COLUMN_METADATA_FAILED",
                status_code=400,
            ) from exc

    if not rows:
        raise AppError(
            "The selected table was not found or is not visible to this connection.",
            code="ORACLE_TABLE_NOT_VISIBLE",
            status_code=404,
        )

    return [
        {
            "name": row[0],
            "data_type": row[1],
            "data_length": row[2],
            "nullable": str(row[3]).upper() == "Y",
            "data_default": str(row[4]).strip() if row[4] is not None else None,
            "column_id": int(row[5]),
        }
        for row in rows
    ]
