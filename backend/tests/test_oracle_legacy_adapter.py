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
