param(
    [switch]$UseClipboard
)

$ErrorActionPreference = "Stop"

$projectRef = "rlgkujdkecbpjadhbdsm"
if ($UseClipboard) {
    $poolerUri = (Get-Clipboard -Raw).Trim()
}
else {
    $poolerUri = Read-Host "Paste the Supabase Session pooler URI as shown, with its password placeholder"
}
$placeholders = @("[YOUR-DATABASE-PASSWORD]", "[YOUR-PASSWORD]", "YOUR-DATABASE-PASSWORD", "YOUR-PASSWORD")
$passwordPlaceholder = $placeholders | Where-Object { $poolerUri.Contains($_) } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($poolerUri) -or $null -eq $passwordPlaceholder) {
    throw "Copy the Session pooler URI as shown, leaving its database-password placeholder in place."
}

$securePassword = Read-Host "Supabase database password (input hidden)" -AsSecureString
if ($securePassword.Length -lt 1) {
    $securePassword.Dispose()
    throw "Enter the database password set for this Supabase project."
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$databaseUri = $null
$passwordText = $null
$escapedPassword = $null
$clipboardUpdated = $false
try {
    $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $escapedPassword = [Uri]::EscapeDataString($passwordText)
    $databaseUri = $poolerUri.Replace($passwordPlaceholder, $escapedPassword)
    $parsedUri = [Uri]$databaseUri
    if ($parsedUri.Host -notlike "*.pooler.supabase.com" -or
        [Uri]::UnescapeDataString($parsedUri.UserInfo.Split(":")[0]) -notlike "*$projectRef*") {
        throw "The URI must be the Session pooler URI for the MarketPulse project."
    }

    if ($databaseUri -match "[?&]sslmode=") {
        $databaseUri = [Regex]::Replace(
            $databaseUri,
            "([?&]sslmode=)[^&]*",
            '$1require',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    else {
        $separator = if ($databaseUri.Contains("?")) { "&" } else { "?" }
        $databaseUri = $databaseUri + $separator + "sslmode=require"
    }

    $vercelOutput = @(
        $databaseUri | & vercel.cmd env add DATABASE_URL `
            --environment production `
            --type secret `
            --force `
            --yes `
            --scope arlotech `
            --project marketpulse-nigeria 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Vercel could not save DATABASE_URL. Check that the Vercel CLI is installed and signed in to arlotech."
    }

    Set-Clipboard -Value $databaseUri
    $clipboardUpdated = $true
    Write-Host ""
    Write-Host "Vercel production DATABASE_URL is saved. The same value is copied for GitHub Actions."
    Write-Host "In GitHub, open Marketpulse → Settings → Secrets and variables → Actions → New repository secret."
    Write-Host "Name it DATABASE_URL and paste the copied value. Return here after saving; the clipboard will be cleared."
    Read-Host "Press Enter after saving the GitHub secret" | Out-Null
}
finally {
    if ($clipboardUpdated) {
        Set-Clipboard -Value ""
        Write-Host "Clipboard cleared."
    }
    if ($null -ne $bstr) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $databaseUri = $null
    $passwordText = $null
    $escapedPassword = $null
    $poolerUri = $null
    $securePassword.Dispose()
}
