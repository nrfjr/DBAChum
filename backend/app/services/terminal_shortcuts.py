from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.schemas.terminal_shortcut import (
    TerminalShortcutCreate,
    TerminalShortcutResponse,
    TerminalShortcutUpdate,
)
from app.services.servers import get_server


def _parse_shortcut_id(shortcut_id: str) -> ObjectId:
    try:
        return ObjectId(shortcut_id)
    except Exception as exc:
        raise AppError(
            "Terminal shortcut not found.",
            code="TERMINAL_SHORTCUT_NOT_FOUND",
            status_code=404,
        ) from exc


def _name_key(name: str) -> str:
    return name.strip().lower()


async def _validate_server_ids(database, server_ids: list[str]) -> None:
    if not server_ids:
        return
    object_ids: list[ObjectId] = []
    for server_id in server_ids:
        try:
            object_ids.append(ObjectId(server_id))
        except Exception as exc:
            raise AppError(
                "One or more terminal shortcut server assignments are invalid.",
                code="INVALID_TERMINAL_SHORTCUT_SERVER",
                status_code=400,
            ) from exc
    count = await database.servers.count_documents({"_id": {"$in": object_ids}})
    if count != len(object_ids):
        raise AppError(
            "One or more terminal shortcut server assignments no longer exist.",
            code="TERMINAL_SHORTCUT_SERVER_NOT_FOUND",
            status_code=400,
        )


def _to_response(doc: dict) -> TerminalShortcutResponse:
    server_ids = doc.get("server_ids", [])
    return TerminalShortcutResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        category=doc.get("category", "General"),
        command=doc["command"],
        mode=doc.get("mode", "execute"),
        server_ids=server_ids,
        enabled=doc.get("enabled", True),
        sort_order=doc.get("sort_order", 100),
        scope_label="All SSH-enabled servers" if not server_ids else f"{len(server_ids)} selected server{'s' if len(server_ids) != 1 else ''}",
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


async def list_terminal_shortcuts(database) -> list[TerminalShortcutResponse]:
    docs = await database.terminal_shortcuts.find().sort(
        [("category", 1), ("sort_order", 1), ("name", 1)]
    ).to_list(None)
    return [_to_response(doc) for doc in docs]


async def list_terminal_shortcuts_for_server(database, server_id: str) -> list[TerminalShortcutResponse]:
    await get_server(database, server_id)
    docs = await database.terminal_shortcuts.find(
        {
            "enabled": True,
            "$or": [
                {"server_ids": {"$size": 0}},
                {"server_ids": server_id},
                {"server_ids": {"$exists": False}},
            ],
        }
    ).sort([("category", 1), ("sort_order", 1), ("name", 1)]).to_list(None)
    return [_to_response(doc) for doc in docs]


async def get_terminal_shortcut_for_server(database, shortcut_id: str, server_id: str) -> dict:
    object_id = _parse_shortcut_id(shortcut_id)
    doc = await database.terminal_shortcuts.find_one({"_id": object_id})
    if doc is None or not doc.get("enabled", True):
        raise AppError(
            "Terminal shortcut is unavailable.",
            code="TERMINAL_SHORTCUT_NOT_FOUND",
            status_code=404,
        )
    server_ids = doc.get("server_ids", [])
    if server_ids and server_id not in server_ids:
        raise AppError(
            "This terminal shortcut is not assigned to the selected server.",
            code="TERMINAL_SHORTCUT_NOT_ASSIGNED",
            status_code=403,
        )
    return doc


async def create_terminal_shortcut(database, data: TerminalShortcutCreate) -> TerminalShortcutResponse:
    await _validate_server_ids(database, data.server_ids)
    now = datetime.now(timezone.utc)
    doc = data.model_dump(mode="json")
    doc.update({"name_key": _name_key(data.name), "created_at": now, "updated_at": now})
    try:
        result = await database.terminal_shortcuts.insert_one(doc)
    except DuplicateKeyError as exc:
        raise AppError(
            "A terminal shortcut with this name already exists.",
            code="TERMINAL_SHORTCUT_NAME_EXISTS",
            status_code=409,
        ) from exc
    return _to_response(await database.terminal_shortcuts.find_one({"_id": result.inserted_id}))


async def update_terminal_shortcut(database, shortcut_id: str, data: TerminalShortcutUpdate) -> TerminalShortcutResponse:
    object_id = _parse_shortcut_id(shortcut_id)
    await _validate_server_ids(database, data.server_ids)
    doc = data.model_dump(mode="json")
    doc.update({"name_key": _name_key(data.name), "updated_at": datetime.now(timezone.utc)})
    try:
        result = await database.terminal_shortcuts.update_one({"_id": object_id}, {"$set": doc})
    except DuplicateKeyError as exc:
        raise AppError(
            "A terminal shortcut with this name already exists.",
            code="TERMINAL_SHORTCUT_NAME_EXISTS",
            status_code=409,
        ) from exc
    if result.matched_count == 0:
        raise AppError("Terminal shortcut not found.", code="TERMINAL_SHORTCUT_NOT_FOUND", status_code=404)
    return _to_response(await database.terminal_shortcuts.find_one({"_id": object_id}))


async def delete_terminal_shortcut(database, shortcut_id: str) -> None:
    object_id = _parse_shortcut_id(shortcut_id)
    result = await database.terminal_shortcuts.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise AppError("Terminal shortcut not found.", code="TERMINAL_SHORTCUT_NOT_FOUND", status_code=404)
