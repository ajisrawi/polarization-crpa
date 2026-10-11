# Regenerate and ERC-check both schematics.
# Usage:  powershell -File hardware\tools\check_schematics.ps1
$k = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
foreach ($s in @(@("rf_frontend", "gen_frontend_sch.py"), @("dsp_gnss", "gen_dsp_sch.py"))) {
    $dir = "hardware\" + $s[0]
    python "$dir\$($s[1])" | Out-Null
    $sch = "$dir\$($s[0]).kicad_sch"
    & $k sch erc --severity-all --format json -o "$dir\erc.json" $sch | Out-Null
    $j = Get-Content "$dir\erc.json" -Raw | ConvertFrom-Json
    $v = @($j.sheets | ForEach-Object { $_.violations })
    Write-Output ("{0}: {1} errors, {2} warnings" -f $s[0], @($v | Where-Object severity -eq "error").Count, @($v | Where-Object severity -eq "warning").Count)
    $v | Group-Object type | ForEach-Object {
        Write-Output ("   {0} x{1} [{2}] {3}" -f $_.Name, $_.Count, $_.Group[0].severity, (($_.Group[0].items | ForEach-Object { $_.description }) -join " | "))
    }
    & $k sch export pdf -o "$dir\$($s[0]).pdf" $sch | Out-Null
}
