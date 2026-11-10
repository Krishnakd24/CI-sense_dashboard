param(
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & $Python --version
    if ($LASTEXITCODE -ne 0) { throw "Python could not be started." }
    Push-Location backend
    try {
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    } finally { Pop-Location }
    Push-Location frontend
    try {
        & npm.cmd run typecheck
        if ($LASTEXITCODE -ne 0) { throw "TypeScript checks failed." }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
} finally { Pop-Location }
