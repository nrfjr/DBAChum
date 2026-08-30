# DBAChum Windows Runtime Packages

DBAChum is developed from the full Git repository but should be deployed to Windows Server from a versioned runtime package. The package contains the Python backend runtime, the already-compiled Vue frontend, Windows operational scripts, safe configuration templates, and production documentation.

It deliberately excludes development-only and machine-specific content such as `.git`, frontend source, `node_modules`, Playwright/E2E tests, backend tests, Python virtual environments, logs, MongoDB backups, and `backend/.env`.

## Build a package

Run from the source repository after the release-readiness gate is green:

```powershell
.\scripts\windows\build_release.ps1 -Version 2.0.0-dev -Port 8080
```

The builder runs `release_check.ps1` by default, verifies that the Git working tree is clean, stages only approved runtime files, writes a `VERSION` file and `release-manifest.json`, calculates SHA-256 hashes for packaged files, and creates:

```text
release\DBAChum-v2.0.0-dev-windows.zip
```

Use `-AllowDirty` only for disposable development packages. A dirty artifact is recorded as such in the manifest and should not be treated as a formal release.

For a package build where the full release gate has already been run in the same candidate state:

```powershell
.\scripts\windows\build_release.ps1 `
    -Version 2.0.0-dev `
    -SkipReleaseCheck
```

## Package contents

A runtime archive contains approximately:

```text
DBAChum-vX.Y.Z-windows\
├── VERSION
├── release-manifest.json
├── README.md
├── backend\
│   ├── app\
│   ├── scripts\
│   └── requirements.txt
├── frontend\
│   └── dist\
├── deployment\
│   └── windows\backend.env.example
├── scripts\
│   └── windows\
│       ├── install_release.ps1
│       ├── configure_production.ps1
│       ├── run_dbachum.ps1
│       ├── run_collector.ps1
│       ├── run_dbachum_stack.ps1
│       ├── install_startup_task.ps1
│       ├── preflight.ps1
│       ├── smoke_test.ps1
│       ├── backup_mongodb.ps1
│       └── restore_mongodb.ps1
└── docs\
```

## New Windows Server installation

Extract the package to its permanent application directory, for example:

```text
C:\DBAChum
```

Then:

```powershell
cd C:\DBAChum
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\install_release.ps1
```

Review `backend\.env`, then run preflight:

```powershell
.\scripts\windows\preflight.ps1 `
    -Port 8080 `
    -RequireMongoTools `
    -StrictProduction
```

Install the Scheduled Task from an elevated PowerShell window:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8080
```

Finally:

```powershell
.\scripts\windows\smoke_test.ps1 -Port 8080
```

## Updating an existing deployment

Do not blindly delete the existing installation directory. `backend\.env`, MongoDB data, backups, and logs are server state and are not part of the release ZIP.

Recommended update flow:

1. Back up MongoDB.
2. Stop the `DBAChum` Scheduled Task. This stops both the web server and collector because they share the unified stack lifecycle.
3. Preserve `backend\.env`.
4. Replace only release-managed runtime files with the new package.
5. Run `install_release.ps1`; it preserves the existing `.env` and updates `APP_VERSION` to the package `VERSION`.
6. Start the Scheduled Task.
7. Run the smoke test.

Until an automated in-place updater is introduced, keep the previous runtime package available for rollback.

## Manifest and integrity

`release-manifest.json` records the package version, build timestamp, source Git commit/branch when available, whether the source tree was dirty, and a SHA-256 hash for every staged runtime file. The builder also prints the SHA-256 hash of the final ZIP.

The manifest is intended for traceability and integrity checking; it does not contain secrets.
