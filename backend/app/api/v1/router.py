from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    alerts,
    auth,
    collector,
    database_connections,
    database_actions,
    database_operations,
    database_parameters,
    database_performance,
    database_backups,
    database_jobs,
    databases,
    health,
    oracle_dba,
    profile,
    provisioning,
    records,
    mysql_dba,
    notification_delivery,
    sqlserver_dba,
    servers,
    server_monitoring,
    server_terminal,
    ssh_access,
    terminal_shortcuts,
    users,
    system_settings,
)


api_router = APIRouter()

api_router.include_router(analytics.router)
api_router.include_router(health.router)
api_router.include_router(alerts.router)
api_router.include_router(auth.router)
api_router.include_router(collector.router)
api_router.include_router(database_connections.router)
api_router.include_router(database_actions.router)
api_router.include_router(database_operations.router)
api_router.include_router(database_parameters.router)
api_router.include_router(database_performance.router)
api_router.include_router(database_backups.router)
api_router.include_router(database_jobs.router)
api_router.include_router(databases.router)
api_router.include_router(oracle_dba.router)
api_router.include_router(profile.router)
api_router.include_router(provisioning.router)
api_router.include_router(records.router)
api_router.include_router(sqlserver_dba.router)
api_router.include_router(mysql_dba.router)
api_router.include_router(notification_delivery.router)
api_router.include_router(servers.router)
api_router.include_router(server_monitoring.router)
api_router.include_router(server_terminal.router)
api_router.include_router(ssh_access.router)
api_router.include_router(terminal_shortcuts.router)
api_router.include_router(users.router)
api_router.include_router(system_settings.router)