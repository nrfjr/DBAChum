import asyncio
import time

from app.core.exceptions import AppError
from app.services.server_monitoring import _connect_transport_sync, resolve_ssh_target


DEFAULT_REMOTE_OPERATION_TIMEOUT = 4 * 60 * 60
MAX_CAPTURE_BYTES = 64 * 1024


def _append_tail(buffer: bytearray, chunk: bytes) -> None:
    buffer.extend(chunk)
    if len(buffer) > MAX_CAPTURE_BYTES:
        del buffer[:-MAX_CAPTURE_BYTES]


def _run_script_sync(target, script: str, timeout: float):
    transport, _latency_ms = _connect_transport_sync(target)
    channel = None
    try:
        channel = transport.open_session(timeout=30.0)
        channel.exec_command("sh -s")
        channel.sendall(script.encode("utf-8"))
        channel.shutdown_write()

        stdout = bytearray()
        stderr = bytearray()
        deadline = time.monotonic() + timeout

        while True:
            progressed = False
            while channel.recv_ready():
                _append_tail(stdout, channel.recv(32768))
                progressed = True
            while channel.recv_stderr_ready():
                _append_tail(stderr, channel.recv_stderr(32768))
                progressed = True

            if (
                channel.exit_status_ready()
                and not channel.recv_ready()
                and not channel.recv_stderr_ready()
            ):
                break

            if time.monotonic() >= deadline:
                raise AppError(
                    f"Remote database operation exceeded the {int(timeout)} second timeout.",
                    code="DATABASE_REMOTE_OPERATION_TIMEOUT",
                    status_code=408,
                )
            if not progressed:
                time.sleep(0.05)

        exit_status = channel.recv_exit_status()
        return {
            "stdout": bytes(stdout).decode("utf-8", errors="replace"),
            "stderr": bytes(stderr).decode("utf-8", errors="replace"),
            "exit_status": int(exit_status),
        }
    finally:
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass
        transport.close()


async def resolve_database_operation_server(database, connection: dict, server_id: str | None):
    linked = [str(item) for item in connection.get("server_ids", []) if item]
    if server_id:
        if server_id not in linked:
            raise AppError(
                "The selected server is not linked to this database connection.",
                code="DATABASE_OPERATION_SERVER_NOT_LINKED",
                status_code=400,
            )
        chosen = server_id
    else:
        if not linked:
            raise AppError(
                "This operation requires a linked Server / SSH entry.",
                code="DATABASE_OPERATION_SERVER_REQUIRED",
                status_code=409,
            )
        if len(linked) > 1:
            raise AppError(
                "Multiple servers are linked. Select the server that should run this operation.",
                code="DATABASE_OPERATION_SERVER_AMBIGUOUS",
                status_code=409,
            )
        chosen = linked[0]
    return await resolve_ssh_target(database, chosen)


async def run_database_remote_script(
    database,
    connection: dict,
    *,
    server_id: str | None,
    script: str,
    timeout: float = DEFAULT_REMOTE_OPERATION_TIMEOUT,
) -> dict:
    target = await resolve_database_operation_server(database, connection, server_id)
    result = await asyncio.to_thread(_run_script_sync, target, script, timeout)
    result.update(
        {
            "server_id": str(target.server["_id"]),
            "server_name": target.server.get("name", target.target),
            "ssh_target": target.target,
        }
    )
    if result["exit_status"] != 0:
        detail = result["stderr"].strip() or result["stdout"].strip() or f"exit status {result['exit_status']}"
        raise AppError(
            f"Remote database operation failed on {target.server.get('name', target.target)}: {detail[-2000:]}",
            code="DATABASE_REMOTE_OPERATION_FAILED",
            status_code=400,
        )
    return result
