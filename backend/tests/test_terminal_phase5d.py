import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.terminal_shortcut import TerminalShortcutCreate
from app.services.server_terminal import TerminalSessionRegistry


def test_terminal_shortcut_supports_execute_and_server_scope():
    shortcut = TerminalShortcutCreate(
        name="SQLPlus SYSDBA",
        category="Oracle",
        command="sqlplus / as sysdba",
        mode="execute",
        server_ids=["507f1f77bcf86cd799439011"],
    )

    assert shortcut.mode.value == "execute"
    assert shortcut.server_ids == ["507f1f77bcf86cd799439011"]


def test_terminal_shortcut_rejects_duplicate_server_assignments():
    with pytest.raises(ValidationError):
        TerminalShortcutCreate(
            name="Alert Log",
            command="cd /tmp",
            server_ids=[
                "507f1f77bcf86cd799439011",
                "507f1f77bcf86cd799439011",
            ],
        )


@pytest.mark.asyncio
async def test_terminal_registry_caps_sessions_per_user_at_three():
    registry = TerminalSessionRegistry()

    await registry.reserve("u1", "s1")
    await registry.reserve("u1", "s2")
    await registry.reserve("u1", "s3")

    with pytest.raises(AppError) as caught:
        await registry.reserve("u1", "s4")

    assert caught.value.code == "TERMINAL_SESSION_LIMIT"

    await registry.release("u1", "s2")
    await registry.reserve("u1", "s4")
