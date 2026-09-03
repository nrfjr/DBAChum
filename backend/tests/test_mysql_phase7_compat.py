from app.connectors.mysql_compat import (
    mysql_capabilities,
    parse_mysql_version,
)


def test_mysql_57_capabilities_are_conservative():
    version = parse_mysql_version("5.7.44-log")
    capabilities = mysql_capabilities(version)

    assert version.generation == "MySQL 5.7"
    assert version.product_name == "MySQL"
    assert capabilities["performance_schema_supported"] is True
    # Runtime capability remains false until a live probe confirms that
    # Performance Schema is actually enabled on the target.
    assert capabilities["performance_schema"] is False
    assert capabilities["roles"] is False
    assert capabilities["native_backup_history"] is False


def test_mysql_84_lts_generation():
    version = parse_mysql_version("8.4.6")
    capabilities = mysql_capabilities(version)

    assert version.generation == "MySQL 8.4 LTS"
    assert capabilities["roles"] is True
    assert capabilities["transactional_data_dictionary"] is True


def test_mariadb_104_is_identified_as_mariadb():
    version = parse_mysql_version("10.4.27-MariaDB")
    capabilities = mysql_capabilities(version)

    assert version.mariadb is True
    assert version.product_name == "MariaDB"
    assert version.generation == "MariaDB 10.4"
    assert capabilities["performance_schema_supported"] is True
    assert capabilities["performance_schema"] is False
    assert capabilities["roles"] is True
    assert capabilities["mariadb_global_priv"] is True


def test_unknown_mysql_version_does_not_assume_runtime_features():
    version = parse_mysql_version(None)
    capabilities = mysql_capabilities(version)

    assert version.generation == "Unknown MySQL generation"
    assert capabilities["performance_schema"] is False
    assert capabilities["native_backup_history"] is False
