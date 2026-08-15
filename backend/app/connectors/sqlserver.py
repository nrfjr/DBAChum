import asyncio

import mssql_python

from app.core.exceptions import AppError
from app.core.security import decrypt_secret


def _test_sqlserver_sync(connection: dict) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)

    server = f'{connection["host"]},{connection["port"]}'

    connect_kwargs = {
        "server": server,
        "uid": connection["username"],
        "pwd": password,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **connect_kwargs,
        ) as sql_connection:
            cursor = sql_connection.cursor()

            cursor.execute(
                """
                SELECT
                    DB_NAME(),
                    SUSER_SNAME(),
                    CAST(
                        SERVERPROPERTY('ProductVersion')
                        AS varchar(128)
                    )
                """
            )

            row = cursor.fetchone()

            return {
                "database_name": row[0] if row else None,
                "connected_user": row[1] if row else None,
                "database_version": row[2] if row else None,
                "service_name": None,
            }

    except mssql_python.Error as exc:
        raise AppError(
            str(exc),
            code="SQLSERVER_CONNECTION_FAILED",
            status_code=400,
        ) from exc


async def test_sqlserver_connection(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _test_sqlserver_sync,
        connection,
    )