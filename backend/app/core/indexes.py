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

    # Email is optional during the 7B.1 identity rollout. The partial unique
    # index only applies to users that actually have an email_key, preserving
    # compatibility with existing local accounts.
    await database.users.create_index(
        "email_key",
        unique=True,
        partialFilterExpression={
            "email_key": {"$type": "string"}
        },
        name="uq_users_email_key",
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
    

    # Phase 8.3 human-readable operational Records catalog.
    await database.records.create_index(
        "identity_key",
        unique=True,
        name="uq_records_identity_key",
    )

    await database.records.create_index(
        "record_type",
        name="ix_records_type",
    )

    await database.records.create_index(
        "environment",
        name="ix_records_environment",
    )

    await database.records.create_index(
        "connection_id",
        name="ix_records_connection_id",
    )

    await database.records.create_index(
        "server_id",
        name="ix_records_server_id",
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
    await database.alerts.create_index(
        "alert_key",
        unique=True,
        name="uq_alerts_alert_key",
    )

    await database.alerts.create_index(
        [
            ("status", 1),
            ("severity", 1),
            ("last_seen_at", -1),
        ],
        name="ix_alerts_status_severity_last_seen",
    )

    await database.alerts.create_index(
        [
            ("source_type", 1),
            ("source_id", 1),
            ("rule_key", 1),
        ],
        name="ix_alerts_source_rule",
    )
    # Phase 7B.4 outbound-email outbox. Event keys deduplicate alert
    # notifications per incident/severity/user, while the TTL keeps delivery
    # diagnostics useful without becoming permanent application telemetry.
    await database.email_deliveries.create_index(
        "event_key",
        unique=True,
        name="uq_email_deliveries_event_key",
    )

    await database.email_deliveries.create_index(
        [("status", 1), ("next_attempt_at", 1), ("created_at", 1)],
        name="ix_email_deliveries_status_next_created",
    )

    await database.email_deliveries.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="ttl_email_deliveries_expires_at",
    )



    await database.app_settings.create_index(
        "updated_at",
        name="ix_app_settings_updated",
    )

    await database.analytics_daily_snapshots.create_index(
        [("target_type", 1), ("target_id", 1), ("day", 1)],
        unique=True,
        name="uq_analytics_daily_target_day",
    )

    await database.analytics_daily_snapshots.create_index(
        [("target_type", 1), ("day", -1)],
        name="ix_analytics_daily_type_day",
    )

    await database.analytics_daily_snapshots.create_index(
        [("target_type", 1), ("target_id", 1), ("collected_at", -1)],
        name="ix_analytics_daily_target_collected",
    )
