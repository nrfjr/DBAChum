from datetime import datetime, timezone

import pytest

from app.schemas.provisioning import ProvisioningPreviewRequest
from app.schemas.user import UserResponse, UserRole
from app.services import provisioning_preview


PROFILE_ID = "a" * 24
SCHEMA_CONNECTION_ID = "b" * 24
TABLE_CONNECTION_ID = "c" * 24


def operator():
    return UserResponse(
        id="admin-1",
        username="meimei",
        display_name="DBA",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


def test_generate_username_keeps_employee_id_digits_and_normalizes_enye():
    username = provisioning_preview.generate_provisioning_username(
        first_name="José",
        middle_name="Peña",
        last_name="Niño",
        employee_id="12-345",
    )

    assert username == "JPNINO12345"




def test_generate_username_preserves_leading_zero_and_sanitizes_compound_names():
    username = provisioning_preview.generate_provisioning_username(
        first_name="John-Doe Michael",
        middle_name=None,
        last_name="O'Connor-Smith Dela Cruz",
        employee_id="0289",
    )

    assert username == "JOCONNORSMITHDELACRUZ0289"


def test_generate_username_uses_middle_initial_when_present():
    username = provisioning_preview.generate_provisioning_username(
        first_name="Mary Anne",
        middle_name="Jane-Marie",
        last_name="Last-name",
        employee_id="00123",
    )

    assert username == "MJLASTNAME00123"

@pytest.mark.asyncio
async def test_preview_resolves_sequence_requester_ip_and_redacts_password(monkeypatch):
    profile = {
        "_id": PROFILE_ID,
        "name": "ORMS",
        "enabled": True,
        "schema_connection_id": SCHEMA_CONNECTION_ID,
        "ldap_enabled": False,
        "table_steps": [
            {
                "name": "Insert USER_MASTER",
                "connection_id": TABLE_CONNECTION_ID,
                "owner": "ORMS",
                "table_name": "USER_MASTER",
                "match_columns": ["USERNAME"],
                "mappings": [
                    {
                        "column_name": "ID",
                        "value_kind": "sequence",
                        "value_key": "USER_MASTER_SEQ",
                    },
                    {
                        "column_name": "USERNAME",
                        "value_kind": "generated",
                        "value_key": "username",
                    },
                    {
                        "column_name": "PASSWORD",
                        "value_kind": "generated",
                        "value_key": "password",
                    },
                    {
                        "column_name": "CREATED_BY",
                        "value_kind": "generated",
                        "value_key": "requester_ip",
                    },
                    {
                        "column_name": "REMARKS",
                        "value_kind": "form",
                        "value_key": "remarks",
                    },
                ],
            }
        ],
    }

    async def fake_get_profile(_database, _profile_id):
        return profile

    async def fake_validate(_database, _profile):
        return []

    async def fake_connection(_database, connection_id):
        return {
            "_id": connection_id,
            "name": "RMSUAT SYS" if connection_id == SCHEMA_CONNECTION_ID else "ORMS APP",
            "engine": "oracle",
            "active": True,
        }

    async def fake_user_exists(_connection, _username):
        return True

    async def fake_match_count(_connection, *, owner, table_name, match_values):
        assert owner == "ORMS"
        assert table_name == "USER_MASTER"
        assert match_values == {"USERNAME": "JPSANTOS12345"}
        return 1

    monkeypatch.setattr(provisioning_preview, "get_provisioning_profile", fake_get_profile)
    monkeypatch.setattr(provisioning_preview, "validate_profile_dependencies", fake_validate)
    monkeypatch.setattr(provisioning_preview, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_preview, "oracle_user_exists", fake_user_exists)
    monkeypatch.setattr(provisioning_preview, "count_oracle_rows_by_match", fake_match_count)

    result = await provisioning_preview.build_provisioning_preview(
        object(),
        PROFILE_ID,
        ProvisioningPreviewRequest(
            password="abc12345",
            first_name="Juan",
            middle_name="Peña",
            last_name="Santos",
            employee_id="12345",
            remarks="RMS access",
        ),
        operator(),
        requester_ip="192.0.2.25",
        parent_connection_id=SCHEMA_CONNECTION_ID,
    )

    assert result.dry_run is True
    assert result.account_exists is True
    assert result.account_action == "alter"
    assert result.username == "JPSANTOS12345"
    assert result.table_steps[0].planned_action == "update"
    assert result.table_steps[0].existing_rows == 1
    assert result.table_steps[0].match_columns == ["USERNAME"]
    columns = {column.column_name: column for column in result.table_steps[0].columns}
    assert columns["ID"].display_value == "ORMS.USER_MASTER_SEQ.NEXTVAL"
    assert columns["CREATED_BY"].display_value == "192.0.2.25"
    assert columns["REMARKS"].display_value == "RMS access"
    assert "abc12345" not in columns["PASSWORD"].display_value
    assert columns["PASSWORD"].sensitive is True


@pytest.mark.asyncio
async def test_preview_rejects_profile_from_another_parent_database(monkeypatch):
    profile = {
        "_id": PROFILE_ID,
        "name": "ORMS",
        "enabled": True,
        "schema_connection_id": SCHEMA_CONNECTION_ID,
        "ldap_enabled": False,
        "table_steps": [],
    }

    async def fake_get_profile(_database, _profile_id):
        return profile

    monkeypatch.setattr(
        provisioning_preview,
        "get_provisioning_profile",
        fake_get_profile,
    )

    with pytest.raises(Exception) as exc_info:
        await provisioning_preview.build_provisioning_preview(
            object(),
            PROFILE_ID,
            ProvisioningPreviewRequest(
                username="JSMITH12345",
                password="abc12345",
            ),
            operator(),
            parent_connection_id="d" * 24,
        )

    assert getattr(exc_info.value, "code", None) == "PROVISIONING_PROFILE_WRONG_DATABASE"
