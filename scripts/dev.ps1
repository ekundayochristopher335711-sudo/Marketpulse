$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$VenvPython = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$PythonCommand = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }

Push-Location $BackendRoot
try {
    & $PythonCommand -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed with exit code $LASTEXITCODE." }
} finally { Pop-Location }

Start-Process powershell -WorkingDirectory $BackendRoot -ArgumentList @('-NoExit', '-Command', "& '$PythonCommand' -m uvicorn app.main:app --reload --port 8000")
Start-Process powershell -WorkingDirectory $BackendRoot -ArgumentList @('-NoExit', '-Command', "& '$PythonCommand' -m app.worker")
Push-Location $ProjectRoot
try { npm.cmd run dev } finally { Pop-Location }
