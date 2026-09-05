from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.core.collections import ALERTS_COLLECTION_NAME, COLLECTOR_STATUS_COLLECTION_NAME
from app.core.config import settings
from app.core.exceptions import AppError
from app.services.email_delivery import (
    enqueue_alert_email_deliveries,
    should_enqueue_alert_email,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertCondition:
    rule_key: str
    active: bool | None
    severity: str
    title: str
    message: str
    required_samples: int = 3
    recovery_samples: int = 2
    current_value: float | int | str | None = None
    threshold: float | int | str | None = None
    context: dict[str, Any] | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _percent_severity(value: float, warning: float, critical: float) -> str:
    return "critical" if value >= critical else "warning"


def _sqlserver_instance_key(connection: dict) -> str:
    host = str(connection.get("host") or "").strip().lower()
    port = int(connection.get("port") or 1433)
    return f"{host}:{port}"


def _mysql_instance_key(connection: dict) -> str:
    host = str(connection.get("host") or "").strip().lower()
    port = int(connection.get("port") or 3306)
    return f"{host}:{port}"


def database_alert_conditions(
    connection: dict,
    sample: dict,
    *,
    include_sqlserver_instance_conditions: bool = True,
    include_mysql_instance_conditions: bool = True,
) -> list[AlertCondition]:
    name = str(connection.get("name") or connection.get("database") or connection.get("_id"))
    status = str(sample.get("status") or "unreachable")
    healthy = status in {"online", "limited"}
    engine = connection.get("engine")
    sqlserver = (sample.get("sqlserver") or {}) if engine == "sqlserver" else {}
    mysql = (sample.get("mysql") or {}) if engine == "mysql" else {}
    conditions: list[AlertCondition] = [
        AlertCondition(
            rule_key="availability",
            active=not healthy,
            severity="critical",
            title=f"{name} is unreachable",
            message=sample.get("error") or "The database collector could not reach this database.",
            required_samples=2,
            recovery_samples=2,
            current_value=status,
            threshold="online/limited",
        )
    ]

    if engine == "sqlserver":
        blocked = sqlserver.get("blocked")
    elif engine == "mysql":
        blocked = mysql.get("blocked_transactions", sample.get("blocked"))
    else:
        blocked = sample.get("blocked")

    include_blocking = not (
        engine == "mysql" and not include_mysql_instance_conditions
    )
    blocked_value = int(blocked) if blocked is not None else None
    conditions.append(
        AlertCondition(
            rule_key="blocking_sessions",
            active=(
                (blocked_value > 0) if healthy and blocked_value is not None else None
            ) if include_blocking else False,
            severity="critical" if blocked_value is not None and blocked_value >= 5 else "warning",
            title=(
                f"Blocked InnoDB transactions on {name}"
                if engine == "mysql"
                else f"Blocking sessions on {name}"
            ),
            message=(
                f"{blocked_value} blocked InnoDB transaction(s) were observed."
                if engine == "mysql" and blocked_value is not None
                else f"{blocked_value} blocked session(s) were observed."
                if blocked_value is not None
                else "Blocking telemetry is unavailable."
            ),
            required_samples=2,
            recovery_samples=2,
            current_value=blocked_value,
            threshold=1,
            context=(
                {
                    "instance_scope": True,
                    "instance_key": _mysql_instance_key(connection),
                    "deduplicated": not include_mysql_instance_conditions,
                }
                if engine == "mysql"
                else None
            ),
        )
    )

    if engine == "sqlserver":
        active_sessions = sqlserver.get("active")
    elif engine == "mysql":
        active_sessions = mysql.get("threads_running", sample.get("active"))
    else:
        active_sessions = sample.get("active")
    active_warning = settings.alert_active_sessions_warning
    active_critical = settings.alert_active_sessions_critical
    active_enabled = active_warning > 0 and active_critical >= active_warning
    if active_enabled:
        active_count = int(active_sessions) if active_sessions is not None else None
        severity = (
            "critical"
            if active_count is not None and active_count >= active_critical
            else "warning"
        )
        conditions.append(
            AlertCondition(
                rule_key="active_sessions",
                active=(
                    (active_count >= active_warning)
                    if healthy and active_count is not None
                    else None
                ) if not (engine == "mysql" and not include_mysql_instance_conditions) else False,
                severity=severity,
                title=(
                    f"High running threads on {name}"
                    if engine == "mysql"
                    else f"High active sessions on {name}"
                ),
                message=(
                    f"{active_count} running thread(s) were observed."
                    if engine == "mysql" and active_count is not None
                    else f"{active_count} active session(s) were observed."
                    if active_count is not None
                    else "Active-workload telemetry is unavailable."
                ),
                required_samples=3,
                recovery_samples=2,
                current_value=active_count,
                threshold=active_warning,
                context={
                    "critical_threshold": active_critical,
                    **(
                        {
                            "instance_scope": True,
                            "instance_key": _mysql_instance_key(connection),
                            "deduplicated": not include_mysql_instance_conditions,
                        }
                        if engine == "mysql"
                        else {}
                    ),
                },
            )
        )

    if engine == "sqlserver":
        database_state = sqlserver.get("database_state")
        normalized_state = (
            str(database_state).strip().upper()
            if database_state is not None
            else None
        )
        conditions.append(
            AlertCondition(
                rule_key="sqlserver:database_state",
                active=(normalized_state != "ONLINE") if healthy and normalized_state else None,
                severity="critical",
                title=f"SQL Server database state on {name}",
                message=(
                    f"Database state is {normalized_state}."
                    if normalized_state
                    else "Database-state telemetry is unavailable."
                ),
                required_samples=1,
                recovery_samples=2,
                current_value=normalized_state,
                threshold="ONLINE",
                context={
                    "recovery_model": sqlserver.get("recovery_model"),
                    "log_reuse_wait": sqlserver.get("log_reuse_wait"),
                },
            )
        )

        log_used = sqlserver.get("log_used_percent")
        log_value = float(log_used) if log_used is not None else None
        if log_value is None:
            log_active = None
            log_severity = "warning"
        else:
            log_active = log_value >= settings.alert_sqlserver_log_warning_percent
            log_severity = _percent_severity(
                log_value,
                settings.alert_sqlserver_log_warning_percent,
                settings.alert_sqlserver_log_critical_percent,
            )
        conditions.append(
            AlertCondition(
                rule_key="sqlserver:transaction_log",
                active=log_active if healthy else None,
                severity=log_severity,
                title=f"Transaction log pressure on {name}",
                message=(
                    f"Transaction log is {log_value:.1f}% used."
                    if log_value is not None
                    else "Transaction-log usage telemetry is unavailable."
                ),
                required_samples=1 if log_severity == "critical" else 2,
                recovery_samples=2,
                current_value=log_value,
                threshold=settings.alert_sqlserver_log_warning_percent,
                context={
                    "critical_threshold": settings.alert_sqlserver_log_critical_percent,
                    "log_reuse_wait": sqlserver.get("log_reuse_wait"),
                    "log_size_bytes": sqlserver.get("log_size_bytes"),
                },
            )
        )

        tempdb_used = sqlserver.get("tempdb_used_percent")
        tempdb_value = float(tempdb_used) if tempdb_used is not None else None
        if tempdb_value is None:
            tempdb_active = None
            tempdb_severity = "warning"
        else:
            tempdb_active = tempdb_value >= settings.alert_sqlserver_tempdb_warning_percent
            tempdb_severity = _percent_severity(
                tempdb_value,
                settings.alert_sqlserver_tempdb_warning_percent,
                settings.alert_sqlserver_tempdb_critical_percent,
            )
        conditions.append(
            AlertCondition(
                rule_key="sqlserver:tempdb",
                active=(
                    tempdb_active if healthy else None
                ) if include_sqlserver_instance_conditions else False,
                severity=tempdb_severity,
                title=f"tempdb pressure on {name}",
                message=(
                    f"tempdb data files are {tempdb_value:.1f}% used."
                    if tempdb_value is not None
                    else "tempdb usage telemetry is unavailable."
                ),
                required_samples=1 if tempdb_severity == "critical" else 3,
                recovery_samples=2,
                current_value=tempdb_value,
                threshold=settings.alert_sqlserver_tempdb_warning_percent,
                context={
                    "critical_threshold": settings.alert_sqlserver_tempdb_critical_percent,
                    "allocated_bytes": sqlserver.get("tempdb_allocated_bytes"),
                    "instance_scope": True,
                    "instance_key": _sqlserver_instance_key(connection),
                    "deduplicated": not include_sqlserver_instance_conditions,
                },
            )
        )

        agent_available = sqlserver.get("agent_available")
        failed_jobs = sqlserver.get("agent_failed_jobs")
        failed_count = int(failed_jobs) if failed_jobs is not None else None
        conditions.append(
            AlertCondition(
                rule_key="sqlserver:agent_failures",
                active=(
                    (failed_count > 0)
                    if healthy and agent_available is True and failed_count is not None
                    else None
                ) if include_sqlserver_instance_conditions else False,
                severity="critical" if failed_count is not None and failed_count >= 3 else "warning",
                title=f"SQL Agent job failures on {name}",
                message=(
                    f"{failed_count} enabled SQL Agent job(s) have a failed/canceled latest outcome."
                    if failed_count is not None
                    else "SQL Agent job telemetry is unavailable."
                ),
                required_samples=1,
                recovery_samples=1,
                current_value=failed_count,
                threshold=0,
                context={
                    "failed_jobs": sqlserver.get("failed_jobs") or [],
                    "instance_scope": True,
                    "instance_key": _sqlserver_instance_key(connection),
                    "deduplicated": not include_sqlserver_instance_conditions,
                },
            )
        )

        long_threshold = settings.alert_sqlserver_long_running_seconds
        if long_threshold > 0:
            longest_ms = sqlserver.get("longest_request_ms")
            longest_seconds = (
                float(longest_ms) / 1000
                if longest_ms is not None
                else None
            )
            conditions.append(
                AlertCondition(
                    rule_key="sqlserver:long_running",
                    active=(longest_seconds >= long_threshold) if healthy and longest_seconds is not None else None,
                    severity="warning",
                    title=f"Long-running SQL Server request on {name}",
                    message=(
                        f"Longest active request is {longest_seconds:.0f}s."
                        if longest_seconds is not None
                        else "Long-running-request telemetry is unavailable."
                    ),
                    required_samples=2,
                    recovery_samples=2,
                    current_value=longest_seconds,
                    threshold=long_threshold,
                )
            )

    if engine == "mysql":
        connection_used = mysql.get("connection_utilization_percent")
        connection_value = (
            float(connection_used)
            if connection_used is not None
            else None
        )
        if connection_value is None:
            connection_active = None
            connection_severity = "warning"
        else:
            connection_active = (
                connection_value >= settings.alert_mysql_connection_warning_percent
            )
            connection_severity = _percent_severity(
                connection_value,
                settings.alert_mysql_connection_warning_percent,
                settings.alert_mysql_connection_critical_percent,
            )
        conditions.append(
            AlertCondition(
                rule_key="mysql:connection_utilization",
                active=(
                    connection_active if healthy else None
                ) if include_mysql_instance_conditions else False,
                severity=connection_severity,
                title=f"MySQL/MariaDB connection pressure on {name}",
                message=(
                    f"Connections are {connection_value:.1f}% of max_connections."
                    if connection_value is not None
                    else "Connection-utilization telemetry is unavailable."
                ),
                required_samples=1 if connection_severity == "critical" else 2,
                recovery_samples=2,
                current_value=connection_value,
                threshold=settings.alert_mysql_connection_warning_percent,
                context={
                    "critical_threshold": settings.alert_mysql_connection_critical_percent,
                    "current_connections": mysql.get("connections_current"),
                    "max_connections": mysql.get("connections_maximum"),
                    "instance_scope": True,
                    "instance_key": _mysql_instance_key(connection),
                    "deduplicated": not include_mysql_instance_conditions,
                },
            )
        )

        long_threshold = settings.alert_mysql_long_running_seconds
        if long_threshold > 0:
            longest_seconds = mysql.get("longest_active_seconds")
            longest_value = (
                float(longest_seconds)
                if longest_seconds is not None
                else None
            )
            conditions.append(
                AlertCondition(
                    rule_key="mysql:long_running",
                    active=(
                        longest_value >= long_threshold
                        if healthy and longest_value is not None
                        else None
                    ),
                    severity="warning",
                    title=f"Long-running MySQL/MariaDB workload on {name}",
                    message=(
                        f"Longest active session is {longest_value:.0f}s."
                        if longest_value is not None
                        else "Long-running-session telemetry is unavailable."
                    ),
                    required_samples=2,
                    recovery_samples=2,
                    current_value=longest_value,
                    threshold=long_threshold,
                    context={
                        "long_running_sessions": mysql.get("long_running_sessions"),
                        "processlist_source": mysql.get("processlist_source"),
                    },
                )
            )

    oracle = sample.get("oracle") or {}
    storage = oracle.get("storage")
    if storage is not None:
        for tablespace in storage.get("tablespaces") or []:
            used = tablespace.get("used_percent")
            ts_name = str(tablespace.get("name") or "UNKNOWN")
            if used is None:
                active = None
                severity = "warning"
            else:
                used = float(used)
                active = used >= settings.alert_tablespace_warning_percent
                severity = _percent_severity(
                    used,
                    settings.alert_tablespace_warning_percent,
                    settings.alert_tablespace_critical_percent,
                )
            conditions.append(
                AlertCondition(
                    rule_key=f"tablespace:{ts_name}",
                    active=active,
                    severity=severity,
                    title=f"Tablespace {ts_name} pressure on {name}",
                    message=(
                        f"Tablespace {ts_name} is {used:.1f}% used."
                        if used is not None
                        else f"Tablespace {ts_name} usage is unavailable."
                    ),
                    required_samples=1 if severity == "critical" else 2,
                    recovery_samples=2,
                    current_value=used,
                    threshold=settings.alert_tablespace_warning_percent,
                    context={
                        "tablespace": ts_name,
                        "critical_threshold": settings.alert_tablespace_critical_percent,
                    },
                )
            )

        fra = storage.get("fra")
        if fra:
            used = fra.get("used_percent")
            if used is None:
                active = None
                severity = "warning"
            else:
                used = float(used)
                active = used >= settings.alert_fra_warning_percent
                severity = _percent_severity(
                    used,
                    settings.alert_fra_warning_percent,
                    settings.alert_fra_critical_percent,
                )
            conditions.append(
                AlertCondition(
                    rule_key="fra_usage",
                    active=active,
                    severity=severity,
                    title=f"FRA pressure on {name}",
                    message=(
                        f"Fast Recovery Area is {used:.1f}% used."
                        if used is not None
                        else "Fast Recovery Area usage is unavailable."
                    ),
                    required_samples=1 if severity == "critical" else 2,
                    recovery_samples=2,
                    current_value=used,
                    threshold=settings.alert_fra_warning_percent,
                    context={
                        "destination": fra.get("destination"),
                        "critical_threshold": settings.alert_fra_critical_percent,
                    },
                )
            )

    return conditions


def server_alert_conditions(server: dict, sample: dict) -> list[AlertCondition]:
    name = str(server.get("name") or server.get("hostname") or server.get("_id"))
    status = str(sample.get("status") or "unreachable")
    healthy = status in {"online", "limited"}
    conditions: list[AlertCondition] = [
        AlertCondition(
            rule_key="availability",
            active=not healthy,
            severity="critical",
            title=f"{name} is unreachable over SSH",
            message=sample.get("error") or "The server collector could not reach this host over SSH.",
            required_samples=2,
            recovery_samples=2,
            current_value=status,
            threshold="online/limited",
        )
    ]

    cpu = sample.get("cpu_used_percent")
    cpu_value = float(cpu) if cpu is not None else None
    conditions.append(
        AlertCondition(
            rule_key="cpu_pressure",
            active=(cpu_value >= settings.alert_server_cpu_warning_percent) if healthy and cpu_value is not None else None,
            severity=(
                "critical"
                if cpu_value is not None and cpu_value >= settings.alert_server_cpu_critical_percent
                else "warning"
            ),
            title=f"High CPU on {name}",
            message=f"Host CPU usage is {cpu_value:.1f}%." if cpu_value is not None else "CPU telemetry is unavailable.",
            required_samples=3,
            recovery_samples=2,
            current_value=cpu_value,
            threshold=settings.alert_server_cpu_warning_percent,
            context={"critical_threshold": settings.alert_server_cpu_critical_percent},
        )
    )

    memory = sample.get("memory") or {}
    memory_used = memory.get("used_percent")
    memory_value = float(memory_used) if memory_used is not None else None
    conditions.append(
        AlertCondition(
            rule_key="memory_pressure",
            active=(memory_value >= settings.alert_server_memory_warning_percent) if healthy and memory_value is not None else None,
            severity=(
                "critical"
                if memory_value is not None and memory_value >= settings.alert_server_memory_critical_percent
                else "warning"
            ),
            title=f"High memory usage on {name}",
            message=f"Host memory usage is {memory_value:.1f}%." if memory_value is not None else "Memory telemetry is unavailable.",
            required_samples=3,
            recovery_samples=2,
            current_value=memory_value,
            threshold=settings.alert_server_memory_warning_percent,
            context={"critical_threshold": settings.alert_server_memory_critical_percent},
        )
    )

    if healthy:
        for filesystem in sample.get("filesystems") or []:
            mount = str(filesystem.get("mount_point") or filesystem.get("filesystem") or "unknown")
            used = filesystem.get("used_percent")
            used_value = float(used) if used is not None else None
            conditions.append(
                AlertCondition(
                    rule_key=f"filesystem:{mount}",
                    active=(used_value >= settings.alert_filesystem_warning_percent) if used_value is not None else None,
                    severity=(
                        "critical"
                        if used_value is not None and used_value >= settings.alert_filesystem_critical_percent
                        else "warning"
                    ),
                    title=f"Filesystem {mount} pressure on {name}",
                    message=f"Filesystem {mount} is {used_value:.1f}% used." if used_value is not None else f"Filesystem {mount} usage is unavailable.",
                    required_samples=3,
                    recovery_samples=2,
                    current_value=used_value,
                    threshold=settings.alert_filesystem_warning_percent,
                    context={
                        "mount_point": mount,
                        "filesystem": filesystem.get("filesystem"),
                        "critical_threshold": settings.alert_filesystem_critical_percent,
                    },
                )
            )

    return conditions


def transition_alert(existing: dict | None, condition: AlertCondition, now: datetime) -> tuple[str, dict | None]:

    if condition.active is None:
        return "noop", None

    if condition.active:
        if existing and existing.get("status") == "cleared":
            return "update", {
                "last_seen_at": now,
                "severity": condition.severity,
                "title": condition.title,
                "message": condition.message,
                "current_value": condition.current_value,
                "threshold": condition.threshold,
                "context": condition.context or {},
                "good_count": 0,
            }

        previous_bad = int(existing.get("bad_count") or 0) if existing else 0
        reopened = bool(existing and existing.get("status") == "resolved")
        if reopened:
            previous_bad = 0
        bad_count = previous_bad + 1
        status = "active" if bad_count >= condition.required_samples else "pending"
        update = {
            "status": status,
            "bad_count": bad_count,
            "good_count": 0,
            "last_seen_at": now,
            "severity": condition.severity,
            "title": condition.title,
            "message": condition.message,
            "current_value": condition.current_value,
            "threshold": condition.threshold,
            "context": condition.context or {},
            "resolved_at": None,
            "cleared_at": None,
            "cleared_by": None,
        }
        if reopened:
            update["first_seen_at"] = now
        return "update", update

    if not existing:
        return "noop", None

    status = existing.get("status")
    if status == "pending":
        return "delete", None
    if status == "resolved":
        return "noop", None

    good_count = int(existing.get("good_count") or 0) + 1
    if status == "cleared":
        if good_count >= condition.recovery_samples:
            return "delete", None
        return "update", {"good_count": good_count}

    if status == "active":
        if good_count >= condition.recovery_samples:
            return "update", {
                "status": "resolved",
                "good_count": good_count,
                "resolved_at": now,
            }
        return "update", {"good_count": good_count}

    return "noop", None


async def _evaluate_source(
    database,
    *,
    source_type: str,
    source_id: str,
    source_name: str,
    conditions: list[AlertCondition],
    source_engine: str | None = None,
    fully_evaluated_prefixes: tuple[str, ...] = (),
) -> None:
    collection = database[ALERTS_COLLECTION_NAME]
    existing_items = await collection.find(
        {"source_type": source_type, "source_id": source_id}
    ).to_list(None)
    existing_by_rule = {str(item["rule_key"]): item for item in existing_items}
    conditions_by_rule = {condition.rule_key: condition for condition in conditions}

    for rule_key in existing_by_rule:
        if rule_key in conditions_by_rule:
            continue
        if any(rule_key.startswith(prefix) for prefix in fully_evaluated_prefixes):
            existing = existing_by_rule[rule_key]
            conditions_by_rule[rule_key] = AlertCondition(
                rule_key=rule_key,
                active=False,
                severity=str(existing.get("severity") or "warning"),
                title=str(existing.get("title") or rule_key),
                message=str(existing.get("message") or "Condition recovered."),
                required_samples=int(existing.get("required_samples") or 2),
                recovery_samples=int(existing.get("recovery_samples") or 2),
            )

    now = _utcnow()
    for rule_key, condition in conditions_by_rule.items():
        existing = existing_by_rule.get(rule_key)
        action, change = transition_alert(existing, condition, now)
        alert_key = f"{source_type}:{source_id}:{rule_key}"
        if action == "noop":
            continue
        if action == "delete":
            await collection.delete_one({"alert_key": alert_key})
            continue

        base = {
            "alert_key": alert_key,
            "source_type": source_type,
            "source_id": source_id,
            "source_name": source_name,
            "rule_key": rule_key,
            "required_samples": condition.required_samples,
            "recovery_samples": condition.recovery_samples,
        }
        if source_engine:
            base["source_engine"] = source_engine
        update = {**base, **(change or {})}
        set_on_insert = {"first_seen_at": now}
        await collection.update_one(
            {"alert_key": alert_key},
            {"$set": update, "$setOnInsert": set_on_insert},
            upsert=True,
        )

        if action == "update":
            updated_alert = await collection.find_one({"alert_key": alert_key})
            if updated_alert and should_enqueue_alert_email(existing, updated_alert):
                try:
                    await enqueue_alert_email_deliveries(database, updated_alert)
                except Exception:
                    logger.exception(
                        "Failed to queue email notification alert_key=%s",
                        alert_key,
                    )


async def evaluate_database_sample(
    database,
    connection: dict,
    sample: dict,
    *,
    include_sqlserver_instance_alerts: bool = True,
    include_mysql_instance_alerts: bool = True,
) -> None:
    storage_present = bool((sample.get("oracle") or {}).get("storage") is not None)
    await _evaluate_source(
        database,
        source_type="database",
        source_id=str(connection["_id"]),
        source_name=str(connection.get("name") or connection.get("database") or connection["_id"]),
        conditions=database_alert_conditions(
            connection,
            sample,
            include_sqlserver_instance_conditions=include_sqlserver_instance_alerts,
            include_mysql_instance_conditions=include_mysql_instance_alerts,
        ),
        source_engine=str(connection.get("engine") or "").lower() or None,
        fully_evaluated_prefixes=("tablespace:",) if storage_present else (),
    )


async def evaluate_server_sample(database, server: dict, sample: dict) -> None:
    healthy = str(sample.get("status")) in {"online", "limited"}
    await _evaluate_source(
        database,
        source_type="server",
        source_id=str(server["_id"]),
        source_name=str(server.get("name") or server.get("hostname") or server["_id"]),
        conditions=server_alert_conditions(server, sample),
        fully_evaluated_prefixes=("filesystem:",) if healthy else (),
    )


async def sync_collector_heartbeat_alert(database) -> None:
    if not settings.metrics_collector_enabled:
        return

    status = await database[COLLECTOR_STATUS_COLLECTION_NAME].find_one({"_id": "primary"})
    now = _utcnow()
    heartbeat = status.get("last_heartbeat_at") if status else None
    if heartbeat is not None and heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    state = status.get("state") if status else "not_started"
    alive = bool(
        heartbeat is not None
        and (now - heartbeat).total_seconds() <= settings.alert_collector_stale_seconds
        and state in {"starting", "running", "degraded"}
    )
    message = "The DBAChum background collector heartbeat is healthy."
    if not alive:
        if heartbeat is None:
            message = "The DBAChum background collector has not produced a heartbeat."
        else:
            age = max(0, int((now - heartbeat).total_seconds()))
            message = f"The DBAChum collector heartbeat is {age} seconds old (state: {state})."

    await _evaluate_source(
        database,
        source_type="collector",
        source_id="primary",
        source_name="DBAChum Collector",
        conditions=[
            AlertCondition(
                rule_key="heartbeat",
                active=not alive,
                severity="critical",
                title="Background collector heartbeat missing",
                message=message,
                required_samples=1,
                recovery_samples=1,
                current_value=state,
                threshold=f"heartbeat <= {settings.alert_collector_stale_seconds}s",
            )
        ],
    )


def _response(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "alert_key": document["alert_key"],
        "source_type": document["source_type"],
        "source_id": document["source_id"],
        "source_name": document["source_name"],
        "rule_key": document["rule_key"],
        "severity": document["severity"],
        "status": document["status"],
        "title": document["title"],
        "message": document["message"],
        "first_seen_at": document["first_seen_at"],
        "last_seen_at": document["last_seen_at"],
        "resolved_at": document.get("resolved_at"),
        "current_value": document.get("current_value"),
        "threshold": document.get("threshold"),
        "context": document.get("context") or {},
    }


async def list_alerts(database, *, status: str = "active", severity: str | None = None, limit: int = 200) -> list[dict]:
    await sync_collector_heartbeat_alert(database)
    query: dict[str, Any] = {"status": {"$in": ["active", "resolved"]}}
    if status in {"active", "resolved"}:
        query["status"] = status
    if severity in {"warning", "critical"}:
        query["severity"] = severity
    cursor = database[ALERTS_COLLECTION_NAME].find(query).sort(
        [("status", 1), ("severity", 1), ("last_seen_at", -1)]
    ).limit(limit)
    documents = await cursor.to_list(None)
    def sort_key(item: dict):
        last_seen = item.get("last_seen_at")
        last_seen_ts = last_seen.timestamp() if last_seen is not None else 0.0
        return (
            0 if item.get("status") == "active" else 1,
            0 if item.get("severity") == "critical" else 1,
            -last_seen_ts,
        )

    documents.sort(key=sort_key)
    return [_response(document) for document in documents]


async def get_alert_summary(database) -> dict:
    await sync_collector_heartbeat_alert(database)
    collection = database[ALERTS_COLLECTION_NAME]
    active = await collection.count_documents({"status": "active"})
    warning = await collection.count_documents({"status": "active", "severity": "warning"})
    critical = await collection.count_documents({"status": "active", "severity": "critical"})
    resolved = await collection.count_documents({"status": "resolved"})
    return {"active": active, "warning": warning, "critical": critical, "resolved": resolved}


async def clear_alert(database, alert_id: str, cleared_by: str) -> dict:
    try:
        object_id = ObjectId(alert_id)
    except Exception:
        raise AppError("Alert not found.", code="ALERT_NOT_FOUND", status_code=404)

    collection = database[ALERTS_COLLECTION_NAME]
    document = await collection.find_one({"_id": object_id})
    if not document or document.get("status") not in {"active", "resolved"}:
        raise AppError("Alert not found.", code="ALERT_NOT_FOUND", status_code=404)

    if document.get("status") == "resolved":
        await collection.delete_one({"_id": object_id})
        return {"cleared": True, "suppressed_until_recovery": False}

    now = _utcnow()
    await collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "cleared",
                "cleared_at": now,
                "cleared_by": cleared_by,
                "good_count": 0,
            }
        },
    )
    return {"cleared": True, "suppressed_until_recovery": True}


async def clear_resolved_alerts(database) -> int:
    result = await database[ALERTS_COLLECTION_NAME].delete_many({"status": "resolved"})
    return int(result.deleted_count)
