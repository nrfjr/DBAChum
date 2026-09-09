from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.core.collections import APP_BRANDING_COLLECTION_NAME
from app.core.config import settings
from app.core.indexes import create_indexes
from app.schemas.system_settings import (
    CleanupRequest,
    DataSettingsUpdate,
    GeneralSettingsUpdate,
    MonitoringSettingsUpdate,
)


APP_SETTINGS_ID = "global"
APP_SETTINGS_COLLECTION = "app_settings"
BRANDING_LOGO_ID = "logo"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _defaults() -> dict[str, Any]:
    return {
        "general": {
            "installation_name": "DBAChum",
            "default_page_size": 10,
            "default_analytics_months": 12,
        },
        "monitoring": {
            "enabled": settings.metrics_collector_enabled,
            "database_interval_seconds": settings.metrics_collector_interval_seconds,
            "server_interval_seconds": settings.server_metrics_interval_seconds,
            "storage_interval_seconds": max(
                settings.oracle_storage_interval_seconds,
                settings.sqlserver_storage_interval_seconds,
                settings.mysql_storage_interval_seconds,
            ),
            "analytics_snapshot_interval_seconds": settings.analytics_snapshot_interval_seconds,
            "target_timeout_seconds": settings.metrics_target_timeout_seconds,
            "concurrency": settings.metrics_collector_concurrency,
            "stale_threshold_seconds": settings.alert_collector_stale_seconds,
        },
        "data": {
            "analytics_retention_days": 730,
            "action_audit_retention_days": 365,
            "terminal_audit_retention_days": 365,
            "provisioning_history_retention_days": 365,
        },
    }


def _merge_settings(document: dict | None) -> dict[str, Any]:
    merged = _defaults()
    if not document:
        return merged
    for section in ("general", "monitoring", "data"):
        values = document.get(section)
        if isinstance(values, dict):
            merged[section].update(values)
    return merged


async def get_system_settings(database) -> dict[str, Any]:
    document = await database[APP_SETTINGS_COLLECTION].find_one({"_id": APP_SETTINGS_ID})
    return _merge_settings(document)


async def branding_logo_document(database) -> dict | None:
    return await database[APP_BRANDING_COLLECTION_NAME].find_one({"_id": BRANDING_LOGO_ID})


async def public_branding_response(database) -> dict:
    general = (await get_system_settings(database))["general"]
    logo = await database[APP_BRANDING_COLLECTION_NAME].find_one(
        {"_id": BRANDING_LOGO_ID},
        {"updated_at": 1},
    )
    updated_at = logo.get("updated_at") if logo else None
    return {
        "installation_name": general["installation_name"],
        "has_logo": logo is not None,
        "logo_version": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
    }


async def save_branding_logo(database, *, content_type: str, data: bytes, username: str) -> dict:
    now = _utcnow()
    await database[APP_BRANDING_COLLECTION_NAME].update_one(
        {"_id": BRANDING_LOGO_ID},
        {
            "$set": {
                "content_type": content_type,
                "data": data,
                "updated_at": now,
                "updated_by": username,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return await public_branding_response(database)


async def delete_branding_logo(database) -> dict:
    await database[APP_BRANDING_COLLECTION_NAME].delete_one({"_id": BRANDING_LOGO_ID})
    return await public_branding_response(database)


async def update_general_settings(database, payload: GeneralSettingsUpdate, *, username: str) -> dict:
    values = payload.model_dump()
    await database[APP_SETTINGS_COLLECTION].update_one(
        {"_id": APP_SETTINGS_ID},
        {
            "$set": {
                "general": values,
                "updated_at": _utcnow(),
                "updated_by": username,
            },
            "$setOnInsert": {"created_at": _utcnow()},
        },
        upsert=True,
    )
    return await general_settings_response(database)


async def update_monitoring_settings(database, payload: MonitoringSettingsUpdate, *, username: str) -> dict:
    values = payload.model_dump()
    await database[APP_SETTINGS_COLLECTION].update_one(
        {"_id": APP_SETTINGS_ID},
        {
            "$set": {
                "monitoring": values,
                "updated_at": _utcnow(),
                "updated_by": username,
            },
            "$setOnInsert": {"created_at": _utcnow()},
        },
        upsert=True,
    )
    return await monitoring_settings_response(database)


async def update_data_settings(database, payload: DataSettingsUpdate, *, username: str) -> dict:
    values = payload.model_dump()
    await database[APP_SETTINGS_COLLECTION].update_one(
        {"_id": APP_SETTINGS_ID},
        {
            "$set": {
                "data": values,
                "updated_at": _utcnow(),
                "updated_by": username,
            },
            "$setOnInsert": {"created_at": _utcnow()},
        },
        upsert=True,
    )
    return await data_settings_response(database)


async def general_settings_response(database) -> dict:
    values = (await get_system_settings(database))["general"]
    return {
        **values,
        "environment": settings.environment,
        "app_version": settings.app_version,
        "api_docs_enabled": settings.api_docs_enabled,
    }


async def monitoring_settings_response(database) -> dict:
    values = (await get_system_settings(database))["monitoring"]
    status = await database.collector_status.find_one(
        {"_id": "primary"},
        {"_id": 0, "owner_id": 0, "lease_until": 0},
    )
    return {
        **values,
        "telemetry_retention_hours": settings.metrics_retention_hours,
        "collector": status or {"state": "not_started"},
    }


async def _collection_stats(database, collection_name: str) -> dict:
    try:
        result = await database.command({"collStats": collection_name, "scale": 1})
        return {
            "name": collection_name,
            "count": int(result.get("count") or 0),
            "size_bytes": int(result.get("size") or 0),
            "storage_bytes": int(result.get("storageSize") or 0),
            "index_bytes": int(result.get("totalIndexSize") or 0),
        }
    except Exception:
        # A missing optional collection should still be represented cleanly.
        count = await database[collection_name].count_documents({})
        return {
            "name": collection_name,
            "count": int(count),
            "size_bytes": None,
            "storage_bytes": None,
            "index_bytes": None,
        }


DATA_COLLECTIONS = (
    "database_metric_samples",
    "server_metric_samples",
    "analytics_daily_snapshots",
    "database_action_audit",
    "terminal_session_audit",
    "provisioning_runs",
    "email_deliveries",
    "alerts",
    "records",
)


async def data_settings_response(database) -> dict:
    values = (await get_system_settings(database))["data"]
    stats = [await _collection_stats(database, name) for name in DATA_COLLECTIONS]
    return {
        **values,
        "telemetry_retention_hours": settings.metrics_retention_hours,
        "collections": stats,
    }


async def runtime_monitoring_settings(database) -> dict[str, Any]:
    return (await get_system_settings(database))["monitoring"]


async def runtime_data_settings(database) -> dict[str, Any]:
    return (await get_system_settings(database))["data"]


async def run_retention_cleanup(database, data_settings: dict[str, Any] | None = None) -> dict[str, int]:
    data = data_settings or await runtime_data_settings(database)
    now = _utcnow()
    rules = [
        (
            "analytics_daily_snapshots",
            "collected_at",
            int(data["analytics_retention_days"]),
            {},
        ),
        (
            "database_action_audit",
            "started_at",
            int(data["action_audit_retention_days"]),
            {"status": {"$nin": ["running", "queued"]}},
        ),
        (
            "terminal_session_audit",
            "started_at",
            int(data["terminal_audit_retention_days"]),
            {"ended_at": {"$ne": None}},
        ),
        (
            "provisioning_runs",
            "started_at",
            int(data["provisioning_history_retention_days"]),
            {"status": {"$nin": ["running", "queued"]}},
        ),
    ]
    deleted: dict[str, int] = {}
    for collection_name, field_name, days, extra in rules:
        query = {field_name: {"$lt": now - timedelta(days=days)}, **extra}
        result = await database[collection_name].delete_many(query)
        deleted[collection_name] = int(result.deleted_count)
    return deleted


async def _orphaned_analytics_count(database) -> int:
    connection_ids = {str(item["_id"]) for item in await database.database_connections.find({}, {"_id": 1}).to_list(None)}
    server_ids = {str(item["_id"]) for item in await database.servers.find({}, {"_id": 1}).to_list(None)}
    count = 0
    docs = await database.analytics_daily_snapshots.find({}, {"target_type": 1, "target_id": 1}).to_list(None)
    for doc in docs:
        target_id = str(doc.get("target_id") or "")
        if doc.get("target_type") == "database" and target_id not in connection_ids:
            count += 1
        elif doc.get("target_type") == "server" and target_id not in server_ids:
            count += 1
    return count


async def _remove_orphaned_analytics(database) -> int:
    connection_ids = {str(item["_id"]) for item in await database.database_connections.find({}, {"_id": 1}).to_list(None)}
    server_ids = {str(item["_id"]) for item in await database.servers.find({}, {"_id": 1}).to_list(None)}
    deleted = 0
    if connection_ids:
        result = await database.analytics_daily_snapshots.delete_many(
            {"target_type": "database", "target_id": {"$nin": list(connection_ids)}}
        )
    else:
        result = await database.analytics_daily_snapshots.delete_many({"target_type": "database"})
    deleted += int(result.deleted_count)
    if server_ids:
        result = await database.analytics_daily_snapshots.delete_many(
            {"target_type": "server", "target_id": {"$nin": list(server_ids)}}
        )
    else:
        result = await database.analytics_daily_snapshots.delete_many({"target_type": "server"})
    deleted += int(result.deleted_count)
    return deleted


async def _stale_terminal_count(database) -> int:
    cutoff = _utcnow() - timedelta(hours=24)
    return int(await database.terminal_session_audit.count_documents({"ended_at": None, "started_at": {"$lt": cutoff}}))


async def _reconcile_stale_terminals(database) -> int:
    cutoff = _utcnow() - timedelta(hours=24)
    result = await database.terminal_session_audit.update_many(
        {"ended_at": None, "started_at": {"$lt": cutoff}},
        {
            "$set": {
                "ended_at": _utcnow(),
                "status": "stale",
                "close_reason": "Reconciled by DBAChum system maintenance.",
            }
        },
    )
    return int(result.modified_count)


async def maintenance_diagnostics(database) -> dict:
    settings_doc = await get_system_settings(database)
    collector = await database.collector_status.find_one(
        {"_id": "primary"},
        {"_id": 0, "owner_id": 0, "lease_until": 0},
    )
    collections = await database.list_collection_names()
    return {
        "generated_at": _utcnow(),
        "mongodb_ok": True,
        "collection_count": len(collections),
        "collector": collector or {"state": "not_started"},
        "orphaned_analytics": await _orphaned_analytics_count(database),
        "stale_terminal_sessions": await _stale_terminal_count(database),
        "retention": settings_doc["data"],
    }


async def run_system_cleanup(database, payload: CleanupRequest) -> dict:
    result: dict[str, Any] = {
        "retention_deleted": {},
        "orphaned_analytics_deleted": 0,
        "stale_terminal_sessions_reconciled": 0,
    }
    if payload.apply_retention:
        result["retention_deleted"] = await run_retention_cleanup(database)
    if payload.remove_orphaned_analytics:
        result["orphaned_analytics_deleted"] = await _remove_orphaned_analytics(database)
    if payload.reconcile_stale_terminal_sessions:
        result["stale_terminal_sessions_reconciled"] = await _reconcile_stale_terminals(database)
    return result


async def verify_system_indexes(database) -> dict:
    await create_indexes(database)
    return {
        "verified_at": _utcnow(),
        "message": "DBAChum MongoDB indexes verified.",
    }


async def export_system_metadata(database) -> dict:
    def json_safe(value):
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, dict):
            return {key: json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [json_safe(item) for item in value]
        return value

    def clean(document: dict, *, drop: set[str]) -> dict:
        result = {key: value for key, value in document.items() if key not in drop}
        if "_id" in result:
            result["id"] = str(result.pop("_id"))
        return json_safe(result)

    connections = await database.database_connections.find({}).sort("name", 1).to_list(None)
    servers = await database.servers.find({}).sort("name", 1).to_list(None)
    records = await database.records.find({}).sort("name", 1).to_list(None)
    settings_doc = await get_system_settings(database)

    connection_secret_fields = {
        "password_encrypted", "password", "username_encrypted", "credential_encrypted",
        "wallet_password_encrypted", "private_key_encrypted", "secret_encrypted",
    }
    server_secret_fields = {"password", "password_encrypted", "private_key_encrypted", "passphrase_encrypted"}
    record_secret_fields = {"password_encrypted", "lookup_password_encrypted"}

    return {
        "exported_at": _utcnow(),
        "format": "dbachum-metadata-v1",
        "settings": settings_doc,
        "database_connections": [clean(item, drop=connection_secret_fields) for item in connections],
        "servers": [clean(item, drop=server_secret_fields) for item in servers],
        "records": [clean(item, drop=record_secret_fields) for item in records],
    }
