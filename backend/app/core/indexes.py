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

    await database.servers.create_index(
        "ssh_profile_id",
        name="ix_servers_ssh_profile_id",
    )

    await database.ssh_access_profiles.create_index(
        "name_key",
        unique=True,
        name="uq_ssh_access_profiles_name_key",
    )

    await database.terminal_shortcuts.create_index(
        "name_key",
        unique=True,
        name="uq_terminal_shortcuts_name_key",
    )

    await database.terminal_shortcuts.create_index(
        "server_ids",
        name="ix_terminal_shortcuts_server_ids",
    )

    await database.terminal_session_audit.create_index(
        "session_id",
        unique=True,
        name="uq_terminal_session_audit_session_id",
    )

    await database.terminal_session_audit.create_index(
        [("operator_user_id", 1), ("started_at", -1)],
        name="ix_terminal_session_audit_operator_started",
    )

    await database.terminal_session_audit.create_index(
        [("server_id", 1), ("started_at", -1)],
        name="ix_terminal_session_audit_server_started",
    )


    await database.database_action_audit.create_index(
        [
            ("connection_id", 1),
            ("started_at", -1),
        ],
        name="ix_database_action_audit_connection_started",
    )

    await database.database_action_audit.create_index(
        [
            ("operator_user_id", 1),
            ("started_at", -1),
        ],
        name="ix_database_action_audit_operator_started",
    )

    await database.provisioning_profiles.create_index(
        "name_key",
        unique=True,
        name="uq_provisioning_profiles_name_key",
    )

    await database.provisioning_profiles.create_index(
        "schema_connection_id",
        name="ix_provisioning_profiles_schema_connection",
    )

    await database.provisioning_profiles.create_index(
        "table_steps.connection_id",
        name="ix_provisioning_profiles_table_connections",
    )

    await database.provisioning_runs.create_index(
        [
            ("parent_connection_id", 1),
            ("username", 1),
            ("started_at", -1),
        ],
        name="ix_provisioning_runs_parent_username_started",
    )

    await database.provisioning_runs.create_index(
        [
            ("parent_connection_id", 1),
            ("started_at", -1),
        ],
        name="ix_provisioning_runs_parent_started",
    )

    await database.provisioning_runs.create_index(
        [
            ("profile_id", 1),
            ("started_at", -1),
        ],
        name="ix_provisioning_runs_profile_started",
    )
