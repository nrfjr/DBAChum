from pathlib import Path
import ast
import re

from app.core.permissions import (
    Permission,
    has_permission,
    permission_values_for_role,
)
from app.schemas.user import UserRole


ENDPOINT_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints"


def test_role_matrix_keeps_viewer_read_only_and_operator_operational():
    assert permission_values_for_role(UserRole.VIEWER) == [
        Permission.MONITOR_READ.value,
    ]

    operator = set(permission_values_for_role(UserRole.OPERATOR))
    assert Permission.MONITOR_READ.value in operator
    assert Permission.CONNECTION_TEST.value in operator
    assert Permission.DATABASE_INSPECT.value in operator
    assert Permission.DBA_OPERATE.value in operator
    assert Permission.TERMINAL_USE.value in operator
    assert Permission.ALERT_MANAGE.value in operator

    assert Permission.CONNECTION_MANAGE.value not in operator
    assert Permission.SERVER_MANAGE.value not in operator
    assert Permission.USER_MANAGE.value not in operator
    assert Permission.PROVISIONING_MANAGE.value not in operator
    assert Permission.LDAP_MANAGE.value not in operator


def test_admin_is_superset_of_operator():
    operator = set(permission_values_for_role(UserRole.OPERATOR))
    admin = set(permission_values_for_role(UserRole.ADMIN))
    assert operator < admin
    assert Permission.CONNECTION_MANAGE.value in admin
    assert Permission.SERVER_MANAGE.value in admin
    assert Permission.USER_MANAGE.value in admin


def test_unknown_role_never_receives_permissions():
    assert permission_values_for_role("unknown") == []
    assert not has_permission("unknown", Permission.MONITOR_READ)


def _router_functions(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        router_decorated = False
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "router"
            ):
                router_decorated = True
                break

        if router_decorated:
            yield node.name, ast.get_source_segment(source, node) or ""


def test_all_non_public_routes_have_an_auth_or_permission_boundary():
    public_endpoint_files = {"auth.py", "health.py"}

    for path in ENDPOINT_DIR.glob("*.py"):
        if path.name in public_endpoint_files or path.name == "__init__.py":
            continue

        for function_name, source in _router_functions(path):
            if path.name == "profile.py":
                assert "get_current_user" in source, (path.name, function_name)
                continue

            if path.name == "server_terminal.py":
                assert "get_user_from_session" in source, (path.name, function_name)
                assert "Permission.TERMINAL_USE" in source, (path.name, function_name)
                continue

            assert re.search(
                r"require_permission\s*\(\s*Permission\.",
                source,
            ), (path.name, function_name)


def test_sensitive_route_families_use_narrow_boundaries():
    alerts = (ENDPOINT_DIR / "alerts.py").read_text(encoding="utf-8")
    terminal = (ENDPOINT_DIR / "server_terminal.py").read_text(encoding="utf-8")
    monitoring = (ENDPOINT_DIR / "server_monitoring.py").read_text(encoding="utf-8")
    mysql = (ENDPOINT_DIR / "mysql_dba.py").read_text(encoding="utf-8")
    sqlserver = (ENDPOINT_DIR / "sqlserver_dba.py").read_text(encoding="utf-8")
    oracle = (ENDPOINT_DIR / "oracle_dba.py").read_text(encoding="utf-8")

    assert alerts.count("Permission.ALERT_MANAGE") == 2
    assert "Permission.TERMINAL_USE" in terminal
    assert "Permission.CONNECTION_TEST" in monitoring
    assert "Permission.DATABASE_INSPECT" in mysql
    assert "Permission.DATABASE_INSPECT" in sqlserver
    assert "Permission.DATABASE_INSPECT" in oracle
    assert "Permission.DBA_OPERATE" in oracle
