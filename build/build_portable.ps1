param([string]$DistPath = 'dist', [string]$WorkPath = 'build')
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$npm = Get-Command npm -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $python)) {
    throw "Create the project venv and install requirements-build.lock.txt first: $python"
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
$savedHashSeed = $env:PYTHONHASHSEED
$savedEpoch = $env:SOURCE_DATE_EPOCH
try {
    # Reproducible interpreter ordering and PE timestamps; current process only.
    $env:PYTHONHASHSEED = '0'
    $epoch = & git show -s --format=%ct HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read source commit timestamp.' }
    $env:SOURCE_DATE_EPOCH = $epoch.Trim()
    & $python -m PyInstaller --clean --noconfirm --distpath $DistPath --workpath $WorkPath (Join-Path $repoRoot 'build\portable_onedir.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    $env:PYTHONHASHSEED = $savedHashSeed
    $env:SOURCE_DATE_EPOCH = $savedEpoch
    Pop-Location
}

Write-Host 'Local Beta build is in dist\G10-Control. Use stage_beta.py for evidence; redistribution remains blocked.'
