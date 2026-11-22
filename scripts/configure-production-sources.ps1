param(
    [string]$ApiBaseUrl = "https://marketpulse-vdwt.onrender.com",
    [string]$PermissionReference = "owner-confirmed-approval-2026-11-23",
    [switch]$UseClipboard
)

$ErrorActionPreference = "Stop"
$ApiBaseUrl = $ApiBaseUrl.TrimEnd('/')

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

Write-Host "Checking $ApiBaseUrl ..."
$health = Invoke-RestMethod -Uri "$ApiBaseUrl/api/health" -Method Get -TimeoutSec 30
if ($health.status -ne "ok") {
    throw "The hosted API did not report status ok."
}

$adminToken = if ($UseClipboard) {
    $clipboard = (Get-Clipboard -Raw).Trim()
    if ($clipboard -match '(?m)^\s*MARKETPULSE_ADMIN_TOKEN\s*=\s*(.+?)\s*$') {
        $clipboard = $Matches[1]
    }
    ($clipboard -replace '\s', '').Trim()
} else {
    Read-PlainSecret "Paste MARKETPULSE_ADMIN_TOKEN (input stays hidden)"
}
if ([string]::IsNullOrWhiteSpace($adminToken)) {
    throw "An admin token is required. Copy the token first, then rerun with -UseClipboard."
}

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

$headers = @{
    "X-Admin-Token" = $adminToken
    "Accept" = "application/json"
}

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
