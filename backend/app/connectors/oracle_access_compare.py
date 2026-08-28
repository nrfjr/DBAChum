from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _source_key(source: dict[str, Any]) -> tuple[Any, ...]:
    return (
        source.get("kind"),
        tuple(source.get("via") or []),
        bool(source.get("admin_option")),
        source.get("default_role"),
        source.get("grantable"),
    )


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for source in sources:
        key = _source_key(source)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _role_key(item: dict[str, Any]) -> tuple[str]:
    return (str(item["name"]).upper(),)


def _system_privilege_key(item: dict[str, Any]) -> tuple[str]:
    return (str(item["name"]).upper(),)


def _object_privilege_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item["owner"]).upper(),
        str(item["object_name"]).upper(),
        str(item["privilege"]).upper(),
        str(item.get("column_name") or "").upper(),
    )


def _admin_privilege_key(item: str) -> tuple[str]:
    return (str(item).upper(),)


def _role_label(item: dict[str, Any]) -> str:
    return str(item["name"]).upper()


def _system_privilege_label(item: dict[str, Any]) -> str:
    return str(item["name"]).upper()


def _object_privilege_label(item: dict[str, Any]) -> str:
    owner = str(item["owner"]).upper()
    object_name = str(item["object_name"]).upper()
    privilege = str(item["privilege"]).upper()
    column = str(item.get("column_name") or "").upper()
    target = f"{owner}.{object_name}"
    if column:
        target += f".{column}"
    return f"{privilege} ON {target}"


def _admin_privilege_label(item: str) -> str:
    return str(item).upper()


def _compare_category(
    left_items: list[Any],
    right_items: list[Any],
    *,
    key_fn: Callable[[Any], tuple[Any, ...]],
    label_fn: Callable[[Any], str],
    sources_fn: Callable[[Any], list[dict[str, Any]]],
    powerful_fn: Callable[[Any], bool],
) -> dict[str, list[dict[str, Any]]]:
    left_map = {key_fn(item): item for item in left_items}
    right_map = {key_fn(item): item for item in right_items}

    common_keys = sorted(set(left_map) & set(right_map))
    left_only_keys = sorted(set(left_map) - set(right_map))
    right_only_keys = sorted(set(right_map) - set(left_map))

    def make_item(key: tuple[Any, ...], include_left: bool, include_right: bool) -> dict[str, Any]:
        left = left_map.get(key) if include_left else None
        right = right_map.get(key) if include_right else None
        template = left if left is not None else right
        assert template is not None
        return {
            "key": "|".join(str(part) for part in key),
            "label": label_fn(template),
            "powerful": bool(
                (left is not None and powerful_fn(left))
                or (right is not None and powerful_fn(right))
            ),
            "left_sources": _dedupe_sources(sources_fn(left)) if left is not None else [],
            "right_sources": _dedupe_sources(sources_fn(right)) if right is not None else [],
        }

    return {
        "common": [make_item(key, True, True) for key in common_keys],
        "left_only": [make_item(key, True, False) for key in left_only_keys],
        "right_only": [make_item(key, False, True) for key in right_only_keys],
    }


def _compare_access_payloads(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    roles = _compare_category(
        left.get("roles", []),
        right.get("roles", []),
        key_fn=_role_key,
        label_fn=_role_label,
        sources_fn=lambda item: list(item.get("sources", [])),
        powerful_fn=lambda item: bool(item.get("powerful")),
    )
    system_privileges = _compare_category(
        left.get("system_privileges", []),
        right.get("system_privileges", []),
        key_fn=_system_privilege_key,
        label_fn=_system_privilege_label,
        sources_fn=lambda item: list(item.get("sources", [])),
        powerful_fn=lambda item: bool(item.get("powerful")),
    )
    object_privileges = _compare_category(
        left.get("object_privileges", []),
        right.get("object_privileges", []),
        key_fn=_object_privilege_key,
        label_fn=_object_privilege_label,
        sources_fn=lambda item: list(item.get("sources", [])),
        powerful_fn=lambda item: False,
    )
    administrative_privileges = _compare_category(
        left.get("administrative_privileges", []),
        right.get("administrative_privileges", []),
        key_fn=_admin_privilege_key,
        label_fn=_admin_privilege_label,
        sources_fn=lambda _item: [
            {
                "kind": "password_file",
                "via": [],
                "admin_option": False,
                "default_role": None,
                "grantable": None,
            }
        ],
        powerful_fn=lambda _item: True,
    )

    categories = {
        "roles": roles,
        "system_privileges": system_privileges,
        "object_privileges": object_privileges,
        "administrative_privileges": administrative_privileges,
    }

    common_count = sum(len(category["common"]) for category in categories.values())
    left_only_count = sum(len(category["left_only"]) for category in categories.values())
    right_only_count = sum(len(category["right_only"]) for category in categories.values())

    warnings = [
        f'{left["username"]}: {warning}' for warning in left.get("warnings", [])
    ] + [
        f'{right["username"]}: {warning}' for warning in right.get("warnings", [])
    ]

    return {
        "left": {
            "username": left["username"],
            "status": left.get("status", ""),
            "profile": left.get("profile"),
            "default_tablespace": left.get("default_tablespace"),
            "temporary_tablespace": left.get("temporary_tablespace"),
        },
        "right": {
            "username": right["username"],
            "status": right.get("status", ""),
            "profile": right.get("profile"),
            "default_tablespace": right.get("default_tablespace"),
            "temporary_tablespace": right.get("temporary_tablespace"),
        },
        "roles": roles,
        "system_privileges": system_privileges,
        "object_privileges": object_privileges,
        "administrative_privileges": administrative_privileges,
        "common_count": common_count,
        "left_only_count": left_only_count,
        "right_only_count": right_only_count,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc),
    }


async def get_oracle_access_compare(
    connection: dict[str, Any],
    left_username: str,
    right_username: str,
) -> dict[str, Any]:
    # Keep the pure compare helpers import-light for unit testing. Oracle runtime
    # dependencies are only needed when the live endpoint executes.
    from app.connectors.oracle_access_inspector import get_oracle_user_access_inspector
    from app.connectors.oracle_provisioning import normalize_oracle_identifier
    from app.core.exceptions import AppError

    left_username = normalize_oracle_identifier(left_username, field_name="First username")
    right_username = normalize_oracle_identifier(right_username, field_name="Second username")
    if left_username == right_username:
        raise AppError(
            "Choose two different Oracle users to compare.",
            code="ORACLE_ACCESS_COMPARE_SAME_USER",
            status_code=400,
        )

    left = await get_oracle_user_access_inspector(connection, left_username)
    right = await get_oracle_user_access_inspector(connection, right_username)
    return _compare_access_payloads(left, right)
