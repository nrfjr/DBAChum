from datetime import date, datetime

import pytest

from app.connectors.sqlserver_backups import _backup_item, _window_clause
from app.services import database_backups


def test_sqlserver_backup_row_is_normalized_with_transparent_sizes():
    started = datetime(2026, 9, 1, 1, 0, 0)
    finished = datetime(2026, 9, 1, 1, 10, 0)
    row = {
        "backup_set_id": 42,
        "media_set_id": 7,
        "database_name": "ERP",
        "type": "D",
        "backup_start_date": started,
        "backup_finish_date": finished,
        "backup_size": 4096,
        "compressed_backup_size": 1024,
        "name": "ERP FULL",
        "user_name": "sa",
        "recovery_model": "FULL",
        "has_backup_checksums": 1,
        "is_copy_only": 0,
    }
    media = {
        7: [
            {
                "media_set_id": 7,
                "physical_device_name": r"D:\Backup\ERP.bak",
                "logical_device_name": None,
                "device_type": 2,
                "family_sequence_number": 1,
            }
        ]
    }

    item = _backup_item(row, media)

    assert item["backup_id"] == "42"
    assert item["kind"] == "full"
    assert item["duration_seconds"] == 600
    assert item["input_bytes"] == 4096
    assert item["output_bytes"] == 1024
    assert item["backup_size_bytes"] == 1024
    assert item["destinations"] == [r"D:\Backup\ERP.bak"]
    assert item["device_type"] == "Disk"
    assert item["details"]["recovery_model"] == "FULL"
    assert item["details"]["has_backup_checksums"] is True
    assert item["status"] == "successful"


def test_sqlserver_custom_backup_window_uses_exclusive_end_date():
    clause, parameters = _window_clause(
        {
            "window": "custom",
            "start_date": date(2026, 8, 30),
            "end_date": date(2026, 9, 2),
        }
    )

    assert "backup_finish_date >= ?" in clause
    assert "backup_finish_date < ?" in clause
    assert parameters[0] == datetime(2026, 8, 30, 0, 0, 0)
    assert parameters[1] == datetime(2026, 9, 3, 0, 0, 0)


@pytest.mark.asyncio
async def test_backup_service_dispatches_sqlserver_with_range(monkeypatch):
    connection = {"_id": "x", "engine": "sqlserver"}
    received_filter = None

    async def fake_connection(_database, _connection_id):
        return connection

    async def fake_sqlserver(_connection, history_filter):
        nonlocal received_filter
        received_filter = history_filter
        return {
            "available": True,
            "source": "msdb backup history",
            "scope": "database",
            "database_name": "ERP",
            "generation": "SQL Server 2000",
            "latest_backup": None,
            "summaries": [],
            "items": [],
            "truncated": False,
            "warnings": [],
            "notes": [],
            "checked_at": datetime(2026, 9, 1, 0, 0, 0),
        }

    monkeypatch.setattr(database_backups, "get_database_connection", fake_connection)
    monkeypatch.setattr(database_backups, "get_sqlserver_backups", fake_sqlserver)

    result = await database_backups.load_database_backups(
        object(),
        "abc",
        window="7d",
    )

    assert result["connection_id"] == "abc"
    assert result["engine"] == "sqlserver"
    assert result["source"] == "msdb backup history"
    assert result["selected_window"] == "7d"
    assert received_filter == {
        "window": "7d",
        "start_date": None,
        "end_date": None,
    }


def test_custom_range_requires_dates():
    with pytest.raises(Exception):
        database_backups._backup_filter("custom", None, None)
