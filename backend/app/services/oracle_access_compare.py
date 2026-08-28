from app.connectors.oracle_access_compare import get_oracle_access_compare
from app.services.oracle_dba import get_oracle_target


async def load_oracle_access_compare(database, connection_id: str, left_username: str, right_username: str):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_access_compare(connection, left_username, right_username)
