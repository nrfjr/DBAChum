from app.schemas.database_connection import DatabaseConnectionCreate
from app.services.database_connections import (
    connection_is_active,
    connection_is_monitored,
    monitored_connections_filter,
)


def _payload(**overrides):
    payload = {
        "name": "Provisioning Oracle",
        "engine": "oracle",
        "host": "ora01",
        "port": 1521,
        "username": "SYS",
        "password": "secret",
        "oracle_identifier_type": "service_name",
        "oracle_identifier": "ORMS",
        "oracle_auth_mode": "sysdba",
        "server_ids": [],
    }
    payload.update(overrides)
    return payload


def test_legacy_disabled_means_not_monitored_but_still_usable():
    legacy = {"enabled": False}

    assert connection_is_active(legacy) is True
    assert connection_is_monitored(legacy) is False


def test_new_flags_are_independent():
    connection = {
        "active": True,
        "monitor_enabled": False,
        "enabled": False,
    }

    assert connection_is_active(connection) is True
    assert connection_is_monitored(connection) is False


def test_old_payload_maps_enabled_to_monitoring_only():
    model = DatabaseConnectionCreate(**_payload(enabled=False))

    assert model.active is True
    assert model.monitor_enabled is False
    assert model.enabled is False


def test_new_payload_keeps_legacy_monitor_alias_in_sync():
    model = DatabaseConnectionCreate(
        **_payload(active=True, monitor_enabled=False)
    )

    assert model.active is True
    assert model.monitor_enabled is False
    assert model.enabled is False


def test_monitor_query_requires_active_and_monitored():
    query = monitored_connections_filter()

    assert "$and" in query
    assert {"active": True} in query["$and"][0]["$or"]
    assert {"monitor_enabled": True} in query["$and"][1]["$or"]
