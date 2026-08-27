import io

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppError
from app.schemas.provisioning import BulkProvisionRequest, BulkProvisionRowInput
from app.services import bulk_provisioning


@pytest.mark.asyncio
async def test_csv_import_requires_identity_headers(monkeypatch):
    upload = UploadFile(
        filename="users.csv",
        file=io.BytesIO(b"first_name,last_name\nJuan,Santos\n"),
    )

    with pytest.raises(AppError) as exc:
        await bulk_provisioning.import_bulk_provision_file(None, "db1", upload)

    assert exc.value.code == "BULK_IMPORT_HEADERS_MISSING"


@pytest.mark.asyncio
async def test_csv_import_generates_username_and_password(monkeypatch):
    async def fake_target(database, connection_id):
        return {"id": connection_id}

    async def fake_existing(connection, usernames):
        return set()

    monkeypatch.setattr(bulk_provisioning, "get_oracle_target", fake_target)
    monkeypatch.setattr(bulk_provisioning, "find_existing_oracle_users", fake_existing)

    upload = UploadFile(
        filename="users.csv",
        file=io.BytesIO(
            b"employee_id,first_name,middle_name,last_name,reference_user,password\n"
            b"12345,Juan,M,Santos,,\n"
        ),
    )

    result = await bulk_provisioning.import_bulk_provision_file(None, "db1", upload)

    assert result.row_count == 1
    assert result.valid_count == 1
    row = result.rows[0]
    assert row.username == "JMSANTOS12345"
    assert row.reference_user is None
    assert row.password_mode == "generated"
    assert len(row.password) == 8


@pytest.mark.asyncio
async def test_import_marks_existing_oracle_username_invalid(monkeypatch):
    async def fake_target(database, connection_id):
        return {"id": connection_id}

    async def fake_existing(connection, usernames):
        return set(usernames)

    monkeypatch.setattr(bulk_provisioning, "get_oracle_target", fake_target)
    monkeypatch.setattr(bulk_provisioning, "find_existing_oracle_users", fake_existing)

    upload = UploadFile(
        filename="users.csv",
        file=io.BytesIO(b"employee_id,first_name,last_name\n12345,Juan,Santos\n"),
    )

    result = await bulk_provisioning.import_bulk_provision_file(None, "db1", upload)

    assert result.invalid_count == 1
    assert result.rows[0].errors["username"] == "This Oracle username already exists."


def test_bulk_common_reference_is_required_when_enabled():
    with pytest.raises(ValueError):
        BulkProvisionRequest(
            use_common_reference=True,
            rows=[
                BulkProvisionRowInput(
                    row_number=2,
                    employee_id="12345",
                    first_name="Juan",
                    last_name="Santos",
                    password="abc12345",
                )
            ],
        )
