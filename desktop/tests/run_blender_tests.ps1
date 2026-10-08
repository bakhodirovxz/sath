# Sath Blender addoni headless testlari (Blender 5.2 + Bonsai; FreeCAD kerak emas).
#   .\desktop\tests\run_blender_tests.ps1
$blender = if ($env:GES_BLENDER) { $env:GES_BLENDER } else { "$env:USERPROFILE\Tools\blender-5.2\blender.exe" }
$runner = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "blender_headless.py"
$tests = @(
    @("smoke", ""), @("tasks_async", ""), @("secret_ops", ""), @("kinds_mesh", ""), @("ifc_bridge", "--bonsai"), @("objects", "--bonsai"),
    @("server_ops", ""), @("ops_async", "--bonsai"), @("review_ops", "--bonsai"), @("sim_ops", ""), @("monitor_ops", "--bonsai"),
    @("import_ops", ""), @("import_guid", ""), @("import_edges", ""), @("import_ezdxf", ""), @("import_ifc", "--bonsai"), @("import_fallback", ""), @("demo_plant", "--bonsai"), @("roundtrip_ges", "--bonsai"), @("undo_rep", "--bonsai")
)
if ($env:GES_TEST_SERVER) { $tests += ,@("e2e_server", "--bonsai"); $tests += ,@("commit_conflict", "--bonsai"); $tests += ,@("sim_hydro", "--bonsai"); $tests += ,@("sim_twin", "--bonsai") }  # real server bilan uchdan-uchiga
$fails = 0; $skips = 0
foreach ($t in $tests) {
    $out = & $blender -b --python $runner -- --test $t[0] $t[1] 2>&1 | Out-String
    if ($out -match "\[OK\] $($t[0])") { "[OK]   $($t[0])" }
    elseif ($out -match "\[SKIP\] $($t[0]):(.*)") { "[SKIP] $($t[0]):$($Matches[1].Trim())"; $skips++ }
    else { "[FAIL] $($t[0])"; $out | Select-String -Pattern "Error|assert" | ForEach-Object { "       " + $_.Line }; $fails++ }
}
"`nFAIL soni: $fails · SKIP: $skips"
if ($fails -eq 0 -and $skips -gt 0 -and $env:SATH_REQUIRE_NO_SKIP -eq "1") { "SKIP taqiqlangan (SATH_REQUIRE_NO_SKIP=1)"; exit 1 }
exit $fails
