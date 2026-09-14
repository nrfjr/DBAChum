from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError
from app.services.release_updates import (
    _parse_stable_version,
    _version_text,
    check_for_updates,
)


logger = logging.getLogger(__name__)

IN_PROGRESS_STATES = frozenset({"queued", "running"})
STATUS_FIELDS = (
    "update_id",
    "state",
    "requested_version",
    "installed_version",
    "created_at",
    "started_at",
    "finished_at",
    "message",
    "log_file",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _status_path(root: Path | None = None) -> Path:
    base = root or _project_root()
    return base / ".update" / "status.json"


def _is_windows() -> bool:
    return os.name == "nt"


def _normalize_release_version(value: str) -> str:
    parsed = _parse_stable_version(value)
    if parsed is None:
        raise AppError(
            "DBAChum in-app updates accept stable semantic versions only.",
            code="INVALID_UPDATE_VERSION",
            status_code=400,
        )
    return _version_text(parsed)


def _idle_status() -> dict[str, Any]:
    return {
        "update_id": None,
        "state": "idle",
        "requested_version": None,
        "installed_version": None,
        "created_at": None,
        "started_at": None,
        "finished_at": None,
        "message": "No DBAChum update is currently running.",
        "log_file": None,
    }


def get_update_install_status(*, root: Path | None = None) -> dict[str, Any]:
    path = _status_path(root)
    if not path.exists():
        return _idle_status()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Unable to read DBAChum update status from %s", path, exc_info=exc)
        return {
            **_idle_status(),
            "state": "unknown",
            "message": "DBAChum update status is unavailable.",
        }

    if not isinstance(payload, dict):
        return {
            **_idle_status(),
            "state": "unknown",
            "message": "DBAChum update status is unavailable.",
        }

    result = _idle_status()
    for field in STATUS_FIELDS:
        if field in payload:
            result[field] = payload[field]
    return result


def _queue_script_path(root: Path | None = None) -> Path:
    base = root or _project_root()
    return base / "scripts" / "windows" / "queue_dbachum_update.ps1"


def _build_queue_command(
    *,
    powershell: str,
    script: Path,
    root: Path,
    version: str,
    update_id: str,
) -> list[str]:
    return [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ReleaseVersion",
        version,
        "-UpdateId",
        update_id,
        "-TargetRoot",
        str(root),
    ]


def _queue_windows_update(*, version: str, update_id: str, root: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise AppError(
            "Windows PowerShell was not found; DBAChum cannot queue the update.",
            code="UPDATE_LAUNCH_FAILED",
            status_code=500,
        )

    script = _queue_script_path(root)
    if not script.is_file():
        raise AppError(
            "The DBAChum update launcher is missing from this installation.",
            code="UPDATE_LAUNCH_FAILED",
            status_code=500,
        )

    command = _build_queue_command(
        powershell=powershell,
        script=script,
        root=root,
        version=version,
        update_id=update_id,
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.exception("Unable to launch DBAChum update queue script")
        raise AppError(
            "DBAChum could not queue the update on Windows.",
            code="UPDATE_LAUNCH_FAILED",
            status_code=500,
        ) from exc

    if completed.returncode != 0:
        logger.error(
            "DBAChum update queue failed exit=%s stdout=%s stderr=%s",
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )
        raise AppError(
            "DBAChum could not queue the update. Review the server log for details.",
            code="UPDATE_LAUNCH_FAILED",
            status_code=500,
        )


async def queue_update_install(version: str) -> dict[str, Any]:
    normalized = _normalize_release_version(version)

    if not _is_windows():
        raise AppError(
            "DBAChum in-app installation is currently supported on Windows deployments only.",
            code="UPDATE_PLATFORM_UNSUPPORTED",
            status_code=501,
        )

    existing = get_update_install_status()
    if existing.get("state") in IN_PROGRESS_STATES:
        raise AppError(
            "A DBAChum update is already in progress.",
            code="UPDATE_ALREADY_RUNNING",
            status_code=409,
        )

    release = await check_for_updates(force_refresh=True)
    latest = release.get("latest_version")
    if not release.get("update_available") or latest != normalized:
        raise AppError(
            "The requested DBAChum version is not the current stable update.",
            code="UPDATE_VERSION_NOT_OFFERED",
            status_code=409,
        )
    if not release.get("installable"):
        raise AppError(
            "The current DBAChum release does not contain all required update assets.",
            code="UPDATE_ASSETS_MISSING",
            status_code=409,
        )

    root = _project_root()
    update_id = uuid.uuid4().hex[:16]
    await asyncio.to_thread(
        _queue_windows_update,
        version=normalized,
        update_id=update_id,
        root=root,
    )

    logger.info("Queued DBAChum update id=%s version=%s", update_id, normalized)
    return {
        "update_id": update_id,
        "state": "queued",
        "requested_version": normalized,
        "message": (
            f"DBAChum v{normalized} has been queued. "
            "The application will restart automatically during installation."
        ),
    }
