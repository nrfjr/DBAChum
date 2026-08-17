from pymongo.errors import CollectionInvalid

from app.core.config import settings


METRICS_COLLECTION_NAME = (
    "database_metric_samples"
)


async def ensure_metrics_collection(
    database,
) -> None:
    expire_after_seconds = (
        max(
            settings.metrics_retention_days,
            1,
        )
        * 24
        * 60
        * 60
    )

    collection_names = (
        await database.list_collection_names()
    )

    if (
        METRICS_COLLECTION_NAME
        not in collection_names
    ):
        try:
            await database.create_collection(
                METRICS_COLLECTION_NAME,

                timeseries={
                    "timeField":
                        "collected_at",

                    "metaField":
                        "meta",

                    "granularity":
                        "seconds",
                },

                expireAfterSeconds=(
                    expire_after_seconds
                ),
            )

        except CollectionInvalid:
            pass

    await database.command(
        {
            "collMod":
                METRICS_COLLECTION_NAME,

            "expireAfterSeconds":
                expire_after_seconds,
        }
    )