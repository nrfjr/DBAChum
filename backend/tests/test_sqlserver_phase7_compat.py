from app.connectors.sqlserver_compat import (
    parse_sqlserver_version,
    sqlserver_capabilities,
)


def test_sqlserver_2000_is_legacy_capability_tier():
    version = parse_sqlserver_version("8.00.2039")

    assert version.major == 8
    assert version.generation == "SQL Server 2000"

    capabilities = sqlserver_capabilities(version)
    assert capabilities["legacy_system_tables"] is True
    assert capabilities["dm_exec"] is False
    assert capabilities["database_files_catalog"] is False
    assert capabilities["backup_history_msdb"] is True


def test_sqlserver_2008_r2_is_detected_from_minor_version():
    version = parse_sqlserver_version("10.50.6560.0")
    assert version.generation == "SQL Server 2008 R2"
    assert sqlserver_capabilities(version)["dm_exec"] is True


def test_sqlserver_2025_uses_modern_capabilities():
    version = parse_sqlserver_version("17.0.1000.7")

    assert version.generation == "SQL Server 2025"
    capabilities = sqlserver_capabilities(version)
    assert capabilities["dm_exec"] is True
    assert capabilities["datediff_big"] is True
    assert capabilities["compression_metadata"] is True


def test_unknown_sqlserver_version_stays_conservative():
    version = parse_sqlserver_version("not-a-version")

    assert version.major is None
    assert sqlserver_capabilities(version)["dm_exec"] is False
