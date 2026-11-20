$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$VenvPython = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$PythonCommand = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }

Push-Location $ProjectRoot
try {
    npm.cmd run check
    if ($LASTEXITCODE -ne 0) { throw "Frontend checks failed with exit code $LASTEXITCODE." }
    & $PythonCommand -m compileall -q (Join-Path $BackendRoot 'app') (Join-Path $BackendRoot 'tests')
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed with exit code $LASTEXITCODE." }
    & $PythonCommand -m unittest discover -s (Join-Path $BackendRoot 'tests') -v
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed with exit code $LASTEXITCODE." }
    Push-Location $BackendRoot
    try {
        & $PythonCommand -m alembic check
        if ($LASTEXITCODE -ne 0) { throw "Alembic check failed with exit code $LASTEXITCODE." }
    } finally { Pop-Location }
    Write-Host 'All MarketPulse checks passed.' -ForegroundColor Green
} finally {
    Pop-Location
}
