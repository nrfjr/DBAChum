from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.dependencies import auth


class FakeRequest:
    def __init__(self):
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                database=object(),
            )
        )


@pytest.mark.asyncio
async def test_missing_session_cookie_returns_auth_required():
    with pytest.raises(AppError) as exc_info:
        await auth.get_current_user(
            FakeRequest(),
            session_token=None,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_session_returns_401_instead_of_500(
    monkeypatch,
):
    async def fake_get_user_from_session(
        _database,
        _session_token,
    ):
        return None

    monkeypatch.setattr(
        auth,
        "get_user_from_session",
        fake_get_user_from_session,
    )

    with pytest.raises(AppError) as exc_info:
        await auth.get_current_user(
            FakeRequest(),
            session_token="expired-token",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_SESSION"


@pytest.mark.asyncio
async def test_inactive_user_is_rejected(
    monkeypatch,
):
    async def fake_get_user_from_session(
        _database,
        _session_token,
    ):
        return {
            "_id": "user-1",
            "username": "viewer",
            "display_name": "Viewer",
            "role": "viewer",
            "is_active": False,
        }

    monkeypatch.setattr(
        auth,
        "get_user_from_session",
        fake_get_user_from_session,
    )

    with pytest.raises(AppError) as exc_info:
        await auth.get_current_user(
            FakeRequest(),
            session_token="inactive-token",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_valid_session_returns_user_response(
    monkeypatch,
):
    async def fake_get_user_from_session(
        _database,
        _session_token,
    ):
        return {
            "_id": "user-1",
            "username": "operator",
            "display_name": "Operator",
            "role": "operator",
            "is_active": True,
        }

    monkeypatch.setattr(
        auth,
        "get_user_from_session",
        fake_get_user_from_session,
    )

    result = await auth.get_current_user(
        FakeRequest(),
        session_token="valid-token",
    )

    assert result.id == "user-1"
    assert result.username == "operator"
    assert result.role.value == "operator"
    assert result.is_active is True


@pytest.mark.asyncio
async def test_inactive_session_user_is_removed_from_session_store(
    monkeypatch,
):
    from datetime import datetime, timedelta, timezone

    from app.services import auth as auth_service

    deleted = []

    class FakeSessions:
        async def find_one(self, _query):
            return {
                "_id": "session-1",
                "user_id": "user-1",
                "expires_at": datetime.now(timezone.utc)
                + timedelta(hours=1),
            }

        async def delete_one(self, query):
            deleted.append(query)

    class FakeDatabase:
        auth_sessions = FakeSessions()

    async def fake_get_user_by_id(
        _database,
        _user_id,
    ):
        return {
            "_id": "user-1",
            "username": "disabled-user",
            "role": "viewer",
            "is_active": False,
        }

    monkeypatch.setattr(
        auth_service,
        "get_user_by_id",
        fake_get_user_by_id,
    )

    result = await auth_service.get_user_from_session(
        FakeDatabase(),
        "token",
    )

    assert result is None
    assert deleted == [
        {
            "_id": "session-1",
        }
    ]
