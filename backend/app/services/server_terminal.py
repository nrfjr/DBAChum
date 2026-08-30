import asyncio
import socket
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import AppError
from app.schemas.terminal_shortcut import TerminalSessionAuditResponse
from app.services.server_monitoring import _connect_transport_sync, resolve_ssh_target
from app.services.terminal_shortcuts import get_terminal_shortcut_for_server


MAX_TERMINALS_PER_USER = 3
TERMINAL_RECV_SIZE = 32768
TERMINAL_KEEPALIVE_SECONDS = 30


class TerminalSessionRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, set[str]] = defaultdict(set)

    async def reserve(self, user_id: str, session_id: str) -> None:
        async with self._lock:
            sessions = self._sessions[user_id]
            if len(sessions) >= MAX_TERMINALS_PER_USER:
                raise AppError(
                    f"You already have {MAX_TERMINALS_PER_USER} active SSH terminals. Close one before opening another.",
                    code="TERMINAL_SESSION_LIMIT",
                    status_code=409,
                )
            sessions.add(session_id)

    async def release(self, user_id: str, session_id: str) -> None:
        async with self._lock:
            sessions = self._sessions.get(user_id)
            if not sessions:
                return
            sessions.discard(session_id)
            if not sessions:
                self._sessions.pop(user_id, None)


terminal_registry = TerminalSessionRegistry()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def start_terminal_audit(database, *, session_id: str, user: dict, target) -> None:
    profile = target.profile
    await database.terminal_session_audit.insert_one(
        {
            "session_id": session_id,
            "operator_user_id": str(user["_id"]),
            "operator_username": user.get("username", "unknown"),
            "server_id": str(target.server["_id"]),
            "server_name": target.server.get("name", target.target),
            "target": target.target,
            "ssh_username": target.username,
            "ssh_profile_id": str(profile["_id"]),
            "ssh_profile_name": profile.get("name", "SSH profile"),
            "started_at": _utcnow(),
            "ended_at": None,
            "duration_seconds": None,
            "close_reason": None,
            "status": "connecting",
            "input_bytes": 0,
            "output_bytes": 0,
            "shortcut_actions": [],
        }
    )


async def mark_terminal_connected(database, session_id: str) -> None:
    await database.terminal_session_audit.update_one(
        {"session_id": session_id},
        {"$set": {"status": "connected"}},
    )


async def finish_terminal_audit(
    database,
    *,
    session_id: str,
    started_monotonic: float,
    close_reason: str,
    status: str,
    input_bytes: int,
    output_bytes: int,
) -> None:
    await database.terminal_session_audit.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "ended_at": _utcnow(),
                "duration_seconds": round(max(time.monotonic() - started_monotonic, 0.0), 2),
                "close_reason": close_reason[:512],
                "status": status,
                "input_bytes": input_bytes,
                "output_bytes": output_bytes,
            }
        },
    )


async def audit_shortcut(database, *, session_id: str, shortcut: dict) -> None:
    await database.terminal_session_audit.update_one(
        {"session_id": session_id},
        {
            "$push": {
                "shortcut_actions": {
                    "shortcut_id": str(shortcut["_id"]),
                    "name": shortcut.get("name", "Shortcut"),
                    "mode": shortcut.get("mode", "execute"),
                    "used_at": _utcnow(),
                }
            }
        },
    )


def _open_shell_sync(target, cols: int, rows: int) -> tuple[Any, Any]:
    transport, _latency_ms = _connect_transport_sync(target)
    try:
        transport.set_keepalive(TERMINAL_KEEPALIVE_SECONDS)
        channel = transport.open_session(timeout=10.0)
        channel.get_pty(
            term="xterm-256color",
            width=max(20, min(cols, 500)),
            height=max(5, min(rows, 200)),
        )
        channel.invoke_shell()
        channel.settimeout(0.0)
        return transport, channel
    except Exception:
        transport.close()
        raise


def _resize_sync(channel, cols: int, rows: int) -> None:
    channel.resize_pty(
        width=max(20, min(cols, 500)),
        height=max(5, min(rows, 200)),
    )


def _send_sync(channel, data: str) -> int:
    payload = data.encode("utf-8", errors="replace")
    if not payload:
        return 0
    channel.sendall(payload)
    return len(payload)


def _recv_sync(channel) -> bytes:
    try:
        if channel.recv_ready():
            return channel.recv(TERMINAL_RECV_SIZE)
    except socket.timeout:
        return b""
    return b""


async def list_terminal_audit(database, *, limit: int = 50) -> list[TerminalSessionAuditResponse]:
    docs = await database.terminal_session_audit.find().sort("started_at", -1).limit(limit).to_list(None)
    return [
        TerminalSessionAuditResponse(
            session_id=doc["session_id"],
            operator_user_id=doc["operator_user_id"],
            operator_username=doc.get("operator_username", "unknown"),
            server_id=doc["server_id"],
            server_name=doc.get("server_name", doc.get("target", "Server")),
            target=doc.get("target", ""),
            ssh_username=doc.get("ssh_username", ""),
            ssh_profile_id=doc.get("ssh_profile_id", ""),
            ssh_profile_name=doc.get("ssh_profile_name", ""),
            started_at=doc["started_at"],
            ended_at=doc.get("ended_at"),
            duration_seconds=doc.get("duration_seconds"),
            close_reason=doc.get("close_reason"),
            status=doc.get("status", "unknown"),
            input_bytes=doc.get("input_bytes", 0),
            output_bytes=doc.get("output_bytes", 0),
            shortcut_actions=doc.get("shortcut_actions", []),
        )
        for doc in docs
    ]


async def run_terminal_session(websocket, database, *, user: dict, server_id: str, cols: int, rows: int) -> None:
    session_id = str(uuid.uuid4())
    user_id = str(user["_id"])
    started_monotonic = time.monotonic()
    transport = None
    channel = None
    input_bytes = 0
    output_bytes = 0
    close_reason = "client disconnected"
    final_status = "closed"
    audit_started = False

    await terminal_registry.reserve(user_id, session_id)
    try:
        target = await resolve_ssh_target(database, server_id)
        await start_terminal_audit(database, session_id=session_id, user=user, target=target)
        audit_started = True

        transport, channel = await asyncio.to_thread(_open_shell_sync, target, cols, rows)
        await mark_terminal_connected(database, session_id)
        await websocket.send_json(
            {
                "type": "ready",
                "session_id": session_id,
                "server_id": server_id,
                "server_name": target.server.get("name", target.target),
                "target": target.target,
                "ssh_username": target.username,
                "max_sessions": MAX_TERMINALS_PER_USER,
            }
        )

        async def output_loop() -> None:
            nonlocal output_bytes, close_reason
            while True:
                if channel.closed or not transport.is_active():
                    close_reason = "remote SSH session closed"
                    try:
                        await websocket.send_json({"type": "closed", "message": close_reason})
                        await websocket.close()
                    except Exception:
                        pass
                    return
                data = await asyncio.to_thread(_recv_sync, channel)
                if data:
                    output_bytes += len(data)
                    await websocket.send_json(
                        {
                            "type": "output",
                            "data": data.decode("utf-8", errors="replace"),
                        }
                    )
                    continue
                await asyncio.sleep(0.025)

        output_task = asyncio.create_task(output_loop())
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")

                if message_type == "input":
                    data = str(message.get("data", ""))
                    sent = await asyncio.to_thread(_send_sync, channel, data)
                    input_bytes += sent

                elif message_type == "resize":
                    await asyncio.to_thread(
                        _resize_sync,
                        channel,
                        int(message.get("cols", 80)),
                        int(message.get("rows", 24)),
                    )

                elif message_type == "shortcut":
                    shortcut_id = str(message.get("shortcut_id", ""))
                    shortcut = await get_terminal_shortcut_for_server(database, shortcut_id, server_id)
                    command = shortcut["command"]
                    if shortcut.get("mode", "execute") == "execute":
                        command = f"{command}\r"
                    sent = await asyncio.to_thread(_send_sync, channel, command)
                    input_bytes += sent
                    await audit_shortcut(database, session_id=session_id, shortcut=shortcut)
                    await websocket.send_json(
                        {
                            "type": "shortcut_ack",
                            "shortcut_id": shortcut_id,
                            "name": shortcut.get("name", "Shortcut"),
                            "mode": shortcut.get("mode", "execute"),
                        }
                    )

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif message_type == "close":
                    close_reason = "closed by user"
                    return
        finally:
            output_task.cancel()
            await asyncio.gather(output_task, return_exceptions=True)

    except AppError as exc:
        close_reason = exc.message
        final_status = "failed"
        try:
            await websocket.send_json({"type": "error", "code": exc.code, "message": exc.message})
        except Exception:
            pass
    except Exception as exc:
        name = exc.__class__.__name__
        if name == "WebSocketDisconnect":
            if close_reason == "client disconnected":
                close_reason = "browser disconnected"
        else:
            close_reason = str(exc).strip() or name
            final_status = "failed"
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "TERMINAL_SESSION_FAILED",
                        "message": f"SSH terminal session failed: {close_reason}",
                    }
                )
            except Exception:
                pass
    finally:
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        if audit_started:
            await finish_terminal_audit(
                database,
                session_id=session_id,
                started_monotonic=started_monotonic,
                close_reason=close_reason,
                status=final_status,
                input_bytes=input_bytes,
                output_bytes=output_bytes,
            )
        await terminal_registry.release(user_id, session_id)
