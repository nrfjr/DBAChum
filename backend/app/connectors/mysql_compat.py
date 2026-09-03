from dataclasses import dataclass


@dataclass(frozen=True)
class MySqlVersion:
    raw: str | None
    major: int | None
    minor: int | None
    patch: int | None
    generation: str
    mariadb: bool = False

    @property
    def product_name(self) -> str:
        if self.mariadb:
            return "MariaDB"
        return "MySQL"


def parse_mysql_version(value: object) -> MySqlVersion:
    raw = None if value is None else str(value).strip() or None
    mariadb = bool(raw and "mariadb" in raw.lower())
    parts: list[int] = []

    if raw:
        numeric = raw.split("-", 1)[0]
        for piece in numeric.split(".")[:3]:
            digits = "".join(char for char in piece if char.isdigit())
            if not digits:
                break
            parts.append(int(digits))

    major = parts[0] if len(parts) >= 1 else None
    minor = parts[1] if len(parts) >= 2 else None
    patch = parts[2] if len(parts) >= 3 else None

    if mariadb:
        if major is None:
            generation = "MariaDB"
        else:
            generation = f"MariaDB {major}.{minor or 0}"
    elif major is None:
        generation = "Unknown MySQL generation"
    elif major == 8 and minor == 4:
        generation = "MySQL 8.4 LTS"
    elif major == 8:
        generation = "MySQL 8.0"
    elif major >= 9:
        generation = f"MySQL {major}.{minor or 0}"
    else:
        generation = f"MySQL {major}.{minor or 0}"

    return MySqlVersion(
        raw=raw,
        major=major,
        minor=minor,
        patch=patch,
        generation=generation,
        mariadb=mariadb,
    )


def mysql_capabilities(version: MySqlVersion) -> dict[str, bool]:
    """Return version-level capabilities only.

    Runtime probes refine these flags after a connection is established.
    This distinction matters for installations where Performance Schema is
    compiled/installed but disabled, which is common on older XAMPP/MariaDB
    deployments.
    """
    if version.major is None:
        return {
            "performance_schema_supported": False,
            "performance_schema": False,
            "information_schema": True,
            "information_schema_innodb_trx": False,
            "processlist": True,
            "roles": False,
            "transactional_data_dictionary": False,
            "mariadb_global_priv": False,
            "native_backup_history": False,
        }

    version_tuple = (version.major, version.minor or 0)

    if version.mariadb:
        # MariaDB has a related but distinct feature timeline from Oracle
        # MySQL. Keep this conservative and let the runtime probe prove what
        # the connected server actually exposes.
        return {
            "performance_schema_supported": version_tuple >= (5, 5),
            "performance_schema": False,
            "information_schema": True,
            "information_schema_innodb_trx": version_tuple >= (5, 5),
            "processlist": True,
            "roles": version_tuple >= (10, 0),
            "transactional_data_dictionary": False,
            "mariadb_global_priv": version_tuple >= (10, 4),
            "native_backup_history": False,
        }

    return {
        "performance_schema_supported": version_tuple >= (5, 5),
        "performance_schema": False,
        "information_schema": version_tuple >= (5, 0),
        "information_schema_innodb_trx": version_tuple >= (5, 1),
        "processlist": True,
        "roles": version_tuple >= (8, 0),
        "transactional_data_dictionary": version_tuple >= (8, 0),
        "mariadb_global_priv": False,
        "native_backup_history": False,
    }
