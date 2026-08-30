from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    collector,
    database_connections,
    database_actions,
    databases,
    health,
    oracle_dba,
    provisioning,
    mysql_dba,
    sqlserver_dba,
    servers,
    server_monitoring,
    server_terminal,
    ssh_access,
    terminal_shortcuts,
    users,
)


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(collector.router)
api_router.include_router(database_connections.router)
api_router.include_router(database_actions.router)
api_router.include_router(databases.router)
api_router.include_router(oracle_dba.router)
api_router.include_router(provisioning.router)
api_router.include_router(sqlserver_dba.router)
api_router.include_router(mysql_dba.router)
api_router.include_router(servers.router)
api_router.include_router(server_monitoring.router)
api_router.include_router(server_terminal.router)
api_router.include_router(ssh_access.router)
api_router.include_router(terminal_shortcuts.router)
api_router.include_router(users.router)