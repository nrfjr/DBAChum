from enum import Enum

from pydantic import BaseModel, Field, field_validator


class NotificationSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"


class NotificationCategory(str, Enum):
    AVAILABILITY = "availability"
    BLOCKING = "blocking"
    STORAGE = "storage"
    PERFORMANCE = "performance"
    JOBS = "jobs"
    BACKUP = "backup"
    SYSTEM = "system"


class NotificationEngine(str, Enum):
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"
    MYSQL = "mysql"


class NotificationScope(str, Enum):
    ALL = "all"
    SELECTED = "selected"


_DEFAULT_SEVERITIES = [
    NotificationSeverity.CRITICAL,
    NotificationSeverity.WARNING,
]

_DEFAULT_CATEGORIES = [
    NotificationCategory.AVAILABILITY,
    NotificationCategory.BLOCKING,
    NotificationCategory.STORAGE,
    NotificationCategory.PERFORMANCE,
    NotificationCategory.JOBS,
    NotificationCategory.BACKUP,
    NotificationCategory.SYSTEM,
]

_DEFAULT_ENGINES = [
    NotificationEngine.ORACLE,
    NotificationEngine.SQLSERVER,
    NotificationEngine.MYSQL,
]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


class UserNotificationPreferences(BaseModel):


    email_enabled: bool = False
    severities: list[NotificationSeverity] = Field(
        default_factory=lambda: list(_DEFAULT_SEVERITIES),
    )
    categories: list[NotificationCategory] = Field(
        default_factory=lambda: list(_DEFAULT_CATEGORIES),
    )
    engines: list[NotificationEngine] = Field(
        default_factory=lambda: list(_DEFAULT_ENGINES),
    )
    include_servers: bool = True
    include_system: bool = True
    scope: NotificationScope = NotificationScope.ALL
    database_connection_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
    )
    server_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
    )

    @field_validator(
        "database_connection_ids",
        "server_ids",
    )
    @classmethod
    def normalize_source_ids(
        cls,
        values: list[str],
    ) -> list[str]:
        return _dedupe_strings(values)


class UserNotificationPreferencesUpdate(BaseModel):
    email_enabled: bool | None = None
    severities: list[NotificationSeverity] | None = None
    categories: list[NotificationCategory] | None = None
    engines: list[NotificationEngine] | None = None
    include_servers: bool | None = None
    include_system: bool | None = None
    scope: NotificationScope | None = None
    database_connection_ids: list[str] | None = Field(
        default=None,
        max_length=500,
    )
    server_ids: list[str] | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator(
        "database_connection_ids",
        "server_ids",
    )
    @classmethod
    def normalize_source_ids(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        return _dedupe_strings(values)
