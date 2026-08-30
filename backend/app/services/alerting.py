from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.core.collections import ALERTS_COLLECTION_NAME, COLLECTOR_STATUS_COLLECTION_NAME
from app.core.config import settings
from app.core.exceptions import AppError


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


def database_alert_conditions(connection: dict, sample: dict) -> list[AlertCondition]:
    name = str(connection.get("name") or connection.get("database") or connection.get("_id"))
    status = str(sample.get("status") or "unreachable")
    healthy = status in {"online", "limited"}
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

    blocked = sample.get("blocked")
    conditions.append(
        AlertCondition(
            rule_key="blocking_sessions",
            active=(int(blocked) > 0) if healthy and blocked is not None else None,
            severity="critical" if blocked is not None and int(blocked) >= 5 else "warning",
            title=f"Blocking sessions on {name}",
            message=(
                f"{int(blocked)} blocked session(s) were observed."
                if blocked is not None
                else "Blocking-session telemetry is unavailable."
            ),
            required_samples=2,
            recovery_samples=2,
            current_value=int(blocked) if blocked is not None else None,
            threshold=1,
        )
    )

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
                active=(active_count >= active_warning) if healthy and active_count is not None else None,
                severity=severity,
                title=f"High active sessions on {name}",
                message=(
                    f"{active_count} active session(s) were observed."
                    if active_count is not None
                    else "Active-session telemetry is unavailable."
                ),
                required_samples=3,
                recovery_samples=2,
                current_value=active_count,
                threshold=active_warning,
                context={"critical_threshold": active_critical},
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
    """Return (action, document/update). Pure state transition for testing."""
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
            # A cleared active condition stays suppressed until it genuinely
            # recovers. Deleting here rearms the alert for a future incident.
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
    fully_evaluated_prefixes: tuple[str, ...] = (),
) -> None:
    collection = database[ALERTS_COLLECTION_NAME]
    existing_items = await collection.find(
        {"source_type": source_type, "source_id": source_id}
    ).to_list(None)
    existing_by_rule = {str(item["rule_key"]): item for item in existing_items}
    conditions_by_rule = {condition.rule_key: condition for condition in conditions}

    # Dynamic rule families (tablespaces/filesystems) can disappear after a
    # recovery or mount change. When the current snapshot fully evaluated that
    # family, synthesize a healthy result so stale alerts can resolve/rearm.
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
        update = {**base, **(change or {})}
        set_on_insert = {"first_seen_at": now}
        await collection.update_one(
            {"alert_key": alert_key},
            {"$set": update, "$setOnInsert": set_on_insert},
            upsert=True,
        )


async def evaluate_database_sample(database, connection: dict, sample: dict) -> None:
    storage_present = bool((sample.get("oracle") or {}).get("storage") is not None)
    await _evaluate_source(
        database,
        source_type="database",
        source_id=str(connection["_id"]),
        source_name=str(connection.get("name") or connection.get("database") or connection["_id"]),
        conditions=database_alert_conditions(connection, sample),
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
