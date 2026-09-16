from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.core.config import settings
from app.core.security import (
    generate_session_token,
    hash_session_token,
    verify_password,
)
from app.services.system_settings import runtime_security_settings
from app.services.users import (
    get_user_by_id,
    get_user_by_username,
)


async def authenticate_user(
    database,
    username: str,
    password: str,
):
    user = await get_user_by_username(
        database,
        username,
    )

    if user is None:
        return None
    
    if not user.get(
        "is_active",
        True,
    ):
        return None

    if not verify_password(
        password,
        user["password_hash"],
    ):
        return None

    return user


async def create_session(
    database,
    user: dict,
) -> tuple[str, datetime]:
    now = datetime.now(
        timezone.utc
    )

    expires_at = now + timedelta(
        hours=settings.session_hours
    )

    raw_token = generate_session_token()

    await database.auth_sessions.insert_one(
        {
            "user_id": user["_id"],

            "token_hash": hash_session_token(
                raw_token
            ),

            "created_at": now,
            "last_activity_at": now,
            "expires_at": expires_at,
        }
    )

    return raw_token, expires_at


async def get_user_from_session(
    database,
    raw_token: str,
):
    now = datetime.now(
        timezone.utc
    )

    token_hash = hash_session_token(
        raw_token
    )

    session = (
        await database.auth_sessions.find_one(
            {
                "token_hash": token_hash
            }
        )
    )

    if session is None:
        return None

    expires_at = session["expires_at"]

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= now:
        await database.auth_sessions.delete_one(
            {
                "_id": session["_id"]
            }
        )

        return None

    security = await runtime_security_settings(database)
    idle_minutes = int(security.get("session_idle_timeout_minutes", 30))
    last_activity_at = session.get("last_activity_at") or session.get("created_at")
    if last_activity_at is None:
        last_activity_at = now
    elif last_activity_at.tzinfo is None:
        last_activity_at = last_activity_at.replace(tzinfo=timezone.utc)

    if last_activity_at + timedelta(minutes=idle_minutes) <= now:
        await database.auth_sessions.delete_one({"_id": session["_id"]})
        return None

    user = await get_user_by_id(
        database,
        session["user_id"],
    )

    if user is None or not user.get(
        "is_active",
        True,
    ):
        await database.auth_sessions.delete_one(
            {
                "_id": session["_id"]
            }
        )
        return None

    return user


async def delete_session(
    database,
    raw_token: str,
) -> None:
    await database.auth_sessions.delete_one(
        {
            "token_hash": hash_session_token(
                raw_token
            )
        }
    )

async def touch_session_activity(
    database,
    raw_token: str,
) -> bool:
    user = await get_user_from_session(database, raw_token)
    if user is None:
        return False

    result = await database.auth_sessions.update_one(
        {"token_hash": hash_session_token(raw_token)},
        {"$set": {"last_activity_at": datetime.now(timezone.utc)}},
    )
    return bool(result.matched_count)
