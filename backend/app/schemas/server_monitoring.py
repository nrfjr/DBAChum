from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SshConnectionState(str, Enum):
    CONNECTED = "connected"
    UNTRUSTED = "untrusted"


class SshConnectionTestResponse(BaseModel):
    state: SshConnectionState
    checked_at: datetime
    target: str
    port: int
    username: str
    latency_ms: float | None = None
    fingerprint: str
    trusted_fingerprint: str | None = None
    message: str


class SshTrustHostKeyRequest(BaseModel):
    fingerprint: str = Field(min_length=8, max_length=256)


class ServerMemorySnapshot(BaseModel):
    total_bytes: int | None = None
    used_bytes: int | None = None
    available_bytes: int | None = None
    used_percent: float | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None
    swap_used_percent: float | None = None


class ServerFilesystemSnapshot(BaseModel):
    filesystem: str
    mount_point: str
    total_bytes: int
    used_bytes: int
    available_bytes: int
    used_percent: float


class ServerProcessSnapshot(BaseModel):
    pid: int
    user: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    elapsed: str | None = None
    command: str


class ServerServiceSnapshot(BaseModel):
    manager: str = "unknown"
    state: str = "unknown"
    failed_services: list[str] = Field(default_factory=list)
    note: str | None = None


class ServerHealthSnapshot(BaseModel):
    checked_at: datetime
    target: str
    port: int
    ssh_latency_ms: float | None = None

    remote_hostname: str | None = None
    os_name: str | None = None
    kernel_release: str | None = None
    uptime_seconds: int | None = None

    load_1: float | None = None
    load_5: float | None = None
    load_15: float | None = None
    cpu_used_percent: float | None = None
    cpu_measurement: str | None = None

    memory: ServerMemorySnapshot = Field(default_factory=ServerMemorySnapshot)
    filesystems: list[ServerFilesystemSnapshot] = Field(default_factory=list)
    top_processes: list[ServerProcessSnapshot] = Field(default_factory=list)
    services: ServerServiceSnapshot = Field(default_factory=ServerServiceSnapshot)

    warnings: list[str] = Field(default_factory=list)
