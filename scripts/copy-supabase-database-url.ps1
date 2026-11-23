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
$poolerUri = ([string]$poolerUri).Trim().Trim('"').Trim("'")
$placeholderPattern = '(?i)(\[(?:YOUR[-_ ]?)?(?:DATABASE[-_ ]?)?PASSWORD\]|<(?:YOUR[-_ ]?)?(?:DATABASE[-_ ]?)?PASSWORD>|(?:YOUR[-_ ]?)?(?:DATABASE[-_ ]?)?PASSWORD)'
$passwordPlaceholder = [regex]::Match($poolerUri, $placeholderPattern)
$securePassword = $null
$bstr = [IntPtr]::Zero
$databaseUri = $null
$passwordText = $null
$escapedPassword = $null
$clipboardUpdated = $false
try {
    if ([string]::IsNullOrWhiteSpace($poolerUri)) {
        throw "Copy the Session pooler URI from Supabase Connect."
    }

    if ($passwordPlaceholder.Success) {
        $securePassword = Read-Host "Supabase database password (input hidden)" -AsSecureString
        if ($securePassword.Length -lt 1) {
            throw "Enter the database password set for this Supabase project."
        }

        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        $escapedPassword = [Uri]::EscapeDataString($passwordText)
        $databaseUri = [regex]::new($placeholderPattern).Replace($poolerUri, $escapedPassword, 1)
    }
    else {
        # Some dashboard copy actions include an already-filled password. Accept it
        # without printing or prompting for it; validation below still checks scope.
        $databaseUri = $poolerUri
    }

    $parsedUri = [Uri]$databaseUri
    $userInfo = $parsedUri.UserInfo.Split(":", 2)
    if ($userInfo.Count -lt 2) {
        throw "The URI must include the database username and password."
    }
    $databaseUsername = [Uri]::UnescapeDataString($userInfo[0])
    if ($parsedUri.Host -notlike "*.pooler.supabase.com" -or
        $parsedUri.Port -ne 5432 -or
        $databaseUsername -notlike "*$projectRef*" -or
        [string]::IsNullOrWhiteSpace($userInfo[1])) {
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

    # Windows PowerShell 5.1 converts native CLI stderr into NativeCommandError.
    # Capture it with Continue so Vercel's banner does not abort the helper after
    # the environment variable has already been saved.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $vercelOutput = @(
            $databaseUri | & vercel.cmd env add DATABASE_URL `
                --environment production `
                --type secret `
                --force `
                --yes `
                --scope arlotech `
                --project marketpulse-nigeria 2>&1
        )
        $vercelExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($vercelExitCode -ne 0) {
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
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $databaseUri = $null
    $passwordText = $null
    $escapedPassword = $null
    $poolerUri = $null
    if ($null -ne $securePassword) {
        $securePassword.Dispose()
    }
}
