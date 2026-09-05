from pymongo.errors import CollectionInvalid

from app.core.config import settings


METRICS_COLLECTION_NAME = "database_metric_samples"
SERVER_METRICS_COLLECTION_NAME = "server_metric_samples"
ORACLE_SQL_TEXT_COLLECTION_NAME = "oracle_sql_texts"
COLLECTOR_STATUS_COLLECTION_NAME = "collector_status"
ALERTS_COLLECTION_NAME = "alerts"


def telemetry_retention_seconds() -> int:
    return settings.metrics_retention_hours * 60 * 60


async def _ensure_timeseries_collection(
    database,
    name: str,
    *,
    meta_field: str = "meta",
) -> None:
    expire_after_seconds = telemetry_retention_seconds()
    collection_names = await database.list_collection_names()

    if name not in collection_names:
        try:
            await database.create_collection(
                name,
                timeseries={
                    "timeField": "collected_at",
                    "metaField": meta_field,
                    "granularity": "seconds",
                },
                expireAfterSeconds=expire_after_seconds,
            )
        except CollectionInvalid:
            pass

    await database.command(
        {
            "collMod": name,
            "expireAfterSeconds": expire_after_seconds,
        }
    )


async def ensure_metrics_collection(database) -> None:
    await _ensure_timeseries_collection(
        database,
        METRICS_COLLECTION_NAME,
    )


async def ensure_server_metrics_collection(database) -> None:
    await _ensure_timeseries_collection(
        database,
        SERVER_METRICS_COLLECTION_NAME,
    )


async def ensure_telemetry_collections(database) -> None:
    await ensure_metrics_collection(database)
    await ensure_server_metrics_collection(database)

    await database[ORACLE_SQL_TEXT_COLLECTION_NAME].create_index(
        [
            ("connection_id", 1),
            ("sql_id", 1),
            ("child_number", 1),
        ],
        unique=True,
        name="uq_oracle_sql_text_connection_sql_child",
    )
    await database[ORACLE_SQL_TEXT_COLLECTION_NAME].create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="ttl_oracle_sql_text_expires_at",
    )

    await database[COLLECTOR_STATUS_COLLECTION_NAME].create_index(
        "last_heartbeat_at",
        name="ix_collector_status_heartbeat",
    )
