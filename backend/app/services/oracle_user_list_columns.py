from collections import OrderedDict
from datetime import datetime, timezone

from bson import ObjectId

from app.connectors.oracle_metadata import list_oracle_columns
from app.connectors.oracle_user_list_enrichment import (
    fetch_oracle_user_list_values,
    fetch_oracle_user_list_values_multi,
)
from app.core.exceptions import AppError
from app.services.database_connections import connection_is_active, get_database_connection


MAX_EXTRA_COLUMNS = 8
TEXT_JOIN_TYPES = {"CHAR", "NCHAR", "VARCHAR2", "NVARCHAR2"}


def _parse_id(column_id: str) -> ObjectId:
    try:
        return ObjectId(column_id)
    except Exception as exc:
        raise AppError(
            "Additional user-list column not found.",
            code="ORACLE_USER_LIST_COLUMN_NOT_FOUND",
            status_code=404,
        ) from exc


async def _get_oracle_connection(database, connection_id: str) -> dict:
    connection = await get_database_connection(database, connection_id)
    if connection.get("engine") != "oracle":
        raise AppError(
            "Additional user-list columns are only available for Oracle connections.",
            code="ORACLE_USER_LIST_COLUMN_ORACLE_REQUIRED",
            status_code=400,
        )
    if not connection_is_active(connection):
        raise AppError(
            "This database connection is disabled.",
            code="CONNECTION_DISABLED",
            status_code=400,
        )
    return connection


def _clean_label(value: str) -> str:
    label = " ".join(value.strip().split())
    if not label:
        raise AppError(
            "Column label is required.",
            code="ORACLE_USER_LIST_COLUMN_LABEL_REQUIRED",
            status_code=400,
        )
    if len(label) > 40:
        raise AppError(
            "Column label must be 40 characters or fewer.",
            code="ORACLE_USER_LIST_COLUMN_LABEL_TOO_LONG",
            status_code=400,
        )
    return label


async def _validate_mappings(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
) -> tuple[dict, dict, dict[str, dict]]:
    connection = await _get_oracle_connection(database, connection_id)
    columns = await list_oracle_columns(connection, owner, table_name)
    column_map = {str(item["name"]).upper(): item for item in columns}

    join = column_map.get(join_column.strip().upper())
    if join is None:
        raise AppError(
            "The selected relationship column is not available in the source table.",
            code="ORACLE_USER_LIST_JOIN_COLUMN_NOT_FOUND",
            status_code=400,
        )
    if str(join.get("data_type") or "").upper() not in TEXT_JOIN_TYPES:
        raise AppError(
            "The relationship column must be a character column so it can match DBA_USERS.USERNAME.",
            code="ORACLE_USER_LIST_JOIN_COLUMN_NOT_TEXT",
            status_code=400,
        )

    display_map: dict[str, dict] = {}
    for raw_display in display_columns:
        normalized = raw_display.strip().upper()
        display = column_map.get(normalized)
        if display is None:
            raise AppError(
                f"The selected display column '{normalized}' is not available in the source table.",
                code="ORACLE_USER_LIST_DISPLAY_COLUMN_NOT_FOUND",
                status_code=400,
            )
        display_map[normalized] = display

    if not display_map:
        raise AppError(
            "Select at least one column to add to the user list.",
            code="ORACLE_USER_LIST_DISPLAY_COLUMN_REQUIRED",
            status_code=400,
        )

    return connection, join, display_map


async def _validate_mapping(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
) -> tuple[dict, dict, dict]:
    connection, join, display_map = await _validate_mappings(
        database,
        connection_id,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[display_column],
    )
    return connection, join, next(iter(display_map.values()))


def _document_to_response(
    document: dict,
    *,
    duplicate_matches: int = 0,
    warning: str | None = None,
) -> dict:
    return {
        "id": str(document["_id"]),
        "label": document["label"],
        "owner": document["owner"],
        "table_name": document["table_name"],
        "join_column": document["join_column"],
        "display_column": document["display_column"],
        "duplicate_matches": duplicate_matches,
        "warning": warning,
    }


async def list_oracle_user_list_columns(database, connection_id: str) -> list[dict]:
    cursor = database.oracle_user_list_columns.find(
        {"connection_id": connection_id}
    ).sort("created_at", 1)
    documents = await cursor.to_list(None)
    return [_document_to_response(document) for document in documents]


async def preview_oracle_user_list_columns(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    columns: list[dict],
    base_users: list[dict],
) -> dict:
    selections: list[dict] = []
    seen_display: set[str] = set()
    for item in columns:
        display_column = str(item.get("display_column") or "").strip().upper()
        label = _clean_label(str(item.get("label") or ""))
        if not display_column:
            raise AppError(
                "Display column is required.",
                code="ORACLE_USER_LIST_DISPLAY_COLUMN_REQUIRED",
                status_code=400,
            )
        if display_column in seen_display:
            raise AppError(
                f"Column '{display_column}' was selected more than once.",
                code="ORACLE_USER_LIST_COLUMN_DUPLICATE_SELECTION",
                status_code=400,
            )
        seen_display.add(display_column)
        selections.append({"display_column": display_column, "label": label})

    connection, join, display_map = await _validate_mappings(
        database,
        connection_id,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[item["display_column"] for item in selections],
    )

    usernames = [str(item["username"]) for item in base_users]
    values, duplicate_keys = await fetch_oracle_user_list_values_multi(
        connection,
        usernames,
        owner=owner,
        table_name=table_name,
        join_column=str(join["name"]),
        display_columns=[str(display_map[item["display_column"]]["name"]) for item in selections],
    )

    preview_user = next(
        (item for item in base_users if str(item["username"]) in values),
        base_users[0] if base_users else None,
    )
    if preview_user is None:
        raise AppError(
            "No Oracle users are available to preview this mapping.",
            code="ORACLE_USER_LIST_PREVIEW_NO_USERS",
            status_code=400,
        )

    username = str(preview_user["username"])
    warning = None
    if username in duplicate_keys:
        warning = (
            "This relationship found multiple source rows for the previewed user. "
            "DBAChum will keep the main DBA_USERS row intact and use the first source row."
        )
    elif not values:
        warning = (
            "No current DBA_USERS account matched this source relationship. "
            "The added columns will show — when no source row exists."
        )

    row_values = values.get(username, {})
    return {
        "username": username,
        "status": str(preview_user.get("status") or ""),
        "values": [
            {
                "display_column": item["display_column"],
                "label": item["label"],
                "value": row_values.get(item["display_column"]),
            }
            for item in selections
        ],
        "matched": username in values,
        "duplicate_match": username in duplicate_keys,
        "warning": warning,
    }


async def preview_oracle_user_list_column(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
    label: str,
    base_users: list[dict],
) -> dict:
    """Backward-compatible single-column preview wrapper."""

    result = await preview_oracle_user_list_columns(
        database,
        connection_id,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        columns=[{"display_column": display_column, "label": label}],
        base_users=base_users,
    )
    value = result["values"][0]
    return {
        "label": value["label"],
        "username": result["username"],
        "status": result["status"],
        "value": value["value"],
        "matched": result["matched"],
        "duplicate_match": result["duplicate_match"],
        "warning": result["warning"],
    }


async def create_oracle_user_list_columns(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    columns: list[dict],
    created_by: str,
) -> list[dict]:
    selections: list[dict] = []
    seen_display: set[str] = set()
    seen_labels: set[str] = set()
    for item in columns:
        display_column = str(item.get("display_column") or "").strip().upper()
        label = _clean_label(str(item.get("label") or ""))
        label_key = label.casefold()
        if not display_column:
            raise AppError(
                "Display column is required.",
                code="ORACLE_USER_LIST_DISPLAY_COLUMN_REQUIRED",
                status_code=400,
            )
        if display_column in seen_display:
            raise AppError(
                f"Column '{display_column}' was selected more than once.",
                code="ORACLE_USER_LIST_COLUMN_DUPLICATE_SELECTION",
                status_code=400,
            )
        if label_key in seen_labels:
            raise AppError(
                f"List heading '{label}' was used more than once.",
                code="ORACLE_USER_LIST_COLUMN_LABEL_DUPLICATE_SELECTION",
                status_code=400,
            )
        seen_display.add(display_column)
        seen_labels.add(label_key)
        selections.append(
            {
                "display_column": display_column,
                "label": label,
                "label_key": label_key,
            }
        )

    connection, join, display_map = await _validate_mappings(
        database,
        connection_id,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[item["display_column"] for item in selections],
    )
    del connection

    existing = await database.oracle_user_list_columns.find(
        {"connection_id": connection_id}
    ).to_list(None)
    if len(existing) + len(selections) > MAX_EXTRA_COLUMNS:
        remaining = max(0, MAX_EXTRA_COLUMNS - len(existing))
        raise AppError(
            f"A maximum of {MAX_EXTRA_COLUMNS} additional columns can be shown for one user list. "
            f"You can add {remaining} more.",
            code="ORACLE_USER_LIST_COLUMN_LIMIT",
            status_code=400,
        )

    owner_normalized = owner.strip().upper()
    table_normalized = table_name.strip().upper()
    join_normalized = str(join["name"]).upper()

    existing_labels = {
        str(item.get("label_key") or item.get("label", "")).casefold()
        for item in existing
    }
    existing_sources = {
        (
            str(item.get("owner") or "").upper(),
            str(item.get("table_name") or "").upper(),
            str(item.get("join_column") or "").upper(),
            str(item.get("display_column") or "").upper(),
        )
        for item in existing
    }

    for item in selections:
        if item["label_key"] in existing_labels:
            raise AppError(
                f"An additional column with the label '{item['label']}' already exists.",
                code="ORACLE_USER_LIST_COLUMN_LABEL_EXISTS",
                status_code=409,
            )
        source_key = (
            owner_normalized,
            table_normalized,
            join_normalized,
            item["display_column"],
        )
        if source_key in existing_sources:
            raise AppError(
                f"Source column '{item['display_column']}' is already added through this mapping.",
                code="ORACLE_USER_LIST_COLUMN_EXISTS",
                status_code=409,
            )

    now = datetime.now(timezone.utc)
    documents = [
        {
            "connection_id": connection_id,
            "label": item["label"],
            "label_key": item["label_key"],
            "owner": owner_normalized,
            "table_name": table_normalized,
            "join_column": join_normalized,
            "display_column": str(display_map[item["display_column"]]["name"]).upper(),
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        for item in selections
    ]

    if not documents:
        raise AppError(
            "Select at least one column to add to the user list.",
            code="ORACLE_USER_LIST_DISPLAY_COLUMN_REQUIRED",
            status_code=400,
        )

    result = await database.oracle_user_list_columns.insert_many(documents)
    responses: list[dict] = []
    for document, inserted_id in zip(documents, result.inserted_ids, strict=True):
        document["_id"] = inserted_id
        responses.append(_document_to_response(document))
    return responses


async def create_oracle_user_list_column(
    database,
    connection_id: str,
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
    label: str,
    created_by: str,
) -> dict:
    """Backward-compatible single-column create wrapper."""

    results = await create_oracle_user_list_columns(
        database,
        connection_id,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        columns=[{"display_column": display_column, "label": label}],
        created_by=created_by,
    )
    return results[0]


async def delete_oracle_user_list_column(
    database,
    connection_id: str,
    column_id: str,
) -> None:
    result = await database.oracle_user_list_columns.delete_one(
        {"_id": _parse_id(column_id), "connection_id": connection_id}
    )
    if result.deleted_count == 0:
        raise AppError(
            "Additional user-list column not found.",
            code="ORACLE_USER_LIST_COLUMN_NOT_FOUND",
            status_code=404,
        )


async def enrich_oracle_user_list(
    database,
    connection_id: str,
    *,
    connection: dict,
    items: list[dict],
) -> tuple[list[dict], list[dict]]:
    columns = await list_oracle_user_list_columns(database, connection_id)
    if not columns or not items:
        for item in items:
            item.setdefault("extra_values", {})
        return items, columns

    usernames = [str(item["username"]) for item in items]
    by_username = {str(item["username"]): item for item in items}
    for item in items:
        item["extra_values"] = {}

    # Group display columns by source relationship. This is the key optimization:
    # TBL1.STATUS + TBL1.EMPLOYEE_ID uses one Oracle query, not one query per column.
    grouped: OrderedDict[tuple[str, str, str], list[dict]] = OrderedDict()
    for column in columns:
        key = (
            column["owner"],
            column["table_name"],
            column["join_column"],
        )
        grouped.setdefault(key, []).append(column)

    enriched_by_id: dict[str, dict] = {}
    for (owner, table_name, join_column), source_columns in grouped.items():
        warning = None
        try:
            values, duplicate_keys = await fetch_oracle_user_list_values_multi(
                connection,
                usernames,
                owner=owner,
                table_name=table_name,
                join_column=join_column,
                display_columns=[column["display_column"] for column in source_columns],
            )
        except AppError as exc:
            # A custom source must never take down the authoritative DBA_USERS list.
            values = {}
            duplicate_keys = set()
            warning = exc.message

        for username, item in by_username.items():
            source_values = values.get(username, {})
            for column in source_columns:
                item["extra_values"][column["id"]] = source_values.get(
                    column["display_column"]
                )

        for column in source_columns:
            enriched = dict(column)
            enriched["duplicate_matches"] = len(duplicate_keys)
            enriched["warning"] = warning
            enriched_by_id[column["id"]] = enriched

    # Keep configured column order stable even though queries were grouped by source.
    enriched_columns = [enriched_by_id[column["id"]] for column in columns]
    return items, enriched_columns
