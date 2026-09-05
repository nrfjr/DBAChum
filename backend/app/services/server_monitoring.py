import asyncio
import base64
import hashlib
import io
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.core.exceptions import AppError
from app.core.security import decrypt_secret
from app.schemas.server import ServerOsFamily
from app.schemas.server_monitoring import (
    ServerFilesystemSnapshot,
    ServerHealthSnapshot,
    ServerMemorySnapshot,
    ServerProcessSnapshot,
    ServerServiceSnapshot,
    SshConnectionState,
    SshConnectionTestResponse,
)
from app.schemas.ssh_access import SshAuthType
from app.services.servers import get_server
from app.services.server_monitoring_parsers import (
    parse_df_pk,
    parse_proc_meminfo,
    parse_proc_stat_pair,
    parse_ps,
    parse_systemd_failed,
    parse_uptime_load,
    parse_uptime_command,
    parse_vmstat_cpu,
    parse_svmon_global,
    parse_aix_src_inoperative,
)


CONNECT_TIMEOUT_SECONDS = 8.0
AUTH_TIMEOUT_SECONDS = 30.0
COMMAND_TIMEOUT_SECONDS = 10.0


@dataclass
class ResolvedSshTarget:
    server: dict
    profile: dict
    target: str
    port: int
    username: str
    trusted_fingerprint: str | None


@dataclass
class RemoteCommandResult:
    stdout: str
    stderr: str
    exit_status: int


def _load_paramiko():
    try:
        import paramiko  # type: ignore
    except ImportError as exc:
        raise AppError(
            "SSH support is not installed on the DBAChum backend. Install the updated backend requirements and restart DBAChum.",
            code="SSH_RUNTIME_MISSING",
            status_code=503,
        ) from exc
    return paramiko


def _fingerprint_for_key(key) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def _normalize_fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


async def resolve_ssh_target(database, server_id: str) -> ResolvedSshTarget:
    server = await get_server(database, server_id)

    if not server.get("enabled", True):
        raise AppError(
            "This server asset is disabled.",
            code="SERVER_DISABLED",
            status_code=409,
        )

    profile_id = server.get("ssh_profile_id")
    if not profile_id:
        raise AppError(
            "No SSH access profile is assigned to this server.",
            code="SSH_PROFILE_NOT_ASSIGNED",
            status_code=409,
        )

    try:
        profile_object_id = ObjectId(profile_id)
    except Exception as exc:
        raise AppError(
            "The assigned SSH access profile is invalid.",
            code="INVALID_SSH_PROFILE",
            status_code=409,
        ) from exc

    profile = await database.ssh_access_profiles.find_one({"_id": profile_object_id})
    if profile is None:
        raise AppError(
            "The assigned SSH access profile no longer exists.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=409,
        )
    if not profile.get("enabled", True):
        raise AppError(
            "The assigned SSH access profile is disabled.",
            code="SSH_PROFILE_DISABLED",
            status_code=409,
        )

    target = (server.get("ip_address") or server.get("hostname") or "").strip()
    if not target:
        raise AppError(
            "This server has no usable hostname or IP address.",
            code="SSH_TARGET_MISSING",
            status_code=409,
        )

    return ResolvedSshTarget(
        server=server,
        profile=profile,
        target=target,
        port=int(profile.get("port", 22)),
        username=profile["username"],
        trusted_fingerprint=_normalize_fingerprint(server.get("ssh_host_key_fingerprint")),
    )


def _probe_host_key_sync(target: ResolvedSshTarget) -> tuple[str, float]:
    paramiko = _load_paramiko()
    started = time.perf_counter()
    sock = None
    transport = None
    try:
        sock = socket.create_connection(
            (target.target, target.port),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
        transport = paramiko.Transport(sock)
        transport.banner_timeout = CONNECT_TIMEOUT_SECONDS
        transport.start_client(timeout=CONNECT_TIMEOUT_SECONDS)
        key = transport.get_remote_server_key()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return _fingerprint_for_key(key), latency_ms
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            f"Unable to reach SSH on {target.target}:{target.port}: {exc}",
            code="SSH_CONNECTION_FAILED",
            status_code=502,
        ) from exc
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        elif sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _load_private_key(paramiko, private_key: str, passphrase: str | None):
    key_types = [
        getattr(paramiko, "Ed25519Key", None),
        getattr(paramiko, "ECDSAKey", None),
        getattr(paramiko, "RSAKey", None),
    ]
    errors: list[str] = []
    for key_type in key_types:
        if key_type is None:
            continue
        try:
            return key_type.from_private_key(
                io.StringIO(private_key),
                password=passphrase,
            )
        except Exception as exc:
            errors.append(str(exc))

    detail = errors[-1] if errors else "unsupported key format"
    raise AppError(
        f"The stored SSH private key could not be loaded: {detail}",
        code="SSH_PRIVATE_KEY_INVALID",
        status_code=409,
    )


def _connect_transport_sync(target: ResolvedSshTarget) -> tuple[Any, float]:
    paramiko = _load_paramiko()
    started = time.perf_counter()
    sock = None
    transport = None
    try:
        sock = socket.create_connection(
            (target.target, target.port),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
        transport = paramiko.Transport(sock)
        transport.banner_timeout = CONNECT_TIMEOUT_SECONDS
        transport.auth_timeout = AUTH_TIMEOUT_SECONDS
        transport.start_client(timeout=CONNECT_TIMEOUT_SECONDS)

        remote_key = transport.get_remote_server_key()
        fingerprint = _fingerprint_for_key(remote_key)
        trusted = target.trusted_fingerprint
        if not trusted:
            raise AppError(
                f"SSH host key is not trusted yet. Fingerprint: {fingerprint}",
                code="SSH_HOST_KEY_UNTRUSTED",
                status_code=409,
            )
        if fingerprint != trusted:
            raise AppError(
                f"SSH host key mismatch. Expected {trusted}, received {fingerprint}. Do not continue until the host identity is verified.",
                code="SSH_HOST_KEY_MISMATCH",
                status_code=409,
            )

        auth_type = target.profile.get("auth_type", SshAuthType.PASSWORD.value)
        if auth_type == SshAuthType.PRIVATE_KEY.value:
            encrypted_key = target.profile.get("private_key_encrypted")
            if not encrypted_key:
                raise AppError(
                    "The SSH profile has no stored private key.",
                    code="SSH_PRIVATE_KEY_REQUIRED",
                    status_code=409,
                )
            private_key = decrypt_secret(encrypted_key)
            passphrase = None
            if target.profile.get("passphrase_encrypted"):
                passphrase = decrypt_secret(target.profile["passphrase_encrypted"])
            pkey = _load_private_key(paramiko, private_key, passphrase)
            transport.auth_publickey(target.username, pkey)
        else:
            encrypted_password = target.profile.get("password_encrypted")
            if not encrypted_password:
                raise AppError(
                    "The SSH profile has no stored password.",
                    code="SSH_PASSWORD_REQUIRED",
                    status_code=409,
                )

            transport.auth_password(
                target.username,
                decrypt_secret(encrypted_password),
                fallback=True,
            )

        if not transport.is_authenticated():
            raise AppError(
                "SSH authentication failed.",
                code="SSH_AUTHENTICATION_FAILED",
                status_code=502,
            )

        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return transport, latency_ms
    except AppError:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        elif sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        raise
    except Exception as exc:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        elif sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        text = str(exc).strip() or exc.__class__.__name__
        class_name = exc.__class__.__name__
        lower_text = text.lower()

        if "authentication" in lower_text and "timeout" in lower_text:
            raise AppError(
                f"SSH authentication timed out after {AUTH_TIMEOUT_SECONDS:.0f} seconds. "
                "The SSH connection and host key succeeded, but the server did not finish authentication in time.",
                code="SSH_AUTHENTICATION_TIMEOUT",
                status_code=504,
            ) from exc

        if class_name == "BadAuthenticationType":
            allowed = getattr(exc, "allowed_types", None) or []
            allowed_text = ", ".join(allowed) if allowed else "unknown"
            raise AppError(
                f"The SSH server does not allow this profile's authentication method. "
                f"Server allows: {allowed_text}.",
                code="SSH_AUTHENTICATION_METHOD_NOT_ALLOWED",
                status_code=409,
            ) from exc

        if "Authentication failed" in text or "AuthenticationException" in class_name:
            auth_type = target.profile.get("auth_type", SshAuthType.PASSWORD.value)
            method = "password" if auth_type == SshAuthType.PASSWORD.value else "private-key"
            raise AppError(
                f"SSH {method} authentication was rejected by the server for user {target.username}. "
                "The SSH endpoint and trusted host key were reached successfully.",
                code="SSH_AUTHENTICATION_FAILED",
                status_code=502,
            ) from exc
        raise AppError(
            f"Unable to establish SSH connection to {target.target}:{target.port}: {text}",
            code="SSH_CONNECTION_FAILED",
            status_code=502,
        ) from exc


def _run_command_sync(transport, command: str, timeout: float = COMMAND_TIMEOUT_SECONDS) -> RemoteCommandResult:
    channel = transport.open_session(timeout=timeout)
    try:
        channel.settimeout(timeout)
        channel.exec_command(command)
        stdout = channel.makefile("rb", -1).read().decode("utf-8", errors="replace")
        stderr = channel.makefile_stderr("rb", -1).read().decode("utf-8", errors="replace")
        exit_status = channel.recv_exit_status()
        return RemoteCommandResult(stdout=stdout, stderr=stderr, exit_status=exit_status)
    finally:
        channel.close()


def _safe_command(transport, command: str, warnings: list[str], label: str) -> RemoteCommandResult | None:
    try:
        result = _run_command_sync(transport, command)
        if result.exit_status != 0 and not result.stdout.strip():
            detail = result.stderr.strip() or f"exit status {result.exit_status}"
            warnings.append(f"{label} unavailable: {detail}")
            return None
        return result
    except Exception as exc:
        warnings.append(f"{label} unavailable: {str(exc).strip() or exc.__class__.__name__}")
        return None


def _collect_posix_health_sync(target: ResolvedSshTarget) -> ServerHealthSnapshot:
    transport, latency_ms = _connect_transport_sync(target)
    warnings: list[str] = []
    try:
        identity = _safe_command(
            transport,
            "printf '%s\\n' \"$(hostname 2>/dev/null)\" \"$(uname -s 2>/dev/null)\" \"$(uname -r 2>/dev/null)\"",
            warnings,
            "Host identity",
        )
        identity_lines = identity.stdout.splitlines() if identity else []
        remote_hostname = identity_lines[0].strip() if len(identity_lines) > 0 else None
        os_name = identity_lines[1].strip() if len(identity_lines) > 1 else None
        kernel_release = identity_lines[2].strip() if len(identity_lines) > 2 else None

        uptime_result = _safe_command(
            transport,
            "if [ -r /proc/uptime ] && [ -r /proc/loadavg ]; then awk '{print $1}' /proc/uptime | tr '\\n' ' '; awk '{print $1, $2, $3}' /proc/loadavg; else uptime 2>/dev/null; fi",
            warnings,
            "Uptime/load",
        )
        uptime_text = uptime_result.stdout if uptime_result else ""
        uptime_seconds, load_1, load_5, load_15 = parse_uptime_load(uptime_text)
        if uptime_seconds is None and uptime_text:
            uptime_seconds, load_1, load_5, load_15 = parse_uptime_command(uptime_text)

        cpu_used_percent = None
        cpu_measurement = None
        first_cpu = _safe_command(transport, "head -n 1 /proc/stat 2>/dev/null", warnings, "CPU sample")
        if first_cpu and first_cpu.stdout.strip().startswith("cpu "):
            time.sleep(0.35)
            second_cpu = _safe_command(transport, "head -n 1 /proc/stat 2>/dev/null", warnings, "CPU sample")
            if second_cpu:
                cpu_used_percent = parse_proc_stat_pair(first_cpu.stdout, second_cpu.stdout)
                if cpu_used_percent is not None:
                    cpu_measurement = "Host CPU used during a short sample"
        if cpu_used_percent is None:
            vmstat = _safe_command(
                transport,
                "LC_ALL=C vmstat 1 2 2>/dev/null",
                warnings,
                "CPU fallback",
            )
            if vmstat:
                cpu_used_percent = parse_vmstat_cpu(vmstat.stdout)
                if cpu_used_percent is not None:
                    cpu_measurement = "Host CPU used from vmstat"

        memory = ServerMemorySnapshot()
        mem_result = _safe_command(transport, "cat /proc/meminfo 2>/dev/null", [], "Memory")
        if mem_result and "MemTotal" in mem_result.stdout:
            memory = parse_proc_meminfo(mem_result.stdout)
        else:
            svmon_result = _safe_command(
                transport,
                "command -v svmon >/dev/null 2>&1 && svmon -G -O unit=MB 2>/dev/null || true",
                [],
                "AIX memory",
            )
            aix_memory = parse_svmon_global(svmon_result.stdout if svmon_result else "")
            if aix_memory is not None:
                memory = aix_memory
            else:
                warnings.append("Detailed memory metrics are unavailable from /proc/meminfo or svmon on this host.")

        filesystems: list[ServerFilesystemSnapshot] = []
        df_result = _safe_command(
            transport,
            "LC_ALL=C df -Pk 2>/dev/null",
            warnings,
            "Filesystems",
        )
        if df_result:
            filesystems = parse_df_pk(df_result.stdout)
            filesystems.sort(key=lambda item: item.used_percent, reverse=True)

        top_processes: list[ServerProcessSnapshot] = []
        ps_result = _safe_command(
            transport,
            "LC_ALL=C ps -eo pid=,user=,pcpu=,pmem=,etime=,comm=,args= 2>/dev/null",
            warnings,
            "Processes",
        )
        if ps_result:
            top_processes = parse_ps(ps_result.stdout)

        services = ServerServiceSnapshot(
            manager="unknown",
            state="unknown",
            note="Service-manager detail is unavailable on this host.",
        )
        systemd_probe = _safe_command(
            transport,
            "command -v systemctl >/dev/null 2>&1 && systemctl is-system-running 2>/dev/null || true",
            [],
            "systemd",
        )
        if systemd_probe and systemd_probe.stdout.strip():
            state = systemd_probe.stdout.strip().splitlines()[-1]
            failed_result = _safe_command(
                transport,
                "systemctl --no-pager --plain --no-legend --failed --type=service 2>/dev/null || true",
                warnings,
                "Failed services",
            )
            failed = parse_systemd_failed(failed_result.stdout if failed_result else "")
            services = ServerServiceSnapshot(
                manager="systemd",
                state=state,
                failed_services=failed,
                note=None if not failed else f"{len(failed)} failed service(s) detected.",
            )
        else:
            src_result = _safe_command(
                transport,
                "command -v lssrc >/dev/null 2>&1 && lssrc -a 2>/dev/null || true",
                [],
                "AIX SRC",
            )
            if src_result and src_result.stdout.strip():
                failed = parse_aix_src_inoperative(src_result.stdout)
                services = ServerServiceSnapshot(
                    manager="src",
                    state="running" if not failed else "degraded",
                    failed_services=failed,
                    note=None if not failed else f"{len(failed)} inoperative subsystem(s) detected.",
                )

        return ServerHealthSnapshot(
            checked_at=datetime.now(timezone.utc),
            target=target.target,
            port=target.port,
            ssh_latency_ms=latency_ms,
            remote_hostname=remote_hostname,
            os_name=os_name,
            kernel_release=kernel_release,
            uptime_seconds=uptime_seconds,
            load_1=load_1,
            load_5=load_5,
            load_15=load_15,
            cpu_used_percent=cpu_used_percent,
            cpu_measurement=cpu_measurement,
            memory=memory,
            filesystems=filesystems,
            top_processes=top_processes,
            services=services,
            warnings=warnings,
        )
    finally:
        transport.close()


async def test_server_ssh(database, server_id: str) -> SshConnectionTestResponse:
    target = await resolve_ssh_target(database, server_id)
    fingerprint, probe_latency_ms = await asyncio.to_thread(_probe_host_key_sync, target)

    if not target.trusted_fingerprint:
        return SshConnectionTestResponse(
            state=SshConnectionState.UNTRUSTED,
            checked_at=datetime.now(timezone.utc),
            target=target.target,
            port=target.port,
            username=target.username,
            latency_ms=probe_latency_ms,
            fingerprint=fingerprint,
            trusted_fingerprint=None,
            message="SSH endpoint reached. Verify and trust this host key before DBAChum sends credentials.",
        )

    if fingerprint != target.trusted_fingerprint:
        raise AppError(
            f"SSH host key mismatch. Expected {target.trusted_fingerprint}, received {fingerprint}. Do not continue until the host identity is verified.",
            code="SSH_HOST_KEY_MISMATCH",
            status_code=409,
        )

    transport, authenticated_latency_ms = await asyncio.to_thread(_connect_transport_sync, target)
    transport.close()
    return SshConnectionTestResponse(
        state=SshConnectionState.CONNECTED,
        checked_at=datetime.now(timezone.utc),
        target=target.target,
        port=target.port,
        username=target.username,
        latency_ms=authenticated_latency_ms,
        fingerprint=fingerprint,
        trusted_fingerprint=target.trusted_fingerprint,
        message="SSH connection and authentication succeeded.",
    )


async def trust_server_ssh_host_key(
    database,
    server_id: str,
    requested_fingerprint: str,
) -> SshConnectionTestResponse:
    target = await resolve_ssh_target(database, server_id)
    fingerprint, probe_latency_ms = await asyncio.to_thread(_probe_host_key_sync, target)
    requested = _normalize_fingerprint(requested_fingerprint)
    if requested != fingerprint:
        raise AppError(
            f"The SSH host key changed before it could be trusted. Expected {requested}, received {fingerprint}.",
            code="SSH_HOST_KEY_CHANGED",
            status_code=409,
        )

    await database.servers.update_one(
        {"_id": target.server["_id"]},
        {
            "$set": {
                "ssh_host_key_fingerprint": fingerprint,
                "ssh_host_key_trusted_at": datetime.now(timezone.utc),
            }
        },
    )

    target.trusted_fingerprint = fingerprint
    transport, authenticated_latency_ms = await asyncio.to_thread(_connect_transport_sync, target)
    transport.close()

    return SshConnectionTestResponse(
        state=SshConnectionState.CONNECTED,
        checked_at=datetime.now(timezone.utc),
        target=target.target,
        port=target.port,
        username=target.username,
        latency_ms=authenticated_latency_ms or probe_latency_ms,
        fingerprint=fingerprint,
        trusted_fingerprint=fingerprint,
        message="SSH host key trusted and authentication succeeded.",
    )


async def collect_server_health(database, server_id: str) -> ServerHealthSnapshot:
    target = await resolve_ssh_target(database, server_id)
    os_family = target.server.get("os_family")
    if os_family == ServerOsFamily.WINDOWS.value:
        raise AppError(
            "Windows SSH connectivity can be tested, but host metrics are not enabled in this first Phase 5C collector.",
            code="SSH_WINDOWS_METRICS_NOT_SUPPORTED",
            status_code=501,
        )
    if os_family not in {
        ServerOsFamily.LINUX.value,
        ServerOsFamily.AIX.value,
        ServerOsFamily.UNIX.value,
    }:
        raise AppError(
            "SSH host metrics currently support Linux, AIX and Unix server assets.",
            code="SSH_METRICS_OS_NOT_SUPPORTED",
            status_code=501,
        )
    return await asyncio.to_thread(_collect_posix_health_sync, target)


def _collect_posix_telemetry_sync(target: ResolvedSshTarget) -> dict:

    transport, latency_ms = _connect_transport_sync(target)
    warnings: list[str] = []
    try:
        uptime_result = _safe_command(
            transport,
            "if [ -r /proc/uptime ] && [ -r /proc/loadavg ]; then awk '{print $1}' /proc/uptime | tr '\\n' ' '; awk '{print $1, $2, $3}' /proc/loadavg; else uptime 2>/dev/null; fi",
            warnings,
            "Uptime/load",
        )
        uptime_text = uptime_result.stdout if uptime_result else ""
        uptime_seconds, load_1, load_5, load_15 = parse_uptime_load(uptime_text)
        if uptime_seconds is None and uptime_text:
            uptime_seconds, load_1, load_5, load_15 = parse_uptime_command(uptime_text)

        cpu_used_percent = None
        first_cpu = _safe_command(
            transport,
            "head -n 1 /proc/stat 2>/dev/null",
            warnings,
            "CPU sample",
        )
        if first_cpu and first_cpu.stdout.strip().startswith("cpu "):
            time.sleep(0.35)
            second_cpu = _safe_command(
                transport,
                "head -n 1 /proc/stat 2>/dev/null",
                warnings,
                "CPU sample",
            )
            if second_cpu:
                cpu_used_percent = parse_proc_stat_pair(
                    first_cpu.stdout,
                    second_cpu.stdout,
                )
        if cpu_used_percent is None:
            vmstat = _safe_command(
                transport,
                "LC_ALL=C vmstat 1 2 2>/dev/null",
                warnings,
                "CPU fallback",
            )
            if vmstat:
                cpu_used_percent = parse_vmstat_cpu(vmstat.stdout)

        memory = ServerMemorySnapshot()
        mem_result = _safe_command(
            transport,
            "cat /proc/meminfo 2>/dev/null",
            [],
            "Memory",
        )
        if mem_result and "MemTotal" in mem_result.stdout:
            memory = parse_proc_meminfo(mem_result.stdout)
        else:
            svmon_result = _safe_command(
                transport,
                "command -v svmon >/dev/null 2>&1 && svmon -G -O unit=MB 2>/dev/null || true",
                [],
                "AIX memory",
            )
            aix_memory = parse_svmon_global(
                svmon_result.stdout if svmon_result else ""
            )
            if aix_memory is not None:
                memory = aix_memory
            else:
                warnings.append(
                    "Detailed memory metrics are unavailable from /proc/meminfo or svmon on this host."
                )

        filesystems: list[ServerFilesystemSnapshot] = []
        df_result = _safe_command(
            transport,
            "LC_ALL=C df -Pk 2>/dev/null",
            warnings,
            "Filesystems",
        )
        if df_result:
            filesystems = parse_df_pk(df_result.stdout)
            filesystems.sort(
                key=lambda item: item.used_percent,
                reverse=True,
            )

        return {
            "checked_at": datetime.now(timezone.utc),
            "status": "limited" if warnings else "online",
            "ssh_latency_ms": latency_ms,
            "uptime_seconds": uptime_seconds,
            "load_1": load_1,
            "load_5": load_5,
            "load_15": load_15,
            "cpu_used_percent": cpu_used_percent,
            "memory": memory.model_dump(mode="python"),
            "filesystems": [
                item.model_dump(mode="python")
                for item in filesystems
            ],
            "warnings": warnings,
            "error": None,
        }
    finally:
        transport.close()


async def collect_server_telemetry(database, server_id: str) -> dict:
    target = await resolve_ssh_target(database, server_id)
    os_family = target.server.get("os_family")
    if os_family == ServerOsFamily.WINDOWS.value:
        raise AppError(
            "Windows host telemetry is not enabled yet.",
            code="SSH_WINDOWS_METRICS_NOT_SUPPORTED",
            status_code=501,
        )
    if os_family not in {
        ServerOsFamily.LINUX.value,
        ServerOsFamily.AIX.value,
        ServerOsFamily.UNIX.value,
    }:
        raise AppError(
            "Background SSH metrics currently support Linux, AIX and Unix server assets.",
            code="SSH_METRICS_OS_NOT_SUPPORTED",
            status_code=501,
        )
    return await asyncio.to_thread(
        _collect_posix_telemetry_sync,
        target,
    )
