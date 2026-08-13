import asyncio
from datetime import (
    datetime,
    timezone,
)
from getpass import getpass

from pymongo import AsyncMongoClient

from app.core.config import settings
from app.core.security import hash_password
from app.services.users import (
    normalize_username,
)


async def main() -> None:
    username = normalize_username(
        input(
            "Admin username: "
        )
    )

    display_name = input(
        "Display name: "
    ).strip()

    password = getpass(
        "Password: "
    )

    confirm_password = getpass(
        "Confirm password: "
    )

    if password != confirm_password:
        print(
            "Passwords do not match."
        )
        return

    if len(password) < 12:
        print(
            "Password must be at least "
            "12 characters."
        )
        return

    client = AsyncMongoClient(
        settings.mongodb_uri
    )

    database = client[
        settings.mongodb_database
    ]

    existing = await database.users.find_one(
        {
            "username": username
        }
    )

    if existing is not None:
        print(
            "User already exists."
        )

        await client.close()
        return

    now = datetime.now(
        timezone.utc
    )

    await database.users.insert_one(
        {
            "username": username,

            "display_name": (
                display_name
                or username
            ),

            "password_hash": hash_password(
                password
            ),

            "role": "admin",
            "is_active": True,

            "created_at": now,
            "updated_at": now,
        }
    )

    await client.close()

    print(
        f"Admin user '{username}' created."
    )


if __name__ == "__main__":
    asyncio.run(main())