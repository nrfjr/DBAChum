from app.connectors.oracle_access_inspector import get_oracle_user_access_inspector
from app.services.oracle_dba import get_oracle_target


async def load_oracle_user_access_inspector(database, connection_id: str, username: str):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_user_access_inspector(connection, username)
