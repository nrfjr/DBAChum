import re

from app.schemas.server_monitoring import (
    ServerFilesystemSnapshot,
    ServerMemorySnapshot,
    ServerProcessSnapshot,
)


def parse_proc_meminfo(text: str) -> ServerMemorySnapshot:
    values: dict[str, int] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        match = re.search(r"(\d+)", value)
        if match:
            values[key.strip()] = int(match.group(1)) * 1024

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if available is None:
        available = sum(
            values.get(key, 0)
            for key in ("MemFree", "Buffers", "Cached")
        ) or None
    used = max(total - available, 0) if total is not None and available is not None else None
    used_percent = round((used / total) * 100, 1) if total and used is not None else None

    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    swap_used = max(swap_total - swap_free, 0) if swap_total is not None and swap_free is not None else None
    swap_percent = round((swap_used / swap_total) * 100, 1) if swap_total and swap_used is not None else 0.0 if swap_total == 0 else None

    return ServerMemorySnapshot(
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        used_percent=used_percent,
        swap_total_bytes=swap_total,
        swap_used_bytes=swap_used,
        swap_used_percent=swap_percent,
    )


def parse_df_pk(text: str) -> list[ServerFilesystemSnapshot]:
    rows: list[ServerFilesystemSnapshot] = []
    for line in text.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 6:
            continue
        filesystem = parts[0]
        try:
            total_kb = int(parts[1])
            used_kb = int(parts[2])
            available_kb = int(parts[3])
            percent = float(parts[4].rstrip("%"))
        except ValueError:
            continue
        mount_point = " ".join(parts[5:])
        rows.append(
            ServerFilesystemSnapshot(
                filesystem=filesystem,
                mount_point=mount_point,
                total_bytes=total_kb * 1024,
                used_bytes=used_kb * 1024,
                available_bytes=available_kb * 1024,
                used_percent=percent,
            )
        )
    return rows


def parse_ps(text: str, limit: int = 10) -> list[ServerProcessSnapshot]:
    rows: list[ServerProcessSnapshot] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        user = parts[1]
        try:
            cpu = float(parts[2])
        except ValueError:
            cpu = None
        try:
            memory = float(parts[3])
        except ValueError:
            memory = None
        elapsed = parts[4]
        command = parts[6] if len(parts) >= 7 else parts[5]
        rows.append(
            ServerProcessSnapshot(
                pid=pid,
                user=user,
                cpu_percent=cpu,
                memory_percent=memory,
                elapsed=elapsed,
                command=command,
            )
        )
    rows.sort(key=lambda item: item.cpu_percent if item.cpu_percent is not None else -1, reverse=True)
    return rows[:limit]


def parse_uptime_load(text: str) -> tuple[int | None, float | None, float | None, float | None]:
    fields = text.strip().split()
    if len(fields) >= 4:
        try:
            return int(float(fields[0])), float(fields[1]), float(fields[2]), float(fields[3])
        except ValueError:
            pass
    return None, None, None, None


def parse_proc_stat_pair(first: str, second: str) -> float | None:
    def values(text: str) -> list[int] | None:
        line = text.strip().splitlines()[0] if text.strip() else ""
        parts = line.split()
        if not parts or parts[0] != "cpu":
            return None
        try:
            return [int(value) for value in parts[1:]]
        except ValueError:
            return None

    a = values(first)
    b = values(second)
    if not a or not b or len(a) < 4 or len(b) < 4:
        return None
    size = min(len(a), len(b))
    delta = [b[index] - a[index] for index in range(size)]
    total = sum(delta)
    if total <= 0:
        return None
    idle = delta[3] + (delta[4] if size > 4 else 0)
    return round(max(0.0, min(100.0, (1 - idle / total) * 100)), 1)


def parse_systemd_failed(text: str) -> list[str]:
    services: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        unit = line.split(None, 1)[0]
        if unit.endswith(".service"):
            services.append(unit)
    return services[:25]


def parse_uptime_command(text: str) -> tuple[int | None, float | None, float | None, float | None]:
    line = " ".join(text.strip().split())
    if not line:
        return None, None, None, None

    load_match = re.search(
        r"load averages?:?\s*([0-9.]+)[, ]+\s*([0-9.]+)[, ]+\s*([0-9.]+)",
        line,
        re.IGNORECASE,
    )
    loads = (None, None, None)
    if load_match:
        loads = tuple(float(load_match.group(index)) for index in range(1, 4))

    uptime_seconds = 0
    matched_duration = False
    days_match = re.search(r"up\s+(\d+)\s+days?", line, re.IGNORECASE)
    if days_match:
        uptime_seconds += int(days_match.group(1)) * 86400
        matched_duration = True

    time_match = re.search(r"up(?:\s+\d+\s+days?,)?\s+(\d+):(\d+)", line, re.IGNORECASE)
    if time_match:
        uptime_seconds += int(time_match.group(1)) * 3600 + int(time_match.group(2)) * 60
        matched_duration = True
    else:
        hours_match = re.search(r"up(?:\s+\d+\s+days?,)?\s+(\d+)\s+hrs?", line, re.IGNORECASE)
        mins_match = re.search(r"up(?:\s+\d+\s+days?,)?\s+(\d+)\s+mins?", line, re.IGNORECASE)
        if hours_match:
            uptime_seconds += int(hours_match.group(1)) * 3600
            matched_duration = True
        if mins_match:
            uptime_seconds += int(mins_match.group(1)) * 60
            matched_duration = True

    return (
        uptime_seconds if matched_duration else None,
        loads[0],
        loads[1],
        loads[2],
    )


def parse_vmstat_cpu(text: str) -> float | None:
    lines = [line.split() for line in text.splitlines() if line.strip()]
    header_index = None
    idle_index = None
    for index, fields in enumerate(lines):
        lowered = [field.lower() for field in fields]
        if "id" in lowered and ("us" in lowered or "sy" in lowered):
            header_index = index
            idle_index = lowered.index("id")

    if header_index is None or idle_index is None:
        return None

    for fields in reversed(lines[header_index + 1 :]):
        if len(fields) <= idle_index:
            continue
        try:
            idle = float(fields[idle_index])
        except ValueError:
            continue
        return round(max(0.0, min(100.0, 100.0 - idle)), 1)
    return None


def parse_svmon_global(text: str) -> ServerMemorySnapshot | None:
    for raw_line in text.splitlines():
        fields = raw_line.split()
        if not fields or fields[0].lower() != "memory" or len(fields) < 4:
            continue
        try:
            total_mb = float(fields[1])
            used_mb = float(fields[2])
            free_mb = float(fields[3])
        except ValueError:
            continue
        total = int(total_mb * 1024 * 1024)
        used = int(used_mb * 1024 * 1024)
        available = int(free_mb * 1024 * 1024)
        used_percent = round((used / total) * 100, 1) if total else None
        return ServerMemorySnapshot(
            total_bytes=total,
            used_bytes=used,
            available_bytes=available,
            used_percent=used_percent,
        )
    return None


def parse_aix_src_inoperative(text: str) -> list[str]:
    rows: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("subsystem"):
            continue
        fields = line.split()
        if len(fields) >= 4 and fields[-1].lower() in {"inoperative", "failed"}:
            rows.append(fields[0])
    return rows[:25]
