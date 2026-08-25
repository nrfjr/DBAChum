from __future__ import annotations

import re
import unicodedata

from app.core.exceptions import AppError


# Based on the working v1 LDIF layout, but converted to a configurable template.
# Company-specific values remain editable under Settings -> LDAP.
DEFAULT_LDIF_TEMPLATE = """dn: cn=<USERNAME>,cn=Users,<BASE_DN>
objectclass: top
objectclass: organizationalperson
objectclass: person
objectclass: inetorgperson
objectclass: TESTOBJ
objectclass: rsimUser
givenname: <FIRSTNAME>
sn: <LASTNAME>
cn: <USERNAME>
uid: <USERNAME>
employeenumber: <EMPLOYEE ID>
mail: <USERNAME>@test
description: Department Store
displayname: <USERNAME>
preferredlanguage: en
userstore: rsimStoreId=2,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=1,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=3,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=4,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=5,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=6,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=7,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=8,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=9,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=41,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=42,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=43,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=45,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=46,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=44,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=47,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=48,cn=rsimStores,cn=RSIM,<BASE_DN>
userstore: rsimStoreId=49,cn=rsimStores,cn=RSIM,<BASE_DN>
employmentstatus: 0
ssn: 123456789
preferredcountry: US
userrole: rsimRoleName=TEST Admin,cn=rsimRoles,cn=RSIM,<BASE_DN>
homestore: rsimStoreId=2,cn=rsimStores,cn=RSIM,<BASE_DN>
userpassword: <PASSWORD>
"""

SUPPORTED_LDIF_TOKENS = {
    "<USERNAME>",
    "<FIRSTNAME>",
    "<MIDDLENAME>",
    "<LASTNAME>",
    "<EMPLOYEE ID>",
    "<PASSWORD>",
    "<BASE_DN>",
}


def normalize_person_name(value: str | None) -> str | None:
    if value is None:
        return None

    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character) and ord(character) < 128
    )
    letters_and_spaces = re.sub(r"[^A-Za-z ]+", "", ascii_value)
    normalized = re.sub(r"\s+", " ", letters_and_spaces).strip()
    return normalized or None


def normalize_employee_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "", value).strip()
    return normalized or None


def render_ldif(
    template: str,
    *,
    username: str,
    password: str,
    first_name: str | None,
    middle_name: str | None,
    last_name: str | None,
    employee_id: str | None,
    base_dn: str,
) -> str:
    normalized_first = normalize_person_name(first_name)
    normalized_middle = normalize_person_name(middle_name) or ""
    normalized_last = normalize_person_name(last_name)
    normalized_employee_id = normalize_employee_id(employee_id)

    if not normalized_first or not normalized_last or not normalized_employee_id:
        raise AppError(
            "First name, last name and employee ID are required to generate an LDIF file.",
            code="LDIF_IDENTITY_FIELDS_REQUIRED",
            status_code=400,
        )

    if not base_dn.strip():
        raise AppError(
            "LDAP Base DN is required to generate an LDIF file.",
            code="LDAP_BASE_DN_REQUIRED",
            status_code=400,
        )

    values = {
        "<USERNAME>": username,
        "<FIRSTNAME>": normalized_first,
        "<MIDDLENAME>": normalized_middle,
        "<LASTNAME>": normalized_last,
        "<EMPLOYEE ID>": normalized_employee_id,
        "<PASSWORD>": password,
        "<BASE_DN>": base_dn.strip(),
    }

    result = template or DEFAULT_LDIF_TEMPLATE
    for token, value in values.items():
        result = result.replace(token, value)

    unresolved = sorted(set(re.findall(r"<[^>]+>", result)))
    if unresolved:
        raise AppError(
            "LDIF template contains unresolved placeholders: " + ", ".join(unresolved),
            code="LDIF_TEMPLATE_INVALID",
            status_code=400,
        )

    return result.rstrip() + "\n"
