
SYSTEM_ORACLE_USERS = {
    "SYS",
    "SYSTEM",
    "SYSBACKUP",
    "SYSDG",
    "SYSKM",
    "SYSRAC",
    "AUDSYS",
    "DBSNMP",
    "SYSMAN",
    "MGMT_VIEW",
    "OUTLN",
    "XDB",
    "WMSYS",
    "CTXSYS",
    "MDSYS",
    "MDDATA",
    "ORDSYS",
    "ORDDATA",
    "ORDPLUGINS",
    "OLAPSYS",
    "DVSYS",
    "DVF",
    "LBACSYS",
    "OJVMSYS",
    "APPQOSSYS",
    "GSMADMIN_INTERNAL",
    "GSMCATUSER",
    "GSMUSER",
    "GGSYS",
    "ANONYMOUS",
    "DIP",
    "ORACLE_OCM",
    "XS$NULL",
    "EXFSYS",
    "SI_INFORMTN_SCHEMA",
    "OWBSYS",
    "OWBSYS_AUDIT",
    "SPATIAL_CSW_ADMIN_USR",
    "SPATIAL_WFS_ADMIN_USR",
}

SYSTEM_ORACLE_PREFIXES = (
    "APEX_",
    "FLOWS_",
)


def is_oracle_system_account(username: str | None) -> bool:
    normalized = (username or "").strip().upper()
    if not normalized:
        return False
    return normalized in SYSTEM_ORACLE_USERS or normalized.startswith(
        SYSTEM_ORACLE_PREFIXES
    )
