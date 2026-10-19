$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$npm = Get-Command npm -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $python)) {
    throw "Create the project venv and install requirements-build.txt first: $python"
}
if (-not $npm) {
    throw 'Node.js/npm is required only to build the React static assets.'
}

Push-Location (Join-Path $repoRoot 'desktop-ui\web')
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Push-Location $repoRoot
try {
    & $python -m PyInstaller --clean --noconfirm (Join-Path $repoRoot 'build\portable_onedir.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host 'Draft onedir output is in dist\G10-Control. It is not a validated portable release.'
