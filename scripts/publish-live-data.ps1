param([switch]$Once)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$collectorPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $collectorPython)) {
    throw 'Run scripts/setup.ps1 first to install the backend.'
}

$startedWorker = $null
Push-Location $backendRoot
try {
    & $collectorPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'The local database needs attention before publishing.' }
    if (-not $Once) {
        $runningWorker = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
            $_.ExecutablePath -eq $collectorPython -and $_.CommandLine -match '-m\s+app\.worker(?:\s|$)'
        }
        if (-not $runningWorker) {
            $logRoot = Join-Path $backendRoot '.collector-logs'
            New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
            $logName = Get-Date -Format 'yyyyMMdd-HHmmss'
            $startedWorker = Start-Process -FilePath $collectorPython -ArgumentList @('-m','app.worker') `
                -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $logRoot "$logName-out.log") `
                -RedirectStandardError (Join-Path $logRoot "$logName-error.log")
        }
        Write-Host 'Collection and publishing are running. Keep this window and computer on. Ctrl+C stops this session.'
    }
    $syncArgs = @('-m', 'app.sync')
    if ($Once) { $syncArgs += '--once' }
    & $collectorPython @syncArgs
    if ($LASTEXITCODE -ne 0) { throw 'Publishing did not complete. Check the message above.' }
} finally {
    if ($startedWorker -and -not $startedWorker.HasExited) { $startedWorker | Stop-Process }
    Pop-Location
}
