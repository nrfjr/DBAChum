import pytest
from pydantic import ValidationError

from app.schemas.server import ServerCreate
from app.schemas.ssh_access import SshAccessProfileCreate


def test_server_asset_supports_application_server_and_relationships():
    model = ServerCreate(
        name="OAS PROD",
        hostname="oasappsprd",
        server_type="application",
        os_family="linux",
        ssh_profile_id="507f1f77bcf86cd799439011",
        database_connection_ids=["507f191e810c19729de860ea"],
    )

    assert model.server_type.value == "application"
    assert model.database_connection_ids == ["507f191e810c19729de860ea"]


def test_server_asset_rejects_duplicate_database_relationships():
    with pytest.raises(ValidationError):
        ServerCreate(
            name="DB PROD",
            hostname="dbprod01",
            os_family="linux",
            database_connection_ids=[
                "507f191e810c19729de860ea",
                "507f191e810c19729de860ea",
            ],
        )


def test_password_ssh_profile_requires_password_on_create():
    with pytest.raises(ValidationError):
        SshAccessProfileCreate(
            name="Linux DBA",
            username="oracle",
            auth_type="password",
        )


def test_private_key_ssh_profile_requires_key_on_create():
    with pytest.raises(ValidationError):
        SshAccessProfileCreate(
            name="Linux DBA Key",
            username="oracle",
            auth_type="private_key",
        )

