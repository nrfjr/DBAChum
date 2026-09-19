from datetime import date, datetime
from decimal import Decimal

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.oracle_provisioning import (
    normalize_oracle_identifier,
    quote_oracle_identifier,
)
from app.core.exceptions import AppError


MAX_BIND_VALUES = 500
FILTER_OPERATORS = {"=", "!=", "IN", "IS NULL", "IS NOT NULL"}


def _display_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _chunks(values: list[str], size: int = MAX_BIND_VALUES):
    for start in range(0, len(values), size):
        yield values[start : start + size]


async def fetch_oracle_user_list_values_multi(
    connection: dict,
    usernames: list[str],
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
    filters: list[dict] | None = None,
) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    """Fetch several display columns from one mapped source in one query per bind chunk.

    The source relationship is shared by every requested display column. DBA_USERS remains
    authoritative: duplicate source rows never create duplicate base-list rows. The first
    source row returned by Oracle is retained and the username is reported in duplicate_keys.
    """

    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")
    join_column = normalize_oracle_identifier(join_column, field_name="Relationship column")

    normalized_display_columns: list[str] = []
    seen: set[str] = set()
    for display_column in display_columns:
        normalized = normalize_oracle_identifier(
            display_column,
            field_name="Display column",
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_display_columns.append(normalized)

    normalized_filters: list[dict] = []
    for source_filter in filters or []:
        filter_column = normalize_oracle_identifier(
            str(source_filter.get("column") or ""),
            field_name="Filter column",
        )
        operator = " ".join(str(source_filter.get("operator") or "=").strip().upper().split())
        if operator not in FILTER_OPERATORS:
            raise AppError(
                "Unsupported source filter operator.",
                code="ORACLE_USER_LIST_FILTER_INVALID",
                status_code=400,
            )
        normalized_filters.append(
            {
                "column": filter_column,
                "operator": operator,
                "value": source_filter.get("value"),
            }
        )

    if not usernames or not normalized_display_columns:
        return {}, set()

    table_ref = (
        f"{quote_oracle_identifier(owner)}."
        f"{quote_oracle_identifier(table_name)}"
    )
    join_ref = quote_oracle_identifier(join_column)
    display_refs = [
        quote_oracle_identifier(column)
        for column in normalized_display_columns
    ]

    values: dict[str, dict[str, str | None]] = {}
    duplicate_keys: set[str] = set()

    async with open_oracle_connection(connection) as oracle_connection:
        for chunk in _chunks(usernames):
            binds = {f"u{index}": username for index, username in enumerate(chunk)}
            placeholders = ", ".join(f":u{index}" for index in range(len(chunk)))
            projection = ", ".join([join_ref, *display_refs])
            where_parts = [f"{join_ref} IN ({placeholders})"]
            for filter_index, source_filter in enumerate(normalized_filters):
                filter_ref = quote_oracle_identifier(source_filter["column"])
                operator = source_filter["operator"]
                if operator in {"IS NULL", "IS NOT NULL"}:
                    where_parts.append(f"{filter_ref} {operator}")
                elif operator == "IN":
                    filter_values = [
                        part.strip()
                        for part in str(source_filter.get("value") or "").split(",")
                        if part.strip()
                    ]
                    filter_placeholders: list[str] = []
                    for value_index, filter_value in enumerate(filter_values):
                        bind_name = f"f{filter_index}_{value_index}"
                        binds[bind_name] = filter_value
                        filter_placeholders.append(f":{bind_name}")
                    where_parts.append(f"{filter_ref} IN ({', '.join(filter_placeholders)})")
                else:
                    bind_name = f"f{filter_index}"
                    binds[bind_name] = str(source_filter.get("value") or "")
                    where_parts.append(f"{filter_ref} {operator} :{bind_name}")
            sql = f"""
                SELECT {projection}
                FROM {table_ref}
                WHERE {' AND '.join(where_parts)}
            """
            try:
                rows = await oracle_connection.fetchall(sql, binds)
            except oracledb.Error as exc:
                raise AppError(
                    oracle_error_message(exc),
                    code="ORACLE_USER_LIST_ENRICHMENT_FAILED",
                    status_code=400,
                ) from exc

            for row in rows:
                raw_key = row[0]
                key = str(raw_key) if raw_key is not None else ""
                if not key:
                    continue
                if key in values:
                    duplicate_keys.add(key)
                    continue
                values[key] = {
                    column: _display_value(row[index + 1])
                    for index, column in enumerate(normalized_display_columns)
                }

    return values, duplicate_keys


async def fetch_oracle_user_list_values(
    connection: dict,
    usernames: list[str],
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_column: str,
) -> tuple[dict[str, str | None], set[str]]:
    """Backward-compatible single-column wrapper."""

    normalized_display = normalize_oracle_identifier(
        display_column,
        field_name="Display column",
    )
    rows, duplicate_keys = await fetch_oracle_user_list_values_multi(
        connection,
        usernames,
        owner=owner,
        table_name=table_name,
        join_column=join_column,
        display_columns=[normalized_display],
    )
    return (
        {
            username: values.get(normalized_display)
            for username, values in rows.items()
        },
        duplicate_keys,
    )
