import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pymongo import UpdateOne

from app.connectors.oracle_telemetry import collect_oracle_telemetry
from app.connectors.sqlserver_health import get_sqlserver_health
from app.core.collections import (
    METRICS_COLLECTION_NAME,
    ORACLE_SQL_TEXT_COLLECTION_NAME,
    SERVER_METRICS_COLLECTION_NAME,
    telemetry_retention_seconds,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.services.database_connections import monitored_connections_filter
from app.services.database_overview import collect_database_overview
from app.services.server_monitoring import collect_server_telemetry
from app.services.alerting import evaluate_database_sample, evaluate_server_sample


logger = logging.getLogger(__name__)

TOP_SQL_LIMIT = 10
TOP_SESSION_LIMIT = 10
TOP_WAIT_LIMIT = 5

SYSTEM_STAT_FIELD_MAP = {
    "CPU used by this session": "cpu_centiseconds",
    "execute count": "execute_count",
    "session logical reads": "logical_reads",
    "physical reads": "physical_reads",
    "user commits": "user_commits",
    "user rollbacks": "user_rollbacks",
    "redo size": "redo_bytes",
    "parse count (hard)": "hard_parses",
}

SQL_COUNTER_FIELDS = (
    "cpu_time_us",
    "elapsed_time_us",
    "executions",
    "buffer_gets",
    "disk_reads",
    "rows_processed",
)


@dataclass
class CollectorDeltaState:
    system_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    sql_stats: dict[str, dict[tuple[str, int], dict[str, int]]] = field(default_factory=dict)
    session_cpu: dict[str, dict[tuple[int, int], int]] = field(default_factory=dict)
    wait_stats: dict[str, dict[str, tuple[int, int]]] = field(default_factory=dict)
    last_storage_at: dict[str, datetime] = field(default_factory=dict)
    last_sqlserver_health_at: dict[str, datetime] = field(default_factory=dict)
    sqlserver_health: dict[str, dict] = field(default_factory=dict)
    last_server_at: dict[str, datetime] = field(default_factory=dict)

    def reset_connection(self, connection_id: str) -> None:
        self.system_stats.pop(connection_id, None)
        self.sql_stats.pop(connection_id, None)
        self.session_cpu.pop(connection_id, None)
        self.wait_stats.pop(connection_id, None)
        self.last_sqlserver_health_at.pop(connection_id, None)
        self.sqlserver_health.pop(connection_id, None)

    def storage_due(self, connection_id: str, now: datetime) -> bool:
        previous = self.last_storage_at.get(connection_id)
        if previous is None:
            return True
        return (
            now - previous
        ).total_seconds() >= settings.oracle_storage_interval_seconds

    def sqlserver_health_due(self, connection_id: str, now: datetime) -> bool:
        previous = self.last_sqlserver_health_at.get(connection_id)
        if previous is None:
            return True
        return (
            now - previous
        ).total_seconds() >= settings.sqlserver_health_interval_seconds

    def server_due(self, server_id: str, now: datetime) -> bool:
        previous = self.last_server_at.get(server_id)
        if previous is None:
            return True
        return (
            now - previous
        ).total_seconds() >= settings.server_metrics_interval_seconds


@dataclass
class CollectionBatchResult:
    target_count: int = 0
    inserted_count: int = 0
    online_count: int = 0
    failed_count: int = 0
    performed: bool = True


@dataclass
class CollectorCycleResult:
    database: CollectionBatchResult
    server: CollectionBatchResult

    @property
    def inserted_count(self) -> int:
        return self.database.inserted_count + self.server.inserted_count


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _counter_delta(current: int, previous: int | None) -> int | None:
    if previous is None or current < previous:
        return None
    return current - previous


def build_metric_sample(overview: dict) -> dict:
    return {
        "meta": {
            "connection_id": overview["connection_id"],
            "engine": overview["engine"],
        },
        "collected_at": overview.get("collected_at") or _utcnow(),
        "checked_at": overview.get("checked_at") or overview.get("collected_at"),
        "status": overview.get("status", "unreachable"),
        "response_time_ms": overview.get("response_time_ms"),
        "active": overview.get("active"),
        "connections": overview.get("connections"),
        "blocked": overview.get("blocked"),
        "uptime_seconds": overview.get("uptime_seconds"),
        "warnings": overview.get("warnings", []),
        "error": overview.get("error"),
    }


def _system_deltas(
    state: CollectorDeltaState,
    connection_id: str,
    current_stats: dict[str, int],
) -> dict[str, int | float | None]:
    previous_stats = state.system_stats.get(connection_id, {})
    result: dict[str, int | float | None] = {}

    for oracle_name, field_name in SYSTEM_STAT_FIELD_MAP.items():
        current = int(current_stats.get(oracle_name, 0))
        previous = previous_stats.get(oracle_name)
        delta = _counter_delta(current, previous)
        result[field_name] = delta

    cpu_centiseconds = result.get("cpu_centiseconds")
    result["cpu_time_seconds"] = (
        round(float(cpu_centiseconds) / 100.0, 3)
        if cpu_centiseconds is not None
        else None
    )

    state.system_stats[connection_id] = {
        name: int(value)
        for name, value in current_stats.items()
    }
    return result


def _sql_deltas(
    state: CollectorDeltaState,
    connection_id: str,
    candidates: list[dict],
) -> tuple[list[dict], list[dict]]:
    previous = state.sql_stats.get(connection_id, {})
    next_state: dict[tuple[str, int], dict[str, int]] = {}
    ranked: list[dict] = []
    sql_texts: list[dict] = []

    for item in candidates:
        sql_id = item.get("sql_id")
        if not sql_id:
            continue
        child_number = int(item.get("child_number") or 0)
        key = (str(sql_id), child_number)
        previous_counters = previous.get(key, {})
        current_counters = {
            name: int(item.get(name) or 0)
            for name in SQL_COUNTER_FIELDS
        }
        next_state[key] = current_counters

        output = {
            "sql_id": str(sql_id),
            "child_number": child_number,
            "plan_hash_value": int(item.get("plan_hash_value") or 0),
            "parsing_schema_name": item.get("parsing_schema_name"),
            "module": item.get("module"),
            "last_active_time": item.get("last_active_time"),
            "baseline": key not in previous,
        }
        for name, current in current_counters.items():
            output[f"delta_{name}"] = _counter_delta(
                current,
                previous_counters.get(name),
            )
        ranked.append(output)

        sql_text = item.get("sql_text")
        if sql_text:
            sql_texts.append(
                {
                    "sql_id": str(sql_id),
                    "child_number": child_number,
                    "sql_text": str(sql_text),
                    "parsing_schema_name": item.get("parsing_schema_name"),
                    "module": item.get("module"),
                }
            )

    state.sql_stats[connection_id] = next_state

    def rank_key(item: dict):
        cpu = item.get("delta_cpu_time_us")
        elapsed = item.get("delta_elapsed_time_us")
        return (
            -1 if cpu is None else int(cpu),
            -1 if elapsed is None else int(elapsed),
        )

    ranked.sort(key=rank_key, reverse=True)
    return ranked[:TOP_SQL_LIMIT], sql_texts


def _session_deltas(
    state: CollectorDeltaState,
    connection_id: str,
    candidates: list[dict],
) -> list[dict]:
    previous = state.session_cpu.get(connection_id, {})
    next_state: dict[tuple[int, int], int] = {}
    ranked: list[dict] = []

    for item in candidates:
        key = (
            int(item.get("sid") or 0),
            int(item.get("serial_number") or 0),
        )
        current = int(item.get("cpu_centiseconds") or 0)
        next_state[key] = current
        delta_cs = _counter_delta(current, previous.get(key))
        ranked.append(
            {
                "sid": key[0],
                "serial_number": key[1],
                "username": item.get("username"),
                "sql_id": item.get("sql_id"),
                "status": item.get("status"),
                "module": item.get("module"),
                "machine": item.get("machine"),
                "event": item.get("event"),
                "wait_class": item.get("wait_class"),
                "active_seconds": item.get("active_seconds"),
                "blocking_session": item.get("blocking_session"),
                "cpu_time_seconds": (
                    round(delta_cs / 100.0, 3)
                    if delta_cs is not None
                    else None
                ),
                "baseline": key not in previous,
            }
        )

    state.session_cpu[connection_id] = next_state
    ranked.sort(
        key=lambda item: (
            -1
            if item["cpu_time_seconds"] is None
            else float(item["cpu_time_seconds"]),
            int(item.get("active_seconds") or 0),
        ),
        reverse=True,
    )
    return ranked[:TOP_SESSION_LIMIT]


def _wait_deltas(
    state: CollectorDeltaState,
    connection_id: str,
    waits: list[dict],
) -> list[dict]:
    previous = state.wait_stats.get(connection_id, {})
    next_state: dict[str, tuple[int, int]] = {}
    ranked: list[dict] = []

    for item in waits:
        event = str(item.get("event") or "Unknown")
        total_waits = int(item.get("total_waits") or 0)
        time_waited_cs = int(item.get("time_waited_centiseconds") or 0)
        next_state[event] = (total_waits, time_waited_cs)
        previous_value = previous.get(event)
        delta_waits = _counter_delta(
            total_waits,
            previous_value[0] if previous_value else None,
        )
        delta_time_cs = _counter_delta(
            time_waited_cs,
            previous_value[1] if previous_value else None,
        )
        ranked.append(
            {
                "event": event,
                "waits": delta_waits,
                "wait_time_seconds": (
                    round(delta_time_cs / 100.0, 3)
                    if delta_time_cs is not None
                    else None
                ),
                "baseline": previous_value is None,
            }
        )

    state.wait_stats[connection_id] = next_state
    ranked.sort(
        key=lambda item: -1
        if item["wait_time_seconds"] is None
        else float(item["wait_time_seconds"]),
        reverse=True,
    )
    return ranked[:TOP_WAIT_LIMIT]


async def _cache_sql_texts(database, connection_id: str, items: list[dict]) -> None:
    if not items:
        return

    now = _utcnow()
    expires_at = now + timedelta(seconds=telemetry_retention_seconds())
    operations = []
    for item in items:
        operations.append(
            UpdateOne(
                {
                    "connection_id": connection_id,
                    "sql_id": item["sql_id"],
                    "child_number": item["child_number"],
                },
                {
                    "$set": {
                        "sql_text": item["sql_text"],
                        "parsing_schema_name": item.get("parsing_schema_name"),
                        "module": item.get("module"),
                        "last_seen_at": now,
                        "expires_at": expires_at,
                    },
                    "$setOnInsert": {
                        "first_seen_at": now,
                    },
                },
                upsert=True,
            )
        )

    try:
        await database[ORACLE_SQL_TEXT_COLLECTION_NAME].bulk_write(
            operations,
            ordered=False,
        )
    except Exception:
        logger.exception(
            "Oracle SQL text cache update failed connection_id=%s",
            connection_id,
        )


def _compact_sqlserver_health(health: dict) -> dict:
    database = health.get("database") or {}
    log = health.get("transaction_log") or {}
    workload = health.get("workload") or {}
    tempdb = health.get("tempdb") or {}
    agent = health.get("agent") or {}
    failed_jobs = [
        {
            "name": item.get("name"),
            "status": item.get("last_status"),
            "last_run_at": (
                item.get("last_run_at").isoformat()
                if hasattr(item.get("last_run_at"), "isoformat")
                else item.get("last_run_at")
            ),
        }
        for item in (agent.get("jobs") or [])
        if item.get("enabled")
        and item.get("last_status") in {"failed", "canceled"}
    ][:10]

    return {
        "health_checked_at": health.get("checked_at"),
        "database_name": health.get("database_name"),
        "generation": health.get("generation"),
        "database_state": database.get("state"),
        "recovery_model": database.get("recovery_model"),
        "log_reuse_wait": database.get("log_reuse_wait"),
        "log_size_bytes": log.get("size_bytes"),
        "log_used_bytes": log.get("used_bytes"),
        "log_used_percent": log.get("used_percent"),
        "active": workload.get("active"),
        "blocked": workload.get("blocked"),
        "long_running": workload.get("long_running"),
        "longest_request_ms": workload.get("longest_request_ms"),
        "long_running_threshold_seconds": workload.get("long_running_threshold_seconds"),
        "tempdb_allocated_bytes": tempdb.get("allocated_bytes"),
        "tempdb_used_bytes": tempdb.get("used_bytes"),
        "tempdb_used_percent": tempdb.get("used_percent"),
        "agent_available": agent.get("available"),
        "agent_enabled_jobs": agent.get("enabled_jobs"),
        "agent_failed_jobs": agent.get("failed_jobs"),
        "agent_running_jobs": agent.get("running_jobs"),
        "failed_jobs": failed_jobs,
        "warnings": health.get("warnings") or [],
    }


async def _collect_database_sample(
    database,
    connection: dict,
    state: CollectorDeltaState,
) -> dict:
    connection_id = str(connection["_id"])
    engine = connection["engine"]

    if engine == "sqlserver":
        overview = await collect_database_overview(connection)
        sample = build_metric_sample(overview)
        if overview.get("status") == "unreachable":
            state.reset_connection(connection_id)
            return sample

        now = _utcnow()
        if state.sqlserver_health_due(connection_id, now):
            try:
                health = await get_sqlserver_health(connection)
                compact = _compact_sqlserver_health(health)
                state.sqlserver_health[connection_id] = compact
                state.last_sqlserver_health_at[connection_id] = now
            except Exception as exc:
                logger.warning(
                    "SQL Server operational telemetry unavailable connection_id=%s: %s",
                    connection_id,
                    exc,
                )
                # Availability is already proven by Overview. Do not turn a
                # permission/secondary telemetry problem into a false outage.
                sample["warnings"].append(
                    "SQL Server operational health snapshot unavailable."
                )

        if connection_id in state.sqlserver_health:
            sample["sqlserver"] = state.sqlserver_health[connection_id]
        return sample

    if engine != "oracle":
        overview = await collect_database_overview(connection)
        return build_metric_sample(overview)

    now = _utcnow()
    include_storage = state.storage_due(connection_id, now)
    telemetry = await collect_oracle_telemetry(
        connection,
        include_storage=include_storage,
    )
    if include_storage:
        state.last_storage_at[connection_id] = now

    sample = build_metric_sample(
        {
            "connection_id": connection_id,
            "engine": engine,
            **telemetry,
            "checked_at": telemetry.get("collected_at"),
        }
    )

    if telemetry.get("status") == "unreachable":
        # Do not calculate a recovery sample against stale counters from before
        # an outage. The first healthy sample after a gap becomes a baseline.
        state.reset_connection(connection_id)
        return sample

    system_deltas = _system_deltas(
        state,
        connection_id,
        telemetry.get("system_stats", {}),
    )
    top_sql, sql_texts = _sql_deltas(
        state,
        connection_id,
        telemetry.get("sql_candidates", []),
    )
    top_sessions = _session_deltas(
        state,
        connection_id,
        telemetry.get("session_candidates", []),
    )
    top_waits = _wait_deltas(
        state,
        connection_id,
        telemetry.get("system_waits", []),
    )

    sample["oracle"] = {
        "database_name": telemetry.get("database_name"),
        "service_name": telemetry.get("service_name"),
        "instance_name": telemetry.get("instance_name"),
        "version": telemetry.get("version"),
        "system_deltas": system_deltas,
        "top_sql": top_sql,
        "top_sessions": top_sessions,
        "top_waits": top_waits,
    }
    if telemetry.get("storage") is not None:
        sample["oracle"]["storage"] = telemetry["storage"]

    await _cache_sql_texts(database, connection_id, sql_texts)
    return sample


def _sqlserver_instance_key(connection: dict) -> str:
    host = str(connection.get("host") or "").strip().lower()
    port = int(connection.get("port") or 1433)
    return f"{host}:{port}"


def _sqlserver_instance_alert_owners(
    connections: list[dict],
    samples: list[dict] | None = None,
) -> set[str]:
    """Pick one deterministic healthy DB connection per SQL Server instance.

    tempdb and SQL Agent belong to the SQL Server instance, not an individual
    database. Prefer the first healthy monitored connection for each host:port;
    if every connection is unavailable, fall back to the first one so existing
    instance alerts can still transition predictably.
    """
    samples = samples or []
    owners: dict[str, tuple[str, bool]] = {}
    for index, connection in enumerate(connections):
        if connection.get("engine") != "sqlserver":
            continue
        instance_key = _sqlserver_instance_key(connection)
        sample = samples[index] if index < len(samples) else {}
        healthy = str(sample.get("status") or "") in {"online", "limited"}
        current = owners.get(instance_key)
        if current is None or (healthy and not current[1]):
            owners[instance_key] = (str(connection["_id"]), healthy)
    return {owner_id for owner_id, _healthy in owners.values()}


async def collect_database_metrics_once(
    database,
    state: CollectorDeltaState,
) -> CollectionBatchResult:
    cursor = (
        database.database_connections
        .find(monitored_connections_filter())
        .sort("name", 1)
    )
    connections = await cursor.to_list(None)
    result = CollectionBatchResult(target_count=len(connections))
    if not connections:
        return result

    semaphore = asyncio.Semaphore(settings.metrics_collector_concurrency)

    async def collect_one(connection: dict) -> dict:
        connection_id = str(connection.get("_id", "unknown"))
        try:
            async with semaphore:
                return await asyncio.wait_for(
                    _collect_database_sample(database, connection, state),
                    timeout=settings.metrics_target_timeout_seconds,
                )
        except asyncio.TimeoutError:
            state.reset_connection(connection_id)
            logger.warning(
                "Database telemetry timed out connection_id=%s engine=%s",
                connection_id,
                connection.get("engine"),
            )
            return build_metric_sample(
                {
                    "connection_id": connection_id,
                    "engine": connection.get("engine", "oracle"),
                    "status": "unreachable",
                    "warnings": [],
                    "error": (
                        "Telemetry collection timed out after "
                        f"{settings.metrics_target_timeout_seconds} seconds."
                    ),
                }
            )
        except Exception as exc:
            state.reset_connection(connection_id)
            logger.exception(
                "Database telemetry failed connection_id=%s engine=%s",
                connection_id,
                connection.get("engine"),
            )
            return build_metric_sample(
                {
                    "connection_id": connection_id,
                    "engine": connection.get("engine", "oracle"),
                    "status": "unreachable",
                    "warnings": [],
                    "error": str(exc).strip() or exc.__class__.__name__,
                }
            )

    samples = await asyncio.gather(
        *[collect_one(connection) for connection in connections]
    )
    if samples:
        insert_result = await database[METRICS_COLLECTION_NAME].insert_many(samples)
        result.inserted_count = len(insert_result.inserted_ids)

        sqlserver_instance_owners = _sqlserver_instance_alert_owners(connections, samples)
        alert_results = await asyncio.gather(
            *(
                evaluate_database_sample(
                    database,
                    connection,
                    sample,
                    include_sqlserver_instance_alerts=(
                        connection.get("engine") != "sqlserver"
                        or str(connection["_id"]) in sqlserver_instance_owners
                    ),
                )
                for connection, sample in zip(connections, samples)
            ),
            return_exceptions=True,
        )
        for connection, alert_result in zip(connections, alert_results):
            if isinstance(alert_result, Exception):
                logger.error(
                    "Database alert evaluation failed connection_id=%s: %s",
                    connection.get("_id"),
                    alert_result,
                )

    result.online_count = sum(
        1 for sample in samples if sample.get("status") in {"online", "limited"}
    )
    result.failed_count = result.target_count - result.online_count
    return result


def _build_server_sample(server: dict, telemetry: dict) -> dict:
    return {
        "meta": {
            "server_id": str(server["_id"]),
            "os_family": server.get("os_family"),
        },
        "collected_at": telemetry.get("checked_at") or _utcnow(),
        "status": telemetry.get("status", "unreachable"),
        "ssh_latency_ms": telemetry.get("ssh_latency_ms"),
        "uptime_seconds": telemetry.get("uptime_seconds"),
        "load_1": telemetry.get("load_1"),
        "load_5": telemetry.get("load_5"),
        "load_15": telemetry.get("load_15"),
        "cpu_used_percent": telemetry.get("cpu_used_percent"),
        "memory": telemetry.get("memory") or {},
        "filesystems": telemetry.get("filesystems") or [],
        "warnings": telemetry.get("warnings") or [],
        "error": telemetry.get("error"),
    }


async def collect_server_metrics_once(
    database,
    state: CollectorDeltaState,
) -> CollectionBatchResult:
    now = _utcnow()
    cursor = database.servers.find(
        {
            "enabled": {"$ne": False},
            "ssh_profile_id": {"$exists": True, "$nin": [None, ""]},
            "os_family": {"$in": ["linux", "aix", "unix"]},
        }
    ).sort("name", 1)
    servers = await cursor.to_list(None)
    due_servers = [
        server
        for server in servers
        if state.server_due(str(server["_id"]), now)
    ]
    result = CollectionBatchResult(
        target_count=len(due_servers),
        performed=bool(due_servers),
    )
    if not due_servers:
        return result

    semaphore = asyncio.Semaphore(settings.metrics_collector_concurrency)

    async def collect_one(server: dict) -> dict:
        server_id = str(server["_id"])
        state.last_server_at[server_id] = now
        try:
            async with semaphore:
                telemetry = await asyncio.wait_for(
                    collect_server_telemetry(database, server_id),
                    timeout=settings.metrics_target_timeout_seconds,
                )
            return _build_server_sample(server, telemetry)
        except asyncio.TimeoutError:
            return _build_server_sample(
                server,
                {
                    "status": "unreachable",
                    "error": (
                        "SSH telemetry timed out after "
                        f"{settings.metrics_target_timeout_seconds} seconds."
                    ),
                },
            )
        except AppError as exc:
            return _build_server_sample(
                server,
                {
                    "status": "unreachable",
                    "error": exc.message,
                },
            )
        except Exception as exc:
            logger.exception("Server telemetry failed server_id=%s", server_id)
            return _build_server_sample(
                server,
                {
                    "status": "unreachable",
                    "error": str(exc).strip() or exc.__class__.__name__,
                },
            )

    samples = await asyncio.gather(
        *[collect_one(server) for server in due_servers]
    )
    if samples:
        insert_result = await database[SERVER_METRICS_COLLECTION_NAME].insert_many(samples)
        result.inserted_count = len(insert_result.inserted_ids)

        alert_results = await asyncio.gather(
            *(
                evaluate_server_sample(database, server, sample)
                for server, sample in zip(due_servers, samples)
            ),
            return_exceptions=True,
        )
        for server, alert_result in zip(due_servers, alert_results):
            if isinstance(alert_result, Exception):
                logger.error(
                    "Server alert evaluation failed server_id=%s: %s",
                    server.get("_id"),
                    alert_result,
                )

    result.online_count = sum(
        1 for sample in samples if sample.get("status") in {"online", "limited"}
    )
    result.failed_count = result.target_count - result.online_count
    return result


async def collect_collector_cycle(
    database,
    state: CollectorDeltaState,
) -> CollectorCycleResult:
    database_result = await collect_database_metrics_once(database, state)
    server_result = await collect_server_metrics_once(database, state)
    return CollectorCycleResult(
        database=database_result,
        server=server_result,
    )


# Backward-compatible helper retained for the existing one-shot utility/tests.
async def collect_metrics_once(database) -> int:
    state = CollectorDeltaState()
    result = await collect_database_metrics_once(database, state)
    return result.inserted_count


async def run_metrics_collector(database) -> None:
    state = CollectorDeltaState()
    interval = settings.metrics_collector_interval_seconds
    logger.info("Metrics collector started interval_seconds=%s", interval)
    while True:
        try:
            await collect_collector_cycle(database, state)
        except asyncio.CancelledError:
            logger.info("Metrics collector stopped")
            raise
        except Exception:
            logger.exception("Metrics collector cycle failed")
        await asyncio.sleep(interval)
