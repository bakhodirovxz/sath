# SPIKE: barcha sinovlarni ketma-ket ishga tushiradi. Natija: spike.log
#   .\run.ps1            -> Blender 4.5 LTS (py3.11) + o'rnatilgan FreeCAD 1.1 (C:\Program Files\FreeCAD 1.1)
#   .\run.ps1 -Stack 52  -> Blender 5.2 LTS (py3.13) + conda-forge FreeCAD 1.1.3 py313 (~\Tools\fc-py313)
param([string]$Stack = "45")
if ($Stack -eq "52") {
    $blender = "$env:USERPROFILE\Tools\blender-5.2\blender.exe"
    $env:GES_FC_HOME = "$env:USERPROFILE\Tools\fc-py313"
} else {
    $blender = "$env:USERPROFILE\Tools\blender-4.5\blender.exe"
    Remove-Item Env:GES_FC_HOME -ErrorAction SilentlyContinue
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here "spike-$Stack.log"
"== Sath spike $(Get-Date -Format s) stack=$Stack blender=$blender FC=$env:GES_FC_HOME" | Out-File $log -Encoding utf8
foreach ($t in @("fc_bridge.py", "test_dxf.py", "test_bonsai.py")) {
    "`n#### $t (headless)" | Out-File $log -Append -Encoding utf8
    & $blender -b --python (Join-Path $here $t) 2>&1 | Select-String -Pattern '^\[(OK|FAIL)\]|^\s{4}\w|Traceback|Error' | ForEach-Object { $_.Line } | Out-File $log -Append -Encoding utf8
}
"`n#### gui_run.py (GUI, avto yopiladi)" | Out-File $log -Append -Encoding utf8
# GUI jarayon chiqishi pipe da kesilib qoladi -> faylga yo'naltirib o'qiymiz
$guiLog = Join-Path $env:TEMP "ges_spike_gui.log"
cmd /c "`"$blender`" --python `"$(Join-Path $here 'gui_run.py')`" > `"$guiLog`" 2>&1"
Get-Content $guiLog | Select-String -Pattern '^\[(OK|FAIL)\]|SAQLANDI|Traceback|Error' | ForEach-Object { $_.Line } | Out-File $log -Append -Encoding utf8
Get-Content $log
$fails = (Select-String -Path $log -Pattern '^\[FAIL\]').Count
"`nFAIL soni: $fails"
