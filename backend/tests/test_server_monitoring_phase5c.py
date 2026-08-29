from app.services.server_monitoring_parsers import (
    parse_df_pk,
    parse_proc_meminfo,
    parse_proc_stat_pair,
    parse_ps,
    parse_systemd_failed,
    parse_uptime_load,
)


def test_parse_linux_memory_snapshot():
    snapshot = parse_proc_meminfo(
        """
MemTotal:       16384000 kB
MemFree:         1024000 kB
MemAvailable:    4096000 kB
Buffers:          256000 kB
Cached:          2048000 kB
SwapTotal:       2097152 kB
SwapFree:        1048576 kB
"""
    )

    assert snapshot.total_bytes == 16384000 * 1024
    assert snapshot.available_bytes == 4096000 * 1024
    assert snapshot.used_percent == 75.0
    assert snapshot.swap_used_bytes == 1048576 * 1024
    assert snapshot.swap_used_percent == 50.0


def test_parse_df_pk_sorts_data_fields_without_mount_loss():
    rows = parse_df_pk(
        """Filesystem 1024-blocks Used Available Capacity Mounted on
/dev/mapper/root 104857600 52428800 52428800 50% /
/dev/sdb1 209715200 188743680 20971520 90% /u01
"""
    )

    assert len(rows) == 2
    assert rows[1].mount_point == "/u01"
    assert rows[1].used_percent == 90.0
    assert rows[1].total_bytes == 209715200 * 1024


def test_parse_cpu_delta_uses_idle_delta():
    first = "cpu  100 0 100 800 0 0 0 0 0 0\n"
    second = "cpu  150 0 150 900 0 0 0 0 0 0\n"

    # 100 busy ticks + 100 idle ticks => 50.0% used.
    assert parse_proc_stat_pair(first, second) == 50.0


def test_parse_processes_orders_by_cpu():
    rows = parse_ps(
        """
101 oracle 1.2 3.4 00:10:00 ora_pmon_ORCL ora_pmon_ORCL
202 root 8.5 1.0 00:00:15 backup /usr/local/bin/backup --run
"""
    )

    assert [row.pid for row in rows] == [202, 101]
    assert rows[0].command == "/usr/local/bin/backup --run"


def test_parse_uptime_and_load_tuple():
    assert parse_uptime_load("86461 0.40 0.30 0.20\n") == (86461, 0.4, 0.3, 0.2)


def test_parse_systemd_failed_services():
    failed = parse_systemd_failed(
        """
httpd.service loaded failed failed The Apache HTTP Server
custom-agent.service loaded failed failed Custom Agent
"""
    )
    assert failed == ["httpd.service", "custom-agent.service"]


def test_parse_aix_style_uptime_and_load():
    from app.services.server_monitoring_parsers import parse_uptime_command

    uptime, load1, load5, load15 = parse_uptime_command(
        "  09:48AM up 12 days, 3:14, 4 users, load average: 0.22, 0.18, 0.15"
    )
    assert uptime == 12 * 86400 + 3 * 3600 + 14 * 60
    assert (load1, load5, load15) == (0.22, 0.18, 0.15)


def test_parse_vmstat_idle_by_header_position():
    from app.services.server_monitoring_parsers import parse_vmstat_cpu

    text = """
kthr memory page faults cpu time
r b avm fre re pi po fr sr cy in sy cs us sy id wa
1 0 100 200 0 0 0 0 0 0 1 2 3 10 5 80 5
"""
    assert parse_vmstat_cpu(text) == 20.0


def test_parse_aix_svmon_memory():
    from app.services.server_monitoring_parsers import parse_svmon_global

    snapshot = parse_svmon_global(
        """
               size       inuse        free         pin     virtual
memory     32768.00    24576.00     8192.00     4096.00    18000.00
"""
    )
    assert snapshot is not None
    assert snapshot.total_bytes == 32768 * 1024 * 1024
    assert snapshot.used_percent == 75.0


def test_password_auth_keeps_keyboard_interactive_fallback_enabled():
    """Prevent regressions that reject PAM/keyboard-interactive password logins."""
    from pathlib import Path

    source_path = Path(__file__).parents[1] / "app" / "services" / "server_monitoring.py"
    source = source_path.read_text(encoding="utf-8")
    assert "fallback=True" in source
    assert "fallback=False" not in source


def test_authentication_has_separate_longer_timeout():
    """EL7/PAM authentication must not share the short TCP/banner timeout."""
    from pathlib import Path

    source_path = Path(__file__).parents[1] / "app" / "services" / "server_monitoring.py"
    source = source_path.read_text(encoding="utf-8")
    assert "AUTH_TIMEOUT_SECONDS = 30.0" in source
    assert "transport.auth_timeout = AUTH_TIMEOUT_SECONDS" in source
    assert "transport.auth_timeout = CONNECT_TIMEOUT_SECONDS" not in source


def test_authentication_timeout_is_not_reported_as_bad_password():
    from pathlib import Path

    source_path = Path(__file__).parents[1] / "app" / "services" / "server_monitoring.py"
    source = source_path.read_text(encoding="utf-8")
    assert "SSH_AUTHENTICATION_TIMEOUT" in source
    assert "SSH_AUTHENTICATION_METHOD_NOT_ALLOWED" in source
    assert "authentication was rejected by the server" in source
