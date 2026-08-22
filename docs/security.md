# DBAChum Production Security Baseline

DBAChum is an administrative application and should be treated as privileged infrastructure. The native Windows deployment is intended for a trusted internal network unless it is placed behind an HTTPS reverse proxy.

## Required production settings

Run the production configuration helper after `setup.ps1`:

```powershell
.\scripts\windows\configure_production.ps1
```

The helper preserves the database URI and encryption key while setting:

```text
ENVIRONMENT=production
API_DOCS_ENABLED=false
CORS_ORIGINS=
TRUSTED_HOSTS=<local hostnames and IPv4 addresses>
```

Review `TRUSTED_HOSTS` in `backend\.env`. Add every DNS alias, FQDN, or IP address users actually place in the browser address bar. Requests with any other Host header are rejected.

## HTTP versus HTTPS

The basic native deployment can run directly over HTTP on an approved internal network. In that mode:

```text
COOKIE_SECURE=false
```

Do not expose that configuration to the public internet.

When IIS, a load balancer, or another trusted reverse proxy terminates HTTPS, run:

```powershell
.\scripts\windows\configure_production.ps1 -EnableSecureCookie
```

That enables secure session cookies. DBAChum also emits HSTS when secure-cookie mode is enabled.

## Browser safeguards

Production responses include conservative security headers:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- restricted camera, microphone, and geolocation permissions
- CSP restrictions for framing, base URLs, and embedded objects
- `Cache-Control: no-store` on API responses

OpenAPI/Swagger/ReDoc endpoints are disabled by the production template.

## CORS

The compiled Vue frontend and API are served from the same FastAPI origin, so production normally needs no CORS configuration. Leave `CORS_ORIGINS` empty unless a separate trusted frontend must call the API.

Never configure a wildcard CORS origin in production. DBAChum rejects that configuration at startup.

## Secrets

`backend\.env` contains the connection-encryption key and may contain a MongoDB URI with credentials. It must never be committed to Git, copied into a release archive, posted in logs, or shared in tickets/chat.

The release preflight fails if `backend/.env` is tracked by Git. The root `.gitignore` also excludes environment files, logs, backups, and local database data.

Back up the production encryption key securely. Saved database passwords cannot be decrypted after the key is lost or replaced.

## Passwords and sessions

New managed-user passwords and password resets require at least 12 characters. Session cookies are HTTP-only and SameSite=Lax. Disabled or deleted users no longer retain a usable server-side session; stale sessions are removed when encountered.

## Network exposure

`run_dbachum.ps1` listens on all interfaces by default so internal clients can reach the server. Windows Firewall remains the primary host-level boundary.

When installing the optional inbound firewall rule:

```powershell
.\scripts\windows\install_startup_task.ps1 -Port 8080 -OpenFirewall
```

DBAChum now limits that rule to Domain/Private profiles and `LocalSubnet` by default. To use a narrower source range:

```powershell
.\scripts\windows\install_startup_task.ps1 `
  -Port 8080 `
  -OpenFirewall `
  -FirewallRemoteAddress '10.20.30.0/24'
```

Prefer a specific management subnet when your network design allows it.

## Release gate

A release candidate must pass the strict production preflight as part of:

```powershell
.\scripts\windows\release_check.ps1 -Port 8080
```

The release gate requires production mode, disabled API docs, a non-wildcard trusted-host allow-list, a valid encryption key, and MongoDB backup/restore tooling in addition to the automated backend/frontend tests and live smoke test.
