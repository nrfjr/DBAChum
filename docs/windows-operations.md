# DBAChum Windows Operations Runbook

## Service model

MongoDB runs as its native Windows service. DBAChum itself is a long-running Uvicorn process launched by the `DBAChum` Windows Scheduled Task.

## Start / stop / restart

```powershell
Start-ScheduledTask -TaskName DBAChum
Stop-ScheduledTask -TaskName DBAChum
```

Restart:

```powershell
Stop-ScheduledTask -TaskName DBAChum
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName DBAChum
```

Check state and last result:

```powershell
Get-ScheduledTask -TaskName DBAChum
Get-ScheduledTaskInfo -TaskName DBAChum
```

## Health verification

```powershell
.\scripts\windows\smoke_test.ps1
```

Direct API readiness:

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/health/ready
```

## Logs

Primary server log:

```text
logs\dbachum-server.log
```

Tail it:

```powershell
Get-Content .\logs\dbachum-server.log -Wait -Tail 100
```

## MongoDB service

```powershell
Get-Service MongoDB
Start-Service MongoDB
Stop-Service MongoDB
Restart-Service MongoDB
```

If your MongoDB service has another name, use that service name instead.

## Backup

Default quiesced backup (DBAChum task is paused while `mongodump` runs):

```powershell
.\scripts\windows\backup_mongodb.ps1
```

Online backup without pausing DBAChum:

```powershell
.\scripts\windows\backup_mongodb.ps1 -Online
```

Archives are written to `backups\` by default.

## Restore

A restore is destructive because existing collections in the selected database are dropped before restore. The helper requires the literal confirmation token `RESTORE`:

```powershell
.\scripts\windows\restore_mongodb.ps1 `
  -Archive .\backups\dbachum-mongodb-YYYYMMDDTHHMMSSZ.archive.gz `
  -ConfirmRestore RESTORE
```

The DBAChum task is stopped for the restore and restarted afterward if it was running beforehand.

## Application update

Recommended sequence:

```powershell
.\scripts\windows\backup_mongodb.ps1
Stop-ScheduledTask -TaskName DBAChum
# update the repository/files
.\scripts\windows\setup.ps1
Start-ScheduledTask -TaskName DBAChum
.\scripts\windows\smoke_test.ps1
```

## Common failures

### Task immediately stops

Inspect:

```powershell
Get-ScheduledTaskInfo -TaskName DBAChum
Get-Content .\logs\dbachum-server.log -Tail 200
```

Then run the launcher manually to see the failure in the console:

```powershell
.\scripts\windows\run_dbachum.ps1
```

### MongoDB is unavailable

Check the Windows service and the URI in `backend\.env`:

```powershell
Get-Service MongoDB
Select-String -Path .\backend\.env -Pattern '^MONGODB_URI='
```

### Port 8080 is occupied

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

Install DBAChum on another port if necessary:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8081
```

### Frontend loads but old assets remain

Rebuild the frontend and hard-refresh the browser/PWA:

```powershell
.\scripts\windows\setup.ps1 -SkipDependencies
```

### Database connections fail only after deployment

Test reachability from the Windows Server itself. DBAChum connects from the server, not from the administrator's workstation. Verify DNS, firewall routes, database listener ports, and the saved DBAChum connection credentials.

## Security configuration check

After changing server names, IP addresses, DNS aliases, HTTPS termination, or firewall scope, review `backend\.env` and rerun:

```powershell
.\scripts\windows\preflight.ps1 -Port 8080 -RequireMongoTools -StrictProduction
```

If a new hostname/FQDN is used to access DBAChum, add it to `TRUSTED_HOSTS` before restarting the Scheduled Task.

Do not copy `backend\.env`, `backups\`, or `logs\` into production release archives or source-control commits.
