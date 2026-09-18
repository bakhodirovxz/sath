# Sath Blender addoni headless testlari (Blender 5.2 + FreeCAD py313 + Bonsai kerak).
#   .\desktop\tests\run_blender_tests.ps1
$blender = if ($env:GES_BLENDER) { $env:GES_BLENDER } else { "$env:USERPROFILE\Tools\blender-5.2\blender.exe" }
$runner = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "blender_headless.py"
$tests = @(
    @("smoke", ""), @("engine", ""), @("ifc_bridge", "--bonsai"), @("objects", "--bonsai"),
    @("server_ops", ""), @("review_ops", "--bonsai"), @("sim_ops", ""), @("monitor_ops", "--bonsai"),
    @("import_ops", ""), @("demo_plant", "--bonsai")
)
if ($env:GES_TEST_SERVER) { $tests += ,@("e2e_server", "--bonsai"); $tests += ,@("sim_hydro", "--bonsai"); $tests += ,@("sim_twin", "--bonsai") }  # real server bilan uchdan-uchiga
$fails = 0
foreach ($t in $tests) {
    $out = & $blender -b --python $runner -- --test $t[0] $t[1] 2>&1 | Out-String
    if ($out -match "\[OK\] $($t[0])") { "[OK]   $($t[0])" } else { "[FAIL] $($t[0])"; $out | Select-String -Pattern "Error|assert" | ForEach-Object { "       " + $_.Line }; $fails++ }
}
"`nFAIL soni: $fails"
exit $fails
