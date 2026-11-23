param(
    [string]$ApiBaseUrl = "https://marketpulse-nigeria-pi.vercel.app",
    [string]$PermissionReference = "owner-confirmed-approval-2026-11-23",
    [switch]$UseClipboard,
    [switch]$UseEnvFile
)

$ErrorActionPreference = "Stop"
$ApiBaseUrl = $ApiBaseUrl.TrimEnd('/')
if ($UseClipboard -and $UseEnvFile) { throw 'Choose either -UseClipboard or -UseEnvFile.' }

function Read-PlainSecret {
    param([string]$Prompt)

    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Read-AdminToken {
    while ($true) {
        if ($UseEnvFile) {
            $envPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
            $entry = Get-Content -LiteralPath $envPath | Where-Object { $_ -match '^\s*MARKETPULSE_ADMIN_TOKEN\s*=' } | Select-Object -First 1
            if (-not $entry) { throw 'MARKETPULSE_ADMIN_TOKEN is missing from the project root .env.' }
            $candidate = ($entry -split '=', 2)[1]
        } elseif ($UseClipboard) {
            Write-Host ""
            Write-Host "PAUSED: Copy the current MARKETPULSE_ADMIN_TOKEN value now."
            Write-Host "Return here and press Enter. The script will then read your clipboard."
            [void](Read-Host "Press Enter AFTER copying the token")
            $candidate = [string](Get-Clipboard -Raw)
        } else {
            Write-Host "Paste the token, then press Enter. Hidden input will show no characters."
            $candidate = Read-PlainSecret "MARKETPULSE_ADMIN_TOKEN"
        }

        $candidate = $candidate.Trim()
        if ($candidate -match '^MARKETPULSE_ADMIN_TOKEN\s*=\s*(.+)$') {
            $candidate = $Matches[1].Trim()
        }
        $candidate = $candidate.Trim('"').Trim("'")

        if ($candidate -notmatch '^[A-Za-z0-9_+/=-]{32,4096}$') {
            if ($UseEnvFile) { throw 'The admin token in the root .env must contain at least 32 valid characters.' }
            Write-Host "That input is not a token. Use only the token value (at least 32 characters)."
            Write-Host "No authorization request was sent. Try again, or press Ctrl+C to cancel."
            continue
        }

        return $candidate
    }
}

$adminToken = Read-AdminToken

Write-Host "Checking $ApiBaseUrl ..."
$health = Invoke-RestMethod -Uri "$ApiBaseUrl/api/health" -Method Get -TimeoutSec 60
if ($health.status -ne "ok") {
    throw "The hosted API did not report status ok."
}

while ($true) {
    $headers = @{
        "X-Admin-Token" = $adminToken
        "Accept" = "application/json"
    }
    try {
        # Check authentication without changing any source settings.
        $null = Invoke-RestMethod `
            -Uri "$ApiBaseUrl/api/admin/audit?limit=1" `
            -Method Get `
            -Headers $headers `
            -TimeoutSec 30
        break
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) {
            if ($UseEnvFile) { throw 'The admin token in the root .env does not match the hosted API.' }
            Write-Host "The API did not accept that token. Source settings have not been changed."
            Write-Host "Enter the token again below, or press Ctrl+C to cancel."
            $adminToken = Read-AdminToken
            continue
        }
        throw
    }
}
Write-Host "Admin token accepted. Configuring sources..."

$categories = @(
    "Vehicles",
    "Property",
    "Phones & Tablets",
    "Electronics",
    "Home & Garden",
    "Fashion & Beauty",
    "Health & Beauty",
    "Services",
    "Repair & Construction",
    "Commercial Equipment & Tools",
    "Leisure & Activities",
    "Babies & Kids",
    "Agriculture & Foodstuff",
    "Animals & Pets",
    "Jobs",
    "Seeking Work - CVs",
    "Business & Industry"
)

$fields = @(
    "source_listing_id",
    "title",
    "category",
    "asking_price",
    "currency",
    "location",
    "state",
    "city",
    "source_url",
    "condition",
    "observed_at"
)

$common = @{
    permission_status = "approved"
    permitted_categories = $categories
    permitted_fields = $fields
    permission_reference = $PermissionReference
    retention_days = 365
}

$sources = @(
    @{ key = "aae"; access_method = "authorized_web"; enabled = $true; minimum_interval_seconds = 3600 },
    @{ key = "enytinplus"; access_method = "authorized_web"; enabled = $true; minimum_interval_seconds = 3600 },
    @{ key = "jax"; access_method = "authorized_web"; enabled = $true; minimum_interval_seconds = 3600 },
    @{ key = "jiji"; access_method = "authorized_web"; enabled = $true; minimum_interval_seconds = 60 },
    @{ key = "naijabargains"; access_method = "authorized_web"; enabled = $true; minimum_interval_seconds = 3600 },
    @{ key = "facebook_marketplace"; access_method = "api"; enabled = $false; minimum_interval_seconds = 3600 }
)

foreach ($source in $sources) {
    $payload = @{
        access_method = $source.access_method
        permission_status = $common.permission_status
        enabled = $source.enabled
        minimum_interval_seconds = $source.minimum_interval_seconds
        permitted_categories = $common.permitted_categories
        permitted_fields = $common.permitted_fields
        permission_reference = $common.permission_reference
        retention_days = $common.retention_days
    } | ConvertTo-Json -Depth 6

    $result = Invoke-RestMethod `
        -Uri "$ApiBaseUrl/api/admin/sources/$($source.key)" `
        -Method Put `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $payload `
        -TimeoutSec 30

    $state = if ($result.enabled) { "enabled" } else { "approved, waiting" }
    Write-Host "$($result.name): $state"
}

Write-Host ""
Write-Host "Production source configuration complete."
Write-Host "Facebook Marketplace is approved but remains disabled until its Meta token is configured."
