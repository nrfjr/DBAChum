from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message


ADVISOR_DEFINITIONS = (
    {
        "key": "sga",
        "label": "SGA",
        "sql": """
            SELECT
                sga_size,
                sga_size_factor,
                estd_db_time,
                estd_db_time_factor,
                estd_physical_reads
            FROM v$sga_target_advice
            ORDER BY sga_size
        """,
        "mapper": lambda row, index: {
            "size_mb": float(row[0]) if row[0] is not None else None,
            "size_factor": float(row[1]) if row[1] is not None else None,
            "current": _is_current_factor(row[1]),
            "estimated_db_time": _float_or_none(row[2]),
            "estimated_db_time_factor": _float_or_none(row[3]),
            "estimated_physical_reads": _int_or_none(row[4]),
        },
    },
    {
        "key": "pga",
        "label": "PGA",
        "sql": """
            SELECT
                pga_target_for_estimate,
                pga_target_factor,
                advice_status,
                estd_time,
                estd_extra_bytes_rw,
                estd_pga_cache_hit_percentage,
                estd_overalloc_count
            FROM v$pga_target_advice
            ORDER BY pga_target_for_estimate
        """,
        "status_index": 2,
        "mapper": lambda row, index: {
            "size_mb": _bytes_to_mb(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_time": _float_or_none(row[3]),
            "estimated_extra_bytes_rw": _int_or_none(row[4]),
            "estimated_cache_hit_percent": _float_or_none(row[5]),
            "estimated_overalloc_count": _int_or_none(row[6]),
        },
    },
    {
        "key": "buffer_cache",
        "label": "Buffer Cache",
        "sql": """
            SELECT
                size_for_estimate,
                size_factor,
                advice_status,
                estd_physical_read_factor,
                estd_physical_reads
            FROM v$db_cache_advice
            WHERE name = 'DEFAULT'
              AND block_size = TO_NUMBER((SELECT value FROM v$parameter WHERE name = 'db_block_size'))
            ORDER BY size_for_estimate
        """,
        "status_index": 2,
        "mapper": lambda row, index: {
            "size_mb": _float_or_none(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_physical_read_factor": _float_or_none(row[3]),
            "estimated_physical_reads": _int_or_none(row[4]),
        },
    },
    {
        "key": "shared_pool",
        "label": "Shared Pool",
        "sql": """
            SELECT
                shared_pool_size_for_estimate,
                shared_pool_size_factor,
                estd_lc_time_saved,
                estd_lc_time_saved_factor,
                estd_lc_load_time,
                estd_lc_load_time_factor
            FROM v$shared_pool_advice
            ORDER BY shared_pool_size_for_estimate
        """,
        "mapper": lambda row, index: {
            "size_mb": _float_or_none(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_lc_time_saved": _float_or_none(row[2]),
            "estimated_lc_time_saved_factor": _float_or_none(row[3]),
            "estimated_lc_load_time": _float_or_none(row[4]),
            "estimated_lc_load_time_factor": _float_or_none(row[5]),
        },
    },
    {
        "key": "memory_target",
        "label": "Memory Target",
        "sql": """
            SELECT
                memory_size,
                memory_size_factor,
                estd_db_time,
                estd_db_time_factor
            FROM v$memory_target_advice
            ORDER BY memory_size
        """,
        "mapper": lambda row, index: {
            "size_mb": _float_or_none(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_db_time": _float_or_none(row[2]),
            "estimated_db_time_factor": _float_or_none(row[3]),
        },
    },
    {
        "key": "java_pool",
        "label": "Java Pool",
        "sql": """
            SELECT
                java_pool_size_for_estimate,
                java_pool_size_factor,
                estd_lc_time_saved,
                estd_lc_time_saved_factor,
                estd_lc_load_time,
                estd_lc_load_time_factor
            FROM v$java_pool_advice
            ORDER BY java_pool_size_for_estimate
        """,
        "mapper": lambda row, index: {
            "size_mb": _float_or_none(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_lc_time_saved": _float_or_none(row[2]),
            "estimated_lc_time_saved_factor": _float_or_none(row[3]),
            "estimated_lc_load_time": _float_or_none(row[4]),
            "estimated_lc_load_time_factor": _float_or_none(row[5]),
        },
    },
    {
        "key": "streams_pool",
        "label": "Streams Pool",
        "sql": """
            SELECT
                streams_pool_size_for_estimate,
                streams_pool_size_factor,
                estd_spill_count,
                estd_spill_time,
                estd_unspill_count,
                estd_unspill_time
            FROM v$streams_pool_advice
            ORDER BY streams_pool_size_for_estimate
        """,
        "mapper": lambda row, index: {
            "size_mb": _float_or_none(row[0]),
            "size_factor": _float_or_none(row[1]),
            "current": _is_current_factor(row[1]),
            "estimated_spill_count": _int_or_none(row[2]),
            "estimated_spill_time": _float_or_none(row[3]),
            "estimated_unspill_count": _int_or_none(row[4]),
            "estimated_unspill_time": _float_or_none(row[5]),
        },
    },
    {
        "key": "mttr",
        "label": "MTTR",
        "sql": """
            SELECT
                mttr_target_for_estimate,
                advice_status,
                estd_cache_writes,
                estd_cache_write_factor,
                estd_total_writes,
                estd_total_write_factor,
                estd_total_ios,
                estd_total_io_factor
            FROM v$mttr_target_advice
        """,
        "status_index": 1,
        "mapper": lambda row, index: {
            "mttr_target_seconds": _int_or_none(row[0]),
            "current": index == 0,
            "estimated_cache_writes": _int_or_none(row[2]),
            "estimated_cache_write_factor": _float_or_none(row[3]),
            "estimated_total_writes": _int_or_none(row[4]),
            "estimated_total_write_factor": _float_or_none(row[5]),
            "estimated_total_ios": _int_or_none(row[6]),
            "estimated_total_io_factor": _float_or_none(row[7]),
        },
        "sort_key": lambda item: item.get("mttr_target_seconds") or 0,
    },
)


def _float_or_none(value):
    return float(value) if value is not None else None


def _int_or_none(value):
    return int(value) if value is not None else None


def _bytes_to_mb(value):
    if value is None:
        return None
    return float(value) / 1024 / 1024


def _is_current_factor(value):
    if value is None:
        return False
    return abs(float(value) - 1.0) < 0.0001


async def get_oracle_advisors(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    sections = []

    async with open_oracle_connection(connection) as oracle_connection:
        for definition in ADVISOR_DEFINITIONS:
            try:
                rows = await oracle_connection.fetchall(definition["sql"])
                items = [
                    definition["mapper"](row, index)
                    for index, row in enumerate(rows)
                ]
                sort_key = definition.get("sort_key")
                if sort_key:
                    items.sort(key=sort_key)

                sections.append(
                    {
                        "key": definition["key"],
                        "label": definition["label"],
                        "available": bool(items),
                        "advice_status": (
                            str(rows[0][definition["status_index"]])
                            if rows and definition.get("status_index") is not None
                            and rows[0][definition["status_index"]] is not None
                            else None
                        ),
                        "items": items,
                        "warning": None,
                    }
                )
            except oracledb.Error as exc:
                sections.append(
                    {
                        "key": definition["key"],
                        "label": definition["label"],
                        "available": False,
                        "advice_status": None,
                        "items": [],
                        "warning": oracle_error_message(exc),
                    }
                )

    return {
        "available": any(section["available"] for section in sections),
        "sections": sections,
        "checked_at": checked_at,
    }
