from fastapi import APIRouter, Depends, Request, Response, status

from app.dependencies.auth import get_current_user
from app.schemas.database_connection import (
    DatabaseConnectionCreate,
    DatabaseConnectionResponse,
    DatabaseConnectionUpdate,
)
from app.schemas.user import UserResponse
from app.services.database_connections import (
    connection_to_response,
    create_database_connection,
    delete_database_connection,
    get_database_connection,
    list_database_connections,
    update_database_connection,
)


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
    current_user: UserResponse = Depends(get_current_user),
):
    return await list_database_connections(
        request.app.state.database
    )


@router.get(
    "/{connection_id}",
    response_model=DatabaseConnectionResponse,
)
async def get_connection(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
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
    current_user: UserResponse = Depends(get_current_user),
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
    current_user: UserResponse = Depends(get_current_user),
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
    current_user: UserResponse = Depends(get_current_user),
):
    await delete_database_connection(
        request.app.state.database,
        connection_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)