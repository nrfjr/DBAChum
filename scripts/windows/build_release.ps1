param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$Version,

    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$OutputDirectory = 'release',

    [switch]$SkipReleaseCheck,
    [switch]$SkipE2E,
    [switch]$SkipSmoke,
    [switch]$AllowDirty,
    [switch]$KeepStaging
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ReleaseName = "DBAChum-v$Version-windows"

$ProductionEnv = Join-Path $ProjectRoot 'frontend\.env.production'

if (-not (Test-Path $ProductionEnv)) {
    throw 'frontend/.env.production is missing.'
}

$ProductionApiBase = Select-String `
    -Path $ProductionEnv `
    -Pattern '^VITE_API_BASE_URL=/api/v1$'

if (-not $ProductionApiBase) {
    throw 'frontend/.env.production must contain VITE_API_BASE_URL=/api/v1.'
}

if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $ReleaseRoot = $OutputDirectory
}
else {
    $ReleaseRoot = Join-Path $ProjectRoot $OutputDirectory
}

$StagingRoot = Join-Path $ReleaseRoot '_staging'
$StagingDir = Join-Path $StagingRoot $ReleaseName
$ZipPath = Join-Path $ReleaseRoot "$ReleaseName.zip"
$ReleaseCheckScript = Join-Path $PSScriptRoot 'release_check.ps1'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Copy-RequiredItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationRelativePath
    )

    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path $source)) {
        throw "Required release input is missing: $RelativePath"
    }

    $destination = Join-Path $StagingDir $DestinationRelativePath
    $parent = Split-Path $destination -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -Path $source -Destination $destination -Recurse -Force
}

function Get-GitValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($null -eq $gitCommand) {
        $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    }

    if ($null -eq $gitCommand -or -not (Test-Path (Join-Path $ProjectRoot '.git'))) {
        return $null
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $ProjectRoot
    try {
        $value = (& $gitCommand.Source @Arguments 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $value
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $previousPreference
    }
}

function Set-EnvTemplateVersion {
    $templatePath = Join-Path $StagingDir 'deployment\windows\backend.env.example'
    $text = Get-Content $templatePath -Raw

    if ($text -match '(?m)^APP_VERSION=.*$') {
        $text = [regex]::Replace(
            $text,
            '(?m)^APP_VERSION=.*$',
            "APP_VERSION=$Version"
        )
    }
    else {
        $text = "APP_VERSION=$Version`r`n$text"
    }

    [System.IO.File]::WriteAllText(
        $templatePath,
        $text,
        $Utf8NoBom
    )
}

function Remove-DevelopmentArtifacts {
    Get-ChildItem $StagingDir -Recurse -Directory -Force |
        Where-Object {
            $_.Name -in @(
                '__pycache__',
                '.pytest_cache',
                '.mypy_cache',
                '.ruff_cache'
            )
        } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force

    Get-ChildItem $StagingDir -Recurse -File -Force |
        Where-Object {
            $_.Extension -in @('.pyc', '.pyo') -or
            $_.Name -eq '.eslintcache'
        } |
        Remove-Item -Force
}

function Assert-ReleaseIsClean {
    $forbiddenDirectories = @(
        '.git',
        'node_modules',
        '.venv',
        'venv',
        'tests',
        'e2e',
        'test-results',
        'playwright-report',
        'backups',
        'logs',
        'src'
    )

    $badDirectories = Get-ChildItem $StagingDir -Recurse -Directory -Force |
        Where-Object { $_.Name -in $forbiddenDirectories }

    if ($badDirectories) {
        throw (
            'Release contains forbidden development/runtime-state directories: ' +
            (($badDirectories | ForEach-Object { $_.FullName }) -join ', ')
        )
    }

    $badFiles = Get-ChildItem $StagingDir -Recurse -File -Force |
        Where-Object {
            $_.Name -eq '.env' -or
            $_.Name -match '\.(?:pyc|pyo|log|bak|tmp|temp)$' -or
            $_.Name -match '\.archive\.gz$' -or
            $_.Name -eq 'trace.zip'
        }

    if ($badFiles) {
        throw (
            'Release contains forbidden secrets/runtime-state files: ' +
            (($badFiles | ForEach-Object { $_.FullName }) -join ', ')
        )
    }

    $requiredFiles = @(
        'VERSION',
        'backend\requirements.txt',
        'backend\app\main.py',
        'frontend\dist\index.html',
        'deployment\windows\backend.env.example',
        'scripts\windows\install_release.ps1',
        'scripts\windows\run_dbachum.ps1',
        'scripts\windows\run_collector.ps1',
        'scripts\windows\run_dbachum_stack.ps1',
        'scripts\windows\install_startup_task.ps1',
        'scripts\windows\preflight.ps1',
        'scripts\windows\smoke_test.ps1'
    )

    foreach ($relativePath in $requiredFiles) {
        if (-not (Test-Path (Join-Path $StagingDir $relativePath))) {
            throw "Release is missing required runtime file: $relativePath"
        }
    }
}

function Write-ReleaseManifest {
    param(
        [AllowNull()]
        [string]$Commit,

        [AllowNull()]
        [string]$Branch,

        [bool]$Dirty
    )

    $files = @()
    $allFiles = Get-ChildItem $StagingDir -Recurse -File -Force |
        Where-Object { $_.Name -ne 'release-manifest.json' } |
        Sort-Object FullName

    foreach ($file in $allFiles) {
        $relative = $file.FullName.Substring($StagingDir.Length)
        $relative = $relative.TrimStart([char[]]@('\', '/'))
        $files += [ordered]@{
            path = $relative.Replace('\', '/')
            size_bytes = $file.Length
            sha256 = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

    $manifest = [ordered]@{
        product = 'DBAChum'
        version = $Version
        release_name = $ReleaseName
        platform = 'windows-native'
        built_at_utc = [DateTime]::UtcNow.ToString('o')
        source_commit = $Commit
        source_branch = $Branch
        source_dirty = $Dirty
        file_count = $files.Count
        files = $files
    }

    $manifestPath = Join-Path $StagingDir 'release-manifest.json'
    [System.IO.File]::WriteAllText(
        $manifestPath,
        ($manifest | ConvertTo-Json -Depth 6),
        $Utf8NoBom
    )
}

Write-Step 'Validate source checkout'

$gitCommit = Get-GitValue -Arguments @('rev-parse', 'HEAD')
$gitBranch = Get-GitValue -Arguments @('rev-parse', '--abbrev-ref', 'HEAD')
$gitStatus = Get-GitValue -Arguments @('status', '--porcelain')
$gitDirty = -not [string]::IsNullOrWhiteSpace($gitStatus)

if ($gitDirty -and -not $AllowDirty) {
    throw (
        'Working tree is not clean. Commit the release candidate first, ' +
        'or use -AllowDirty only for a disposable development package.'
    )
}

if ($gitDirty) {
    Write-Warning 'Building from a dirty working tree. This artifact is not suitable for a formal release.'
}
elseif ($null -ne $gitCommit) {
    Write-Host "PASS  Git checkout is clean at $gitCommit" -ForegroundColor Green
}
else {
    Write-Warning 'Git metadata is unavailable; manifest source_commit will be null.'
}

if (-not $SkipReleaseCheck) {
    Write-Step 'Run release-readiness gate'

    if (-not (Test-Path $ReleaseCheckScript)) {
        throw "Release check script was not found: $ReleaseCheckScript"
    }

    $releaseCheckArgs = @('-Port', $Port)
    if ($SkipE2E) { $releaseCheckArgs += '-SkipE2E' }
    if ($SkipSmoke) { $releaseCheckArgs += '-SkipSmoke' }

    & $ReleaseCheckScript @releaseCheckArgs
}
else {
    Write-Warning 'Release-readiness gate skipped.'
}

$frontendIndex = Join-Path $ProjectRoot 'frontend\dist\index.html'
if (-not (Test-Path $frontendIndex)) {
    throw 'frontend/dist/index.html is missing. Build the production frontend before packaging.'
}

$FrontendAssets = Join-Path $ProjectRoot 'frontend\dist\assets'

if (-not (Test-Path $FrontendAssets)) {
    throw 'frontend/dist/assets is missing. Build the production frontend before packaging.'
}

$BadApiReference = Get-ChildItem `
    -Path $FrontendAssets `
    -Filter '*.js' `
    -File |
    Select-String 'localhost:8000' |
    Select-Object -First 1

if ($BadApiReference) {
    throw @'
Production frontend contains localhost:8000.

Rebuild the frontend with:
    VITE_API_BASE_URL=/api/v1
before creating a release package.
'@
}
Write-Step "Stage $ReleaseName"

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
if (Test-Path $StagingDir) {
    Remove-Item $StagingDir -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

# Backend runtime only.
Copy-RequiredItem 'backend\app' 'backend\app'
Copy-RequiredItem 'backend\scripts' 'backend\scripts'
Copy-RequiredItem 'backend\requirements.txt' 'backend\requirements.txt'
if (Test-Path (Join-Path $ProjectRoot 'backend\main.py')) {
    Copy-RequiredItem 'backend\main.py' 'backend\main.py'
}

# Compiled frontend only. No Vue source, npm dependencies, or E2E files.
Copy-RequiredItem 'frontend\dist' 'frontend\dist'

# Safe production configuration template.
Copy-RequiredItem 'deployment\windows\backend.env.example' 'deployment\windows\backend.env.example'

# Runtime/operations scripts only. build_release.ps1 intentionally stays in source.
$runtimeScripts = @(
    'install_release.ps1',
    'configure_production.ps1',
    'run_dbachum.ps1',
    'run_collector.ps1',
    'run_dbachum_stack.ps1',
    'install_startup_task.ps1',
    'preflight.ps1',
    'smoke_test.ps1',
    'backup_mongodb.ps1',
    'restore_mongodb.ps1'
)

foreach ($scriptName in $runtimeScripts) {
    Copy-RequiredItem `
        "scripts\windows\$scriptName" `
        "scripts\windows\$scriptName"
}

$runtimeDocs = @(
    'windows-deployment.md',
    'windows-operations.md',
    'security.md',
    'release-package.md'
)

foreach ($docName in $runtimeDocs) {
    Copy-RequiredItem "docs\$docName" "docs\$docName"
}

[System.IO.File]::WriteAllText(
    (Join-Path $StagingDir 'VERSION'),
    "$Version`r`n",
    $Utf8NoBom
)

$releaseReadme = @"
# DBAChum $Version - Windows Runtime Package

This package contains only the files required to run DBAChum on native Windows Server.
It intentionally excludes the Git repository, frontend source, tests, developer dependencies, logs, backups, and secrets.

New installation:

    Set-ExecutionPolicy -Scope Process Bypass
    .\scripts\windows\install_release.ps1

Then, from an elevated PowerShell window:

    .\scripts\windows\install_startup_task.ps1 -Port 8080

Validate:

    .\scripts\windows\smoke_test.ps1 -Port 8080

Existing deployment:
Read docs\release-package.md before replacing runtime files. Always back up MongoDB first and preserve backend\.env.
"@

[System.IO.File]::WriteAllText(
    (Join-Path $StagingDir 'README.md'),
    $releaseReadme,
    $Utf8NoBom
)

Set-EnvTemplateVersion
Remove-DevelopmentArtifacts
Assert-ReleaseIsClean
Write-ReleaseManifest -Commit $gitCommit -Branch $gitBranch -Dirty $gitDirty

Write-Step 'Create release archive'
Compress-Archive -Path $StagingDir -DestinationPath $ZipPath -CompressionLevel Optimal

if (-not (Test-Path $ZipPath)) {
    throw "Release archive was not created: $ZipPath"
}

$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$zipSizeMB = [Math]::Round((Get-Item $ZipPath).Length / 1MB, 2)

if (-not $KeepStaging) {
    Remove-Item $StagingDir -Recurse -Force
    if ((Test-Path $StagingRoot) -and -not (Get-ChildItem $StagingRoot -Force | Select-Object -First 1)) {
        Remove-Item $StagingRoot -Force
    }
}

Write-Host ''
Write-Host 'PASS  DBAChum Windows runtime package created.' -ForegroundColor Green
Write-Host "      Version : $Version"
Write-Host "      Archive : $ZipPath"
Write-Host "      Size MB : $zipSizeMB"
Write-Host "      SHA256  : $zipHash"
if ($gitDirty) {
    Write-Host '      Source  : DIRTY WORKTREE (development artifact)' -ForegroundColor Yellow
}
elseif ($null -ne $gitCommit) {
    Write-Host "      Commit  : $gitCommit"
}
