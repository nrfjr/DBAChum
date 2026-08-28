from app.connectors.oracle_access_lookup import get_oracle_access_lookup
from app.services.oracle_dba import get_oracle_target


async def load_oracle_access_lookup(
    database,
    connection_id: str,
    *,
    kind: str,
    value: str | None = None,
    owner: str | None = None,
    object_name: str | None = None,
    privilege: str | None = None,
):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_access_lookup(
        connection,
        kind=kind,
        value=value,
        owner=owner,
        object_name=object_name,
        privilege=privilege,
    )
