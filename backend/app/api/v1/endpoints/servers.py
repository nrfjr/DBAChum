from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)

from app.dependencies.auth import get_current_user
from app.schemas.database_connection import (
    DatabaseConnectionResponse,
)
from app.schemas.server import (
    ServerCreate,
    ServerResponse,
    ServerUpdate,
)
from app.schemas.user import UserResponse
from app.services.database_connections import (
    connection_to_response,
)
from app.services.servers import (
    create_server,
    delete_server,
    get_server,
    list_server_databases,
    list_servers,
    server_to_response,
    update_server,
)


router = APIRouter(
    prefix="/servers",
    tags=["Servers"],
)


@router.get(
    "",
    response_model=list[ServerResponse],
)
async def get_servers(
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await list_servers(
        request.app.state.database
    )


@router.get(
    "/{server_id}",
    response_model=ServerResponse,
)
async def get_server_detail(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    server = await get_server(
        request.app.state.database,
        server_id,
    )

    return await server_to_response(
        request.app.state.database,
        server,
    )


@router.get(
    "/{server_id}/databases",
    response_model=list[DatabaseConnectionResponse],
)
async def get_server_database_list(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    connections = await list_server_databases(
        request.app.state.database,
        server_id,
    )

    return [
        connection_to_response(connection)
        for connection in connections
    ]


@router.post(
    "",
    response_model=ServerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_server_endpoint(
    data: ServerCreate,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await create_server(
        request.app.state.database,
        data,
    )


@router.put(
    "/{server_id}",
    response_model=ServerResponse,
)
async def update_server_endpoint(
    server_id: str,
    data: ServerUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await update_server(
        request.app.state.database,
        server_id,
        data,
    )


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_server_endpoint(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    await delete_server(
        request.app.state.database,
        server_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )