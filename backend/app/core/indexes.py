import logging


logger = logging.getLogger(__name__)


async def create_indexes(
    database,
) -> None:
    await database.users.create_index(
        "username",
        unique=True,
        name="uq_users_username",
    )

    await database.auth_sessions.create_index(
        "token_hash",
        unique=True,
        name="uq_auth_sessions_token_hash",
    )

    await database.auth_sessions.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="ttl_auth_sessions_expires_at",
    )

    logger.info(
        "MongoDB indexes verified"
    )