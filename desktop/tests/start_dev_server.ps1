# Lokal test serveri (yangi vaqtinchalik DB, admin/admin123, CFD o'chiq) - Blender e2e/GUI sinovlari uchun.
#   .\desktop\tests\start_dev_server.ps1 [-Fresh]
param([switch]$Fresh)
$d = Join-Path $env:TEMP "ges_twin_test"
if ($Fresh -and (Test-Path $d)) { Remove-Item -Recurse -Force $d }
New-Item -ItemType Directory -Force $d | Out-Null
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:GES_DATA_DIR = $d
$env:GES_DATABASE_URL = "sqlite:///" + $d.Replace("\", "/") + "/ges.db"
$env:GES_ADMIN_PASSWORD = "admin123"
$env:GES_SECRET_KEY = "e2e-secret-key-that-is-at-least-32-bytes-long"
$env:GES_CFD_MODE = "off"
$p = Start-Process -FilePath (Join-Path $root ".venv\Scripts\python.exe") -ArgumentList "-m", "uvicorn", "ges_server.main:app", "--port", "8000" -WorkingDirectory (Join-Path $root "server") -RedirectStandardOutput (Join-Path $d "server.out") -RedirectStandardError (Join-Path $d "server.err") -PassThru
Start-Sleep -Seconds 8
"server pid $($p.Id) - http://127.0.0.1:8000 (log: $d\server.err)"
