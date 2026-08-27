from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from app.connectors import oracle_users


class FakeOracleConnection:
    def __init__(self, rows, *, supports_oracle_maintained=False):
        self.rows = rows
        self.supports_oracle_maintained = supports_oracle_maintained
        self.sql_calls = []
        self.parameters = []

    async def fetchall(self, sql, parameters=None):
        self.sql_calls.append(sql)
        self.parameters.append(parameters)
        if "oracle_maintained" in sql.lower():
            if not self.supports_oracle_maintained:
                raise oracle_users.oracledb.Error("ORA-00904")
            return self.rows
        return self.rows


@pytest.mark.asyncio
async def test_oracle_user_inventory_is_unlimited_and_filters_system_accounts_on_legacy_oracle(
    monkeypatch,
):
    created = datetime(2025, 1, 1, tzinfo=timezone.utc)

    fake_connection = FakeOracleConnection(
        [
            (
                "APP_USER",
                "OPEN",
                "USERS",
                "TEMP",
                "DEFAULT",
                created,
                None,
                None,
            ),
            (
                "LOCKED_USER",
                "LOCKED(TIMED)",
                "USERS",
                "TEMP",
                "DEFAULT",
                created,
                created,
                None,
            ),
            (
                "OLD_USER",
                "EXPIRED & LOCKED",
                "USERS",
                "TEMP",
                "DEFAULT",
                created,
                created,
                created,
            ),
            (
                "SYS",
                "OPEN",
                "SYSTEM",
                "TEMP",
                "DEFAULT",
                created,
                None,
                None,
            ),
            (
                "APEX_230100",
                "LOCKED",
                "SYSAUX",
                "TEMP",
                "DEFAULT",
                created,
                created,
                None,
            ),
        ]
    )

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake_connection

    monkeypatch.setattr(
        oracle_users,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_users.get_oracle_users(
        {"engine": "oracle"}
    )

    assert result["available"] is True
    assert result["total"] == 3
    assert result["open"] == 1
    assert result["locked"] == 2
    assert result["expired"] == 1
    assert [item["username"] for item in result["items"]] == [
        "APP_USER",
        "LOCKED_USER",
        "OLD_USER",
    ]
    assert len(fake_connection.sql_calls) == 2
    assert all("ROWNUM" not in sql.upper() for sql in fake_connection.sql_calls)
    assert fake_connection.parameters == [None, None]


@pytest.mark.asyncio
async def test_oracle_user_inventory_uses_oracle_maintained_when_available(
    monkeypatch,
):
    created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    fake_connection = FakeOracleConnection(
        [
            (
                "BUSINESS_USER",
                "OPEN",
                "USERS",
                "TEMP",
                "DEFAULT",
                created,
                None,
                None,
                "N",
            ),
            (
                "NEW_INTERNAL_SCHEMA",
                "LOCKED",
                "SYSAUX",
                "TEMP",
                "DEFAULT",
                created,
                created,
                None,
                "Y",
            ),
        ],
        supports_oracle_maintained=True,
    )

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake_connection

    monkeypatch.setattr(
        oracle_users,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_users.get_oracle_users(
        {"engine": "oracle"}
    )

    assert result["available"] is True
    assert result["total"] == 1
    assert result["items"][0]["username"] == "BUSINESS_USER"
    assert len(fake_connection.sql_calls) == 1
    assert "oracle_maintained" in fake_connection.sql_calls[0].lower()
    assert "ROWNUM" not in fake_connection.sql_calls[0].upper()
