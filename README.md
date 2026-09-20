# DBAChum

DBAChum is a self-hosted database administration and monitoring workspace built for day-to-day DBA operations.

Current release: **v1.7.1**

## Supported Databases

- Oracle Database
- Microsoft SQL Server
- MySQL
- MariaDB

## Features

- Database connection and health monitoring
- Sessions, storage, parameters, jobs, maintenance, and performance views
- Historical metrics and background telemetry collection
- Database and tablespace growth analytics
- Oracle Advisor views for SGA, PGA, Buffer Cache, Shared Pool, Memory Target, Java Pool, Streams Pool, and MTTR
- Oracle user/schema administration and provisioning
- Server monitoring and SSH terminal access
- Global terminal dock with up to three concurrent SSH sessions
- Context-aware terminal launch from supported alerts and server views
- Per-profile terminal foreground/background colors and warning/error highlighting
- Right-click paste in the built-in terminal
- Alerts
- User and role management
- LDAP integration
- Connection, profile, and application settings
- Windows background deployment

## Requirements

For the Windows release:

- Windows / Windows Server
- Python 3
- MongoDB Server
- MongoDB Database Tools for backup/restore

Oracle Instant Client is optional and is required for Oracle Thick mode and Oracle 10g connectivity.

## Windows Installation

Download the latest package from **GitHub Releases** and extract it.

Install the runtime:

```powershell
.\scripts\windows\install_release.ps1 -PythonCommand py
```

Configure `backend\.env`, particularly the MongoDB connection.

Run the production preflight:

```powershell
.\scripts\windows\preflight.ps1 -RequireMongoTools -StrictProduction
```

Create the initial administrator:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.bootstrap_admin
cd ..
```

Install DBAChum as a background task from an elevated PowerShell:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8080
Start-ScheduledTask -TaskName DBAChum
```

Verify the deployment:

```powershell
.\scripts\windows\smoke_test.ps1 -Port 8080
```

Then open:

```text
http://localhost:8080
```

## Development

Frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Release

Latest stable release: **DBAChum v1.7.1**

Release packages, checksums, and release notes are available under GitHub Releases.
