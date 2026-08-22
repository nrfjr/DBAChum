param(
    [string[]]$TrustedHosts = @(),

    [switch]$EnableSecureCookie
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$EnvFile = Join-Path $ProjectRoot 'backend\.env'

if (-not (Test-Path $EnvFile)) {
    throw "backend/.env was not found: $EnvFile. Run setup.ps1 first."
}

function Get-DefaultTrustedHosts {
    $hosts = @(
        'localhost'
        '127.0.0.1'
    )

    if (-not [string]::IsNullOrWhiteSpace($env:COMPUTERNAME)) {
        $hosts += $env:COMPUTERNAME
    }

    try {
        $addresses = Get-NetIPAddress `
            -AddressFamily IPv4 `
            -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne '127.0.0.1' -and
                $_.IPAddress -notlike '169.254.*'
            } |
            Select-Object -ExpandProperty IPAddress

        $hosts += $addresses
    }
    catch {
        Write-Warning 'Unable to enumerate local IPv4 addresses.'
    }

    return @(
        $hosts |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Sort-Object -Unique
    )
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [AllowEmptyString()]
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    $replacement = "$Name=$Value"

    if ([regex]::IsMatch($Text, $pattern)) {
        return [regex]::Replace(
            $Text,
            $pattern,
            [System.Text.RegularExpressions.MatchEvaluator]{
                param($match)
                return $replacement
            }
        )
    }

    return $Text.TrimEnd() + "`r`n$replacement`r`n"
}

if ($TrustedHosts.Count -eq 0) {
    $TrustedHosts = Get-DefaultTrustedHosts
}
else {
    $TrustedHosts = @(
        (Get-DefaultTrustedHosts) + $TrustedHosts |
        Sort-Object -Unique
    )
}

if ($TrustedHosts -contains '*') {
    throw "Wildcard TRUSTED_HOSTS is not allowed for production."
}

$text = Get-Content $EnvFile -Raw
$text = Set-EnvValue -Text $text -Name 'ENVIRONMENT' -Value 'production'
$text = Set-EnvValue -Text $text -Name 'API_DOCS_ENABLED' -Value 'false'
$text = Set-EnvValue -Text $text -Name 'TRUSTED_HOSTS' -Value ($TrustedHosts -join ',')
$text = Set-EnvValue -Text $text -Name 'CORS_ORIGINS' -Value ''

if ($EnableSecureCookie) {
    $text = Set-EnvValue -Text $text -Name 'COOKIE_SECURE' -Value 'true'
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $EnvFile,
    $text,
    $utf8NoBom
)

Write-Host 'PASS  Production security settings updated.' -ForegroundColor Green
Write-Host "      ENVIRONMENT=production"
Write-Host "      API_DOCS_ENABLED=false"
Write-Host "      CORS_ORIGINS=<disabled>"
Write-Host "      TRUSTED_HOSTS=$($TrustedHosts -join ',')"

if ($EnableSecureCookie) {
    Write-Host '      COOKIE_SECURE=true'
}
else {
    Write-Warning 'COOKIE_SECURE was left unchanged. Keep false only for an approved HTTP-only internal deployment; use -EnableSecureCookie behind HTTPS.'
}

Write-Host ''
Write-Host 'Restart DBAChum after changing backend/.env.'
