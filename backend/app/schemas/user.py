from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
)

from app.schemas.notification import UserNotificationPreferences


class UserRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class ThemePreference(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class AccentPreference(str, Enum):
    PURPLE = "purple"
    BLUE = "blue"
    CYAN = "cyan"
    GREEN = "green"
    ORANGE = "orange"
    PINK = "pink"


class DensityPreference(str, Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class DateTimeFormatPreference(str, Enum):
    SYSTEM = "system"
    TWELVE_HOUR = "12h"
    TWENTY_FOUR_HOUR = "24h"


class LandingPagePreference(str, Enum):
    DASHBOARD = "dashboard"
    DATABASES = "databases"
    SERVERS = "servers"
    ALERTS = "alerts"


class HistoryRangePreference(str, Enum):
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"


class UserPreferences(BaseModel):
    """Personal presentation preferences stored with a DBAChum user.

    Notification subscriptions live in a sibling user field rather than here,
    keeping identity/appearance independent from alert-delivery choices.
    """

    timezone: str = Field(
        default="system",
        min_length=1,
        max_length=80,
    )
    date_time_format: DateTimeFormatPreference = DateTimeFormatPreference.SYSTEM
    default_landing_page: LandingPagePreference = LandingPagePreference.DASHBOARD
    default_history_range: HistoryRangePreference = HistoryRangePreference.ONE_HOUR
    theme: ThemePreference = ThemePreference.SYSTEM
    accent: AccentPreference = AccentPreference.PURPLE
    density: DensityPreference = DensityPreference.COMFORTABLE

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return "system"
        return normalized


class UserPreferencesUpdate(BaseModel):
    timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
    )
    date_time_format: DateTimeFormatPreference | None = None
    default_landing_page: LandingPagePreference | None = None
    default_history_range: HistoryRangePreference | None = None
    theme: ThemePreference | None = None
    accent: AccentPreference | None = None
    density: DensityPreference | None = None

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return "system"
        return normalized


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    email: EmailStr | None = None
    role: UserRole
    is_active: bool
    permissions: list[str] = Field(default_factory=list)
    avatar_initials: str = "DB"
    preferences: UserPreferences = Field(
        default_factory=UserPreferences
    )
    notifications: UserNotificationPreferences = Field(
        default_factory=UserNotificationPreferences
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
    )

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()

        if len(normalized) < 3:
            raise ValueError(
                "Username must be at least 3 characters."
            )

        return normalized

    display_name: str | None = Field(
        default=None,
        max_length=120,
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())
        return normalized or None

    email: EmailStr | None = None

    password: str = Field(
        min_length=12,
        max_length=128,
    )

    role: UserRole = UserRole.VIEWER

    is_active: bool = True


class UserUpdate(BaseModel):
    role: UserRole
    is_active: bool

    # Admin identity edits are accepted by the API foundation without forcing
    # the existing Settings > Users controls to submit them on every role/status
    # change. They are only changed when explicitly included in the request.
    display_name: str | None = Field(
        default=None,
        max_length=120,
    )
    email: EmailStr | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError(
                "Display name cannot be blank."
            )
        return normalized


class UserProfileUpdate(BaseModel):
    display_name: str = Field(
        min_length=1,
        max_length=120,
    )
    email: EmailStr | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError(
                "Display name cannot be blank."
            )
        return normalized


class UserPasswordUpdate(BaseModel):
    password: str = Field(
        min_length=12,
        max_length=128,
    )
