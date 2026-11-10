param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root ".local"
New-Item -ItemType Directory -Force $logs | Out-Null
$pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue; if (-not $pythonCommand) { throw "Python not found; pass -Python with its full executable path." }; $Python = $pythonCommand.Source
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { & $Python -m venv (Join-Path $root ".venv"); if ($LASTEXITCODE) { throw "venv setup failed" } }
& $venv -m pip install -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE) { throw "Backend package install failed" }
$envfile = Join-Path $root ".env"
if (-not (Test-Path $envfile)) { Copy-Item (Join-Path $root ".env.example") $envfile; throw "Set ENCRYPTION_KEY, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and ADMIN_GITHUB_IDS in .env, then rerun." }
$envdata = Get-Content $envfile -Raw
if ($envdata -match '(?m)^ENCRYPTION_KEY\s*=\s*$' -or $envdata -match '(?m)^GITHUB_CLIENT_ID\s*=\s*$' -or $envdata -match '(?m)^GITHUB_CLIENT_SECRET\s*=\s*$') { throw "Configure ENCRYPTION_KEY and GitHub App credentials in .env first." }
$frontendEnv = Join-Path $root "frontend\.env.local"
if (-not (Test-Path $frontendEnv)) { Copy-Item (Join-Path $root "frontend\.env.example") $frontendEnv }
Push-Location (Join-Path $root "backend")
try { & $venv -m alembic upgrade head; if ($LASTEXITCODE) { throw "Migration failed; confirm PostgreSQL is running and DATABASE_URL is correct." } } finally { Pop-Location }
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) { Push-Location (Join-Path $root "frontend"); try { & $npm install; if ($LASTEXITCODE) { throw "Frontend package installation failed." } } finally { Pop-Location } }
$apiLog=Join-Path $logs "backend.log";$webLog=Join-Path $logs "frontend.log"
$api=Start-Process $venv -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000","--workers","1","--no-access-log") -WorkingDirectory (Join-Path $root "backend") -WindowStyle Hidden -PassThru -RedirectStandardOutput $apiLog -RedirectStandardError (Join-Path $logs "backend-error.log")
$web=Start-Process $npm -ArgumentList @("run","dev","--","--hostname","127.0.0.1","--port","3000") -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden -PassThru -RedirectStandardOutput $webLog -RedirectStandardError (Join-Path $logs "frontend-error.log")
@{backend=$api.Id;frontend=$web.Id}|ConvertTo-Json|Set-Content (Join-Path $logs "processes.json")
$deadline=(Get-Date).AddSeconds(90)
do { Start-Sleep 2;$a=$false;$b=$false;try{$a=(Invoke-WebRequest "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200}catch{};try{$b=(Invoke-WebRequest "http://127.0.0.1:3000" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200}catch{} } until (($a -and $b) -or (Get-Date) -gt $deadline)
if (-not ($a -and $b)) { throw "Startup timed out. Check logs under ci-sense\.local" }
Write-Host "Dashboard http://localhost:3000 | Backend http://localhost:8000/health"
