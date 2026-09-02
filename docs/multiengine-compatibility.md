# Multi-engine and legacy compatibility

## Scope of this slice

This foundation makes SQL Server monitoring capability-aware and introduces the cross-engine Backup Health workspace.

### SQL Server compatibility

DBAChum no longer assumes that every SQL Server supports the 2005+ DMV/catalog surface.

- SQL Server 2000 (major version 8) uses legacy-safe system tables for Overview, Sessions, Activity, and Storage.
- SQL Server 2005+ uses DMVs/catalog views where they provide materially better data.
- SQL Server Overview deliberately uses the SQL Server 2000-compatible `master.dbo.sysprocesses` / `master.dbo.sysdatabases` surface because modern SQL Server retains that compatibility surface.
- The detected server version is normalized into a generation label from SQL Server 2000 through SQL Server 2025/current major versions.
- Capability flags determine which query family is used. Unknown versions stay conservative instead of assuming modern features.

### SQL Server connection providers

`mssql-python` remains the normal modern provider. Its vendor support statement covers actively supported SQL Server releases, so DBAChum does not treat it as guaranteed SQL Server 2000 support.

A separate `pyodbc` provider path exists for legacy systems:

- `auto`: try the modern provider first, then installed SQL Server ODBC drivers.
- `mssql_python`: modern provider only.
- `pyodbc`: ODBC provider only; an exact driver can be configured.
- encryption can be `auto`, `yes`, or `no`. Auto tries encrypted transport first and only falls back when necessary.

For SQL Server 2000, prefer an installed driver that is known to communicate with that server generation. Do not weaken encryption on modern production instances just to make legacy instances work; the legacy behavior is isolated per connection.

## Backup Health

A new **Backups** tab uses one normalized API across engines:

`GET /databases/{connection_id}/backups`

### SQL Server

Source: `msdb` backup/restore history.

- instance-wide database summary
- recovery model
- latest full backup
- latest differential backup
- latest transaction-log backup
- recent backup-set history
- duration, size, owner, label, and media destination when visible

The current slice treats rows in `msdb.dbo.backupset` as recorded backup sets. Failed-attempt alerting is intentionally not inferred from missing `backupset` rows; that will use SQL Agent/error-log correlation in a later backup-policy slice.

### Oracle

Source: `V$RMAN_BACKUP_JOB_DETAILS` control-file history (available on the legacy Oracle generations DBAChum already targets, including 10g).

The UI normalizes full, incremental, archive-log, controlfile, and SPFILE jobs and preserves RMAN status/device information.

### MySQL

MySQL intentionally returns `external backup provider required` for now. There is no one universal native history source shared by mysqldump, XtraBackup, MySQL Enterprise Backup, filesystem/VM snapshots, and custom scripts. The API and UI contract are already stable so a provider can be plugged in later without redesigning Backup Health.

## Backup policy / alerts

This slice discovers and displays backup health but does **not** impose arbitrary global age thresholds. A 24-hour full-backup SLA would be wrong for some archive databases and would create alert noise.

The next backup-policy slice should add per-database expectations, for example:

- full backup maximum age
- differential/incremental maximum age
- transaction-log/archive-log maximum age
- databases excluded from a policy
- warning and critical thresholds

Once policies exist, the background collector can evaluate them and reuse the alert lifecycle (debounce, resolve, clear/suppress-until-recovery).

## Test matrix

When validating SQL Server, use at least one instance from each available family:

1. SQL Server 2000 — expect legacy mode; test `auto`, then explicit legacy ODBC if required.
2. SQL Server 2005–2008 R2 — expect DMV mode without newer-only functions.
3. SQL Server 2012–2019 — expect modern DMV/catalog mode.
4. SQL Server 2022/2025 when available — expect modern mode.

For each instance validate:

- Connection Test reports version/generation/provider.
- Overview loads without unsupported-object errors.
- Sessions and Activity use the correct capability tier.
- Storage lists data/log files.
- Backups lists visible `msdb` history and all non-tempdb databases.

If a SQL Server 2000 connection only works through an old ODBC driver, record the exact driver name in the connection settings so future restarts/deployments are deterministic.
