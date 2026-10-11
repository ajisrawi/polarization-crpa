# Fill zones, run DRC and export fabrication files for every board under a folder.
# Usage:  powershell -File hardware\tools\check_boards.ps1 hardware\antenna
param([string]$Root = "hardware\antenna", [int]$TimeoutSec = 240)

$k = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
Get-ChildItem -Path $Root -Recurse -Filter "*.kicad_pcb" | ForEach-Object {
    $pcb = $_.FullName
    $dir = $_.DirectoryName
    $name = $_.BaseName
    $drc = Join-Path $dir "drc.json"
    $p = Start-Process -FilePath $k -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $dir "drc.log") `
        -ArgumentList @("pcb", "drc", "--refill-zones", "--save-board", "--severity-all", "--format", "json", "-o", "`"$drc`"", "`"$pcb`"")
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { $p.Kill(); Write-Output "${name}: DRC TIMEOUT"; return }
    $j = Get-Content $drc -Raw | ConvertFrom-Json
    $err = @($j.violations | Where-Object severity -eq "error")
    $warn = @($j.violations | Where-Object severity -eq "warning")
    Write-Output ("{0}: {1} errors, {2} warnings, {3} unconnected" -f $name, $err.Count, $warn.Count, @($j.unconnected_items).Count)
    $j.violations | Group-Object type | ForEach-Object {
        Write-Output ("   {0} x{1} [{2}] {3}" -f $_.Name, $_.Count, $_.Group[0].severity, $_.Group[0].items[0].description)
    }
}
