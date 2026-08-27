from __future__ import annotations

import asyncio
import base64

from ldap3 import BASE, SUBTREE, Connection, Server
from ldap3.utils.conv import escape_filter_chars

from app.core.exceptions import AppError
from app.core.security import decrypt_secret


def _require_enabled_profile(profile: dict) -> None:
    if not profile.get("enabled"):
        raise AppError(
            "The selected LDAP profile is disabled.",
            code="LDAP_PROFILE_DISABLED",
            status_code=409,
        )
    if not profile.get("bind_password_encrypted"):
        raise AppError(
            "The selected LDAP profile does not have a saved bind password.",
            code="LDAP_PROFILE_INCOMPLETE",
            status_code=409,
        )


def _open_bound_connection(profile: dict) -> Connection:
    _require_enabled_profile(profile)
    server = Server(
        profile.get("host", ""),
        port=int(profile.get("port", 636)),
        use_ssl=bool(profile.get("use_ssl", True)),
        connect_timeout=5,
    )
    connection = Connection(
        server,
        user=profile.get("bind_dn", ""),
        password=decrypt_secret(profile["bind_password_encrypted"]),
        receive_timeout=8,
        raise_exceptions=False,
    )
    connection.open()
    if connection.closed:
        raise AppError(
            "Unable to connect to the LDAP server.",
            code="LDAP_CONNECT_FAILED",
            status_code=409,
        )
    if not connection.bind():
        description = (connection.result or {}).get("description") or "bind failed"
        connection.unbind()
        raise AppError(
            f"LDAP bind authentication failed ({description}).",
            code="LDAP_BIND_FAILED",
            status_code=409,
        )
    return connection


def _decode_ldif_value(raw: str, *, base64_encoded: bool) -> str:
    if not base64_encoded:
        return raw
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception as exc:
        raise AppError(
            "LDAP LDIF contains an invalid base64 value.",
            code="LDAP_LDIF_INVALID",
            status_code=400,
        ) from exc


def parse_single_entry_ldif(content: str) -> tuple[str, dict[str, object]]:
    """Parse DBAChum's rendered one-entry LDIF into ldap3 add arguments.

    The profile template is intentionally limited to one LDAP entry. Standard
    continuation lines and base64 values are supported. change records and URL
    values are rejected because provisioning should only create one entry.
    """
    unfolded: list[str] = []
    for raw_line in content.splitlines():
        if raw_line.startswith(" "):
            if not unfolded:
                raise AppError("LDAP LDIF starts with a continuation line.", code="LDAP_LDIF_INVALID", status_code=400)
            unfolded[-1] += raw_line[1:]
        else:
            unfolded.append(raw_line)

    dn: str | None = None
    attributes: dict[str, list[str]] = {}
    for line in unfolded:
        if not line or line.startswith("#"):
            continue
        if ":<" in line:
            raise AppError(
                "LDAP LDIF URL values are not supported for automatic provisioning.",
                code="LDAP_LDIF_UNSUPPORTED",
                status_code=400,
            )
        if "::" in line:
            key, raw_value = line.split("::", 1)
            value = _decode_ldif_value(raw_value.lstrip(), base64_encoded=True)
        elif ":" in line:
            key, raw_value = line.split(":", 1)
            value = raw_value.lstrip()
        else:
            raise AppError(
                f"LDAP LDIF contains an invalid line: {line}",
                code="LDAP_LDIF_INVALID",
                status_code=400,
            )

        key = key.strip()
        if not key:
            raise AppError("LDAP LDIF contains an empty attribute name.", code="LDAP_LDIF_INVALID", status_code=400)
        lowered = key.lower()
        if lowered == "dn":
            if dn is not None:
                raise AppError("LDAP LDIF must contain exactly one DN.", code="LDAP_LDIF_INVALID", status_code=400)
            dn = value.strip()
            continue
        if lowered in {"changetype", "add", "delete", "replace"}:
            raise AppError(
                "LDAP LDIF change records are not supported for automatic provisioning.",
                code="LDAP_LDIF_UNSUPPORTED",
                status_code=400,
            )
        attributes.setdefault(key, []).append(value)

    if not dn:
        raise AppError("LDAP LDIF does not contain a DN.", code="LDAP_LDIF_INVALID", status_code=400)

    normalized: dict[str, object] = {}
    for key, values in attributes.items():
        normalized[key] = values[0] if len(values) == 1 else values
    return dn, normalized


def _dn_is_within_base(dn: str, base_dn: str) -> bool:
    dn_norm = "".join(dn.lower().split())
    base_norm = "".join(base_dn.lower().split())
    return bool(base_norm) and (dn_norm == base_norm or dn_norm.endswith("," + base_norm))


def _find_entries_sync(profile: dict, username: str) -> list[str]:
    connection = _open_bound_connection(profile)
    try:
        base_dn = str(profile.get("base_dn") or "").strip()
        if not base_dn:
            raise AppError("LDAP Base DN is not configured.", code="LDAP_BASE_DN_REQUIRED", status_code=409)
        escaped = escape_filter_chars(username)
        ok = connection.search(
            search_base=base_dn,
            search_filter=f"(|(uid={escaped})(cn={escaped}))",
            search_scope=SUBTREE,
            attributes=[],
        )
        if not ok and (connection.result or {}).get("description") not in {"success", None}:
            description = (connection.result or {}).get("description") or "search failed"
            raise AppError(f"LDAP user lookup failed ({description}).", code="LDAP_SEARCH_FAILED", status_code=409)
        return sorted({str(entry.entry_dn) for entry in connection.entries})
    finally:
        connection.unbind()


async def find_ldap_entries_for_username(profile: dict, username: str) -> list[str]:
    return await asyncio.to_thread(_find_entries_sync, profile, username)


def _add_entry_sync(profile: dict, ldif_content: str) -> dict[str, str]:
    dn, attributes = parse_single_entry_ldif(ldif_content)
    base_dn = str(profile.get("base_dn") or "").strip()
    if not _dn_is_within_base(dn, base_dn):
        raise AppError(
            "The rendered LDAP DN is outside the configured Base DN.",
            code="LDAP_DN_OUTSIDE_BASE",
            status_code=409,
        )

    connection = _open_bound_connection(profile)
    try:
        exists = connection.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=BASE,
            attributes=[],
        )
        if exists and connection.entries:
            return {"action": "already_present", "dn": dn}

        object_class_key = next((key for key in attributes if key.lower() == "objectclass"), None)
        object_classes = attributes.pop(object_class_key) if object_class_key else None
        if not object_classes:
            raise AppError(
                "LDAP LDIF must include at least one objectClass for automatic provisioning.",
                code="LDAP_LDIF_OBJECTCLASS_REQUIRED",
                status_code=400,
            )
        if isinstance(object_classes, str):
            object_classes = [object_classes]

        if not connection.add(dn, object_class=object_classes, attributes=attributes):
            description = (connection.result or {}).get("description") or "add failed"
            raise AppError(
                f"LDAP entry creation failed ({description}).",
                code="LDAP_ADD_FAILED",
                status_code=409,
            )
        return {"action": "created", "dn": dn}
    finally:
        connection.unbind()


async def add_ldap_entry_from_ldif(profile: dict, ldif_content: str) -> dict[str, str]:
    return await asyncio.to_thread(_add_entry_sync, profile, ldif_content)


def _delete_entry_sync(profile: dict, dn: str) -> bool:
    base_dn = str(profile.get("base_dn") or "").strip()
    if not _dn_is_within_base(dn, base_dn):
        raise AppError(
            "The LDAP entry is outside the configured Base DN.",
            code="LDAP_DN_OUTSIDE_BASE",
            status_code=409,
        )
    connection = _open_bound_connection(profile)
    try:
        exists = connection.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=BASE,
            attributes=[],
        )
        if not exists or not connection.entries:
            return False
        if not connection.delete(dn):
            description = (connection.result or {}).get("description") or "delete failed"
            raise AppError(
                f"LDAP entry deletion failed ({description}).",
                code="LDAP_DELETE_FAILED",
                status_code=409,
            )
        return True
    finally:
        connection.unbind()


async def delete_ldap_entry(profile: dict, dn: str) -> bool:
    return await asyncio.to_thread(_delete_entry_sync, profile, dn)
