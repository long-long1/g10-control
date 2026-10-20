# Safe offline acceptance only. No installer, ACL, registry, device or input actions.
param(
    [string]$Bundle = $PSScriptRoot,
    [string]$OutputDirectory = (Join-Path $env:TEMP ('G10 验收 ' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $Bundle).Path
if (Test-Path -LiteralPath $OutputDirectory) { throw 'OutputDirectory must not exist; previous evidence is never overwritten.' }
$session = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$program = Join-Path $session '中文 portable copy'
$results = [System.Collections.Generic.List[object]]::new()
$savedEnvironment = @{}
$names = @('PATH','LOCALAPPDATA','APPDATA') + @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(G10_|PYTHON|VIRTUAL_ENV|WEBVIEW2_)' } | ForEach-Object Name)
foreach ($name in $names) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    $manifest = Get-Content -LiteralPath (Join-Path $source 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $expected = @($manifest.files | ForEach-Object { $_.path }) + 'manifest.json'
    foreach ($entry in $manifest.files) {
        $path = [IO.Path]::GetFullPath((Join-Path $source $entry.path))
        if (-not $path.StartsWith($source + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escapes bundle.' }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Hash mismatch: $($entry.path)" }
    }
    foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
        $relative = $file.FullName.Substring($source.Length + 1).Replace('\','/')
        if ($relative -notin $expected) { throw "Unlisted file: $relative. Use a pristine candidate." }
    }
    Copy-Item -LiteralPath $source -Destination $program -Recurse
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$null,'Process') }
    $env:PATH = Join-Path $env:SystemRoot 'System32'
    $env:LOCALAPPDATA = Join-Path $session 'isolated local'
    $env:APPDATA = Join-Path $session 'isolated roaming'
    foreach ($mode in @('portable','fallback')) {
        if ($mode -eq 'fallback') {
            # Denied mkdir simulation only; no ACL change and no deletion.
            $data = Join-Path $program 'data'
            $resolvedData = [IO.Path]::GetFullPath($data)
            if (-not $resolvedData.StartsWith($session + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe move target.' }
            if (Test-Path -LiteralPath $data) { Move-Item -LiteralPath $data -Destination (Join-Path $program 'preserved-data') }
            Set-Content -LiteralPath $data -Value 'blocks portable data mkdir' -Encoding UTF8
        }
        foreach ($component in @('AudioBridge','Control')) {
            $report = Join-Path $session "$mode-$component.json"
            # No --diagnose-webview: no DOM click, visible UI or hardware.
            $process = Start-Process -FilePath (Join-Path $program "G10-$component.exe") -ArgumentList @('--diagnose-startup',('"' + $report + '"')) -WorkingDirectory $session -WindowStyle Hidden -PassThru
            if (-not $process.WaitForExit(45000)) { throw "Diagnostic timeout; process $($process.Id) was NOT killed. Stop and inspect manually." }
            $value = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
            $ok = $process.ExitCode -eq 0 -and $value.ok -eq $true -and $value.business_started -eq $false
            if ($mode -eq 'fallback') { $ok = $ok -and -not $value.portable -and [bool]$value.fallback_reason }
            $results.Add(@{mode=$mode;component=$component;passed=$ok;exit_code=$process.ExitCode;report=$report})
            if (-not $ok) { throw "Diagnostic failed: $report" }
        }
    }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process') }
    @{checks=@($results.ToArray());clean_vm_acceptance='PENDING: operator must attest Windows 11, no Python/Node/development tree';hardware_used=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $session 'acceptance-summary.json') -Encoding UTF8
    Write-Host "Evidence preserved at $session"
}
