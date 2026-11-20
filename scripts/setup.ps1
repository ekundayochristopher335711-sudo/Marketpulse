$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$VenvPython = Join-Path $BackendRoot '.venv\Scripts\python.exe'

Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        python -m venv (Join-Path $BackendRoot '.venv')
    }
    & $VenvPython -m pip install -r (Join-Path $BackendRoot 'requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed with exit code $LASTEXITCODE." }
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed with exit code $LASTEXITCODE." }
    npm.cmd install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE." }
    Push-Location $BackendRoot
    try {
        & $VenvPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Database migration failed with exit code $LASTEXITCODE." }
    } finally { Pop-Location }
    Write-Host 'MarketPulse setup is complete.' -ForegroundColor Green
} finally {
    Pop-Location
}
