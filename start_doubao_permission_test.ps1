# Run only after the user explicitly authorizes this temporary elevated probe.
# It does not elevate G10 Control or install anything.
param([ValidateSet('button','right-alt','mouse')][string]$Trigger = 'button')
$ErrorActionPreference = 'Stop'
$g10ProbeRoot = $PSScriptRoot
$g10ProbePython = Join-Path $g10ProbeRoot '.venv\Scripts\pythonw.exe'
$g10ProbeScript = Join-Path $g10ProbeRoot 'doubao_ui_probe.py'
if (!(Test-Path -LiteralPath $g10ProbePython) -or !(Test-Path -LiteralPath $g10ProbeScript)) {
    throw 'G10 probe files are missing.'
}
$g10ProbeArguments = '"' + $g10ProbeScript + '" --activate --interactive --trigger ' + $Trigger
Start-Process -FilePath $g10ProbePython -ArgumentList $g10ProbeArguments -WorkingDirectory $g10ProbeRoot -Verb RunAs -WindowStyle Hidden
