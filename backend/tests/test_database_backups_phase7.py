from datetime import datetime

import pytest

from app.connectors.sqlserver_backups import _backup_item
from app.services import database_backups


def test_sqlserver_backup_row_is_normalized():
    started = datetime(2026, 9, 1, 1, 0, 0)
    finished = datetime(2026, 9, 1, 1, 10, 0)
    row = (
        42,
        7,
        "ERP",
        "D",
        started,
        finished,
        1024,
        "ERP FULL",
        "sa",
    )

    item = _backup_item(row, {7: [r"D:\Backup\ERP.bak"]})

    assert item["backup_id"] == "42"
    assert item["kind"] == "full"
    assert item["duration_seconds"] == 600
    assert item["backup_size_bytes"] == 1024
    assert item["destinations"] == [r"D:\Backup\ERP.bak"]
    assert item["status"] == "successful"


@pytest.mark.asyncio
async def test_backup_service_dispatches_sqlserver(monkeypatch):
    connection = {"_id": "x", "engine": "sqlserver"}

    async def fake_connection(_database, _connection_id):
        return connection

    async def fake_sqlserver(_connection):
        return {
            "available": True,
            "source": "msdb backup history",
            "scope": "instance",
            "database_name": "master",
            "generation": "SQL Server 2000",
            "summaries": [],
            "items": [],
            "warnings": [],
            "notes": [],
            "checked_at": datetime(2026, 9, 1, 0, 0, 0),
        }

    monkeypatch.setattr(database_backups, "get_database_connection", fake_connection)
    monkeypatch.setattr(database_backups, "get_sqlserver_backups", fake_sqlserver)

    result = await database_backups.load_database_backups(object(), "abc")

    assert result["connection_id"] == "abc"
    assert result["engine"] == "sqlserver"
    assert result["source"] == "msdb backup history"
