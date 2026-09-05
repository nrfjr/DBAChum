from mysql.connector import Error as MySQLError


PROCESS_LIST_LIMIT = 250


def _processlist_sql(source: str, database_name: str | None) -> tuple[str, tuple]:
    database_filter = ""
    params: list[object] = []

    if database_name:
        database_filter = " AND DB = %s"
        params.append(database_name)

    sql = f"""
        SELECT
            ID,
            USER,
            HOST,
            DB,
            COMMAND,
            TIME,
            STATE,
            INFO

        FROM {source}

        WHERE ID <> CONNECTION_ID()
        {database_filter}

        ORDER BY
            CASE
                WHEN COMMAND <> 'Sleep'
                THEN 0
                ELSE 1
            END,
            TIME DESC

        LIMIT {PROCESS_LIST_LIMIT}
    """

    return sql, tuple(params)


def fetch_processlist(
    cursor,
    capabilities: dict[str, bool] | None = None,
    database_name: str | None = None,
) -> tuple[list[tuple], str]:
    capabilities = capabilities or {}

    if capabilities.get("performance_schema_processlist"):
        sql, params = _processlist_sql(
            "performance_schema.processlist",
            database_name,
        )
        try:
            cursor.execute(sql, params)
            return cursor.fetchall(), "performance_schema.processlist"
        except MySQLError:
            pass

    sql, params = _processlist_sql(
        "information_schema.processlist",
        database_name,
    )
    cursor.execute(sql, params)
    return cursor.fetchall(), "information_schema.processlist"
