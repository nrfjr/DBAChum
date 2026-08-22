import pytest
from pydantic import ValidationError

from app.core.config import Settings


VALID_KEY = (
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)


def make_settings(**overrides):
    values = {
        "connection_encryption_key": VALID_KEY,
        "trusted_hosts": "localhost,127.0.0.1",
    }
    values.update(overrides)

    return Settings(
        _env_file=None,
        **values,
    )


def test_production_security_defaults_can_be_explicitly_locked_down():
    settings = make_settings(
        environment="production",
        api_docs_enabled=False,
        cors_origins="",
        trusted_hosts="localhost,dbachum01,10.10.10.20",
    )

    assert settings.is_production is True
    assert settings.api_docs_enabled is False
    assert settings.cors_origin_list == []
    assert settings.trusted_host_list == [
        "localhost",
        "dbachum01",
        "10.10.10.20",
    ]


def test_production_rejects_wildcard_trusted_host():
    with pytest.raises(
        ValidationError,
        match="TRUSTED_HOSTS cannot contain",
    ):
        make_settings(
            environment="production",
            trusted_hosts="*",
            cors_origins="",
        )


def test_production_rejects_wildcard_cors_origin():
    with pytest.raises(
        ValidationError,
        match="CORS_ORIGINS cannot contain",
    ):
        make_settings(
            environment="production",
            cors_origins="*",
        )


def test_invalid_connection_encryption_key_is_rejected():
    with pytest.raises(
        ValidationError,
        match="valid Fernet key",
    ):
        make_settings(
            connection_encryption_key="not-a-key",
        )


def test_environment_name_is_normalized():
    settings = make_settings(
        environment=" Production ",
        cors_origins="",
    )

    assert settings.environment == "production"
