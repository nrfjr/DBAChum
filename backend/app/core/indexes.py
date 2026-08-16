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
    
    await database.database_connections.create_index(
        "name_key",
        unique=True,
        name="uq_database_connections_name_key",
    )

    await database.database_connections.create_index(
        "engine",
        name="ix_database_connections_engine",
    )
    
    await database.servers.create_index(
        "name_key",
        unique=True,
        name="uq_servers_name_key",
    )

    await database.servers.create_index(
        "environment",
        name="ix_servers_environment",
    )

    await database.database_connections.create_index(
        "server_ids",
        name="ix_database_connections_server_ids",
    )
