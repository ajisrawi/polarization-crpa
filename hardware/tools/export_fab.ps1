# Export Gerbers, drill files, a PNG render and a zip for every board under a folder.
# Run check_boards.ps1 first (it fills the zones and saves the boards).
# Usage:  powershell -File hardware\tools\export_fab.ps1 hardware\antenna
param([string]$Root = "hardware\antenna")

$k = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
Get-ChildItem -Path $Root -Recurse -Filter "*.kicad_pcb" | ForEach-Object {
    $pcb = $_.FullName
    $dir = $_.DirectoryName
    $name = $_.BaseName
    $fab = Join-Path $dir "fab"
    if (Test-Path $fab) { Remove-Item -Recurse -Force $fab }
    New-Item -ItemType Directory -Path $fab | Out-Null
    # note: no trailing backslash on the output folder (it would escape the closing quote)
    & $k pcb export gerbers --output $fab --layers "F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts" $pcb | Out-Null
    & $k pcb export drill --output $fab --format excellon $pcb | Out-Null
    & $k pcb export pos --output "$fab\$name-pos.csv" --format csv --units mm --side both $pcb | Out-Null
    & $k pcb render --side top --width 1200 --height 1200 --quality high --background opaque -o "$dir\render_top.png" $pcb | Out-Null
    & $k pcb render --side bottom --width 1200 --height 1200 --quality high --background opaque -o "$dir\render_bottom.png" $pcb | Out-Null
    $zip = Join-Path $dir "$name-fab.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path "$fab\*" -DestinationPath $zip
    Write-Output ("{0}: {1} fab files -> {2}" -f $name, (Get-ChildItem $fab).Count, (Split-Path $zip -Leaf))
}
