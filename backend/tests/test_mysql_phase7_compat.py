from app.connectors.mysql_compat import (
    mysql_capabilities,
    parse_mysql_version,
)


def test_mysql_57_capabilities_are_conservative():
    version = parse_mysql_version("5.7.44-log")
    capabilities = mysql_capabilities(version)

    assert version.generation == "MySQL 5.7"
    assert capabilities["performance_schema"] is True
    assert capabilities["roles"] is False
    assert capabilities["native_backup_history"] is False


def test_mysql_84_lts_generation():
    version = parse_mysql_version("8.4.6")
    capabilities = mysql_capabilities(version)

    assert version.generation == "MySQL 8.4 LTS"
    assert capabilities["roles"] is True
    assert capabilities["transactional_data_dictionary"] is True


def test_mariadb_does_not_assume_mysql_capabilities():
    version = parse_mysql_version("10.11.8-MariaDB")

    assert version.mariadb is True
    assert mysql_capabilities(version)["performance_schema"] is False
