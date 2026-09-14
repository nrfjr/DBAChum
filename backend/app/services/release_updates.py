from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


GITHUB_RELEASES_URL = "https://api.github.com/repos/nrfjr/DBAChum/releases"
CACHE_TTL_SECONDS = 900
_VERSION_RE = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

_cache_value: dict[str, Any] | None = None
_cache_expires_at = 0.0
_cache_lock = asyncio.Lock()


def _parse_stable_version(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _version_text(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def _asset_url(release: dict[str, Any], name: str) -> str | None:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None

    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != name:
            continue
        url = asset.get("browser_download_url")
        return str(url) if url else None

    return None


def _build_update_status(
    releases: list[dict[str, Any]],
    *,
    current_version: str,
) -> dict[str, Any]:
    current = _parse_stable_version(current_version)
    if current is None:
        raise AppError(
            "The installed DBAChum version is not a stable semantic version.",
            code="INVALID_APP_VERSION",
            status_code=500,
        )

    candidates: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft") or release.get("prerelease"):
            continue
        parsed = _parse_stable_version(str(release.get("tag_name") or ""))
        if parsed is not None:
            candidates.append((parsed, release))

    checked_at = datetime.now(timezone.utc).isoformat()
    if not candidates:
        return {
            "current_version": _version_text(current),
            "latest_version": None,
            "update_available": False,
            "release_name": None,
            "release_notes": "",
            "release_url": None,
            "published_at": None,
            "package_name": None,
            "package_url": None,
            "checksum_name": None,
            "checksum_url": None,
            "installable": False,
            "checked_at": checked_at,
        }

    latest, release = max(candidates, key=lambda item: item[0])
    latest_text = _version_text(latest)
    tag = f"v{latest_text}"
    package_name = f"DBAChum-{tag}-windows.zip"
    checksum_name = f"{package_name}.sha256"
    package_url = _asset_url(release, package_name)
    checksum_url = _asset_url(release, checksum_name)

    return {
        "current_version": _version_text(current),
        "latest_version": latest_text,
        "update_available": latest > current,
        "release_name": str(release.get("name") or tag),
        "release_notes": str(release.get("body") or ""),
        "release_url": str(release.get("html_url") or "") or None,
        "published_at": release.get("published_at"),
        "package_name": package_name if package_url else None,
        "package_url": package_url,
        "checksum_name": checksum_name if checksum_url else None,
        "checksum_url": checksum_url,
        "installable": bool(latest > current and package_url and checksum_url),
        "checked_at": checked_at,
    }


async def _fetch_releases() -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"DBAChum/{settings.app_version}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(
                GITHUB_RELEASES_URL,
                headers=headers,
                params={"per_page": 20},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(
            "Unable to check GitHub Releases for DBAChum updates.",
            code="UPDATE_CHECK_FAILED",
            status_code=503,
        ) from exc

    if not isinstance(payload, list):
        raise AppError(
            "GitHub returned an unexpected release response.",
            code="UPDATE_CHECK_FAILED",
            status_code=503,
        )

    return [item for item in payload if isinstance(item, dict)]


async def check_for_updates(*, force_refresh: bool = False) -> dict[str, Any]:
    global _cache_expires_at, _cache_value

    now = time.monotonic()
    if not force_refresh and _cache_value is not None and now < _cache_expires_at:
        return dict(_cache_value)

    async with _cache_lock:
        now = time.monotonic()
        if not force_refresh and _cache_value is not None and now < _cache_expires_at:
            return dict(_cache_value)

        releases = await _fetch_releases()
        result = _build_update_status(
            releases,
            current_version=settings.app_version,
        )
        _cache_value = result
        _cache_expires_at = time.monotonic() + CACHE_TTL_SECONDS
        return dict(result)
