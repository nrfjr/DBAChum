import pytest

from app.connectors import oracle


class FakeCursor:
    def __init__(self):
        self.rowcount = 1
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return [(1,), (2,)]


class FakeSyncConnection:
    version = "10.2.0.5.0"

    def __init__(self):
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return FakeCursor()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_oracle_adapter_wraps_sync_connection(monkeypatch):
    sync_connection = FakeSyncConnection()
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return sync_connection

    monkeypatch.setattr(
        oracle.oracledb,
        "connect",
        fake_connect,
    )

    adapter = oracle.OracleConnectionAdapter(
        {"user": "SYS", "password": "secret"}
    )

    await adapter.connect()
    assert adapter.version == "10.2.0.5.0"
    assert captured["user"] == "SYS"
    assert await adapter.fetchone("SELECT 1 FROM dual") == (1,)
    assert await adapter.fetchall("SELECT 1 FROM dual") == [(1,), (2,)]

    await adapter.commit()
    await adapter.rollback()
    await adapter.close()

    assert sync_connection.committed is True
    assert sync_connection.rolled_back is True
    assert sync_connection.closed is True


def test_oracle_10g_version_is_legacy_non_multitenant():
    assert oracle._oracle_major_version("10.2.0.5.0") == 10
    assert oracle._oracle_major_version("19.0.0.0.0") == 19


class FakeLegacyQueryConnection:
    def __init__(self, version: str):
        self.version = version
        self.sql = []

    async def fetchone(self, sql, parameters=None):
        self.sql.append((sql, parameters))
        return (0, 0, 0, 0)

    async def fetchall(self, sql, parameters=None):
        self.sql.append((sql, parameters))
        return []


@pytest.mark.asyncio
async def test_oracle_10g_sessions_uses_legacy_safe_sql_exec_start(monkeypatch):
    from contextlib import asynccontextmanager
    from app.connectors import oracle_sessions

    db = FakeLegacyQueryConnection("10.2.0.5.0")

    @asynccontextmanager
    async def fake_open(_connection):
        yield db

    monkeypatch.setattr(
        oracle_sessions,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_sessions.get_oracle_sessions({})

    assert result["available"] is True
    session_sql = db.sql[-1][0]
    assert "CAST(NULL AS DATE) AS sql_exec_start" in session_sql
    assert "                        sql_exec_start," not in session_sql


@pytest.mark.asyncio
async def test_oracle_10g_activity_uses_legacy_safe_sql_exec_start(monkeypatch):
    from contextlib import asynccontextmanager
    from app.connectors import oracle_activity

    db = FakeLegacyQueryConnection("10.2.0.5.0")

    @asynccontextmanager
    async def fake_open(_connection):
        yield db

    monkeypatch.setattr(
        oracle_activity,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_activity.get_oracle_activity({})

    assert result["available"] is True
    activity_sql = db.sql[-1][0]
    assert "CAST(NULL AS DATE) AS sql_exec_start" in activity_sql
    assert "s.sql_exec_start AS sql_exec_start" not in activity_sql


@pytest.mark.asyncio
async def test_oracle_11g_plus_keeps_real_sql_exec_start(monkeypatch):
    from contextlib import asynccontextmanager
    from app.connectors import oracle_sessions, oracle_activity

    sessions_db = FakeLegacyQueryConnection("11.2.0.4.0")
    activity_db = FakeLegacyQueryConnection("19.0.0.0.0")

    @asynccontextmanager
    async def fake_sessions_open(_connection):
        yield sessions_db

    @asynccontextmanager
    async def fake_activity_open(_connection):
        yield activity_db

    monkeypatch.setattr(
        oracle_sessions,
        "open_oracle_connection",
        fake_sessions_open,
    )
    monkeypatch.setattr(
        oracle_activity,
        "open_oracle_connection",
        fake_activity_open,
    )

    assert (await oracle_sessions.get_oracle_sessions({}))["available"] is True
    assert (await oracle_activity.get_oracle_activity({}))["available"] is True

    session_sql = sessions_db.sql[-1][0]
    activity_sql = activity_db.sql[-1][0]

    assert "sql_exec_start AS sql_exec_start" in session_sql
    assert "CAST(NULL AS DATE) AS sql_exec_start" not in session_sql
    assert "s.sql_exec_start AS sql_exec_start" in activity_sql
    assert "CAST(NULL AS DATE) AS sql_exec_start" not in activity_sql
