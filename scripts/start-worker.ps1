param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$backendPath = Join-Path $ProjectRoot "backend"
$storagePath = Join-Path $ProjectRoot "storage"
$workerPython = Join-Path $backendPath ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $workerPython)) {
    throw "Worker environment is missing. Create backend/.venv and install requirements first."
}

New-Item -ItemType Directory -Force -Path $storagePath | Out-Null

$env:DATABASE_URL = "postgresql+asyncpg://rc_user:rc_pass@localhost:5433/research_companion"
$env:DATABASE_URL_SYNC = "postgresql://rc_user:rc_pass@localhost:5433/research_companion"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:STORAGE_PATH = $storagePath
$env:EXECUTOR_IMAGE = "loop-science-executor:latest"

Set-Location -LiteralPath $backendPath
& $workerPython -m celery -A app.core.celery_app.celery_app worker --loglevel=info --pool=solo
