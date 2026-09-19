from collections import OrderedDict
from datetime import datetime, timezone

from bson import ObjectId

from app.connectors.user_list_source import (
    fetch_user_list_source_values_multi,
    list_user_list_source_columns,
    list_user_list_source_schemas,
    list_user_list_source_tables,
    source_join_type_supported,
)
from app.core.exceptions import AppError
from app.services.database_connections import connection_is_active, get_database_connection


MAX_EXTRA_COLUMNS = 8
BASE_COLUMNS = {
    "USERNAME": "username",
    "STATUS": "status",
    "DEFAULT_TABLESPACE": "default_tablespace",
    "TEMPORARY_TABLESPACE": "temporary_tablespace",
    "PROFILE": "profile",
}


def _parse_id(column_id: str) -> ObjectId:
    try:
        return ObjectId(column_id)
    except Exception as exc:
        raise AppError(
            "Additional user-list column not found.",
            code="ORACLE_USER_LIST_COLUMN_NOT_FOUND",
            status_code=404,
        ) from exc


async def _get_target_oracle_connection(database, connection_id: str) -> dict:
    connection = await get_database_connection(database, connection_id)
    if connection.get("engine") != "oracle":
        raise AppError(
            "Additional user-list columns are only available for Oracle user lists.",
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


async def _get_source_connection(database, source_connection_id: str) -> dict:
    connection = await get_database_connection(database, source_connection_id)
    if not connection_is_active(connection):
        raise AppError(
            "The selected source database connection is disabled.",
            code="ORACLE_USER_LIST_SOURCE_CONNECTION_DISABLED",
            status_code=400,
        )
    return connection


def _normalize_base_column(value: str | None) -> str:
    normalized = str(value or "USERNAME").strip().upper()
    if normalized not in BASE_COLUMNS:
        raise AppError(
            "The selected main-list relationship column is not supported.",
            code="ORACLE_USER_LIST_BASE_COLUMN_INVALID",
            status_code=400,
        )
    return normalized


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
    source_connection_id: str | None,
    base_column: str,
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
) -> tuple[dict, str, dict, dict[str, dict]]:
    await _get_target_oracle_connection(database, connection_id)
    source_id = source_connection_id or connection_id
    source_connection = await _get_source_connection(database, source_id)
    normalized_base_column = _normalize_base_column(base_column)
    columns = await list_user_list_source_columns(source_connection, owner, table_name)
    column_map = {str(item["name"]).upper(): item for item in columns}

    join = column_map.get(join_column.strip().upper())
    if join is None:
        raise AppError(
            "The selected relationship column is not available in the source table.",
            code="ORACLE_USER_LIST_JOIN_COLUMN_NOT_FOUND",
            status_code=400,
        )
    if not source_join_type_supported(
        str(source_connection.get("engine") or ""),
        str(join.get("data_type") or ""),
    ):
        raise AppError(
            "The source relationship column must be a character column.",
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

    return source_connection, normalized_base_column, join, display_map


async def _validate_mapping(
    database,
    connection_id: str,
    *,
    source_connection_id: str | None,
    base_column: str,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
) -> tuple[dict, str, dict, dict]:
    source_connection, normalized_base_column, join, display_map = await _validate_mappings(
        database,
        connection_id,
        source_connection_id=source_connection_id,
        base_column=base_column,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[display_column],
    )
    return source_connection, normalized_base_column, join, next(iter(display_map.values()))


def _connection_name(connection: dict | None) -> str | None:
    if connection is None:
        return None
    return str(connection.get("name") or "") or None


def _document_to_response(
    document: dict,
    *,
    connection_id: str,
    source_connection: dict | None = None,
    duplicate_matches: int = 0,
    warning: str | None = None,
) -> dict:
    source_connection_id = str(document.get("source_connection_id") or connection_id)
    return {
        "id": str(document["_id"]),
        "label": document["label"],
        "source_connection_id": source_connection_id,
        "source_connection_name": _connection_name(source_connection),
        "source_engine": source_connection.get("engine") if source_connection else None,
        "base_column": str(document.get("base_column") or "USERNAME").upper(),
        "owner": document["owner"],
        "table_name": document["table_name"],
        "join_column": document["join_column"],
        "display_column": document["display_column"],
        "duplicate_matches": duplicate_matches,
        "warning": warning,
    }


async def _load_source_connections(database, connection_id: str, documents: list[dict]) -> dict[str, dict | None]:
    source_ids = {str(document.get("source_connection_id") or connection_id) for document in documents}
    result: dict[str, dict | None] = {}
    for source_id in source_ids:
        try:
            result[source_id] = await get_database_connection(database, source_id)
        except AppError:
            result[source_id] = None
    return result


async def list_oracle_user_list_columns(database, connection_id: str) -> list[dict]:
    cursor = database.oracle_user_list_columns.find(
        {"connection_id": connection_id}
    ).sort("created_at", 1)
    documents = await cursor.to_list(None)
    source_connections = await _load_source_connections(database, connection_id, documents)
    return [
        _document_to_response(
            document,
            connection_id=connection_id,
            source_connection=source_connections.get(str(document.get("source_connection_id") or connection_id)),
        )
        for document in documents
    ]


async def list_user_list_source_schemas_for_connection(
    database,
    connection_id: str,
    source_connection_id: str,
) -> list[dict]:
    await _get_target_oracle_connection(database, connection_id)
    source_connection = await _get_source_connection(database, source_connection_id)
    return await list_user_list_source_schemas(source_connection)


async def list_user_list_source_tables_for_connection(
    database,
    connection_id: str,
    source_connection_id: str,
    owner: str,
) -> list[dict]:
    await _get_target_oracle_connection(database, connection_id)
    source_connection = await _get_source_connection(database, source_connection_id)
    return await list_user_list_source_tables(source_connection, owner)


async def list_user_list_source_columns_for_connection(
    database,
    connection_id: str,
    source_connection_id: str,
    owner: str,
    table_name: str,
) -> list[dict]:
    await _get_target_oracle_connection(database, connection_id)
    source_connection = await _get_source_connection(database, source_connection_id)
    return await list_user_list_source_columns(source_connection, owner, table_name)


def _base_value(item: dict, base_column: str) -> str | None:
    key = BASE_COLUMNS[base_column]
    value = item.get(key)
    if value is None:
        return None
    text = str(value)
    return text if text else None


async def preview_oracle_user_list_columns(
    database,
    connection_id: str,
    *,
    source_connection_id: str | None,
    base_column: str,
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

    source_connection, normalized_base_column, join, display_map = await _validate_mappings(
        database,
        connection_id,
        source_connection_id=source_connection_id,
        base_column=base_column,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[item["display_column"] for item in selections],
    )

    keyed_users = [
        (item, _base_value(item, normalized_base_column))
        for item in base_users
    ]
    keys = list(dict.fromkeys(value for _, value in keyed_users if value is not None))
    values, duplicate_keys = await fetch_user_list_source_values_multi(
        source_connection,
        keys,
        owner=owner,
        table_name=table_name,
        join_column=str(join["name"]),
        display_columns=[str(display_map[item["display_column"]]["name"]) for item in selections],
    )

    preview_pair = next(
        ((item, value) for item, value in keyed_users if value is not None and value in values),
        next(((item, value) for item, value in keyed_users if value is not None), None),
    )
    if preview_pair is None:
        raise AppError(
            "No Oracle users have a value in the selected main-list relationship column.",
            code="ORACLE_USER_LIST_PREVIEW_NO_USERS",
            status_code=400,
        )

    preview_user, source_key = preview_pair
    warning = None
    if source_key in duplicate_keys:
        warning = (
            "This relationship found multiple source rows for the previewed user. "
            "DBAChum will keep the main user-list row intact and use the first source row."
        )
    elif not values:
        warning = (
            "No current user-list row matched this source relationship. "
            "The added columns will show — when no source row exists."
        )

    row_values = values.get(source_key or "", {})
    return {
        "username": str(preview_user["username"]),
        "status": str(preview_user.get("status") or ""),
        "values": [
            {
                "display_column": str(display_map[item["display_column"]]["name"]),
                "label": item["label"],
                "value": row_values.get(str(display_map[item["display_column"]]["name"])),
            }
            for item in selections
        ],
        "matched": source_key in values if source_key is not None else False,
        "duplicate_match": source_key in duplicate_keys if source_key is not None else False,
        "warning": warning,
    }


async def preview_oracle_user_list_column(
    database,
    connection_id: str,
    *,
    source_connection_id: str | None,
    base_column: str,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
    label: str,
    base_users: list[dict],
) -> dict:
    result = await preview_oracle_user_list_columns(
        database,
        connection_id,
        source_connection_id=source_connection_id,
        base_column=base_column,
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
    source_connection_id: str | None,
    base_column: str,
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

    source_connection, normalized_base_column, join, display_map = await _validate_mappings(
        database,
        connection_id,
        source_connection_id=source_connection_id,
        base_column=base_column,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[item["display_column"] for item in selections],
    )
    source_id = source_connection_id or connection_id

    existing_documents = await database.oracle_user_list_columns.find(
        {"connection_id": connection_id}
    ).to_list(None)
    if len(existing_documents) + len(selections) > MAX_EXTRA_COLUMNS:
        remaining = max(0, MAX_EXTRA_COLUMNS - len(existing_documents))
        raise AppError(
            f"A maximum of {MAX_EXTRA_COLUMNS} additional columns can be shown for one user list. "
            f"You can add {remaining} more.",
            code="ORACLE_USER_LIST_COLUMN_LIMIT",
            status_code=400,
        )

    owner_normalized = owner.strip()
    table_normalized = table_name.strip()
    join_normalized = str(join["name"])

    existing_labels = {
        str(item.get("label_key") or item.get("label", "")).casefold()
        for item in existing_documents
    }
    existing_sources = {
        (
            str(item.get("source_connection_id") or connection_id),
            str(item.get("base_column") or "USERNAME").upper(),
            str(item.get("owner") or "").upper(),
            str(item.get("table_name") or "").upper(),
            str(item.get("join_column") or "").upper(),
            str(item.get("display_column") or "").upper(),
        )
        for item in existing_documents
    }

    for item in selections:
        if item["label_key"] in existing_labels:
            raise AppError(
                f"An additional column with the label '{item['label']}' already exists.",
                code="ORACLE_USER_LIST_COLUMN_LABEL_EXISTS",
                status_code=409,
            )
        source_key = (
            source_id,
            normalized_base_column,
            owner_normalized.upper(),
            table_normalized.upper(),
            join_normalized.upper(),
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
            "source_connection_id": source_id,
            "base_column": normalized_base_column,
            "label": item["label"],
            "label_key": item["label_key"],
            "owner": owner_normalized,
            "table_name": table_normalized,
            "join_column": join_normalized,
            "display_column": str(display_map[item["display_column"]]["name"]),
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
        responses.append(
            _document_to_response(
                document,
                connection_id=connection_id,
                source_connection=source_connection,
            )
        )
    return responses


async def create_oracle_user_list_column(
    database,
    connection_id: str,
    *,
    source_connection_id: str | None,
    base_column: str,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
    label: str,
    created_by: str,
) -> dict:
    results = await create_oracle_user_list_columns(
        database,
        connection_id,
        source_connection_id=source_connection_id,
        base_column=base_column,
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

    for item in items:
        item["extra_values"] = {}

    grouped: OrderedDict[tuple[str, str, str, str, str], list[dict]] = OrderedDict()
    for column in columns:
        key = (
            column["source_connection_id"],
            column["base_column"],
            column["owner"],
            column["table_name"],
            column["join_column"],
        )
        grouped.setdefault(key, []).append(column)

    source_cache: dict[str, dict] = {connection_id: connection}
    enriched_by_id: dict[str, dict] = {}

    for (source_id, base_column, owner, table_name, join_column), source_columns in grouped.items():
        warning = None
        values: dict[str, dict[str, str | None]] = {}
        duplicate_keys: set[str] = set()
        try:
            source_connection = source_cache.get(source_id)
            if source_connection is None:
                source_connection = await _get_source_connection(database, source_id)
                source_cache[source_id] = source_connection
            keys = list(
                dict.fromkeys(
                    value
                    for item in items
                    if (value := _base_value(item, base_column)) is not None
                )
            )
            values, duplicate_keys = await fetch_user_list_source_values_multi(
                source_connection,
                keys,
                owner=owner,
                table_name=table_name,
                join_column=join_column,
                display_columns=[column["display_column"] for column in source_columns],
            )
        except AppError as exc:
            warning = exc.message

        for item in items:
            base_value = _base_value(item, base_column)
            source_values = values.get(base_value or "", {})
            for column in source_columns:
                item["extra_values"][column["id"]] = source_values.get(column["display_column"])

        for column in source_columns:
            enriched = dict(column)
            enriched["duplicate_matches"] = len(duplicate_keys)
            enriched["warning"] = warning or column.get("warning")
            enriched_by_id[column["id"]] = enriched

    enriched_columns = [enriched_by_id[column["id"]] for column in columns]
    return items, enriched_columns
