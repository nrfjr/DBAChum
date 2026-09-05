from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.core.permissions import permission_values_for_role
from app.core.security import hash_password
from app.schemas.notification import (
    UserNotificationPreferences,
    UserNotificationPreferencesUpdate,
)
from app.schemas.user import (
    UserCreate,
    UserPasswordUpdate,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfileUpdate,
    UserResponse,
    UserRole,
    UserUpdate,
)


def normalize_username(
    username: str,
) -> str:
    return username.strip().lower()


def normalize_email(
    email: str | None,
) -> str | None:
    if email is None:
        return None

    normalized = email.strip().lower()
    return normalized or None


def build_avatar_initials(
    display_name: str,
    username: str,
) -> str:
    parts = [
        part
        for part in display_name.strip().split()
        if part
    ]

    if len(parts) >= 2:
        return (
            parts[0][0]
            + parts[-1][0]
        ).upper()

    if parts:
        return parts[0][:2].upper()

    return username[:2].upper() or "DB"


def preferences_from_document(
    user: dict,
) -> UserPreferences:
    raw = user.get("preferences")

    if not isinstance(raw, dict):
        return UserPreferences()

    try:
        return UserPreferences.model_validate(raw)
    except Exception:
        # Older/development records should never make login fail merely
        # because a preference value became invalid during development.
        return UserPreferences()


def notification_preferences_from_document(
    user: dict,
) -> UserNotificationPreferences:
    raw = user.get("notifications")

    if not isinstance(raw, dict):
        return UserNotificationPreferences()

    try:
        return UserNotificationPreferences.model_validate(raw)
    except Exception:
        # Development/legacy user rows should fall back safely rather than
        # making authentication fail because subscription fields changed.
        return UserNotificationPreferences()


async def get_user_by_username(
    database,
    username: str,
):
    return await database.users.find_one(
        {
            "username": normalize_username(
                username
            )
        }
    )


async def get_user_by_id(
    database,
    user_id,
):
    if isinstance(
        user_id,
        str,
    ):
        try:
            user_id = ObjectId(user_id)

        except Exception:
            return None

    return await database.users.find_one(
        {
            "_id": user_id
        }
    )


def user_to_response(
    user: dict,
) -> UserResponse:
    username = user["username"]
    display_name = (
        user.get("display_name")
        or username
    )

    raw_email = user.get("email")
    email = normalize_email(
        str(raw_email)
        if raw_email
        else None
    )

    return UserResponse(
        id=str(user["_id"]),

        username=username,

        display_name=display_name,

        email=email,

        role=user.get(
            "role",
            "viewer",
        ),

        is_active=user.get(
            "is_active",
            True,
        ),

        permissions=permission_values_for_role(
            user.get("role", "viewer")
        ),

        avatar_initials=build_avatar_initials(
            display_name,
            username,
        ),

        preferences=preferences_from_document(
            user
        ),

        notifications=notification_preferences_from_document(
            user
        ),

        created_at=user.get(
            "created_at"
        ),

        updated_at=user.get(
            "updated_at"
        ),
    )


def parse_user_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except Exception:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )


async def list_users(
    database,
) -> list[UserResponse]:
    cursor = database.users.find().sort(
        "username",
        1,
    )

    users = await cursor.to_list(None)

    return [
        user_to_response(user)
        for user in users
    ]


async def create_managed_user(
    database,
    data: UserCreate,
) -> UserResponse:
    now = datetime.now(timezone.utc)

    username = normalize_username(
        data.username
    )

    email = normalize_email(
        str(data.email)
        if data.email is not None
        else None
    )

    display_name = (
        data.display_name
        or username
    )

    document = {
        "username": username,
        "username_key": username,
        "display_name": display_name,
        "password_hash": hash_password(
            data.password
        ),
        "role": data.role.value,
        "is_active": data.is_active,
        "preferences": (
            UserPreferences()
            .model_dump(mode="json")
        ),
        "notifications": (
            UserNotificationPreferences()
            .model_dump(mode="json")
        ),
        "created_at": now,
        "updated_at": now,
    }

    if email is not None:
        document["email"] = email
        document["email_key"] = email

    try:
        result = await database.users.insert_one(
            document
        )

    except DuplicateKeyError:
        raise AppError(
            "A user with this username or email "
            "already exists.",
            code="USER_IDENTITY_EXISTS",
            status_code=409,
        )

    user = await database.users.find_one(
        {
            "_id": result.inserted_id,
        }
    )

    return user_to_response(user)


async def update_managed_user(
    database,
    user_id: str,
    data: UserUpdate,
    current_user_id: str,
) -> UserResponse:
    object_id = parse_user_id(user_id)

    user = await database.users.find_one(
        {
            "_id": object_id,
        }
    )

    if user is None:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )

    if str(object_id) == current_user_id:
        if not data.is_active:
            raise AppError(
                "You cannot disable your own account.",
                code="CANNOT_DISABLE_SELF",
                status_code=400,
            )

        if data.role != UserRole.ADMIN:
            raise AppError(
                "You cannot remove your own "
                "administrator role.",
                code="CANNOT_DEMOTE_SELF",
                status_code=400,
            )

    set_fields = {
        "role": data.role.value,
        "is_active": data.is_active,
        "updated_at": datetime.now(
            timezone.utc
        ),
    }
    unset_fields: dict[str, str] = {}

    if "display_name" in data.model_fields_set:
        if data.display_name is not None:
            set_fields["display_name"] = (
                data.display_name
            )

    if "email" in data.model_fields_set:
        email = normalize_email(
            str(data.email)
            if data.email is not None
            else None
        )

        if email is None:
            unset_fields["email"] = ""
            unset_fields["email_key"] = ""
        else:
            set_fields["email"] = email
            set_fields["email_key"] = email

    update_document: dict[str, dict] = {
        "$set": set_fields,
    }
    if unset_fields:
        update_document["$unset"] = unset_fields

    try:
        await database.users.update_one(
            {
                "_id": object_id,
            },
            update_document,
        )
    except DuplicateKeyError:
        raise AppError(
            "A user with this email already exists.",
            code="USER_EMAIL_EXISTS",
            status_code=409,
        )

    updated = await database.users.find_one(
        {
            "_id": object_id,
        }
    )

    if not data.is_active:
        await database.auth_sessions.delete_many(
            {
                "user_id": object_id,
            }
        )

    return user_to_response(updated)


async def update_current_user_profile(
    database,
    user_id: str,
    data: UserProfileUpdate,
) -> UserResponse:
    object_id = parse_user_id(user_id)

    email = normalize_email(
        str(data.email)
        if data.email is not None
        else None
    )

    set_fields = {
        "display_name": data.display_name,
        "updated_at": datetime.now(
            timezone.utc
        ),
    }
    unset_fields: dict[str, str] = {}

    if email is None:
        unset_fields["email"] = ""
        unset_fields["email_key"] = ""
    else:
        set_fields["email"] = email
        set_fields["email_key"] = email

    update_document: dict[str, dict] = {
        "$set": set_fields,
    }
    if unset_fields:
        update_document["$unset"] = unset_fields

    try:
        result = await database.users.update_one(
            {"_id": object_id},
            update_document,
        )
    except DuplicateKeyError:
        raise AppError(
            "That email is already used by another "
            "DBAChum account.",
            code="USER_EMAIL_EXISTS",
            status_code=409,
        )

    if result.matched_count == 0:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )

    updated = await database.users.find_one(
        {"_id": object_id}
    )
    return user_to_response(updated)


async def update_current_user_preferences(
    database,
    user_id: str,
    data: UserPreferencesUpdate,
) -> UserResponse:
    object_id = parse_user_id(user_id)

    changes = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
        mode="json",
    )

    set_fields = {
        f"preferences.{key}": value
        for key, value in changes.items()
    }
    set_fields["updated_at"] = datetime.now(
        timezone.utc
    )

    result = await database.users.update_one(
        {"_id": object_id},
        {"$set": set_fields},
    )

    if result.matched_count == 0:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )

    updated = await database.users.find_one(
        {"_id": object_id}
    )
    return user_to_response(updated)


async def update_current_user_notifications(
    database,
    user_id: str,
    data: UserNotificationPreferencesUpdate,
) -> UserResponse:
    object_id = parse_user_id(user_id)

    changes = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
        mode="json",
    )

    set_fields = {
        f"notifications.{key}": value
        for key, value in changes.items()
    }
    set_fields["updated_at"] = datetime.now(
        timezone.utc
    )

    result = await database.users.update_one(
        {"_id": object_id},
        {"$set": set_fields},
    )

    if result.matched_count == 0:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )

    updated = await database.users.find_one(
        {"_id": object_id}
    )
    return user_to_response(updated)


async def reset_managed_user_password(
    database,
    user_id: str,
    data: UserPasswordUpdate,
) -> None:
    object_id = parse_user_id(user_id)

    result = await database.users.update_one(
        {
            "_id": object_id,
        },
        {
            "$set": {
                "password_hash":
                    hash_password(
                        data.password
                    ),

                "updated_at":
                    datetime.now(timezone.utc),
            }
        },
    )

    await database.auth_sessions.delete_many(
        {
            "user_id": {
                "$in": [
                    user_id,
                    object_id,
                ]
            }
        }
    )

    if result.matched_count == 0:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )


async def delete_managed_user(
    database,
    user_id: str,
    current_user_id: str,
) -> None:
    object_id = parse_user_id(user_id)

    if str(object_id) == current_user_id:
        raise AppError(
            "You cannot delete your own account.",
            code="CANNOT_DELETE_SELF",
            status_code=400,
        )

    user = await database.users.find_one(
        {
            "_id": object_id,
        }
    )

    if user is None:
        raise AppError(
            "User not found.",
            code="USER_NOT_FOUND",
            status_code=404,
        )

    if user.get("role") == UserRole.ADMIN.value:
        admin_count = await database.users.count_documents(
            {
                "role": UserRole.ADMIN.value,
                "is_active": True,
            }
        )

        if admin_count <= 1:
            raise AppError(
                "The last enabled administrator "
                "cannot be deleted.",
                code="LAST_ADMIN_REQUIRED",
                status_code=400,
            )

    await database.users.delete_one(
        {
            "_id": object_id,
        }
    )

    # Remove their active sessions too.
    await database.auth_sessions.delete_many(
        {
            "user_id": {
                "$in": [
                    user_id,
                    object_id,
                ]
            }
        }
    )
