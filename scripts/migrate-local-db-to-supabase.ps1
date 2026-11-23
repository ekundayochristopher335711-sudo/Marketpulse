$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$migrationScript = Join-Path $repoRoot "scripts\migrate_local_db_to_supabase.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "The backend Python environment was not found at $pythonPath. Run scripts\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "backend\marketpulse.db"))) {
    throw "The local backend database was not found. Open the MarketPulse project folder containing backend\marketpulse.db."
}

Write-Host "This copies the local MarketPulse database into Supabase project rlgkujdkecbpjadhbdsm."
Write-Host "In Supabase, choose Connect > Session pooler and copy its PostgreSQL URI."
$poolerUri = Read-Host "Paste the Session pooler URI as shown, with its password placeholder"
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
$previousDatabaseUrl = $env:DATABASE_URL
try {
    $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $escapedPassword = [Uri]::EscapeDataString($passwordText)
    $databaseUri = $poolerUri.Replace($passwordPlaceholder, $escapedPassword)
    $env:DATABASE_URL = $databaseUri
    & $pythonPath $migrationScript
    if ($LASTEXITCODE -ne 0) {
        throw "The migration stopped. Review its message above; the local database remains unchanged."
    }
}
finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
    if ($null -ne $bstr) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($null -ne $databaseUri) {
        $databaseUri = $null
    }
    $passwordText = $null
    $escapedPassword = $null
    $poolerUri = $null
    $securePassword.Dispose()
}
