from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from app.connectors import oracle_users


class FakeOracleConnection:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.parameters = None

    async def fetchall(self, sql, parameters=None):
        self.sql = sql
        self.parameters = parameters
        return self.rows


@pytest.mark.asyncio
async def test_oracle_user_inventory_maps_accounts_and_counts(
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
    assert result["items"][0]["username"] == "APP_USER"
    assert (
        result["items"][0]["default_tablespace"]
        == "USERS"
    )
    assert "FROM dba_users" in fake_connection.sql
    assert fake_connection.parameters == {
        "user_limit": oracle_users.USER_LIST_LIMIT
    }
