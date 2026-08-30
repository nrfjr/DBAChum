# DBAChum Native Windows Server Deployment

This is the recommended production path when Docker/WSL is unavailable or undesirable.

## Architecture

```text
Browser / PWA
    |
    | HTTP :8080 (or your chosen port)
    v
DBAChum Scheduled Task
    |
    `-- run_dbachum_stack.ps1 (supervisor)
        |-- Uvicorn + FastAPI
        |     |-- /api/v1/* -> DBAChum API
        |     `-- /*        -> compiled Vue frontend/dist
        |
        `-- python -m app.collector -> telemetry + alerts

FastAPI + Collector
    |
    `-- MongoDB Windows service (localhost:27017 by default)
```

There is no Docker, WSL, Nginx, or IIS requirement. The frontend is built once with Vite and then served by FastAPI as static production files.

The deployment intentionally runs one Uvicorn worker. The metrics collector remains a separate Python process, but both the web server and collector are supervised by the single `DBAChum` Scheduled Task. Starting, stopping, restarting, or recovering that task therefore controls the full application stack and prevents duplicate standalone collectors.

## Prerequisites

Install on the Windows Server:

- Python supported by the project
- Node.js/npm supported by `frontend/package.json`
- MongoDB Community Server or a reachable MongoDB server
- MongoDB Database Tools if you want the supplied backup/restore helpers
- Network access from the Windows Server to each monitored database

The MongoDB Windows service normally appears as `MongoDB`. If yours uses a different service name, DBAChum itself is unaffected; only the helper preflight message will need to be interpreted accordingly.

## 1. Build the native deployment

From an elevated or normal PowerShell prompt in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup.ps1
```

The setup script:

1. creates `backend\.venv` if needed;
2. creates `backend\.env` with a generated encryption key if it does not already exist;
3. installs backend dependencies;
4. runs `npm ci`;
5. builds `frontend\dist` with `VITE_API_BASE_URL=/api/v1` for same-origin production requests.

Review `backend\.env` before production use. The default MongoDB URI is `mongodb://localhost:27017`.

## 2. Preflight

```powershell
.\scripts\windows\preflight.ps1
```

If you also require backup/restore tooling:

```powershell
.\scripts\windows\preflight.ps1 -RequireMongoTools
```

## 3. Test manually before installing startup automation

```powershell
.\scripts\windows\run_dbachum_stack.ps1 -Port 8080
```

Open `http://localhost:8080` and confirm login, Databases, History, and Settings work. The unified launcher also starts the collector. Stop the foreground test with Ctrl+C. For component-only debugging, the original `run_dbachum.ps1` and `run_collector.ps1` launchers remain available.

## 4. Install automatic startup

Run PowerShell **as Administrator**:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8080
```

If clients on other machines must connect directly to TCP 8080 and Windows Firewall blocks it:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8080 -OpenFirewall
```

The task runs as Local System at server startup, allows only one instance, and Task Scheduler is configured to restart it after failure. Its stack supervisor launches both the web server and telemetry collector. If either child process exits unexpectedly, the supervisor stops the other child and exits so Task Scheduler restarts both together. Stopping the `DBAChum` task also terminates both child process trees. The execution time limit is explicitly disabled because the default Task Scheduler limit is unsuitable for a long-running application stack.

If an older Phase 6 installation still has a separate `DBAChum Collector` Scheduled Task, the installer stops and removes it automatically before installing the unified task. This prevents two collectors from running at once.

## 5. Verify

```powershell
Get-ScheduledTask -TaskName DBAChum
Get-ScheduledTaskInfo -TaskName DBAChum
.\scripts\windows\smoke_test.ps1 -Port 8080
```

Application output is written to:

```text
logs\dbachum-stack.log
logs\dbachum-server.log
logs\dbachum-collector.log
```

The web and collector launchers rotate their component logs when they reach 10 MB and keep five rotated logs by default. The stack log records coordinated lifecycle events and child-process failures. The supplied `smoke_test.ps1` also waits briefly for the collector heartbeat and fails if the collector is not alive.

## First administrator

From the repository root:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\bootstrap_admin.py
cd ..
```

## Updating DBAChum

Stop the startup task before updating files:

```powershell
Stop-ScheduledTask -TaskName DBAChum
```

Pull/copy the new application version, then rebuild:

```powershell
.\scripts\windows\setup.ps1
Start-ScheduledTask -TaskName DBAChum
.\scripts\windows\smoke_test.ps1
```

## HTTPS

The basic deployment listens directly on HTTP. For an internal trusted network this may be acceptable according to your organization's policy. If you later put DBAChum behind IIS, another HTTPS reverse proxy, or a load balancer, set `COOKIE_SECURE=true` and terminate TLS there.

## Uninstall automatic startup

This removes only the Scheduled Task, not DBAChum data or MongoDB:

```powershell
.\scripts\windows\uninstall_startup_task.ps1
```

## Production security configuration

Before the final release check, convert an existing development `.env` to the production baseline without replacing its MongoDB URI or encryption key:

```powershell
.\scripts\windows\configure_production.ps1
```

Review `TRUSTED_HOSTS` afterward. The helper includes localhost, the Windows computer name, and detected local IPv4 addresses. Add any DNS alias/FQDN used by administrators.

For an HTTPS deployment behind IIS or another trusted reverse proxy:

```powershell
.\scripts\windows\configure_production.ps1 -EnableSecureCookie
```

See `docs/security.md` for the full baseline.

The optional firewall rule is restricted to Domain/Private profiles and `LocalSubnet` by default. A narrower management subnet can be supplied with `-FirewallRemoteAddress`.
