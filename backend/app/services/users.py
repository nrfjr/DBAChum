from bson import ObjectId

from app.schemas.user import UserResponse


def normalize_username(
    username: str,
) -> str:
    return username.strip().lower()


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
    return UserResponse(
        id=str(user["_id"]),
        username=user["username"],
        display_name=user["display_name"],
        role=user.get(
            "role",
            "user",
        ),
        is_active=user.get(
            "is_active",
            True,
        ),
        created_at=user["created_at"],
    )