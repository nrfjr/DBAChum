import oracledb

from app.core.exceptions import AppError
from app.core.security import decrypt_secret


def build_oracle_params(connection: dict) -> oracledb.ConnectParams:
    kwargs = {
        "host": connection["host"],
        "port": connection["port"],
    }

    identifier_type = connection.get("oracle_identifier_type")
    identifier = connection.get("oracle_identifier")

    if identifier_type == "sid":
        kwargs["sid"] = identifier
    else:
        kwargs["service_name"] = identifier

    return oracledb.ConnectParams(**kwargs)


async def test_oracle_connection(connection: dict) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)
    params = build_oracle_params(connection)

    try:
        async with oracledb.connect_async(
            user=connection["username"],
            password=password,
            params=params,
        ) as oracle_connection:
            row = await oracle_connection.fetchone(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
                    SYS_CONTEXT('USERENV', 'CURRENT_USER')
                FROM dual
                """
            )

            return {
                "database_name": row[0] if row else None,
                "service_name": row[1] if row else None,
                "connected_user": row[2] if row else None,
                "database_version": oracle_connection.version,
            }

    except oracledb.Error as exc:
        error = exc.args[0]

        message = getattr(
            error,
            "message",
            str(exc),
        ).strip()

        raise AppError(
            message,
            code="ORACLE_CONNECTION_FAILED",
            status_code=400,
        ) from exc