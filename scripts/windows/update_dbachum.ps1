param(
    [string]$PackagePath = '',

    [string]$ChecksumPath = '',

    [string]$ReleaseVersion = '',

    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$TaskName = 'DBAChum',

    [string]$PythonCommand = '',

    [string]$TargetRoot = '',

    [switch]$ValidateOnly,
    [switch]$SkipDatabaseBackup,
    [switch]$SkipSmoke,
    [switch]$AllowDowngrade,
    [switch]$AllowSameVersion
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-FullPath([string]$Path, [string]$BaseDirectory = '') {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'A required path was empty.'
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    if ([string]::IsNullOrWhiteSpace($BaseDirectory)) {
        $BaseDirectory = (Get-Location).Path
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BaseDirectory $Path))
}

function Get-SemVer([string]$Value) {
    $match = [regex]::Match(
        $Value.Trim(),
        '^v?(?<major>0|[1-9][0-9]*)\.(?<minor>0|[1-9][0-9]*)\.(?<patch>0|[1-9][0-9]*)(?:-(?<pre>[0-9A-Za-z.-]+))?$'
    )

    if (-not $match.Success) {
        throw "Invalid semantic version: $Value"
    }

    return [pscustomobject]@{
        Raw = $Value.Trim().TrimStart('v')
        Major = [int]$match.Groups['major'].Value
        Minor = [int]$match.Groups['minor'].Value
        Patch = [int]$match.Groups['patch'].Value
        Pre = $match.Groups['pre'].Value
    }
}

function Compare-PreRelease([string]$Left, [string]$Right) {
    if ([string]::IsNullOrWhiteSpace($Left) -and [string]::IsNullOrWhiteSpace($Right)) { return 0 }
    if ([string]::IsNullOrWhiteSpace($Left)) { return 1 }
    if ([string]::IsNullOrWhiteSpace($Right)) { return -1 }

    $leftParts = $Left.Split('.')
    $rightParts = $Right.Split('.')
    $count = [Math]::Max($leftParts.Count, $rightParts.Count)

    for ($index = 0; $index -lt $count; $index++) {
        if ($index -ge $leftParts.Count) { return -1 }
        if ($index -ge $rightParts.Count) { return 1 }

        $a = $leftParts[$index]
        $b = $rightParts[$index]
        $aNumeric = $a -match '^[0-9]+$'
        $bNumeric = $b -match '^[0-9]+$'

        if ($aNumeric -and $bNumeric) {
            $aNumber = [System.Numerics.BigInteger]::Parse($a)
            $bNumber = [System.Numerics.BigInteger]::Parse($b)
            if ($aNumber -lt $bNumber) { return -1 }
            if ($aNumber -gt $bNumber) { return 1 }
            continue
        }

        if ($aNumeric -and -not $bNumeric) { return -1 }
        if (-not $aNumeric -and $bNumeric) { return 1 }

        $comparison = [string]::CompareOrdinal($a, $b)
        if ($comparison -lt 0) { return -1 }
        if ($comparison -gt 0) { return 1 }
    }

    return 0
}

function Compare-SemVer([string]$Left, [string]$Right) {
    $a = Get-SemVer $Left
    $b = Get-SemVer $Right

    foreach ($field in @('Major', 'Minor', 'Patch')) {
        if ($a.$field -lt $b.$field) { return -1 }
        if ($a.$field -gt $b.$field) { return 1 }
    }

    return Compare-PreRelease $a.Pre $b.Pre
}

function Get-OfficialGitHubRelease([string]$Version) {
    $parsed = Get-SemVer $Version
    if (-not [string]::IsNullOrWhiteSpace($parsed.Pre)) {
        throw "Official in-app updates accept stable releases only, not prerelease '$Version'."
    }

    $stableVersion = $parsed.Raw
    $tag = "v$stableVersion"
    $apiUrl = "https://api.github.com/repos/nrfjr/DBAChum/releases/tags/$tag"
    $headers = @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = "DBAChum-Updater/$stableVersion"
        'X-GitHub-Api-Version' = '2022-11-28'
    }

    try {
        $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -Method Get
    }
    catch {
        throw "Unable to retrieve official DBAChum release '$tag' from GitHub: $($_.Exception.Message)"
    }

    if ($null -eq $release) {
        throw "GitHub returned an empty release response for '$tag'."
    }
    if ([bool]$release.draft) {
        throw "Refusing GitHub draft release '$tag'."
    }
    if ([bool]$release.prerelease) {
        throw "Refusing GitHub prerelease '$tag'."
    }
    if ([string]$release.tag_name -ne $tag) {
        throw "GitHub returned unexpected tag '$($release.tag_name)' for requested release '$tag'."
    }

    $packageName = "DBAChum-$tag-windows.zip"
    $checksumName = "$packageName.sha256"
    $packageAsset = $null
    $checksumAsset = $null

    foreach ($asset in @($release.assets)) {
        if ([string]$asset.name -eq $packageName) { $packageAsset = $asset }
        if ([string]$asset.name -eq $checksumName) { $checksumAsset = $asset }
    }

    if ($null -eq $packageAsset) {
        throw "Official release '$tag' does not contain required asset '$packageName'."
    }
    if ($null -eq $checksumAsset) {
        throw "Official release '$tag' does not contain required asset '$checksumName'."
    }

    foreach ($assetInfo in @(
        [pscustomobject]@{ Name = $packageName; Url = [string]$packageAsset.browser_download_url },
        [pscustomobject]@{ Name = $checksumName; Url = [string]$checksumAsset.browser_download_url }
    )) {
        if ([string]::IsNullOrWhiteSpace($assetInfo.Url)) {
            throw "GitHub release asset '$($assetInfo.Name)' does not have a download URL."
        }

        $uri = [Uri]$assetInfo.Url
        $expectedPrefix = "/nrfjr/DBAChum/releases/download/$tag/"
        if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or -not $uri.AbsolutePath.StartsWith($expectedPrefix, [StringComparison]::Ordinal)) {
            throw "Refusing unexpected download URL for '$($assetInfo.Name)': $($assetInfo.Url)"
        }
    }

    return [pscustomobject]@{
        Version = $stableVersion
        Tag = $tag
        PackageName = $packageName
        PackageUrl = [string]$packageAsset.browser_download_url
        ChecksumName = $checksumName
        ChecksumUrl = [string]$checksumAsset.browser_download_url
    }
}

function Download-OfficialGitHubRelease([string]$Version, [string]$DestinationRoot) {
    $release = Get-OfficialGitHubRelease $Version
    New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

    $packagePath = Join-Path $DestinationRoot $release.PackageName
    $checksumPath = Join-Path $DestinationRoot $release.ChecksumName

    $previousProtocol = [Net.ServicePointManager]::SecurityProtocol
    try {
        [Net.ServicePointManager]::SecurityProtocol = $previousProtocol -bor [Net.SecurityProtocolType]::Tls12

        Write-Host "Downloading $($release.PackageName)..."
        Invoke-WebRequest -Uri $release.PackageUrl -OutFile $packagePath -Headers @{ 'User-Agent' = 'DBAChum-Updater' }

        Write-Host "Downloading $($release.ChecksumName)..."
        Invoke-WebRequest -Uri $release.ChecksumUrl -OutFile $checksumPath -Headers @{ 'User-Agent' = 'DBAChum-Updater' }
    }
    catch {
        throw "Unable to download official DBAChum release '$($release.Tag)': $($_.Exception.Message)"
    }
    finally {
        [Net.ServicePointManager]::SecurityProtocol = $previousProtocol
    }

    if (-not (Test-Path $packagePath -PathType Leaf)) {
        throw "Release package download did not create: $packagePath"
    }
    if (-not (Test-Path $checksumPath -PathType Leaf)) {
        throw "Release checksum download did not create: $checksumPath"
    }

    return [pscustomobject]@{
        Version = $release.Version
        PackagePath = $packagePath
        ChecksumPath = $checksumPath
    }
}

function Get-ExpectedSha256([string]$Path, [string]$ExpectedFileName) {
    $text = (Get-Content $Path -Raw).Trim()
    $match = [regex]::Match($text, '(?im)^\s*(?<hash>[0-9a-f]{64})(?:\s+\*?(?<name>[^\r\n]+))?\s*$')

    if (-not $match.Success) {
        throw "Checksum file does not contain a valid SHA-256 value: $Path"
    }

    $recordedName = $match.Groups['name'].Value.Trim()
    if (-not [string]::IsNullOrWhiteSpace($recordedName)) {
        $recordedLeaf = Split-Path $recordedName -Leaf
        if ($recordedLeaf -ne $ExpectedFileName) {
            throw "Checksum file is for '$recordedLeaf', not '$ExpectedFileName'."
        }
    }

    return $match.Groups['hash'].Value.ToLowerInvariant()
}

function Test-ProtectedRelativePath([string]$RelativePath) {
    $normalized = $RelativePath.Replace('/', '\').TrimStart('\')
    $lower = $normalized.ToLowerInvariant()

    return (
        $lower -eq 'backend\.env' -or
        $lower -like 'backend\.venv\*' -or
        $lower -eq 'backend\.venv' -or
        $lower -like 'backups\*' -or
        $lower -eq 'backups' -or
        $lower -like 'logs\*' -or
        $lower -eq 'logs' -or
        $lower -like '.update\*' -or
        $lower -eq '.update'
    )
}

function Get-ManifestFiles($Manifest) {
    if ($null -eq $Manifest.files) {
        throw 'release-manifest.json does not contain a files list.'
    }

    $result = @()
    foreach ($entry in $Manifest.files) {
        $relative = [string]$entry.path
        if ([string]::IsNullOrWhiteSpace($relative)) {
            throw 'release-manifest.json contains an empty file path.'
        }
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Contains('..')) {
            throw "Unsafe path in release manifest: $relative"
        }
        if (Test-ProtectedRelativePath $relative) {
            throw "Release manifest attempts to manage protected runtime state: $relative"
        }
        $result += $entry
    }
    return $result
}

function Assert-PackageManifest([string]$PackageRoot, $Manifest, [string]$Version) {
    if ([string]$Manifest.product -ne 'DBAChum') {
        throw "Unexpected release product: $($Manifest.product)"
    }
    if ([string]$Manifest.platform -ne 'windows-native') {
        throw "Unexpected release platform: $($Manifest.platform)"
    }
    if ([string]$Manifest.version -ne $Version) {
        throw "VERSION ($Version) does not match release-manifest.json version ($($Manifest.version))."
    }

    $files = Get-ManifestFiles $Manifest
    if ($files.Count -eq 0) {
        throw 'Release manifest does not contain any managed files.'
    }

    foreach ($entry in $files) {
        $relative = ([string]$entry.path).Replace('/', '\')
        $fullPath = Join-Path $PackageRoot $relative
        if (-not (Test-Path $fullPath -PathType Leaf)) {
            throw "Release package is missing manifest file: $relative"
        }

        $actualHash = (Get-FileHash -Path $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $expectedHash = ([string]$entry.sha256).ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "Manifest SHA-256 mismatch for $relative"
        }
    }

    foreach ($required in @(
        'backend\requirements.txt',
        'frontend\dist\index.html',
        'scripts\windows\install_release.ps1',
        'scripts\windows\update_dbachum.ps1',
        'scripts\windows\smoke_test.ps1',
        'VERSION'
    )) {
        if (-not (Test-Path (Join-Path $PackageRoot $required) -PathType Leaf)) {
            throw "Release package is missing required updater file: $required"
        }
    }
}

function Resolve-PackageRoot([string]$ExtractRoot) {
    if (Test-Path (Join-Path $ExtractRoot 'VERSION') -PathType Leaf) {
        return $ExtractRoot
    }

    $directories = @(Get-ChildItem -Path $ExtractRoot -Directory -Force)
    if ($directories.Count -ne 1) {
        throw 'Release ZIP must contain either runtime files at its root or exactly one top-level release directory.'
    }

    $candidate = $directories[0].FullName
    if (-not (Test-Path (Join-Path $candidate 'VERSION') -PathType Leaf)) {
        throw 'Unable to locate VERSION inside the release ZIP.'
    }

    return $candidate
}

function Resolve-PythonCommand([string]$Requested) {
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        if (-not (Get-Command $Requested -ErrorAction SilentlyContinue)) {
            throw "Python command '$Requested' was not found in PATH."
        }
        return $Requested
    }

    foreach ($candidate in @('python', 'py')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }

    throw 'Python was not found in PATH. Install Python or pass -PythonCommand explicitly.'
}

function Copy-RelativeFile([string]$SourceRoot, [string]$DestinationRoot, [string]$RelativePath) {
    $normalized = $RelativePath.Replace('/', '\')
    $source = Join-Path $SourceRoot $normalized
    $destination = Join-Path $DestinationRoot $normalized
    $parent = Split-Path $destination -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -Path $source -Destination $destination -Force
}

function Remove-ManagedFiles([string]$Root, $Manifest) {
    $files = @(Get-ManifestFiles $Manifest)
    foreach ($entry in $files) {
        $relative = ([string]$entry.path).Replace('/', '\')
        $path = Join-Path $Root $relative
        if (Test-Path $path -PathType Leaf) {
            Remove-Item -Path $path -Force
        }
    }

    # Remove empty directories only. Never remove protected runtime-state directories.
    Get-ChildItem -Path $Root -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object {
            $relative = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
            if (-not (Test-ProtectedRelativePath $relative)) {
                $child = Get-ChildItem -Path $_.FullName -Force -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($null -eq $child) {
                    Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
                }
            }
        }
}

function Copy-ReleaseFiles([string]$SourceRoot, [string]$DestinationRoot, $Manifest) {
    foreach ($entry in (Get-ManifestFiles $Manifest)) {
        Copy-RelativeFile $SourceRoot $DestinationRoot ([string]$entry.path)
    }

    Copy-RelativeFile $SourceRoot $DestinationRoot 'release-manifest.json'
}

function Save-RollbackSnapshot([string]$Root, [string]$RollbackRoot, $Manifest) {
    New-Item -ItemType Directory -Force -Path $RollbackRoot | Out-Null

    foreach ($entry in (Get-ManifestFiles $Manifest)) {
        $relative = ([string]$entry.path).Replace('/', '\')
        $source = Join-Path $Root $relative
        if (Test-Path $source -PathType Leaf) {
            Copy-RelativeFile $Root $RollbackRoot $relative
        }
    }

    $manifestPath = Join-Path $Root 'release-manifest.json'
    if (Test-Path $manifestPath -PathType Leaf) {
        Copy-RelativeFile $Root $RollbackRoot 'release-manifest.json'
    }
}

function Start-TaskAndWait([string]$Name) {
    Start-ScheduledTask -TaskName $Name
    Start-Sleep -Seconds 3
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
else {
    $TargetRoot = Resolve-FullPath $TargetRoot
}

if (-not (Test-Path $TargetRoot -PathType Container)) {
    throw "DBAChum target root was not found: $TargetRoot"
}

$CurrentVersionFile = Join-Path $TargetRoot 'VERSION'
$CurrentManifestPath = Join-Path $TargetRoot 'release-manifest.json'
if (-not (Test-Path $CurrentVersionFile -PathType Leaf)) {
    throw "Installed VERSION file was not found: $CurrentVersionFile"
}
if (-not (Test-Path $CurrentManifestPath -PathType Leaf)) {
    throw "Installed release-manifest.json was not found: $CurrentManifestPath"
}

$CurrentVersion = (Get-Content $CurrentVersionFile -Raw).Trim()
$CurrentManifest = Get-Content $CurrentManifestPath -Raw | ConvertFrom-Json

$UpdateRoot = Join-Path $TargetRoot '.update'
$RunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$WorkRoot = Join-Path $UpdateRoot "work\$RunId"
$ExtractRoot = Join-Path $WorkRoot 'extracted'
$DownloadRoot = Join-Path $WorkRoot 'downloads'
$RollbackRoot = Join-Path $UpdateRoot "rollback\$CurrentVersion-$RunId"

New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null

$usingOfficialRelease = -not [string]::IsNullOrWhiteSpace($ReleaseVersion)
$hasPackagePath = -not [string]::IsNullOrWhiteSpace($PackagePath)
$hasChecksumPath = -not [string]::IsNullOrWhiteSpace($ChecksumPath)
$RequestedReleaseVersion = ''

if ($usingOfficialRelease) {
    if ($hasPackagePath -or $hasChecksumPath) {
        throw 'Use either -ReleaseVersion or -PackagePath/-ChecksumPath, not both.'
    }

    $requested = Get-SemVer $ReleaseVersion
    if (-not [string]::IsNullOrWhiteSpace($requested.Pre)) {
        throw 'Remote GitHub update mode supports stable DBAChum releases only.'
    }
    $RequestedReleaseVersion = $requested.Raw

    $requestedComparison = Compare-SemVer $RequestedReleaseVersion $CurrentVersion
    if ($requestedComparison -lt 0 -and -not $AllowDowngrade) {
        throw "Refusing downgrade from $CurrentVersion to $RequestedReleaseVersion."
    }
    if ($requestedComparison -eq 0 -and -not $AllowSameVersion) {
        throw "DBAChum $CurrentVersion is already installed. Use -AllowSameVersion only for intentional update testing."
    }

    Write-Step "Download official DBAChum v$RequestedReleaseVersion release"
    $download = Download-OfficialGitHubRelease $RequestedReleaseVersion $DownloadRoot
    $PackagePath = $download.PackagePath
    $ChecksumPath = $download.ChecksumPath
    Write-Host "PASS  Downloaded official release assets from nrfjr/DBAChum" -ForegroundColor Green
}
else {
    if (-not $hasPackagePath -or -not $hasChecksumPath) {
        throw 'Pass -ReleaseVersion for an official GitHub release, or pass both -PackagePath and -ChecksumPath for a local package.'
    }

    $PackagePath = Resolve-FullPath $PackagePath
    $ChecksumPath = Resolve-FullPath $ChecksumPath
}

if (-not (Test-Path $PackagePath -PathType Leaf)) {
    throw "Release package was not found: $PackagePath"
}
if (-not (Test-Path $ChecksumPath -PathType Leaf)) {
    throw "Release checksum was not found: $ChecksumPath"
}

try {
    Write-Step 'Verify release archive checksum'
    $expectedHash = Get-ExpectedSha256 $ChecksumPath (Split-Path $PackagePath -Leaf)
    $actualHash = (Get-FileHash -Path $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "Release ZIP SHA-256 mismatch. Expected $expectedHash but calculated $actualHash."
    }
    Write-Host "PASS  Release ZIP SHA-256: $actualHash" -ForegroundColor Green

    Write-Step 'Inspect release package'
    Expand-Archive -Path $PackagePath -DestinationPath $ExtractRoot -Force
    $PackageRoot = Resolve-PackageRoot $ExtractRoot
    $PackageVersionFile = Join-Path $PackageRoot 'VERSION'
    $PackageManifestPath = Join-Path $PackageRoot 'release-manifest.json'
    if (-not (Test-Path $PackageManifestPath -PathType Leaf)) {
        throw 'Release package does not contain release-manifest.json.'
    }

    $PackageVersion = (Get-Content $PackageVersionFile -Raw).Trim()
    $PackageManifest = Get-Content $PackageManifestPath -Raw | ConvertFrom-Json
    Assert-PackageManifest $PackageRoot $PackageManifest $PackageVersion

    if ($usingOfficialRelease -and $PackageVersion -ne $RequestedReleaseVersion) {
        throw "Downloaded package version '$PackageVersion' does not match requested official release '$RequestedReleaseVersion'."
    }

    $versionComparison = Compare-SemVer $PackageVersion $CurrentVersion
    if ($versionComparison -lt 0 -and -not $AllowDowngrade) {
        throw "Refusing downgrade from $CurrentVersion to $PackageVersion. Use -AllowDowngrade only for intentional recovery testing."
    }
    if ($versionComparison -eq 0 -and -not $AllowSameVersion) {
        throw "DBAChum $CurrentVersion is already installed. Use -AllowSameVersion only for intentional update testing."
    }

    Write-Host "PASS  Installed version: $CurrentVersion" -ForegroundColor Green
    Write-Host "PASS  Package version  : $PackageVersion" -ForegroundColor Green
    Write-Host "PASS  Package manifest and per-file SHA-256 hashes verified" -ForegroundColor Green

    if ($ValidateOnly) {
        Write-Host ''
        Write-Host 'PASS  Update package validation completed. No installation changes were made.' -ForegroundColor Green
        return
    }

    if (-not (Test-IsAdministrator)) {
        throw 'Run the updater from an elevated PowerShell window (Run as Administrator).'
    }

    $resolvedPython = Resolve-PythonCommand $PythonCommand
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $taskWasRunning = $null -ne $task -and $task.State -eq 'Running'

    Write-Step 'Create rollback snapshot'
    Save-RollbackSnapshot $TargetRoot $RollbackRoot $CurrentManifest
    Write-Host "PASS  Runtime rollback snapshot: $RollbackRoot" -ForegroundColor Green

    if (-not $SkipDatabaseBackup) {
        Write-Step 'Back up MongoDB before update'
        $backupScript = Join-Path $TargetRoot 'scripts\windows\backup_mongodb.ps1'
        if (-not (Test-Path $backupScript -PathType Leaf)) {
            throw "MongoDB backup script was not found: $backupScript"
        }
        & $backupScript -TaskName $TaskName -Online
        if ($LASTEXITCODE -ne 0) {
            throw "MongoDB backup failed with exit code $LASTEXITCODE."
        }
    }
    else {
        Write-Warning 'MongoDB backup was skipped. Use this only for controlled update testing.'
    }

    if ($taskWasRunning) {
        Write-Step "Stop scheduled task '$TaskName'"
        Stop-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 3
    }

    $installSucceeded = $false
    try {
        Write-Step "Install DBAChum $PackageVersion"
        Remove-ManagedFiles $TargetRoot $CurrentManifest
        Copy-ReleaseFiles $PackageRoot $TargetRoot $PackageManifest

        $installScript = Join-Path $TargetRoot 'scripts\windows\install_release.ps1'
        & $installScript -PythonCommand $resolvedPython
        if ($LASTEXITCODE -ne 0) {
            throw "install_release.ps1 failed with exit code $LASTEXITCODE."
        }

        if ($taskWasRunning) {
            Write-Step "Start scheduled task '$TaskName'"
            Start-TaskAndWait $TaskName
        }

        if (-not $SkipSmoke -and $taskWasRunning) {
            Write-Step 'Run post-update smoke test'
            $smokeScript = Join-Path $TargetRoot 'scripts\windows\smoke_test.ps1'
            & $smokeScript -Port $Port
            if ($LASTEXITCODE -ne 0) {
                throw "smoke_test.ps1 failed with exit code $LASTEXITCODE."
            }
        }
        elseif ($SkipSmoke) {
            Write-Warning 'Post-update smoke test was skipped.'
        }
        elseif (-not $taskWasRunning) {
            Write-Warning "Scheduled task '$TaskName' was not running before the update, so it was left stopped and smoke testing was skipped."
        }

        $installSucceeded = $true
    }
    catch {
        $updateError = $_
        Write-Warning "Update failed: $($updateError.Exception.Message)"
        Write-Warning "Rolling back to DBAChum $CurrentVersion..."

        try {
            $currentTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if ($null -ne $currentTask -and $currentTask.State -eq 'Running') {
                Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }

            Remove-ManagedFiles $TargetRoot $PackageManifest
            Copy-ReleaseFiles $RollbackRoot $TargetRoot $CurrentManifest

            $rollbackInstallScript = Join-Path $TargetRoot 'scripts\windows\install_release.ps1'
            & $rollbackInstallScript -PythonCommand $resolvedPython
            if ($LASTEXITCODE -ne 0) {
                throw "Rollback install_release.ps1 failed with exit code $LASTEXITCODE."
            }

            if ($taskWasRunning) {
                Start-TaskAndWait $TaskName

                if (-not $SkipSmoke) {
                    $rollbackSmoke = Join-Path $TargetRoot 'scripts\windows\smoke_test.ps1'
                    & $rollbackSmoke -Port $Port
                    if ($LASTEXITCODE -ne 0) {
                        throw "Rollback smoke test failed with exit code $LASTEXITCODE."
                    }
                }
            }

            Write-Host "PASS  Rollback restored DBAChum $CurrentVersion" -ForegroundColor Yellow
        }
        catch {
            $rollbackError = $_
            throw (
                "DBAChum update failed and rollback also failed. " +
                "Update error: $($updateError.Exception.Message) " +
                "Rollback error: $($rollbackError.Exception.Message) " +
                "Rollback snapshot remains at: $RollbackRoot"
            )
        }

        throw "DBAChum update failed and was rolled back successfully: $($updateError.Exception.Message)"
    }

    if ($installSucceeded) {
        Write-Host ''
        Write-Host "PASS  DBAChum updated from $CurrentVersion to $PackageVersion" -ForegroundColor Green
        Write-Host "      Rollback snapshot retained at: $RollbackRoot"
    }
}
finally {
    if (Test-Path $WorkRoot) {
        Remove-Item $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
