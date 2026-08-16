from fastapi import APIRouter, Depends, Request, Response, status

from app.dependencies.auth import get_current_user
from app.schemas.database_connection import (
    DatabaseConnectionCreate,
    DatabaseConnectionResponse,
    DatabaseConnectionUpdate,
    DatabaseConnectionTestResponse,
)
from app.schemas.user import UserResponse
from app.services.database_connections import (
    connection_to_response,
    create_database_connection,
    delete_database_connection,
    get_database_connection,
    list_database_connections,
    update_database_connection,
    test_database_connection,
)
from app.core.permissions import Permission
from app.dependencies.permissions import require_permission


router = APIRouter(
    prefix="/connections",
    tags=["Database Connections"],
)


@router.get(
    "",
    response_model=list[DatabaseConnectionResponse],
)
async def get_connections(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await list_database_connections(
        request.app.state.database
    )

@router.post(
    "/{connection_id}/test",
    response_model=DatabaseConnectionTestResponse,
)
async def test_connection(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_TEST)),
):
    return await test_database_connection(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}",
    response_model=DatabaseConnectionResponse,
)
async def get_connection(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    connection = await get_database_connection(
        request.app.state.database,
        connection_id,
    )

    return connection_to_response(connection)


@router.post(
    "",
    response_model=DatabaseConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    data: DatabaseConnectionCreate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_MANAGE)),
):
    return await create_database_connection(
        request.app.state.database,
        data,
    )


@router.put(
    "/{connection_id}",
    response_model=DatabaseConnectionResponse,
)
async def update_connection(
    connection_id: str,
    data: DatabaseConnectionUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_MANAGE)),
):
    return await update_database_connection(
        request.app.state.database,
        connection_id,
        data,
    )


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connection(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_MANAGE)),
):
    await delete_database_connection(
        request.app.state.database,
        connection_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

