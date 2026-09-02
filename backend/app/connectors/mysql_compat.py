from dataclasses import dataclass


@dataclass(frozen=True)
class MySqlVersion:
    raw: str | None
    major: int | None
    minor: int | None
    patch: int | None
    generation: str
    mariadb: bool = False


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
        generation = f"MariaDB-compatible {major or '?'}{'.' + str(minor) if minor is not None else ''}"
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
    if version.mariadb or version.major is None:
        return {
            "performance_schema": False,
            "information_schema_innodb_trx": False,
            "roles": False,
            "transactional_data_dictionary": False,
            "native_backup_history": False,
        }

    version_tuple = (version.major, version.minor or 0)
    return {
        "performance_schema": version_tuple >= (5, 5),
        "information_schema_innodb_trx": version_tuple >= (5, 1),
        "roles": version_tuple >= (8, 0),
        "transactional_data_dictionary": version_tuple >= (8, 0),
        "native_backup_history": False,
    }
