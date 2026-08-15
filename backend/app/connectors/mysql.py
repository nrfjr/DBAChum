import mysql.connector.aio as mysql_aio
from mysql.connector import Error as MySQLError

from app.core.exceptions import AppError
from app.core.security import decrypt_secret


async def test_mysql_connection(
    connection: dict,
) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)

    connect_kwargs = {
        "host": connection["host"],
        "port": connection["port"],
        "user": connection["username"],
        "password": password,
        "connection_timeout": 5,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        async with await mysql_aio.connect(
            **connect_kwargs
        ) as mysql_connection:
            async with await mysql_connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        DATABASE(),
                        CURRENT_USER(),
                        VERSION()
                    """
                )

                row = await cursor.fetchone()

                return {
                    "database_name": row[0] if row else None,
                    "connected_user": row[1] if row else None,
                    "database_version": row[2] if row else None,
                    "service_name": None,
                }

    except MySQLError as exc:
        raise AppError(
            str(exc),
            code="MYSQL_CONNECTION_FAILED",
            status_code=400,
        ) from exc