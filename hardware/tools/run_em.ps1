# Run an openEMS element job with the isolated environment.
# Usage: powershell -File hardware\tools\run_em.ps1 <tag> [params.json] [--quick]
param([string]$Tag, [string]$Params = "", [switch]$Quick)
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$env:CSXCAD_INSTALL_PATH = "$root\tools\openEMS\openEMS"
if (-not $env:EM_WORK) {
    # raw FDTD data (hundreds of MB); keep it out of the repo and off paths with spaces
    $env:EM_WORK = Join-Path $env:TEMP "crpa_em_runs"
}
$a = @("$root\hardware\em\em_element.py", "--tag", $Tag)
if ($Params) { $a += $Params }
if ($Quick) { $a += "--quick" }
$log = "$root\hardware\em\results\$Tag.log"
New-Item -ItemType Directory -Force "$root\hardware\em\results" | Out-Null
$t = Measure-Command { & "$root\tools\emvenv\Scripts\python.exe" @a *> $log }
"$Tag finished in $([int]$t.TotalMinutes) min"
Get-Content $log | Select-String -Pattern "s11_dips|s11_db_min|f_at_min|Traceback|Error:" | ForEach-Object { $_.Line }
