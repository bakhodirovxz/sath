# Poydevor P0–P1: desktop CI, bazaviy o'lchov va fon vazifalari — amalga oshirish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Blender addoni testlari CI da ishlaydi, desktop unumdorligining bazaviy raqamlari yozib olinadi va uzoq tarmoq chaqiruvlari Blender oynasini qotirmaydi (K3, K7).

**Architecture:** Sof (bpy siz) `sath/core/tasks.py` `TaskManager` ishni daemon oqimda bajaradi va natijani navbat orqali asosiy oqimga qaytaradi. `sath/core/ui_tasks.py` uni Blender ga ulaydi: pompa timer, status bar progressi, bekor qilish operatori, `run_op()` yordamchisi. Operatorlar «ishchi qism (tarmoq, bpy siz) → asosiy oqim qismi (bpy)» ga ajratiladi. Fon rejimida (`blender -b`) vazifalar sinxron bajariladi — mavjud headless testlar o'zgarmaydi; asinxron yo'l alohida test bilan majburan sinaladi.

**Tech Stack:** Blender 5.2.2 LTS (Python 3.13, bpy), Bonsai 0.8.5, stdlib (`threading`, `queue`, `urllib`, `http.server`); pytest (Python 3.10+, monorepo `.venv`); GitHub Actions `windows-2022`.

**Spec:** `docs/superpowers/specs/2026-10-08-sath-foundation-design.md` (§3 async vazifa ishchisi, §7 K7, «Bosqichlar» P0–P1)

## Global Constraints

- Blender **5.2.2** (`blender-5.2.2-windows-x64.zip`, sha256 `3849d17a682cba006075aaa3f3597ecb5c9c30ec31035b2e092c53e40679b535`), Bonsai **0.8.5** (sha256 `81c0cfc9a6204e13fdd4391daef6e91ed8033488fde69ca5933b3535f490514f`, `desktop/build/build_blender_bundle.py:94-95` dagi pin).
- `common/sath_common/*` — kanonik manba; nusxalar faqat `python desktop/build/sync_blender.py` bilan yangilanadi, qo'lda tahrirlanmaydi. CI `--check` qiladi.
- Pytest Python **3.10** da ham ishlaydi (monorepo `.venv`) — 3.11+ sintaksis/kutubxona (`tomllib`, `ExceptionGroup`) sof modullarda ishlatilmaydi.
- Ishchi oqim **hech qachon** `bpy` ga tegmaydi; bpy faqat asosiy oqimda (`on_done`/`on_error`/`apply`/`fail` callbacklarida).
- Daemon `threading.Thread` (ThreadPoolExecutor emas). Pompa timer `persistent=True`, interval **0.1 s**.
- Mavjud `bl_idname` lar o'zgarmaydi. Foydalanuvchi matnlari o'zbekcha (lotin), commit xabarlari o'zbekcha `fix(K3): …` / `test(K7): …` / `feat(K3): …` uslubida, oxirida `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- `ruff check server sim desktop` toza qoladi (`ruff.toml`).

## Review Focus

1. **Bir xil amalni ketma-ket ikki marta bosish** (masalan «Ota bilan farq») — ikkinchisi rad etiladi («allaqachon bajarilmoqda»), ikki parallel vazifa ishga tushmaydi → Task 5 `test_same_key_rejected_while_running`, Task 8 `ops_async` dagi ikkinchi `diff` chaqiruvi.
2. **Vazifa davomida chiqish yoki boshqa modelni ochish** — eski natija yangi sahnaga yozilmaydi → Task 7 `tasks_async` dagi epoch tekshiruvi.
3. **Addon o'chirilishi/Blender yopilishi uzoq vazifa paytida** — osilib qolmaydi, vazifalar bekor qilinadi → Task 7 `tasks_async` dagi `unregister` vaqt tekshiruvi.
4. **Server yuklash o'rtasida uziladi yoki javob bermaydi** — qisman `.part` fayl qolmaydi, eski keshdagi IFC buzilmaydi, aniq xato chiqadi → Task 4 `test_download_error_keeps_old_file`, `test_timeout_is_server_error`.
5. **Access token bir vaqtda ikki oqimda eskiradi** (monitoring + diff) — refresh bir marta, ikkala so'rov muvaffaqiyatli → Task 4 `test_concurrent_401_refreshes_once`.

---

## Fayl tuzilmasi

| Fayl | Mas'uliyat |
|---|---|
| `desktop/tests/blender_headless.py` (o'zgaradi) | `[SKIP]` protokoli, FreeCAD yo'lini majburan bermaslik |
| `desktop/tests/sath_tests/_req.py` (yangi) | `require_freecad()` — FreeCAD yo'q bo'lsa `SkipTest` |
| `desktop/tests/run_blender_tests.ps1` (o'zgaradi) | `[SKIP]` ni hisoblash, `tasks_async`/`ops_async` ro'yxatda |
| `desktop/build/ci_blender_setup.py` (yangi) | CI: Blender zip tekshiruvi/ochish, portable, Bonsai o'rnatish |
| `.github/workflows/ci.yml` (o'zgaradi) | `desktop-blender` ishi |
| `desktop/tests/perf_blender.py`, `desktop/tests/perf_baseline.py` (yangi) | bazaviy o'lchov (Blender ichida / tashqi o'lchagich) |
| `docs/benchmark-desktop.md` (yangi) | bazaviy raqamlar |
| `common/sath_common/server_client.py` (o'zgaradi) → `sync_blender.py` | thread-safe refresh, timeout → ServerError, oqimli yuklash |
| `desktop/tests/test_client_threading.py` (yangi) | soxta `urlopen` bilan client testlari |
| `desktop/blender/sath/core/__init__.py`, `core/tasks.py`, `core/events.py` (yangi, sof) | TaskManager, hodisalar |
| `desktop/tests/test_sath_tasks.py`, `test_sath_events.py` (yangi) | sof testlar |
| `desktop/blender/sath/core/ui_tasks.py` (yangi, bpy) | pompa, status bar, bekor qilish, `run_op`, `show_error` |
| `desktop/blender/sath/session.py` (o'zgaradi) | `connect_client`, `set_session`, `remember`, epoch |
| `desktop/blender/sath/ifc.py` (o'zgaradi) | `load()` epoch ni oshiradi, `ifc.loaded` hodisasi |
| `desktop/blender/sath/ops_server.py`, `ops_review.py`, `ops_sim.py`, `ops_twin.py`, `ops_monitor.py`, `update.py` (o'zgaradi) | operatorlarni `run_op`/`TASKS` ga ko'chirish |
| `desktop/tests/sath_tests/tasks_async.py`, `fake_server.py`, `ops_async.py` (yangi) | headless asinxron testlar |
| `desktop/tests/sath_tests/sim_hydro.py`, `sim_twin.py`, `gui_twin.py` (o'zgaradi) | `_poll_factory` → `wait_job` |

---

### Task 1: Headless runner — `[SKIP]` protokoli

FreeCAD siz mashinada (CI) `engine`, `objects`, `demo_plant` testlari yiqilmasin, balki aniq «o'tkazib yuborildi» bo'lsin. P2 da FreeCAD olib tashlanganda bu testlar golden-paritet testlari bilan almashadi.

**Files:**
- Modify: `desktop/tests/blender_headless.py:55-64`
- Create: `desktop/tests/sath_tests/_req.py`
- Modify: `desktop/tests/sath_tests/engine.py`, `objects.py`, `demo_plant.py` (har birining `run()` boshiga bitta qator)
- Modify: `desktop/tests/run_blender_tests.ps1`

**Interfaces:**
- Produces: `sath_tests/_req.py::SkipTest(Exception)`, `require_freecad() -> None`; runner chiqishi `[SKIP] <nom>: <sabab>` va exit 0.

- [ ] **Step 1: Hozirgi holatni yozib oling (FreeCAD siz `engine` yiqiladi)**

```powershell
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"
$env:GES_FC_HOME="C:\yoq"
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test engine 2>&1 | Select-String "OK|FAIL|SKIP"
```
Expected: `[FAIL] engine`

- [ ] **Step 2: `_req.py` ni yarating**

```python
"""Headless testlar uchun talablar: yo'q bo'lsa test yiqilmaydi, [SKIP] bo'ladi (K7)."""

from __future__ import annotations


class SkipTest(Exception):
    """Test sharoiti yo'q (masalan FreeCAD) — runner `[SKIP]` yozadi, exit 0."""


def require_freecad() -> None:
    from sath import fc_engine

    if not fc_engine.available():
        raise SkipTest("FreeCAD topilmadi (GES_FC_HOME) — P2 da FreeCAD siz builder lar bilan almashadi")
```

- [ ] **Step 3: `engine.py`, `objects.py`, `demo_plant.py` ning `def run(ctx):` dan keyingi birinchi qatori**

```python
    from _req import require_freecad

    require_freecad()
```

- [ ] **Step 4: Runner — `GES_FC_HOME` ni majburan bermaslik va `SkipTest` ni ushlash**

`desktop/tests/blender_headless.py` dagi `main()` ni almashtiring:

```python
def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    name = argv[argv.index("--test") + 1] if "--test" in argv else "smoke"
    if "--bonsai" in argv:
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
    # K7: FreeCAD yo'li faqat muhitdan yoki addon sozlamasidan (CI da yo'q → FreeCAD testlari [SKIP])
    addon = load_addon()
    sys.path.insert(0, str(ROOT / "desktop" / "tests" / "sath_tests"))
    from _req import SkipTest

    try:
        importlib.import_module(name).run({"addon": addon})
        print(f"[OK] {name}", flush=True)
        return 0
    except SkipTest as e:
        print(f"[SKIP] {name}: {e}", flush=True)
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print(f"[FAIL] {name}", flush=True)
        return 1
```

`os` importi endi ishlatilmasa, uni olib tashlang (ruff F401).

- [ ] **Step 5: `run_blender_tests.ps1` — `[SKIP]` ni sanash**

Faylning `$fails = 0` dan oxirigacha bo'lgan qismini almashtiring:

```powershell
$fails = 0; $skips = 0
foreach ($t in $tests) {
    $out = & $blender -b --python $runner -- --test $t[0] $t[1] 2>&1 | Out-String
    if ($out -match "\[OK\] $($t[0])") { "[OK]   $($t[0])" }
    elseif ($out -match "\[SKIP\] $($t[0]):(.*)") { "[SKIP] $($t[0]):$($Matches[1].Trim())"; $skips++ }
    else { "[FAIL] $($t[0])"; $out | Select-String -Pattern "Error|assert" | ForEach-Object { "       " + $_.Line }; $fails++ }
}
"`nFAIL soni: $fails · SKIP: $skips"
exit $fails
```

Fayl boshidagi izohni `# Sath Blender addoni headless testlari (Blender 5.2 + Bonsai; FreeCAD bo'lmasa FreeCAD testlari [SKIP]).` ga o'zgartiring.

- [ ] **Step 6: Tekshiring**

```powershell
$env:GES_FC_HOME="C:\yoq"
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test engine 2>&1 | Select-String "OK|FAIL|SKIP"
Remove-Item Env:GES_FC_HOME
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test engine 2>&1 | Select-String "OK|FAIL|SKIP"
```
Expected: birinchisi `[SKIP] engine: FreeCAD topilmadi …`; ikkinchisi (addon sozlamasidagi default `~/Tools/fc-py313` bilan) `[OK] engine`.

- [ ] **Step 7: To'liq to'plam lokal**

Run: `.\desktop\tests\run_blender_tests.ps1`
Expected: `FAIL soni: 0` (bu mashinada FreeCAD bor — SKIP 0).

- [ ] **Step 8: Commit**

```bash
git add desktop/tests/blender_headless.py desktop/tests/run_blender_tests.ps1 desktop/tests/sath_tests/_req.py desktop/tests/sath_tests/engine.py desktop/tests/sath_tests/objects.py desktop/tests/sath_tests/demo_plant.py
git commit -m "test(K7): headless runner da [SKIP] protokoli — FreeCAD siz mashinada FreeCAD testlari yiqilmaydi"
```

---

### Task 2: CI — `desktop-blender` ishi

**Files:**
- Create: `desktop/build/ci_blender_setup.py`
- Modify: `.github/workflows/ci.yml` (yangi ish `desktop-blender`, `e2e` ishidan keyin)

**Interfaces:**
- Consumes: `build_blender_bundle.ensure_bonsai(explicit: Path | None, blender_version: str) -> Path`, `build_blender_bundle.TOOLS`, Task 1 runner.
- Produces: CI muhit o'zgaruvchisi `GES_BLENDER`; artefakt `sath-addon` (`desktop/dist/sath-*.zip`).

- [ ] **Step 1: Bonsai pin hozir extensions.blender.org dagi versiyaga tengmi — tekshiring**

```bash
curl -s "https://extensions.blender.org/api/v1/extensions/?blender_version=5.2.2&platform=windows-x64" | python -c "import json,sys; print(next(e['version'] for e in json.load(sys.stdin)['data'] if e['id']=='bonsai'))"
```
Expected: `0.8.5`. Agar boshqa versiya chiqsa — `ensure_bonsai` CI da yiqiladi. Bu holda ishni to'xtatib, foydalanuvchiga ayting: Bonsai pinini yangilash (yangi zip bilan butun headless to'plamni lokal sinab, `BONSAI_VERSION`/`BONSAI_SHA256` ni o'zgartirish) yoki pinlangan zip ni repo Release asseti sifatida joylash kerak — ikkalasi ham sizning qaroringiz.

- [ ] **Step 2: `ci_blender_setup.py` ni yarating**

```python
"""CI (K7): Blender zip ni sha256 bilan tekshirib ochadi, portable rejim (runner profilidan ajratilgan prefs va
extension lar), Bonsai ni pinlangan versiya va sha256 bilan o'rnatadi. GES_BLENDER ni GITHUB_ENV ga yozadi.

  python desktop/build/ci_blender_setup.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_blender_bundle as bb  # noqa: E402

BLENDER_VERSION = "5.2.2"
BLENDER_SHA256 = "3849d17a682cba006075aaa3f3597ecb5c9c30ec31035b2e092c53e40679b535"
BLENDER_URL = f"https://download.blender.org/release/Blender5.2/blender-{BLENDER_VERSION}-windows-x64.zip"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def ensure_blender() -> Path:
    bb.TOOLS.mkdir(parents=True, exist_ok=True)
    zp = bb.TOOLS / f"blender-{BLENDER_VERSION}-windows-x64.zip"
    if not zp.exists():
        part = zp.with_name(zp.name + ".part")
        print("Blender yuklab olinmoqda:", BLENDER_URL, flush=True)
        urllib.request.urlretrieve(BLENDER_URL, part)  # noqa: S310
        os.replace(part, zp)
    if _sha256(zp) != BLENDER_SHA256:
        zp.unlink()
        raise SystemExit("Blender zip sha256 qotirilgan qiymatga mos emas")
    root = bb.TOOLS / f"blender-{BLENDER_VERSION}-windows-x64"
    if not (root / "blender.exe").exists():
        with zipfile.ZipFile(zp) as z:
            z.extractall(bb.TOOLS)
    (root / "portable").mkdir(exist_ok=True)  # Blender 4.2+: prefs/extensions shu papkada
    return root


def main() -> int:
    root = ensure_blender()
    exe = root / "blender.exe"
    bonsai = bb.ensure_bonsai(None, BLENDER_VERSION)
    subprocess.run(
        [str(exe), "-b", "--command", "extension", "install-file", "--repo", "user_default", "--enable", str(bonsai)],
        check=True,
    )
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"GES_BLENDER={exe}\n")
    print("GES_BLENDER =", exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Lokal tekshiruv (internet bor mashinada, keshdagi zip lar bilan)**

Run: `python desktop/build/ci_blender_setup.py`
Expected: `GES_BLENDER = C:\Users\...\Tools\blender-5.2.2-windows-x64\blender.exe`, xatosiz. (Lokal `~/Tools/blender-5.2` ga tegmaydi — alohida papka.)

- [ ] **Step 4: Ochilgan portable Blender da smoke**

```powershell
$env:GES_BLENDER="$HOME\Tools\blender-5.2.2-windows-x64\blender.exe"; $env:GES_FC_HOME="C:\yoq"
.\desktop\tests\run_blender_tests.ps1
```
Expected: `FAIL soni: 0`, `SKIP: 3` (engine, objects, demo_plant).

- [ ] **Step 5: `ci.yml` ga ish qo'shing (fayl oxiriga)**

```yaml
  desktop-blender:
    # K7: Blender addoni headless testlari — Blender 5.2.2 + Bonsai 0.8.5 (sha256 pin), FreeCAD siz
    # (FreeCAD testlari [SKIP]; P2 da FreeCAD siz builder lar bilan almashadi). Server talab qiladigan
    # testlar (GES_TEST_SERVER) bu yerda ishlamaydi.
    runs-on: windows-2022
    needs: [server]
    steps:
      - uses: actions/checkout@v4
        with: { lfs: true }  # addon wheel lari LFS da
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/cache@v4
        with:
          path: |
            ~/Tools/blender-5.2.2-windows-x64.zip
            ~/Tools/bonsai-0.8.5-py313-win64.zip
          key: blender-5.2.2-bonsai-0.8.5-v1
      - run: python desktop/build/ci_blender_setup.py
      - run: python desktop/build/sync_blender.py --check
      - name: Headless testlar
        shell: pwsh
        run: ./desktop/tests/run_blender_tests.ps1
      - name: Addon zip
        shell: pwsh
        run: python desktop/build/build_blender_addon.py --blender $env:GES_BLENDER
      - uses: actions/upload-artifact@v4
        with: { name: sath-addon, path: desktop/dist/sath-*.zip, retention-days: 14 }
```

- [ ] **Step 6: `build_blender_addon.py` `--blender` argumentini qabul qiladimi — tekshiring**

Run: `python desktop/build/build_blender_addon.py --help`
Expected: `--blender` opsiyasi bor. Agar yo'q bo'lsa (`:17` da `~/Tools/blender-5.2/blender.exe` qat'iy), `argparse` bilan qo'shing: `ap.add_argument("--blender", type=Path, default=Path(os.environ.get("GES_BLENDER", <hozirgi default>)))` va shu qiymatni hozirgi qat'iy yo'l o'rniga ishlating. So'ng: `python desktop/build/build_blender_addon.py --blender "$env:GES_BLENDER"` → `desktop/dist/sath-0.3.0.zip`.

- [ ] **Step 7: Commit va push qilmasdan oldin YAML ni tekshiring**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`

```bash
git add desktop/build/ci_blender_setup.py desktop/build/build_blender_addon.py .github/workflows/ci.yml
git commit -m "ci(K7): desktop-blender ishi — Blender 5.2.2 + Bonsai sha256 pin, headless testlar, addon zip artefakt"
```

CI natijasini (birinchi push dan keyin) foydalanuvchiga ko'rsating; push qilishni foydalanuvchi so'raganda qiling.

---

### Task 3: Bazaviy o'lchov (P0)

C++ ga nimani ko'chirish va byudjetlar (spec §5) shu raqamlarga tayanadi. Faqat lokal ishga tushiriladi (CI da emas).

**Files:**
- Create: `desktop/tests/perf_blender.py` (Blender ichida)
- Create: `desktop/tests/perf_baseline.py` (tizim Python, o'lchagich)
- Create: `docs/benchmark-desktop.md`

**Interfaces:**
- Consumes: `blender_headless.load_addon()`.
- Produces: `perf_blender.py` stdout da bitta qator `PERF {json}`; `perf_baseline.py` → `docs/benchmark-desktop.md`.

- [ ] **Step 1: `perf_blender.py` ni yarating**

```python
"""Blender ichida o'lchov: addon register vaqti, RSS, sintetik IFC (N element) ni Bonsai da ochish.

  blender -b --python desktop/tests/perf_blender.py -- [--n 2000]
Natija: `PERF {...}` (json) — desktop/tests/perf_baseline.py o'qiydi.
"""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_headless  # noqa: E402


def rss_mb() -> float | None:
    if sys.platform != "win32":
        return None

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (n, ctypes.c_size_t)
            for n in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]  # fmt: skip

    c = PMC()
    c.cb = ctypes.sizeof(c)
    h = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 2**20


def synthetic_ifc(n: int, path: Path) -> Path:
    import ifcopenshell.api as api
    import numpy as np

    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="perf")
    api.run("unit.assign_unit", f)
    model = api.run("context.add_context", f, context_type="Model")
    body = api.run(
        "context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", f, relating_object=proj, products=[site])
    for i in range(n):
        el = api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy", name=f"E{i}")
        rep = api.run("geometry.add_wall_representation", f, context=body, length=1.0, height=1.0, thickness=1.0)
        api.run("geometry.assign_representation", f, product=el, representation=rep)
        m = np.eye(4)
        m[0][3], m[1][3] = (i % 100) * 2.0, (i // 100) * 2.0
        api.run("geometry.edit_object_placement", f, product=el, matrix=m)
        api.run("spatial.assign_container", f, relating_structure=site, products=[el])
    f.write(str(path))
    return path


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 2000
    out: dict = {"rss_start_mb": rss_mb()}
    t = time.perf_counter()
    blender_headless.load_addon()
    out["addon_register_ms"] = round((time.perf_counter() - t) * 1000, 1)
    out["rss_addon_mb"] = rss_mb()
    bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
    path = synthetic_ifc(n, Path(tempfile.mkdtemp(prefix="sath-perf-")) / f"perf_{n}.ifc")
    out["ifc_elements"] = n
    out["ifc_size_mb"] = round(path.stat().st_size / 2**20, 2)
    t = time.perf_counter()
    bpy.ops.bim.load_project(filepath=str(path))
    out["ifc_open_s"] = round(time.perf_counter() - t, 2)
    out["rss_ifc_mb"] = rss_mb()
    print("PERF " + json.dumps(out), flush=True)


main()
```

`ifcopenshell.api` funksiya imzolari mos kelmasa (`TypeError`), to'g'ri parametr nomlarini `python -c "import ifcopenshell.api.<modul>.<funksiya> as m; help(m)"` (Blender python ichida) bilan aniqlang va tuzating.

- [ ] **Step 2: Bir marta ishga tushiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/perf_blender.py -- --n 500 2>&1 | Select-String "PERF"`
Expected: `PERF {"rss_start_mb": ..., "addon_register_ms": ..., "ifc_open_s": ...}`

- [ ] **Step 3: `perf_baseline.py` ni yarating**

```python
"""Desktop bazaviy o'lchov (P0): sovuq start (vanilla / +Bonsai / +Sath), register vaqti, RSS, katta IFC ochish.
Har o'lchov 3 marta, mediana. Natija docs/benchmark-desktop.md ga yoziladi.

  python desktop/tests/perf_baseline.py [--blender <exe>] [--n 2000]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))
REPEAT = 3


def wall(cmd: list[str]) -> float:
    t = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    return time.perf_counter() - t


def perf_json(exe: Path, n: int) -> dict:
    r = subprocess.run(
        [str(exe), "-b", "--python", str(ROOT / "desktop" / "tests" / "perf_blender.py"), "--", "--n", str(n)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith("PERF "))
    return json.loads(line[5:])


def median(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    exe = a.blender
    quit_expr = ["--python-expr", "import bpy; bpy.ops.wm.quit_blender()"]
    vanilla = [wall([str(exe), "-b", "--factory-startup", *quit_expr]) for _ in range(REPEAT)]
    bonsai = [
        wall([str(exe), "-b", "--python-expr",
              "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.bonsai'); bpy.ops.wm.quit_blender()"])
        for _ in range(REPEAT)
    ]  # fmt: skip
    runs = [perf_json(exe, a.n) for _ in range(REPEAT)]
    keys = ["addon_register_ms", "rss_start_mb", "rss_addon_mb", "ifc_open_s", "rss_ifc_mb", "ifc_size_mb"]
    med = {k: median([r.get(k) for r in runs]) for k in keys}
    rows = [
        ("Sovuq start, vanilla (-b, factory)", f"{median(vanilla)} s"),
        ("Sovuq start, + Bonsai", f"{median(bonsai)} s"),
        ("Sath import + register", f"{med['addon_register_ms']} ms"),
        ("RSS: start / Sath bilan", f"{med['rss_start_mb']} / {med['rss_addon_mb']} MB"),
        (f"Sintetik IFC ({a.n} element, {med['ifc_size_mb']} MB) ochish", f"{med['ifc_open_s']} s"),
        ("RSS IFC ochilgandan keyin", f"{med['rss_ifc_mb']} MB"),
    ]
    md = [
        "# Desktop (Blender) unumdorligi — bazaviy o'lchov",
        "",
        f"Sana: {date.today().isoformat()} · Mashina: {platform.processor() or platform.machine()} · "
        f"OS: {platform.platform()} · Blender: `{exe}`",
        "",
        f"Usul: `python desktop/tests/perf_baseline.py --n {a.n}` — har o'lchov {REPEAT} marta, mediana. "
        "Spec §5 byudjetlari va C++ (`sath_core`) qarorlari shu raqamlarga tayanadi.",
        "",
        "| O'lchov | Qiymat |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in rows],
        "",
    ]
    out = ROOT / "docs" / "benchmark-desktop.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Ishga tushiring**

Run: `python desktop/tests/perf_baseline.py --n 2000`
Expected: jadval chiqadi va `docs/benchmark-desktop.md` yoziladi; barcha qiymatlar `None` emas (Windows da RSS ham).

- [ ] **Step 5: Commit**

```bash
git add desktop/tests/perf_blender.py desktop/tests/perf_baseline.py docs/benchmark-desktop.md
git commit -m "perf(P0): desktop bazaviy o'lchovi — sovuq start, register, RSS, sintetik IFC ochish"
```

---

### Task 4: `GesClient` — thread-safe refresh, timeout, oqimli yuklash

**Files:**
- Modify: `common/sath_common/server_client.py` (`__init__`, `_request`, `_refresh`, `download_version`)
- Create: `desktop/tests/test_client_threading.py`
- Then: `python desktop/build/sync_blender.py` (addon `shared/` va GesWorkbench nusxalari)

**Interfaces:**
- Produces:
  - `class TransferCancelled(Exception)` (server_client modulida)
  - `GesClient.download_version(version_id: int, dest: Path, progress: Callable[[int, int], None] | None = None, cancelled: Callable[[], bool] | None = None) -> Path` — `dest` faqat to'liq yuklangandan keyin almashtiriladi (`<dest>.part` → `os.replace`); xato/bekor qilishda `.part` o'chiriladi, eski `dest` saqlanadi.
  - `_refresh(stale_token: str | None = None) -> bool` — `threading.Lock` ostida; boshqa oqim allaqachon yangilagan bo'lsa tarmoqqa chiqmaydi.
  - Timeout (`TimeoutError`/`socket.timeout`) → `ServerError(0, "Server javob bermadi (timeout …)")`.

- [ ] **Step 1: Yiqiluvchi testlarni yozing**

```python
"""GesClient: parallel 401 da bitta refresh, timeout → ServerError, oqimli yuklash (.part, progress, bekor qilish).
Soxta urlopen bilan — server kerak emas."""

import io
import json
import sys
import threading
import time
from pathlib import Path
from urllib import error

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common"))

from sath_common import server_client as sc  # noqa: E402


class FakeResp(io.BytesIO):
    def __init__(self, data: bytes, headers: dict | None = None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _http_error(code: int, url: str):
    return error.HTTPError(url, code, "x", {}, io.BytesIO(b'{"detail": "x"}'))


def test_concurrent_401_refreshes_once(monkeypatch):
    calls = {"refresh": 0}
    lock = threading.Lock()

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if url.endswith("/api/auth/refresh"):
            with lock:
                calls["refresh"] += 1
            time.sleep(0.05)
            return FakeResp(json.dumps({"access_token": "new", "refresh_token": "r2"}).encode())
        if req.get_header("Authorization") == "Bearer new":
            return FakeResp(b'{"ok": true}')
        raise _http_error(401, url)

    monkeypatch.setattr(sc.request, "urlopen", fake_urlopen)
    c = sc.GesClient("http://x", token="old")
    c.refresh_token = "r1"
    results = []
    ths = [threading.Thread(target=lambda: results.append(c.me())) for _ in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert results == [{"ok": True}] * 4
    assert calls["refresh"] == 1


def test_timeout_is_server_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(sc.request, "urlopen", fake_urlopen)
    with pytest.raises(sc.ServerError) as ei:
        sc.GesClient("http://x").health()
    assert ei.value.status == 0 and "timeout" in ei.value.message


def test_download_streams_with_progress(monkeypatch, tmp_path):
    data = b"x" * (3 * sc.CHUNK + 10)
    monkeypatch.setattr(
        sc.request, "urlopen", lambda req, timeout=None: FakeResp(data, {"Content-Length": str(len(data))})
    )
    seen = []
    dest = tmp_path / "v.ifc"
    sc.GesClient("http://x").download_version(1, dest, progress=lambda got, total: seen.append((got, total)))
    assert dest.read_bytes() == data
    assert seen[-1] == (len(data), len(data)) and len(seen) == 4
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_cancel_keeps_old_file(monkeypatch, tmp_path):
    data = b"y" * (3 * sc.CHUNK)
    monkeypatch.setattr(sc.request, "urlopen", lambda req, timeout=None: FakeResp(data))
    dest = tmp_path / "v.ifc"
    dest.write_bytes(b"OLD")
    n = {"i": 0}

    def cancelled():
        n["i"] += 1
        return n["i"] > 1

    with pytest.raises(sc.TransferCancelled):
        sc.GesClient("http://x").download_version(1, dest, cancelled=cancelled)
    assert dest.read_bytes() == b"OLD"
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_error_keeps_old_file(monkeypatch, tmp_path):
    class Broken(FakeResp):
        def read(self, n=-1):
            raise ConnectionResetError("uzildi")

    monkeypatch.setattr(sc.request, "urlopen", lambda req, timeout=None: Broken(b""))
    dest = tmp_path / "v.ifc"
    dest.write_bytes(b"OLD")
    with pytest.raises(sc.ServerError):
        sc.GesClient("http://x").download_version(1, dest)
    assert dest.read_bytes() == b"OLD"
    assert not dest.with_name(dest.name + ".part").exists()
```

- [ ] **Step 2: Yiqilishini tekshiring**

Run: `pytest -q desktop/tests/test_client_threading.py`
Expected: FAIL (`AttributeError: ... CHUNK` / `TransferCancelled`, parallel testda refresh > 1).

- [ ] **Step 3: `server_client.py` ni o'zgartiring**

Importlarga qo'shing: `import os`, `import threading`, `from collections.abc import Callable`. `ServerError` dan keyin:

```python
CHUNK = 1 << 20  # oqimli yuklash bo'lagi (1 MiB)


class TransferCancelled(Exception):
    """Yuklash foydalanuvchi tomonidan bekor qilindi (fayl o'zgarmaydi)."""
```

`__init__` oxiriga: `self._lock = threading.Lock()  # K3: refresh bir vaqtda faqat bitta oqimda`

`_request` imzosiga `stream_to: Path | None = None, progress=None, cancelled=None` qo'shing. `req.add_header("Authorization", ...)` dan oldin `sent = self.token` deb yozing. `with request.urlopen(...) as resp:` blokini almashtiring:

```python
        try:
            with request.urlopen(req, timeout=timeout or self.timeout) as resp:
                if stream_to is not None:
                    return self._stream(resp, stream_to, progress, cancelled)
                data = resp.read()
                if raw:
                    return data
                return json.loads(data) if data else None
        except error.HTTPError as e:
            if e.code == 401 and _retry and self.refresh_token and path != "/api/auth/refresh" and self._refresh(sent):
                return self._request(
                    method, path, body=body, content_type=content_type, params=params, raw=raw, timeout=timeout,
                    stream_to=stream_to, progress=progress, cancelled=cancelled, _retry=False,
                )  # fmt: skip
            ...  # mavjud payload/ServerError qismi o'zgarmaydi
        except error.URLError as e:
            raise ServerError(0, f"Serverga ulanib bo'lmadi: {e.reason}") from None
        except TimeoutError:  # socket.timeout — TimeoutError ning taxallusi (3.10+)
            raise ServerError(0, f"Server javob bermadi (timeout {timeout or self.timeout:.0f} s)") from None
        except (ConnectionError, OSError) as e:
            if isinstance(e, TransferCancelled):
                raise
            raise ServerError(0, f"Tarmoq xatosi: {e}") from None
```

(`TransferCancelled` `OSError` emas — `isinstance` qatori himoya uchun; uni `Exception` dan meros qilib qoldiring.)

Yangi metod:

```python
    @staticmethod
    def _stream(resp, dest: Path, progress, cancelled) -> Path:
        """Javobni `<dest>.part` ga bo'laklab yozadi; to'liq bo'lsa `dest` ni almashtiradi. Xato/bekor → .part o'chadi."""
        total = int(resp.headers.get("Content-Length") or 0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        got = 0
        try:
            with open(part, "wb") as fh:
                while True:
                    if cancelled is not None and cancelled():
                        raise TransferCancelled("bekor qilindi")
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if progress is not None:
                        progress(got, total or got)
            os.replace(part, dest)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return dest
```

`_refresh` ni almashtiring:

```python
    def _refresh(self, stale_token: str | None = None) -> bool:
        """Refresh token bilan yangi juftlik (K3: lock ostida). `stale_token` — 401 olgan so'rovdagi token; u allaqachon
        almashtirilgan bo'lsa (boshqa oqim yangiladi) tarmoqqa chiqmasdan True. Muvaffaqiyatsiz → False."""
        with self._lock:
            if stale_token is not None and self.token != stale_token:
                return True
            try:
                r = self._request(
                    "POST",
                    "/api/auth/refresh",
                    body=json.dumps({"refresh_token": self.refresh_token}).encode(),
                    content_type="application/json",
                    _retry=False,
                )
            except ServerError:
                self.refresh_token = None
                return False
            self.token = r["access_token"]
            self.refresh_token = r.get("refresh_token") or None
            return True
```

`download_version` ni almashtiring:

```python
    def download_version(
        self,
        version_id: int,
        dest: Path,
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """IFC ni oqim bilan yuklaydi (`.part` → `dest`); `progress(olingan, jami)`, `cancelled()` → TransferCancelled."""
        return self._request(
            "GET", f"/api/versions/{version_id}/file", stream_to=dest, progress=progress, cancelled=cancelled
        )
```

Modul docstringidagi «faqat standart kutubxona» saqlanadi (yangi importlar ham stdlib).

- [ ] **Step 4: Testlar o'tishini tekshiring**

Run: `pytest -q desktop/tests/test_client_threading.py desktop/tests/test_server_client.py`
Expected: PASS (`test_server_client.py` real uvicorn bilan — mavjud xatti-harakat buzilmagan).

- [ ] **Step 5: Nusxalarni sinxronlang va tekshiring**

Run: `python desktop/build/sync_blender.py; python desktop/build/sync_blender.py --check; pytest -q desktop/tests/test_sath_pure.py`
Expected: `--check` xatosiz, pure testlar PASS.

- [ ] **Step 6: Commit**

```bash
git add common/sath_common/server_client.py desktop/blender/sath/shared/server_client.py desktop/GesWorkbench/ges_workbench/server_client.py desktop/tests/test_client_threading.py
git commit -m "fix(K3): GesClient — refresh lock ostida (parallel 401 da bitta refresh), timeout ServerError, oqimli yuklash .part bilan, progress va bekor qilish"
```

---

### Task 5: `core/tasks.py` — sof `TaskManager`

**Files:**
- Create: `desktop/blender/sath/core/__init__.py` (bitta docstring qatori: `"""Sath yadrosi: bpy siz (tasks, events) va Blender ulagichlari (ui_tasks)."""`)
- Create: `desktop/blender/sath/core/tasks.py`
- Test: `desktop/tests/test_sath_tasks.py`

**Interfaces:**
- Produces (`sath.core.tasks`):
  - `class Cancelled(Exception)`
  - `class Task`: `id: int`, `title: str`, `key: str | None`, `cancellable: bool`, `quiet: bool`, `frac: float | None`, `text: str`, `cancelled: bool` (property), `cancel() -> None`
  - `class TaskContext`: `cancelled: bool` (property), `check() -> None` (bekor bo'lsa `Cancelled`), `progress(frac: float | None, text: str = "") -> None`, `sleep(seconds: float) -> None` (bekor qilinganda darhol uyg'onadi va `Cancelled`)
  - `class TaskManager`: `inline: bool`, `on_error_default: Callable[[Task, BaseException], None]`, `run(title, fn, on_done=None, on_error=None, *, key=None, cancellable=True, quiet=False) -> Task | None`, `pump() -> int`, `running(key: str) -> bool`, `active() -> list[Task]`, `cancel(task_id: int) -> bool`, `cancel_all() -> None`, `drain(timeout: float = 30.0) -> None`
  - `TASKS = TaskManager()` — modul darajasidagi yagona nusxa

- [ ] **Step 1: Yiqiluvchi testlarni yozing**

```python
"""core.tasks (K3): ishchi oqim, asosiy oqimga navbat, kalit bo'yicha takrorni rad etish, bekor qilish, inline rejim."""

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core.tasks import Cancelled, TaskManager  # noqa: E402


def test_run_returns_immediately_and_done_on_pump_thread():
    tm = TaskManager()
    seen = {}
    t0 = time.perf_counter()
    task = tm.run("sekin", lambda ctx: (time.sleep(0.2), 42)[1], lambda r: seen.update(r=r, th=threading.current_thread()))
    assert time.perf_counter() - t0 < 0.05 and task is not None
    assert tm.active() == [task]
    tm.drain(5)
    assert seen == {"r": 42, "th": threading.main_thread()}
    assert tm.active() == []


def test_same_key_rejected_while_running():
    tm = TaskManager()
    ev = threading.Event()
    a = tm.run("a", lambda ctx: ev.wait(5), key="review.diff")
    b = tm.run("b", lambda ctx: 1, key="review.diff")
    assert a is not None and b is None and tm.running("review.diff")
    ev.set()
    tm.drain(5)
    assert not tm.running("review.diff")


def test_error_goes_to_on_error_on_main_thread():
    tm = TaskManager()
    got = {}

    def boom(ctx):
        raise ValueError("yomon")

    tm.run("x", boom, lambda r: got.update(done=True), lambda e: got.update(err=str(e), th=threading.current_thread()))
    tm.drain(5)
    assert got == {"err": "yomon", "th": threading.main_thread()}


def test_error_without_handler_uses_default():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append((task.title, str(e)))
    tm.run("x", lambda ctx: 1 / 0)
    tm.drain(5)
    assert got and got[0][0] == "x" and "division" in got[0][1]


def test_callback_exception_does_not_break_pump():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append(str(e))
    tm.run("a", lambda ctx: 1, lambda r: (_ for _ in ()).throw(RuntimeError("apply xato")))
    tm.run("b", lambda ctx: 2, lambda r: got.append(r))
    tm.drain(5)
    assert "apply xato" in got and 2 in got


def test_cancel_wakes_sleep_and_drops_result():
    tm = TaskManager()
    got = []

    def slow(ctx):
        for _ in range(100):
            ctx.sleep(0.5)
        return "tugadi"

    task = tm.run("sekin", slow, got.append, got.append)
    t0 = time.perf_counter()
    assert tm.cancel(task.id) is True
    tm.drain(5)
    assert time.perf_counter() - t0 < 1.0
    assert got == []  # bekor qilingan vazifaning natijasi ham, xatosi ham tashlanadi


def test_progress_visible_from_main():
    tm = TaskManager()
    ev = threading.Event()

    def work(ctx):
        ctx.progress(0.5, "yarmi")
        ev.wait(5)

    task = tm.run("p", work)
    for _ in range(100):
        if task.frac == 0.5:
            break
        time.sleep(0.01)
    assert (task.frac, task.text) == (0.5, "yarmi")
    ev.set()
    tm.drain(5)


def test_inline_mode_is_synchronous_and_raises_without_handler():
    tm = TaskManager()
    tm.inline = True
    got = []
    assert tm.run("i", lambda ctx: 7, got.append) is not None and got == [7]
    with pytest.raises(ZeroDivisionError):
        tm.run("i", lambda ctx: 1 / 0)
    tm.run("i", lambda ctx: 1 / 0, None, lambda e: got.append(type(e).__name__))
    assert got == [7, "ZeroDivisionError"] and tm.active() == []


def test_cancel_all():
    tm = TaskManager()
    for i in range(3):
        tm.run(f"t{i}", lambda ctx: [ctx.sleep(0.2) for _ in range(50)])
    tm.cancel_all()
    tm.drain(5)
    assert tm.active() == []


def test_cancelled_exception_is_silent():
    tm = TaskManager()
    got = []
    tm.on_error_default = lambda task, e: got.append(e)

    def work(ctx):
        raise Cancelled()

    tm.run("c", work)
    tm.drain(5)
    assert got == []
```

- [ ] **Step 2: Yiqilishini tekshiring**

Run: `pytest -q desktop/tests/test_sath_tasks.py`
Expected: FAIL (`ModuleNotFoundError: sath.core`)

- [ ] **Step 3: `core/tasks.py` ni yozing**

```python
"""Fon vazifalari (K3): tarmoq/og'ir ish daemon oqimda, natija va xato asosiy oqimda (`pump()`).

bpy ga bog'liq emas — pytest bilan sinaladi. Blender ulagichi (timer, status bar, operatorlar): core/ui_tasks.py.
Qoida: `fn(ctx)` bpy ga TEGMAYDI; `on_done`/`on_error` faqat `pump()` dan (asosiy oqim) chaqiriladi.
`inline=True` (Blender -b) — hammasi sinxron: headless testlar ketma-ket ishlaydi.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

_ids = itertools.count(1)


class Cancelled(Exception):
    """Vazifa bekor qilindi (ctx.check/ctx.sleep tashlaydi; natija tashlanadi, xato ko'rsatilmaydi)."""


class Task:
    def __init__(self, title: str, key: str | None, cancellable: bool, quiet: bool):
        self.id = next(_ids)
        self.title = title
        self.key = key
        self.cancellable = cancellable
        self.quiet = quiet  # status barda ko'rsatilmaydi (masalan monitoring tiki)
        self.frac: float | None = None
        self.text = ""
        self._cancel = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()


class TaskContext:
    def __init__(self, task: Task):
        self._task = task

    @property
    def cancelled(self) -> bool:
        return self._task.cancelled

    def check(self) -> None:
        if self._task.cancelled:
            raise Cancelled()

    def progress(self, frac: float | None, text: str = "") -> None:
        self._task.frac = None if frac is None else max(0.0, min(1.0, float(frac)))
        self._task.text = text

    def sleep(self, seconds: float) -> None:
        if self._task._cancel.wait(seconds):
            raise Cancelled()


def _print_error(task: Task, exc: BaseException) -> None:
    print(f"[sath] {task.title}: {exc}", flush=True)
    traceback.print_exception(type(exc), exc, exc.__traceback__)


class TaskManager:
    def __init__(self) -> None:
        self.inline = False
        self.on_error_default: Callable[[Task, BaseException], None] = _print_error
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._active: list[Task] = []

    def run(
        self,
        title: str,
        fn: Callable[[TaskContext], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        *,
        key: str | None = None,
        cancellable: bool = True,
        quiet: bool = False,
    ) -> Task | None:
        """Vazifani boshlaydi; shu `key` bilan vazifa ishlayotgan bo'lsa None (takror rad etildi)."""
        if key is not None and self.running(key):
            return None
        task = Task(title, key, cancellable, quiet)
        if self.inline:
            try:
                result = fn(TaskContext(task))
            except Cancelled:
                return task
            except Exception as e:
                if on_error is None:
                    raise
                on_error(e)
                return task
            if on_done is not None:
                on_done(result)
            return task
        self._active.append(task)
        threading.Thread(
            target=self._work, args=(task, fn, on_done, on_error), name=f"sath:{title}", daemon=True
        ).start()
        return task

    def _work(self, task: Task, fn, on_done, on_error) -> None:
        try:
            result = fn(TaskContext(task))
        except BaseException as e:  # noqa: BLE001 — asosiy oqimga yetkaziladi
            self._q.put((task, None, on_error, None, e))
            return
        self._q.put((task, on_done, None, result, None))

    def pump(self) -> int:
        """Asosiy oqimda: tugagan vazifalarning callbacklarini chaqiradi. Qaytaradi: nechta vazifa yakunlandi."""
        n = 0
        while True:
            try:
                task, on_done, on_error, result, exc = self._q.get_nowait()
            except queue.Empty:
                return n
            n += 1
            if task in self._active:
                self._active.remove(task)
            if task.cancelled or isinstance(exc, Cancelled):
                continue
            try:
                if exc is not None:
                    if on_error is not None:
                        on_error(exc)
                    else:
                        self.on_error_default(task, exc)
                elif on_done is not None:
                    on_done(result)
            except Exception as cb_exc:  # noqa: BLE001 — bitta callback xatosi pompani to'xtatmasin
                self.on_error_default(task, cb_exc)

    def running(self, key: str) -> bool:
        return any(t.key == key for t in self._active)

    def active(self) -> list[Task]:
        return list(self._active)

    def cancel(self, task_id: int) -> bool:
        for t in self._active:
            if t.id == task_id and t.cancellable:
                t.cancel()
                return True
        return False

    def cancel_all(self) -> None:
        for t in self._active:
            t.cancel()

    def drain(self, timeout: float = 30.0) -> None:
        """Barcha vazifalar tugaguncha pompalaydi (headless testlar: -b da timerlar ishlamaydi)."""
        deadline = time.monotonic() + timeout
        while self._active:
            self.pump()
            if time.monotonic() > deadline:
                raise TimeoutError(f"vazifalar tugamadi: {[t.title for t in self._active]}")
            time.sleep(0.01)
        self.pump()


TASKS = TaskManager()
```

- [ ] **Step 4: Testlar o'tishini tekshiring**

Run: `pytest -q desktop/tests/test_sath_tasks.py`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add desktop/blender/sath/core/__init__.py desktop/blender/sath/core/tasks.py desktop/tests/test_sath_tasks.py
git commit -m "feat(K3): core.tasks — daemon oqimda ish, natija asosiy oqimda, kalit bo'yicha takror rad, bekor qilish, inline rejim"
```

---

### Task 6: `core/events.py` — hodisalar shinasi

P3 modullari va 2-quyi-loyiha (WebSocket push) shu shinaga ulanadi. Hozir `session.login/logout` va `ifc.loaded` e'lon qilinadi.

**Files:**
- Create: `desktop/blender/sath/core/events.py`
- Test: `desktop/tests/test_sath_events.py`

**Interfaces:**
- Produces (`sath.core.events`): `subscribe(topic: str, fn: Callable[[dict], None]) -> Callable[[], None]` (obunani bekor qiluvchi funksiya qaytaradi), `publish(topic: str, **payload) -> None`, `clear() -> None`. Mavzular: `"session.login"`, `"session.logout"`, `"ifc.loaded"`. Faqat asosiy oqimdan chaqiriladi.

- [ ] **Step 1: Yiqiluvchi test**

```python
"""core.events: obuna, e'lon, obunani bekor qilish, bitta obunachi xatosi boshqalarni to'xtatmaydi."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import events  # noqa: E402


def test_publish_subscribe_unsubscribe():
    events.clear()
    got = []
    off = events.subscribe("ifc.loaded", lambda p: got.append(p))
    events.publish("ifc.loaded", path="a.ifc")
    off()
    events.publish("ifc.loaded", path="b.ifc")
    assert got == [{"path": "a.ifc"}]


def test_failing_subscriber_does_not_block_others(capsys):
    events.clear()
    got = []
    events.subscribe("session.login", lambda p: 1 / 0)
    events.subscribe("session.login", lambda p: got.append(p["user"]))
    events.publish("session.login", user="admin")
    assert got == ["admin"]
    assert "session.login" in capsys.readouterr().out
```

- [ ] **Step 2: Yiqilishini tekshiring**

Run: `pytest -q desktop/tests/test_sath_events.py`
Expected: FAIL (`ImportError: cannot import name 'events'`)

- [ ] **Step 3: `core/events.py`**

```python
"""Hodisalar shinasi (asosiy oqim): modullar bir-birini import qilmasdan xabar almashadi.

Mavzular: session.login {user}, session.logout {}, ifc.loaded {path}. 2-quyi-loyihada scada.snapshot qo'shiladi.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable

_subs: dict[str, list[Callable[[dict], None]]] = {}


def subscribe(topic: str, fn: Callable[[dict], None]) -> Callable[[], None]:
    _subs.setdefault(topic, []).append(fn)

    def off() -> None:
        lst = _subs.get(topic, [])
        if fn in lst:
            lst.remove(fn)

    return off


def publish(topic: str, **payload) -> None:
    for fn in list(_subs.get(topic, [])):
        try:
            fn(payload)
        except Exception:  # noqa: BLE001 — bitta obunachi boshqalarni to'xtatmasin
            print(f"[sath] hodisa {topic}: obunachi xatosi", flush=True)
            traceback.print_exc()


def clear() -> None:
    _subs.clear()
```

- [ ] **Step 4: O'tishini tekshiring**

Run: `pytest -q desktop/tests/test_sath_events.py`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add desktop/blender/sath/core/events.py desktop/tests/test_sath_events.py
git commit -m "feat(K3): core.events — modullar orasida hodisalar shinasi (session.login/logout, ifc.loaded)"
```

---

### Task 7: Blender ulagichi — `core/ui_tasks.py`, sessiya epoch, `tasks_async` testi

**Files:**
- Create: `desktop/blender/sath/core/ui_tasks.py`
- Modify: `desktop/blender/sath/session.py` (to'liq almashtiriladi — quyida)
- Modify: `desktop/blender/sath/ifc.py:33-38` (`load`)
- Modify: `desktop/blender/sath/__init__.py` (`ui_tasks` ni `MODULES` boshiga)
- Create: `desktop/tests/sath_tests/tasks_async.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`@("tasks_async", "")` ni `smoke` dan keyin)

**Interfaces:**
- Consumes: Task 5 `TASKS`, `Task`, `TaskContext`; Task 6 `events.publish`.
- Produces:
  - `session.connect_client(server: str, username: str, password: str, otp: str = "") -> tuple[GesClient, dict]` (ishchi oqim uchun, bpy siz)
  - `session.set_session(client: GesClient, user: dict) -> None`, `session.remember(server: str, username: str) -> None` (asosiy oqim), `session.epoch() -> int`, `session.bump_epoch() -> None`; `login()`/`logout()` saqlanadi.
  - `ui_tasks.run_op(op, title: str, work: Callable[[TaskContext], Any], apply: Callable[[Any], None] | None = None, *, key: str | None = None, fail: Callable[[BaseException], str | None] | None = None) -> set[str]`
  - `ui_tasks.ensure_pump() -> None`, `ui_tasks.show_error(title: str, msg: str) -> None`, `ui_tasks.EXPECTED: tuple[type[BaseException], ...]`
  - Operator `sath.task_cancel` (`task_id: IntProperty`)

- [ ] **Step 1: Yiqiluvchi headless test `tasks_async.py`**

```python
"""K3: asinxron yo'l (fon rejimida majburan): operator darhol qaytadi, natija asosiy oqimda, epoch eski natijani
tashlaydi, pompa timer Bonsai read_homefile dan omon qoladi, unregister uzoq vazifada osilmaydi."""

import threading
import time

import bpy


def run(ctx):
    from sath import session
    from sath.core import ui_tasks
    from sath.core.tasks import TASKS

    assert TASKS.inline is True  # -b da default sinxron (boshqa headless testlar uchun)
    TASKS.inline = False
    try:
        # 1) asosiy oqimda apply
        seen = {}

        class Op:
            def report(self, level, msg):
                seen["report"] = (level, msg)

        t0 = time.perf_counter()
        r = ui_tasks.run_op(Op(), "sekin", lambda c: (time.sleep(0.3), 5)[1], lambda v: seen.update(v=v, th=threading.current_thread()), key="t.slow")
        assert r == {"FINISHED"} and time.perf_counter() - t0 < 0.1
        assert ui_tasks.run_op(Op(), "sekin", lambda c: 1, key="t.slow") == {"CANCELLED"}  # takror rad
        assert "allaqachon" in seen["report"][1]
        assert bpy.app.timers.is_registered(ui_tasks._pump)
        TASKS.drain(5)
        assert seen["v"] == 5 and seen["th"] is threading.main_thread()

        # 2) epoch: vazifa davomida sessiya almashsa natija qo'llanmaydi
        applied = []
        ui_tasks.run_op(Op(), "eski", lambda c: (time.sleep(0.2), 1)[1], applied.append)
        session.bump_epoch()
        TASKS.drain(5)
        assert applied == []
        assert "eskirdi" in bpy.context.scene.ges.status

        # 3) xato → scene.ges.status (fon rejimida popup yo'q)
        def boom(c):
            raise RuntimeError("server yiqildi")

        ui_tasks.run_op(Op(), "Farq", boom)
        TASKS.drain(5)
        assert "Farq: server yiqildi" in bpy.context.scene.ges.status

        # 4) persistent pompa: read_homefile dan keyin ham ro'yxatda
        ui_tasks.run_op(Op(), "uzun", lambda c: c.sleep(0.5))
        bpy.ops.wm.read_homefile(app_template="")
        assert bpy.app.timers.is_registered(ui_tasks._pump)
        TASKS.drain(5)

        # 5) unregister uzoq vazifada osilmaydi (bekor qilinadi)
        ui_tasks.run_op(Op(), "juda uzun", lambda c: [c.sleep(1) for _ in range(60)])
        t0 = time.perf_counter()
        ui_tasks.unregister()
        assert time.perf_counter() - t0 < 1.0
        TASKS.drain(5)
        ui_tasks.register()
    finally:
        TASKS.inline = True
```

`run_blender_tests.ps1` ro'yxatiga `@("tasks_async", "")` qo'shing.

- [ ] **Step 2: Yiqilishini tekshiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test tasks_async 2>&1 | Select-String "OK|FAIL|Error"`
Expected: `[FAIL] tasks_async` (`ModuleNotFoundError: sath.core.ui_tasks`)

- [ ] **Step 3: `session.py` ni almashtiring**

```python
"""Server sessiyasi: GesClient + token xotirada; server/login prefs da saqlanadi.

K3: `connect_client` ishchi oqimda (bpy siz), `set_session`/`remember` asosiy oqimda. `epoch` sessiya yoki ochiq
model almashganda oshadi — fon vazifasining eskirgan natijasi yangi sahnaga yozilmaydi (core/ui_tasks.run_op).
"""

from __future__ import annotations

from .shared.server_client import GesClient

_client: GesClient | None = None
_user: dict | None = None
_epoch = 0


def epoch() -> int:
    return _epoch


def bump_epoch() -> None:
    global _epoch
    _epoch += 1


def connect_client(server: str, username: str, password: str, otp: str = "") -> tuple[GesClient, dict]:
    """Tarmoq qismi (ishchi oqim uchun xavfsiz): login + me. Global holatga tegmaydi."""
    c = GesClient(server)
    c.login(username, password, otp)
    return c, c.me()


def set_session(client: GesClient, user: dict) -> None:
    global _client, _user
    _client, _user = client, user
    bump_epoch()
    from .core import events

    events.publish("session.login", user=user)


def remember(server: str, username: str) -> None:
    """Asosiy oqim: server va login prefs ga (parol hech qachon saqlanmaydi)."""
    from .prefs import prefs

    p = prefs()
    p.server, p.username = server, username


def login(server: str, username: str, password: str, otp: str = "") -> dict:
    """Sinxron login (testlar va skriptlar uchun)."""
    c, u = connect_client(server, username, password, otp)
    set_session(c, u)
    remember(server, username)
    return u


def logout() -> None:
    global _client, _user
    _client = None
    _user = None
    bump_epoch()
    from .core import events

    events.publish("session.logout")


def client() -> GesClient:
    if _client is None:
        raise RuntimeError("Avval serverga kiring (Sath → Server → Ulanish)")
    return _client


def user() -> dict | None:
    return _user


def is_logged_in() -> bool:
    return _client is not None
```

- [ ] **Step 4: `ifc.load` — epoch va hodisa**

```python
def load(path: Path) -> bool:
    """IFC ni Bonsai da ochadi. Loyiha allaqachon ochiq bo'lsa Bonsai yangi sessiya (read_homefile) boshlaydi —
    Scene.ges yo'qoladi; chaqiruvchi props.snapshot/restore qilsin. Qaytaradi: sessiya yangilandimi.
    K3: epoch oshadi (oldingi model uchun boshlangan fon vazifalari natijasi tashlanadi), `ifc.loaded` e'lon qilinadi."""
    from . import session
    from .core import events

    fresh = file() is not None
    bpy.ops.bim.load_project(filepath=str(path), should_start_fresh_session=fresh)
    session.bump_epoch()
    events.publish("ifc.loaded", path=str(path))
    return fresh
```

- [ ] **Step 5: `core/ui_tasks.py`**

```python
"""Fon vazifalarining Blender ulagichi (K3): pompa timer (0.1 s, persistent), status bar progressi va bekor qilish,
operatorlar uchun `run_op`. Fon rejimida (blender -b) TASKS.inline — hammasi sinxron, xato op.report ga.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import bpy

from .. import session
from ..shared.server_client import ServerError, TransferCancelled
from .tasks import TASKS, Task, TaskContext

PUMP_INTERVAL = 0.1
EXPECTED: tuple[type[BaseException], ...] = (ServerError, RuntimeError)
MAX_SHOWN = 3


def _msg(e: BaseException) -> str:
    return str(getattr(e, "message", None) or e)


def _scene_ges():
    sc = getattr(bpy.context, "scene", None)
    return getattr(sc, "ges", None) if sc is not None else None


def status(text: str) -> None:
    g = _scene_ges()
    if g is not None:
        g.status = text


def show_error(title: str, msg: str) -> None:
    """Asosiy oqim: holat qatori + konsol + (GUI da) popup. Operator allaqachon tugagan — report ishlamaydi."""
    status(f"✖ {title}: {msg}")
    print(f"[sath] {title}: {msg}", flush=True)
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None or not wm.windows:
        return

    def draw(self, _context):
        for line in msg.splitlines()[:8]:
            self.layout.label(text=line)

    with bpy.context.temp_override(window=wm.windows[0]):
        wm.popup_menu(draw, title=title, icon="ERROR")


def _default_error(task: Task, exc: BaseException) -> None:
    if not isinstance(exc, EXPECTED):
        import traceback

        traceback.print_exception(type(exc), exc, exc.__traceback__)
    show_error(task.title, _msg(exc))


def _redraw_statusbar() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == "STATUSBAR":
                area.tag_redraw()


def _pump():
    TASKS.pump()
    _redraw_statusbar()
    return PUMP_INTERVAL if TASKS.active() else None


def ensure_pump() -> None:
    if not TASKS.inline and not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, first_interval=PUMP_INTERVAL, persistent=True)


def run_op(
    op,
    title: str,
    work: Callable[[TaskContext], Any],
    apply: Callable[[Any], None] | None = None,
    *,
    key: str | None = None,
    fail: Callable[[BaseException], str | None] | None = None,
) -> set[str]:
    """Operator ishini fon vazifasiga aylantiradi.

    work(ctx) — ishchi oqimda, bpy ga TEGMAYDI; apply(natija) — asosiy oqimda.
    fail(xato) — asosiy oqimda holatni yozadi va ko'rsatiladigan matnni qaytaradi (None → xato matni).
    Sessiya/model almashgan bo'lsa (epoch) natija qo'llanmaydi."""
    ep = session.epoch()

    def done(result) -> None:
        if session.epoch() != ep:
            status(f"{title}: natija eskirdi (sessiya yoki model almashdi) — qayta bajaring")
            return
        if apply is not None:
            apply(result)

    def error(e: BaseException) -> None:
        if isinstance(e, TransferCancelled):
            return
        msg = (fail(e) if fail is not None else None) or _msg(e)
        show_error(title, msg)

    if TASKS.inline:
        try:
            TASKS.run(title, work, done, key=key)
        except EXPECTED as e:
            op.report({"ERROR"}, (fail(e) if fail is not None else None) or _msg(e))
            return {"CANCELLED"}
        return {"FINISHED"}
    task = TASKS.run(title, work, done, error, key=key)
    if task is None:
        op.report({"WARNING"}, f"{title}: allaqachon bajarilmoqda")
        return {"CANCELLED"}
    ensure_pump()
    return {"FINISHED"}


def draw_tasks(self, _context) -> None:
    shown = [t for t in TASKS.active() if not t.quiet][:MAX_SHOWN]
    for t in shown:
        row = self.layout.row(align=True)
        text = t.title + (f" — {t.text}" if t.text else "")
        if t.frac is None:
            row.label(text=text, icon="SORTTIME")
        else:
            row.progress(factor=t.frac, type="BAR", text=text)
        if t.cancellable:
            row.operator("sath.task_cancel", text="", icon="X", emboss=False).task_id = t.id


class SATH_OT_task_cancel(bpy.types.Operator):
    """Fon vazifasini bekor qilish (natija tashlanadi)"""

    bl_idname = "sath.task_cancel"
    bl_label = "Bekor qilish"
    task_id: bpy.props.IntProperty()

    def execute(self, context):
        return {"FINISHED"} if TASKS.cancel(self.task_id) else {"CANCELLED"}


def register():
    TASKS.inline = bpy.app.background
    TASKS.on_error_default = _default_error
    bpy.utils.register_class(SATH_OT_task_cancel)
    bpy.types.STATUSBAR_HT_header.prepend(draw_tasks)


def unregister():
    TASKS.cancel_all()
    bpy.types.STATUSBAR_HT_header.remove(draw_tasks)
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
    bpy.utils.unregister_class(SATH_OT_task_cancel)
```

`status()` dagi `g.status` — `GesScene.status` (`props.py:66`) mavjud maydon.

- [ ] **Step 6: `__init__.py` — ulagichni ro'yxatga oling**

`from . import (...)` ichiga `ui_tasks` emas, alohida qator: `from .core import ui_tasks` (importlar blokidan keyin) va `MODULES = [ui_tasks, prefs, props, ...]` (birinchi bo'lib — boshqa modullar register da inline bayroqqa tayanadi).

- [ ] **Step 7: O'tishini va qolgan to'plamni tekshiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test tasks_async 2>&1 | Select-String "OK|FAIL|Error"` → `[OK] tasks_async`
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0`
Run: `pytest -q desktop/tests` → PASS

- [ ] **Step 8: Commit**

```bash
git add desktop/blender/sath/core/ui_tasks.py desktop/blender/sath/session.py desktop/blender/sath/ifc.py desktop/blender/sath/__init__.py desktop/tests/sath_tests/tasks_async.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(K3): fon vazifalarining Blender ulagichi — persistent pompa, status bar progressi va bekor qilish, run_op, sessiya epoch"
```

---

### Task 8: Server operatorlari — connect, open_version, pull_head, commit, download_update

**Files:**
- Modify: `desktop/blender/sath/ops_server.py` (`SATH_OT_connect.execute`, `SATH_OT_download_update.execute`, `SATH_OT_open_version.execute`, `SATH_OT_pull_head.execute`, `SATH_OT_commit.execute`)
- Modify: `desktop/blender/sath/flows.py:65-68` (`download_version` ga `progress`, `cancelled`)
- Modify: `desktop/blender/sath/update.py:201-218` (har qanday istisnoda `.part` o'chirilsin)
- Create: `desktop/tests/sath_tests/fake_server.py`, `desktop/tests/sath_tests/ops_async.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`@("ops_async", "--bonsai")`)

**Interfaces:**
- Consumes: Task 4 `GesClient.download_version(..., progress, cancelled)`; Task 7 `run_op`, `session.connect_client/set_session/remember`.
- Produces: `flows.download_version(client, model: dict, version: dict, progress=None, cancelled=None) -> Path`; `fake_server.serve(routes: dict[tuple[str, str], Callable[[], tuple[int, bytes]]]) -> tuple[str, Callable[[], None]]` (base_url, stop).

- [ ] **Step 1: Soxta server yordamchisi `fake_server.py`**

```python
"""Headless testlar uchun soxta Sath serveri (stdlib http.server, alohida oqim). Marshrut → (status, body) funksiyasi;
`?` dan keyingi qism e'tiborga olinmaydi. Kechikish funksiya ichida time.sleep bilan."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def js(obj, status: int = 200):
    return lambda: (status, json.dumps(obj).encode())


def serve(routes: dict) -> tuple[str, callable]:
    class H(BaseHTTPRequestHandler):
        def _go(self):
            fn = routes.get((self.command, self.path.split("?")[0]))
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            status, body = fn() if fn else (404, b'{"detail": "yo\'q"}')
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _go

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv.shutdown
```

- [ ] **Step 2: Yiqiluvchi test `ops_async.py` (connect va open_version)**

```python
"""K3: server operatorlari asinxron — sekin serverda operator darhol qaytadi, natija pompadan keyin sahnada."""

import time
from pathlib import Path

import bpy
from fake_server import js, serve

SLOW = 0.6


def slow(obj):
    def f():
        time.sleep(SLOW)
        return js(obj)()

    return f


def run(ctx):
    from sath import props
    from sath.core.tasks import TASKS
    from sath.prefs import prefs

    sample = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"
    ifc_bytes = sample.read_bytes()
    url, stop = serve({
        ("POST", "/api/auth/login"): slow({"access_token": "t", "refresh_token": "r"}),
        ("GET", "/api/auth/me"): js({"id": 1, "username": "admin"}),
        ("GET", "/api/desktop/latest"): js({"detail": "yo'q"}, 404),
        ("GET", "/api/notifications"): js([]),
        ("GET", "/api/projects"): js([{"id": 7, "name": "P", "my_role": "engineer"}]),
        ("GET", "/api/projects/7/models"): js([{"id": 3, "name": "M"}]),
        ("GET", "/api/models/3/versions"): js([{"id": 11, "number": 1, "state": "wip", "message": "", "author_username": "a"}]),
        ("GET", "/api/versions/11/file"): lambda: (time.sleep(SLOW), (200, ifc_bytes))[1],
        ("GET", "/api/versions/11/diff"): slow({"added": [], "changed": [], "deleted": [], "summary": {"added": 0, "changed": 0, "deleted": 0}}),
        ("POST", "/api/models/3/sim/safety-check"): slow({"scenarios": [], "ok": True}),
    })  # fmt: skip
    TASKS.inline = False
    try:
        s = bpy.context.scene.ges
        prefs().server, prefs().username = url, "admin"
        bpy.context.window_manager.sath_secret.password = "x"

        t0 = time.perf_counter()
        assert bpy.ops.sath.connect() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "connect bloklayapti"
        assert bpy.context.window_manager.sath_secret.password == ""  # parol darhol tozalanadi
        TASKS.drain(10)
        assert "admin sifatida kirildi" in s.status, s.status
        assert len(s.projects) == 1

        props.fill(s.models, [{"item_id": 3, "name": "M"}])
        s.models_index = 0
        props.fill(s.versions, [{"item_id": 11, "number": 1, "name": "v1"}])
        s.versions_index = 0
        t0 = time.perf_counter()
        assert bpy.ops.sath.open_version() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "open_version bloklayapti"
        TASKS.drain(20)
        s = bpy.context.scene.ges
        assert s.version_id == 11 and "v1 ochildi" in s.status, s.status
    finally:
        TASKS.inline = True
        stop()
```

`props.fill` qabul qiladigan kalitlar `props.py` dagi `GesItem` maydonlari bilan mos kelishini tekshiring (`item_id`, `name`, `number`, …) — mos kelmasa, mavjud `flows.version_rows` chiqishini namuna qiling.

`run_blender_tests.ps1` ga `@("ops_async", "--bonsai")` qo'shing.

- [ ] **Step 3: Yiqilishini tekshiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test ops_async --bonsai 2>&1 | Select-String "OK|FAIL|Error|bloklayapti"`
Expected: `AssertionError: connect bloklayapti`

- [ ] **Step 4: `flows.download_version`**

```python
def download_version(client: GesClient, model: dict, version: dict, progress=None, cancelled=None) -> Path:
    dest = cache_dir() / f"m{model['id']}_v{version['number']}.ifc"
    client.download_version(version["id"], dest, progress=progress, cancelled=cancelled)
    return dest
```

- [ ] **Step 5: `ops_server.py` — importlar va `connect`**

Importlarga: `from .core.ui_tasks import run_op`. `guard` saqlanadi (sinxron operatorlar uchun).

```python
    def execute(self, context):
        p, sec = prefs(), props.secret(context)
        server, username, password, otp = p.server, p.username, sec.password, sec.otp
        sec.password = ""  # CODE-05: parol/MFA kodi xotirada qolmaydi — ish boshlanishidan oldin tozalanadi
        sec.otp = ""

        def work(ctx):
            c, u = session.connect_client(server, username, password, otp)
            pkg = flows.newer_package(c, flows.ADDON_VERSION)
            note = flows.check_update(c, flows.ADDON_VERSION) if pkg else None
            return c, u, pkg, note, flows.unread_summary(c), flows.project_rows(c)

        def apply(res):
            c, u, pkg, note, unread, rows = res
            session.set_session(c, u)
            session.remember(server, username)
            s = bpy.context.scene.ges
            s.status = f"{u['username']} sifatida kirildi" + (f" · {unread}" if unread else "")
            s.update_version = pkg["version"] if pkg else ""
            if note:
                s.status += f" · {note}"
            props.fill(s.projects, rows)
            s.projects_index = 0 if len(s.projects) else -1  # update → modellar

        return run_op(self, "Ulanish", work, apply, key="server.connect")
```

Eslatma: `set_session` epoch ni oshiradi — `apply` ichida, `done` ning epoch tekshiruvidan keyin, shuning uchun o'z natijasini tashlamaydi. `s.projects_index = 0` update callbacki `bpy.ops.sath.refresh_models()` ni chaqiradi — u hozircha sinxron (qisqa so'rov), Task doirasidan tashqarida.

- [ ] **Step 6: `open_version`**

```python
    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        m = _sel(s.models, s.models_index)
        v = _sel(s.versions, s.versions_index)
        info = {
            "project_id": p.item_id if p else 0, "model_id": m.item_id, "version_id": v.item_id,
            "version_number": v.number, "model_name": m.name,
            "status": f"{p.name if p else ''} — {m.name} v{v.number} ochildi",
        }  # fmt: skip
        model, version = {"id": m.item_id}, {"id": v.item_id, "number": v.number}

        def work(ctx):
            return flows.download_version(
                session.client(), model, version,
                progress=lambda got, total: ctx.progress(got / total if total else None, f"{got / 2**20:.1f} MB"),
                cancelled=lambda: ctx.cancelled,
            )  # fmt: skip

        def apply(path):
            snap = props.snapshot(bpy.context.scene.ges)  # Bonsai fresh session sahnani almashtiradi
            if ifc.load(path):
                props.restore(bpy.context.scene.ges, snap)
            sc = bpy.context.scene.ges
            for k, val in info.items():
                setattr(sc, k, val)

        return run_op(self, f"v{v.number} ni ochish", work, apply, key="server.open")
```

(`p` `None` bo'lishi mumkin bo'lgan holatni ham qamrab oladi — avval `p.item_id` da `AttributeError` bo'lardi.)

- [ ] **Step 7: `pull_head`**

```python
    def execute(self, context):
        import time

        s = context.scene.ges
        model_id, head_id = s.model_id, s.head_conflict_id
        backup = None
        if ifc.file() is not None:  # lokal o'zgarishlar yo'qolmasin (bpy — asosiy oqimda, ishdan oldin)
            backup = ifc.save(flows.cache_dir() / f"lokal_m{model_id}_{time.strftime('%Y%m%d_%H%M%S')}.ifc")

        def work(ctx):
            c = session.client()
            versions = c.versions(model_id)
            head = next((v for v in versions if v["id"] == head_id), None) if head_id else None
            head = head or max(versions, key=lambda v: v["number"])
            path = flows.download_version(
                c, {"id": model_id}, {"id": head["id"], "number": head["number"]}, cancelled=lambda: ctx.cancelled
            )
            return head, path

        def apply(res):
            head, path = res
            snap = props.snapshot(bpy.context.scene.ges)
            if ifc.load(path):
                props.restore(bpy.context.scene.ges, snap)
            sc = bpy.context.scene.ges
            sc.version_id, sc.version_number, sc.head_conflict_id = head["id"], head["number"], -1
            sc.status = f"v{head['number']} ochildi" + (f"; lokal nusxa: {backup}" if backup else "")
            bpy.ops.sath.refresh_versions()

        return run_op(self, "Eng oxirgi versiya", work, apply, key="server.open")
```

- [ ] **Step 8: `commit` (`execute` ni almashtiring; `invoke`/`draw` o'zgarmaydi)**

```python
    def execute(self, context):
        s = context.scene.ges
        from . import ges_objects

        try:  # bpy qismi (IFC ga yozish) — asosiy oqimda, yuborishdan oldin
            ges_objects.flush_pending()  # kechiktirilgan qayta qurishlar IFC ga kirsin
            if self.assign_missing:
                from .ops_import import assign_imported

                assign_imported([bpy.data.objects[n] for n in unassigned(context) if n in bpy.data.objects])
            ifc.stamp_guids()  # sath_guid — Blender dan FBX/glTF eksportida GUID saqlansin (CAD-07)
            path = ifc.save(flows.cache_dir() / f"commit_m{s.model_id}.ifc")
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        model_id, message, parent, submit = s.model_id, s.commit_message.strip(), s.version_id or None, s.submit_after_commit

        def work(ctx):
            return flows.commit(session.client(), model_id, path, message, parent, submit)

        def apply(r):
            sc = bpy.context.scene.ges
            sc.head_conflict_id = -1
            v = r["version"]
            sc.version_id, sc.version_number = v["id"], v["number"]
            sc.status = f"v{v['number']} yuklandi" + (" va tasdiqqa yuborildi" if r["cr"] else "")
            sc.commit_message = ""
            bpy.ops.sath.refresh_versions()

        def fail(e):
            head = flows.head_conflict(e) if isinstance(e, ServerError) else None
            if head is None:
                return None
            # VCS-01: ota versiya eskirgan — jimgina «vilka» qilinmaydi; foydalanuvchi eng oxirgisini oladi
            sc = bpy.context.scene.ges
            sc.head_conflict_id = head
            sc.status = flows.conflict_text(e)
            return sc.status

        return run_op(self, "Commit", work, apply, key="server.commit", fail=fail)
```

- [ ] **Step 9: `download_update` va `update.py` tozalash**

`update.py` dagi `except OSError as e:` blokidan keyin qo'shing:

```python
    except BaseException:
        part.unlink(missing_ok=True)  # K3: bekor qilish (TransferCancelled/Cancelled) ham .part qoldirmaydi
        raise
```

`SATH_OT_download_update.execute`:

```python
    def execute(self, context):
        kind, pubkey = self.kind, prefs().update_public_key
        dest_dir = flows.cache_dir() / "updates"

        def work(ctx):
            # SEC-03: paket brauzerda ochilmaydi — addon o'zi yuklab, hajm/sha256/imzoni tekshiradi
            client = session.client()
            latest = update.latest(client)
            if not latest:
                raise RuntimeError("Serverda desktop paketi yo'q")
            pkg = next((f for f in latest.get("files", []) if f["kind"] == kind), None)
            if pkg is None:
                raise RuntimeError(f"Serverda {kind} paketi yo'q")

            def prog(got, total):
                ctx.check()
                ctx.progress(got / total if total else None, f"{got / 2**20:.0f} MB")

            try:
                return update.download_and_verify(client, pkg, dest_dir, pubkey, progress=prog)
            except update.UpdateError as e:
                raise RuntimeError(str(e)) from None

        def apply(path):
            bpy.ops.wm.path_open(filepath=str(path.parent))
            signed = "imzo ✓" if pubkey.strip() else "imzo tekshirilmadi (kalit sozlanmagan)"
            bpy.context.scene.ges.status = f"Tekshirildi (hajm, sha256 ✓, {signed}): {path.name} — o'rnatish uchun ishga tushiring"

        return run_op(self, "Yangilanish", work, apply, key="server.update")
```

- [ ] **Step 10: Testlar**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test ops_async --bonsai 2>&1 | Select-String "OK|FAIL|Error"` → `[OK] ops_async`
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0` (`server_ops`, `secret_ops` inline rejimda o'zgarmagan)
Run: `pytest -q desktop/tests/test_update_verify.py desktop/tests/test_sath_flows.py` → PASS

Server mavjud bo'lsa (`.\desktop\tests\start_dev_server.ps1`, keyin `$env:GES_TEST_SERVER="http://127.0.0.1:8000"`): `.\desktop\tests\run_blender_tests.ps1` → `e2e_server`, `commit_conflict` OK.

- [ ] **Step 11: Commit**

```bash
git add desktop/blender/sath/ops_server.py desktop/blender/sath/flows.py desktop/blender/sath/update.py desktop/tests/sath_tests/fake_server.py desktop/tests/sath_tests/ops_async.py desktop/tests/run_blender_tests.ps1
git commit -m "fix(K3): ulanish, versiya ochish, eng oxirgi versiya, commit va yangilanish fon vazifasida — Blender qotmaydi, progress va bekor qilish"
```

---

### Task 9: Taqriz, simulyatsiya, egizak va monitoring operatorlari

**Files:**
- Modify: `desktop/blender/sath/ops_review.py` (`SATH_OT_diff.execute`)
- Modify: `desktop/blender/sath/ops_sim.py` (`SATH_OT_sim_catalog.execute`, `_poll_factory` → `wait_job`, `SATH_OT_sim_run.execute`, `SATH_OT_safety_check.execute`)
- Modify: `desktop/blender/sath/ops_twin.py:153-168` (`_TwinSim.execute`)
- Modify: `desktop/blender/sath/ops_monitor.py` (`_tick`, `_level_at` o'chiriladi, `SATH_OT_monitor_toggle.execute`)
- Modify: `desktop/tests/sath_tests/ops_async.py` (diff va safety_check qismi)
- Modify: `desktop/tests/sath_tests/sim_hydro.py:36-40`, `sim_twin.py:17-22` va `_wait(...)` chaqiruvlari, `gui_twin.py:29-34`

**Interfaces:**
- Consumes: Task 7 `run_op`, `TASKS`, `ensure_pump`, `TaskContext.sleep/progress`.
- Produces: `ops_sim.wait_job(meta: dict, job_id: int, on_done: Callable[[dict], None] | None = None, title: str = "Simulyatsiya") -> Task | None` — ishchi oqimda 0.6 s oralig'ida so'raydi; asosiy oqimda `sim_results`, `sim_water_level`, `sim_status` ni yozadi va `on_done(result)` ni chaqiradi. `_poll_factory` o'chiriladi.

- [ ] **Step 1: `ops_async.py` ga diff va safety_check tekshiruvini qo'shing (open_version qismidan keyin, `finally` dan oldin)**

```python
        s = bpy.context.scene.ges
        t0 = time.perf_counter()
        assert bpy.ops.sath.diff() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "diff bloklayapti"
        try:  # Review Focus 1: takror bosish rad etiladi
            bpy.ops.sath.diff()
        except RuntimeError:
            pass  # -b da WARNING report RuntimeError emas; CANCELLED qaytishi kifoya
        assert sum(1 for t in TASKS.active() if t.key == "review.diff") == 1
        TASKS.drain(10)
        assert "v1:" in bpy.context.scene.ges.diff_note, bpy.context.scene.ges.diff_note

        s = bpy.context.scene.ges
        s.model_id = 3
        t0 = time.perf_counter()
        assert bpy.ops.sath.safety_check() == {"FINISHED"}
        assert time.perf_counter() - t0 < SLOW / 2, "safety_check bloklayapti"
        TASKS.drain(10)
```

`flows.safety_rows(res)` soxta javob `{"scenarios": [], "ok": True}` ni qabul qilishini tekshiring (`flows.py` dagi funksiya); qabul qilmasa, javobni u kutayotgan kalitlar bilan to'ldiring.

- [ ] **Step 2: Yiqilishini tekshiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test ops_async --bonsai 2>&1 | Select-String "OK|FAIL|bloklayapti"`
Expected: `diff bloklayapti`

- [ ] **Step 3: `ops_review.py` — diff**

Importlarga `from .core.ui_tasks import run_op`.

```python
    def execute(self, context):
        s = context.scene.ges
        v = _sel(s.versions, s.versions_index)
        vid, vnum = v.item_id, v.number

        def apply(d):
            sc = bpy.context.scene.ges
            ifc.DIFF_STATE.restore()
            colors, text = flows.diff_colors(d)
            n = ifc.DIFF_STATE.paint(colors)
            note = "" if sc.version_id == vid else "(diqqat: boshqa versiya ochiq) "
            sc.diff_note = f"{note}v{vnum}: {text}. 3D da {n} obyekt bo'yaldi."

        return run_op(self, f"v{vnum} farqi", lambda ctx: session.client().diff(vid), apply, key="review.diff")
```

- [ ] **Step 4: `ops_sim.py` — `wait_job`, catalog, sim_run, safety_check**

Importlarga `from .core.tasks import TASKS` va `from .core.ui_tasks import ensure_pump, run_op, show_error`. `_poll_factory` ni o'chirib, o'rniga:

```python
POLL_S = 0.6


def wait_job(meta: dict, job_id: int, on_done=None, title: str = "Simulyatsiya"):
    """Sim ishini ishchi oqimda kutadi (K3; avval timer ichida bloklovchi so'rov edi); natija asosiy oqimda."""

    def work(ctx):
        c = session.client()
        while True:
            j = c.sim_job(job_id)
            if j["status"] == "done":
                return {"ok": True, "result": c.sim_result(job_id)}
            if j["status"] == "failed":
                return {"ok": False, "error": j.get("error") or "hisob xatosi"}
            ctx.progress(None, j["status"])
            ctx.sleep(POLL_S)

    def apply(res):
        s = bpy.context.scene.ges
        if not res["ok"]:
            s.sim_status = f"Xato: {res['error']}"
            return
        result = res["result"]
        rows, level = flows.sim_result_rows(meta, result)
        props.fill(s.sim_results, rows)
        s.sim_water_level = level if level is not None else -1e9
        s.sim_status = "Tayyor"
        if on_done is not None:
            try:
                on_done(result)
            except Exception as e:  # noqa: BLE001 — animatsiya xatosi natijani yo'qotmasin
                s.sim_status = f"Tayyor (animatsiya xatosi: {e})"

    def error(e):
        bpy.context.scene.ges.sim_status = f"Xato: {e}"
        show_error(title, str(e))

    task = TASKS.run(title, work, apply, error, key=f"sim.job.{job_id}")
    ensure_pump()
    return task
```

`SATH_OT_sim_run.execute` oxiridagi `bpy.app.timers.register(_poll_factory(k, job["id"]), first_interval=0.6)` → `wait_job(k, job["id"], title=k["title"])`.

(`create_sim` — qisqa POST, sinxron qoladi; uzoq qism — kutish.)

`SATH_OT_sim_catalog.execute`:

```python
    def execute(self, context):
        def apply(cat):
            global _catalog
            _catalog = cat
            s = bpy.context.scene.ges
            groups = _catalog.get("groups", {})
            rows = [
                {"item_id": i, "name": k["title"], "col2": groups.get(k["group"], k["group"]),
                 "col4": k.get("description", ""), "guid": k["id"]}
                for i, k in enumerate(_catalog["kinds"])
                if not k.get("custom_ui")
            ]  # fmt: skip
            props.fill(s.sim_kinds, rows)
            s.sim_kind_index = 0 if rows else -1  # update → sim_pick

        return run_op(self, "Sim katalogi", lambda ctx: session.client().sim_catalog(), apply, key="sim.catalog")
```

`SATH_OT_safety_check.execute`:

```python
    def execute(self, context):
        s = context.scene.ges
        if not s.model_id:
            self.report({"ERROR"}, "Avval modelni oching")
            return {"CANCELLED"}
        model_id, version_id = s.model_id, s.version_id or None

        def apply(res):
            sc = bpy.context.scene.ges
            head, rows = flows.safety_rows(res)
            sc.safety_head = head
            props.fill(sc.safety_rows, rows)

        return run_op(
            self, "Xavfsizlik tekshiruvi", lambda ctx: session.client().safety_check(model_id, version_id), apply,
            key="sim.safety",
        )  # fmt: skip
```

`guard` importi `ops_sim` da boshqa joyda ishlatilmasa, uni olib tashlang (ruff).

- [ ] **Step 5: `ops_twin.py` — `_TwinSim.execute` oxiri**

```python
        s.sim_job_id = job["id"]
        s.sim_status = "Hisoblanmoqda…"
        animate = self.animate

        def done(result: dict):
            sc = bpy.context.scene.ges  # eski `s` havolasi IFC qayta yuklangandan keyin yaroqsiz bo'lishi mumkin
            sc.twin_note = animate(bpy.context, result, sc)

        ops_sim.wait_job(self.meta, job["id"], done, title=f"{self.title} (egizak)")
        return {"FINISHED"}
```

- [ ] **Step 6: `ops_monitor.py` — `_tick` ni ishchi/asosiy qismlarga ajrating**

`_tick` va `_level_at` ni almashtiring:

```python
def _fetch(project_id: int, model_id: int, hours: float) -> dict:
    """Ishchi oqim (bpy siz): sensorlar, egizak, sog'liq, vaqt mashinasi uchun sath tarixi."""
    c = session.client()
    if not project_id:
        project_id = c.model(model_id)["project_id"]
    out: dict = {"project_id": project_id, "sensors": c.sensors(project_id, model_id), "twin": None, "health": None,
                 "twin_err": None, "level_sensor": None, "level_pts": None, "level_err": None}  # fmt: skip
    try:
        out["twin"] = c.twin(project_id)
        out["health"] = c.plant_health(project_id)
    except (ServerError, RuntimeError, KeyError, TypeError) as e:
        out["twin_err"] = str(e)
    if hours > 0:
        ls = next((x for x in out["sensors"] if x.get("kind") == "level" and x.get("enabled")), None)
        out["level_sensor"] = ls
        if ls is not None:
            try:
                out["level_pts"] = c.readings(ls["id"], hours=hours + 1)
            except ServerError as e:
                out["level_err"] = str(e)
    return out


def _apply(d: dict, hours: float) -> None:
    s = bpy.context.scene.ges
    if not s.monitor_on:
        return
    s.project_id = d["project_id"]
    sensors = d["sensors"]
    alarms = [x for x in sensors if x.get("enabled") and x.get("alarm") != "ok"]
    s.monitor_status = f"{len(sensors)} sensor · {len(alarms)} alarm · yangilanish {INTERVAL:.0f} s"
    sel = s.sensors_index
    props.fill(s.sensors, flows.sensor_rows(sensors))
    s.sensors_index = min(sel, len(s.sensors) - 1)
    health_assets: list[dict] = []
    if d["twin_err"] is None:
        tw, h = d["twin"], d["health"]
        s.twin_head = flows.twin_head(tw)
        props.fill(s.twin_rows, flows.twin_rows(tw))
        props.fill(s.twin_safety, flows.twin_safety_rows(tw.get("safety") or []))
        s.health_head = flows.health_head(h)
        props.fill(s.health_rows, flows.health_rows(h))
        health_assets = h.get("assets", [])
    else:
        s.twin_head = f"Egizak: {d['twin_err']}"
    ifc.ALARM_STATE.restore()
    if s.monitor_color:
        colors = flows.health_colors(health_assets) if s.monitor_color_mode == "health" else flows.alarm_colors(sensors)
        ifc.ALARM_STATE.paint(colors)
    if s.monitor_water:
        lvl = flows.water_sensor_level(sensors) if hours <= 0 else _level_from(d, hours)
        if lvl is not None:
            water.place_water_plane(bpy.context, lvl)


def _level_from(d: dict, hours_ago: float) -> float | None:
    """Vaqt mashinasi: sath sensori tarixidan N soat oldingi qiymat."""
    s = bpy.context.scene.ges
    ls = d["level_sensor"]
    if ls is None:
        s.time_note = "sath sensori yo'q"
        return None
    if d["level_err"] is not None:
        s.time_note = f"tarix xatosi: {d['level_err']}"
        return None
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    v = flows.reading_at(d["level_pts"] or [], ts)
    s.time_note = f"{hours_ago:.1f} soat oldin: {'—' if v is None else f'{v:.2f} m'} ({ls['name']})"
    return v


def _tick():
    s = bpy.context.scene.ges
    if not s.monitor_on or not session.is_logged_in():
        ifc.ALARM_STATE.restore()
        return None
    pid, mid, hours, ep = s.project_id, s.model_id, s.time_hours, session.epoch()

    def apply(d):
        if session.epoch() == ep:
            _apply(d, hours)

    def error(e):
        bpy.context.scene.ges.monitor_status = f"Xato: {e}"

    # K3: tarmoq ishchi oqimda; oldingi tik hali tugamagan bo'lsa bu tik o'tkazib yuboriladi (key)
    TASKS.run("Monitoring", lambda ctx: _fetch(pid, mid, hours), apply, error, key="monitor.tick", cancellable=False, quiet=True)
    ensure_pump()
    return INTERVAL
```

Importlarga `from .core.tasks import TASKS`, `from .core.ui_tasks import ensure_pump`. `SATH_OT_monitor_toggle.execute` dagi sinxron `session.client().model(...)` qatorini olib tashlang (`project_id` endi `_fetch` da aniqlanadi):

```python
    def execute(self, context):
        s = context.scene.ges
        s.monitor_on = not s.monitor_on
        if s.monitor_on:
            if not bpy.app.timers.is_registered(_tick):
                bpy.app.timers.register(_tick, first_interval=0.0)
        else:
            ifc.ALARM_STATE.restore()
            s.monitor_status = ""
        return {"FINISHED"}
```

`unregister` da `_tick` timer ro'yxatdan chiqariladi (mavjud kod) — o'zgarmaydi.

- [ ] **Step 7: Server testlari va `gui_twin` — `_poll_factory` → `wait_job`**

`sim_hydro.py:36-40` blokini almashtiring:

```python
    ops_sim.wait_job(ops_sim.HYDRO_META, job["id"], lambda r: sim_anim.animate_hydro(bpy.context, r, params))
    TASKS.drain(120)
    assert s.sim_status.startswith("Tayyor"), s.sim_status
```

(`from sath.core.tasks import TASKS` ni `run` ichidagi importlarga qo'shing; `time` importi ishlatilmasa olib tashlang.)

`sim_twin.py` dagi `_wait`:

```python
def _wait(start, s, secs=90):
    from sath.core.tasks import TASKS

    start()
    TASKS.drain(secs)
    assert s.sim_status.startswith("Tayyor"), s.sim_status
```

va har bir `_wait(ops_sim._poll_factory(META, job["id"], cb), s)` ni `_wait(lambda: ops_sim.wait_job(META, job["id"], cb), s)` ga almashtiring (5 joy: 51, 71, 89, 105, 121-qatorlar).

`gui_twin.py:29-34`:

```python
    from sath.core.tasks import TASKS

    ops_sim.wait_job(ops_twin.HAMMER_META, job["id"], lambda r: sim_anim.animate_hammer(bpy.context, r, ges_objects.by_role("penstock:1")))
    TASKS.drain(60)  # GUI da asinxron — drain natijani asosiy oqimda qo'llaydi
    assert s.sim_status.startswith("Tayyor"), s.sim_status
```

Qolgan `_poll_factory` chaqiruvi yo'qligini tekshiring: `rg "_poll_factory" desktop` → natija yo'q.

- [ ] **Step 8: To'liq tekshiruv**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test ops_async --bonsai 2>&1 | Select-String "OK|FAIL"` → `[OK] ops_async`
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0`
Run: `pytest -q desktop/tests; ruff check desktop` → PASS, ruff toza
Server bilan (dev server ishlab turganda, `$env:GES_TEST_SERVER`): `.\desktop\tests\run_blender_tests.ps1` → `e2e_server`, `sim_hydro`, `sim_twin` OK.

- [ ] **Step 9: Qo'lda tekshiruv (GUI)**

`Sath.exe` yoki `blender.exe` ni oching, dev serverga ulaning, katta model versiyasida «Ota bilan farq» ni bosing:
- viewport aylantirilganda qayta chiziladi (qotmaydi);
- status barda «vN farqi» va X tugmasi ko'rinadi;
- X bosilganda vazifa yo'qoladi va rang qo'llanmaydi;
- ikkinchi marta bosish «allaqachon bajarilmoqda» deydi.

- [ ] **Step 10: Commit**

```bash
git add desktop/blender/sath/ops_review.py desktop/blender/sath/ops_sim.py desktop/blender/sath/ops_twin.py desktop/blender/sath/ops_monitor.py desktop/tests/sath_tests/ops_async.py desktop/tests/sath_tests/sim_hydro.py desktop/tests/sath_tests/sim_twin.py desktop/tests/sath_tests/gui_twin.py
git commit -m "fix(K3): farq, xavfsizlik tekshiruvi, sim katalogi, sim kutish va monitoring tiki fon vazifasida — timer ichida bloklovchi so'rov qolmadi"
```

---

### Task 10: Hujjat va roadmap

**Files:**
- Modify: `desktop/blender/README.md` (Testlar bo'limi: `[SKIP]`, `tasks_async`, `ops_async`, CI ishi; Talablar: FreeCAD «hozircha GES obyektlari uchun, P2 da olib tashlanadi»)
- Modify: `docs/roadmap-bim-scada.md:1746` va `:1855` (K3, K7 sarlavhalariga `✅ (<commit>)`)

- [ ] **Step 1: README «Tuzilma» va «Testlar» qatorlarini yangilang**

`Tuzilma` ro'yxatiga qo'shing:

```markdown
  - `core/` — `tasks.py` (fon vazifalari, bpy siz), `events.py` (hodisalar shinasi), `ui_tasks.py` (pompa, status bar
    progressi/bekor qilish, `run_op`) — uzoq tarmoq ishlari Blender ni qotirmaydi (K3)
```

`Testlar` qatorini almashtiring:

```markdown
- Testlar: `pytest desktop/tests` (Blender siz: pure, flows, tasks, events, client threading);
  `.\desktop\tests\run_blender_tests.ps1` (headless Blender; FreeCAD yo'q bo'lsa FreeCAD testlari `[SKIP]`;
  `tasks_async`, `ops_async` — asinxron yo'l soxta sekin server bilan). CI: `desktop-blender` ishi (windows-2022).
- Unumdorlik: `python desktop/tests/perf_baseline.py` → `docs/benchmark-desktop.md`.
```

- [ ] **Step 2: Roadmap belgilari**

`### K3 — Bloklovchi tarmoq chaqiruvlarini olib tashlash` → `### K3 — Bloklovchi tarmoq chaqiruvlarini olib tashlash ✅ (<Task 9 commit qisqa hash>)`; `### K7 — Desktop ni CI ga kiritish` → `… ✅ (<Task 2 commit qisqa hash>)`. Hashlarni `git log --oneline -12` dan oling.

- [ ] **Step 3: Commit**

```bash
git add desktop/blender/README.md docs/roadmap-bim-scada.md
git commit -m "docs(K3,K7): addon README — core/ fon vazifalari, testlar va CI; roadmap K3/K7 bajarildi"
```

---

## Keyingi rejalar (shu spec bo'yicha)

- **P2** — `2026-10-xx-foundation-p2-geometry.md`: golden fayl (FreeCAD bilan), `geom` + `ges_kinds`, FreeCAD ni olib tashlash, K2, K4; tungi server testlari CI da.
- **P3** — modul reyestri, `api.py`, server `permissions`, `SathPanel`, modullarni ko'chirish (`tomllib` Python 3.10 pytest uchun zaxira bilan).
- **P4** — workspace lar, tema, tokens, keymap, FreeCAD siz bundle, byudjetlar.
