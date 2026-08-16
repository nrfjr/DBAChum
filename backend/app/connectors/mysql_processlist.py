from mysql.connector import Error as MySQLError


PROCESS_LIST_LIMIT = 250


async def fetch_processlist(
    cursor,
):
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

        FROM performance_schema.processlist

        WHERE ID <> CONNECTION_ID()

        ORDER BY
            CASE
                WHEN COMMAND <> 'Sleep'
                THEN 0
                ELSE 1
            END,
            TIME DESC

        LIMIT {PROCESS_LIST_LIMIT}
    """

    try:
        await cursor.execute(sql)
        return await cursor.fetchall()

    except MySQLError:
        # Compatibility fallback for installations
        # without Performance Schema processlist.
        await cursor.execute(
            f"""
            SELECT
                ID,
                USER,
                HOST,
                DB,
                COMMAND,
                TIME,
                STATE,
                INFO

            FROM information_schema.processlist

            WHERE ID <> CONNECTION_ID()

            ORDER BY
                CASE
                    WHEN COMMAND <> 'Sleep'
                    THEN 0
                    ELSE 1
                END,
                TIME DESC

            LIMIT {PROCESS_LIST_LIMIT}
            """
        )

        return await cursor.fetchall()