from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    database_connections,
    databases,
    health,
    oracle_dba,
)


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(database_connections.router)
api_router.include_router(databases.router)
api_router.include_router(oracle_dba.router)