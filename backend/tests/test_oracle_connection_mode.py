from app.connectors import oracle
from app.schemas.database_connection import (
    DatabaseConnectionCreate,
)


def oracle_payload(**overrides):
    payload = {
        "name": "ERP",
        "engine": "oracle",
        "host": "ora01",
        "port": 1521,
        "username": "SYS",
        "password": "secret",
        "oracle_identifier_type": "service_name",
        "oracle_identifier": "ERPPRD",
        "enabled": True,
        "server_ids": [],
    }
    payload.update(overrides)
    return payload


def test_oracle_connection_defaults_to_normal_auth_mode():
    connection = DatabaseConnectionCreate(
        **oracle_payload()
    )

    assert connection.oracle_auth_mode == "normal"


def test_non_oracle_connection_discards_oracle_auth_mode():
    connection = DatabaseConnectionCreate(
        name="SQL",
        engine="sqlserver",
        host="sql01",
        port=1433,
        username="sa",
        password="secret",
        database="master",
        oracle_auth_mode="sysdba",
        enabled=True,
        server_ids=[],
    )

    assert connection.oracle_auth_mode is None


def test_sysdba_mode_is_passed_to_python_oracledb(monkeypatch):
    monkeypatch.setattr(
        oracle,
        "build_oracle_params",
        lambda _connection: "params",
    )

    kwargs = oracle.build_oracle_connect_kwargs(
        {
            "username": "SYS",
            "oracle_auth_mode": "sysdba",
        },
        "secret",
    )

    assert kwargs["user"] == "SYS"
    assert kwargs["password"] == "secret"
    assert kwargs["params"] == "params"
    assert kwargs["mode"] == oracle.oracledb.AUTH_MODE_SYSDBA


def test_normal_mode_does_not_send_privileged_mode(monkeypatch):
    monkeypatch.setattr(
        oracle,
        "build_oracle_params",
        lambda _connection: "params",
    )

    kwargs = oracle.build_oracle_connect_kwargs(
        {
            "username": "DBACHUM",
            "oracle_auth_mode": "normal",
        },
        "secret",
    )

    assert "mode" not in kwargs

import pytest

from app.core.exceptions import AppError
from app.schemas.database_connection import DatabaseConnectionUpdate
from app.services.database_connections import update_database_connection


class ExistingConnectionCollection:
    async def find_one(self, _query):
        return {
            "username": "DBACHUM",
        }


class ExistingConnectionDatabase:
    def __init__(self):
        self.database_connections = ExistingConnectionCollection()


@pytest.mark.asyncio
async def test_changing_connection_username_requires_new_password():
    with pytest.raises(AppError) as exc_info:
        await update_database_connection(
            ExistingConnectionDatabase(),
            "0" * 24,
            DatabaseConnectionUpdate(
                name="ERP",
                engine="oracle",
                host="ora01",
                port=1521,
                username="SYS",
                password=None,
                oracle_identifier_type="service_name",
                oracle_identifier="ERPPRD",
                oracle_auth_mode="sysdba",
                enabled=True,
                server_ids=[],
            ),
        )

    assert exc_info.value.code == "CONNECTION_PASSWORD_REQUIRED"
