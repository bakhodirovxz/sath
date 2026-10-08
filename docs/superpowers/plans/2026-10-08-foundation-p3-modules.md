# Poydevor P3: modul tizimi va rolga sezgir UI — amalga oshirish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sath ilovasining funksiyalari ichki reyestrdagi modullarga aylanadi — Sozlamalarda Blender Add-ons ro'yxati kabi jonli yoqiladi/o'chiriladi, yiqilgan modul qolganini buzmaydi, uchinchi tomon moduli faqat imzo bilan yuklanadi; UI foydalanuvchining loyihadagi ruxsatlariga qarab panel va tugmalarni yashiradi yoki sababini aytib kulrang qiladi.

**Architecture:** Sof (bpy siz) `sath/core/registry.py` manifestlarni (`sath_module.toml`) topadi, tekshiradi (API oralig'i, bog'liqlik, Ed25519 imzo), topologik tartiblaydi va hayot siklini (yoqish/o'chirish, ro'yxatga olingan klass va tozalashlarni LIFO qaytarish, xato izolyatsiyasi) boshqaradi — Blender amallari unga tashqaridan beriladi, shuning uchun pytest soxta `register_class` bilan to'liq sinaydi. `sath/core/host.py` uni Blender ga ulaydi (bundle `sath/modules/` + foydalanuvchi papkasi, prefs dagi holat, operatorlar), `sath/api.py` modullarga barqaror fasad beradi, `sath/core/panels.py::SathPanel` — yagona `poll` (modul yoqilgan + workspace tegi + ruxsat + login/model holati). Ruxsatlar serverdan (`ProjectOut.permissions`) loyiha qatoriga yoziladi; eski server uchun `common/sath_common/permissions.py` — server `ROLE_PERMISSIONS` ning ko'zgusi (paritet testi bilan). Mavjud kod «strangler» bilan ko'chadi: avval hammasi `legacy` psevdo-modulda o'zgarishsiz, keyin bittadan `review → sim → scada → twin → io → bim`, oxirida `legacy` yo'qoladi.

**Tech Stack:** Blender 5.2.2 LTS (Python 3.13, bpy), Bonsai 0.9.0; stdlib (`tomllib`/`tomli`, `importlib`, `hashlib`, `json`); server FastAPI + pydantic; pytest (Python 3.10+ monorepo `.venv`, CI 3.12).

**Spec:** `docs/superpowers/specs/2026-10-08-sath-foundation-design.md` (§1 modul tizimi, §2 rolga sezgir UI, «Bosqichlar» P3)

## Global Constraints

- **P2 bu rejadan OLDIN bajarilgan** (FreeCAD, `fc_engine.py`, `sath/wb/` yo'q; `ges_objects.py`/`demo_plant.py` sof Python geometriyada; ehtimol `core/ifc_ops.py`, `sath.sync_ifc`, `ges_objects.restore_from_ifc`). Yangi kod `fc_engine` ni hech qayerda import qilmaydi. `ges_objects`/`demo_plant` ga faqat ochiq funksiya/operatorlari orqali murojaat (`ges_objects.add`, `by_role`, `params_dict`, `KIND_ITEMS`, `register/unregister`, `sath.add_object`, `sath.build_demo_plant`). Vazifa boshida P2 natijasiga mos kelmaydigan joy bo'lsa (nom o'zgargan) — rejadagi nomni P2 dagisiga moslang va hisobotda ayting.
- **Qator oxirlari (EOL) saqlanadi.** Har faylni tahrirlashdan oldin va commit oldidan: `git ls-files --eol <fayl>` — `i/` va `w/` ustunlari o'zgarmasin. Hozir CRLF: `desktop/blender/sath/__init__.py`, `ops_monitor.py`, `ops_sim.py`, `ges_objects.py`, `demo_plant.py`, `water.py`, `desktop/blender/README.md`; `flows.py` — **mixed** (butun faylni normallashtirmang, faqat kerakli qatorlarni Edit bilan). Qolganlari LF. Yangi fayllar — LF. `git diff --stat` da butun fayl qayta yozilgandek ko'rinsa — EOL buzilgan, qaytaring.
- **UTF-8 xavfsiz tahrir:** faqat Edit/Write vositalari yoki `python` (encoding="utf-8"). PowerShell `Get-Content`/`Set-Content`/`Out-File` bilan fayl yozish **taqiqlangan** (cp1251 mojibake bo'lgan). O'zbekcha matnda apostrof — ASCII `'`.
- **Sof modullar Python 3.10 da ishlaydi** (pytest `.venv` 3.10.11): `core/registry.py`, `core/perms.py`, `core/tasks.py`, `common/sath_common/permissions.py`, `desktop/build/sign_module.py`. `tomllib` to'g'ridan-to'g'ri import qilinmaydi — **qaror:** `try: import tomllib except ModuleNotFoundError: import tomli as tomllib`. Asos: Blender 5.2 = Python 3.13 (`tomllib` bor); pytest 3.11 dan past Python da `tomli` ni majburiy bog'liqlik sifatida o'rnatadi (`.venv/Lib/site-packages/tomli` mavjud), CI 3.12 — demak hech qayerda o'z TOML parserimiz kerak emas va manifest to'liq TOML bo'lib qoladi. `ExceptionGroup`, `typing.Self`, `datetime.UTC` ishlatilmaydi.
- `common/sath_common/*` — kanonik manba; `desktop/blender/sath/shared/*` faqat `python desktop/build/sync_blender.py` bilan yangilanadi (qo'lda tahrirlanmaydi). CI `--check` qiladi.
- **`bl_idname` lar o'zgarmaydi:** barcha `sath.*` operatorlar, panel klass nomlari `SATH_PT_server/model/review/sim/monitor/twin/import/notifications/objects`, `SATH_MT_main`, `SATH_UL_simple`. Yangi: `sath.module_toggle`, `sath.modules_rescan`, `SATH_PT_twin_sims`. Fayllar faqat tegilganda ko'chadi: `ops_*.py`, `ges_objects.py`, `demo_plant.py` o'z joyida qoladi (testlar `from sath import ops_sim` qiladi); modul ularni `api.adopt()` bilan biriktiradi va panelini `ui.py` dan oladi.
- Blender klassi atributlariga **tip annotatsiyasi yozilmaydi** (`sath_needs = frozenset()`, `sath_needs: frozenset = …` emas) — Blender klass annotatsiyalarini xususiyat (property) ta'rifi deb o'qiydi.
- Ishchi oqim bpy ga tegmaydi; modul `register(api)`/`unregister(api)` faqat asosiy oqimda. Modul vazifalarining kaliti `<mod_id>.` bilan boshlanadi (o'chirilganda `TASKS.cancel_prefix`).
- `Scene.ges` yadroda qoladi (spec §1); yangi modul holati faqat `api.props.scene_group`.
- Foydalanuvchi matnlari o'zbekcha (lotin). Commit xabarlari o'zbekcha: `feat(MOD): …`, `feat(ROLE): …`, `test(MOD): …`, `refactor(MOD): …`, `docs(MOD): …`; oxirida bo'sh qator va `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Har vazifa — bitta commit (push yo'q).
- `ruff check server sim desktop` toza (`--fix` faqat import tartibi uchun, faqat tegilgan fayllarda).
- Tekshiruv muhiti: `$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"`; pytest — `.venv\Scripts\python.exe -m pytest`.

## Review Focus

1. **Modul paneli ochiq yoki uning fon vazifasi ishlayotganda o'chiriladi** (masalan «Ota bilan farq» davomida `review` o'chadi) — panel yo'qoladi, vazifa bekor qilinadi, eski callback Blender ga xato otmaydi, diff/alarm ranglari tiklanadi → Task 3 `test_cancel_prefix_cancels_only_module_tasks`, Task 5 `_user_modules` (`hello.uzun`), Task 7/9 modul `unregister`.
2. **Uchinchi tomon modulining `register()` i yiqiladi** — Sath va boshqa modullar ishlaydi, yarim ro'yxatdan o'tgan klasslar qaytariladi, traceback Sozlamalarda → Task 3 `test_failed_register_is_isolated`, Task 5 `broken`.
3. **Foydalanuvchi papkasiga imzosiz yoki imzodan keyin o'zgartirilgan modul qo'yiladi** — hech qachon import qilinmaydi (kod bajarilmaydi) → Task 3 `test_discover_bundled_and_signed_user_modules`, Task 5 (`unsigned`, o'zgartirilgan `hello` qayta skanerda yo'qoladi).
4. **Ko'ruvchi (viewer) loyihani ochadi; server eski (permissions maydoni yo'q) yoki loyiha ro'yxatda yo'q** — commit va simulyatsiya yashirin, monitoring ko'rinadi; eski serverda rol bo'yicha bir xil natija; ro'yxatda yo'q loyiha uchun ruxsat bir marta so'raladi → Task 4 `test_sath_perms.py`, Task 8/9 `_viewer_hides`.
5. **`bim` (Object.ges) o'chirilib qayta yoqiladi** — GES obyektlarining parametrlari yo'qolmaydi, unga bog'liq `sim`/`twin` birga o'chadi, commit `bim` siz ham ishlaydi → Task 12 `_bim_keeps_data`.

---

## Fayl tuzilmasi

| Fayl | Mas'uliyat |
|---|---|
| `server/ges_server/projects/router.py` (o'zgaradi) | `ProjectOut.permissions` |
| `server/tests/test_projects.py` (o'zgaradi), `server/tests/test_permissions_mirror.py` (yangi) | server maydoni; ko'zgu paritet testi |
| `common/sath_common/permissions.py` (yangi) → `sath/shared/permissions.py` (sync) | rol → ruxsatlar zaxirasi (server ko'zgusi) |
| `desktop/build/sync_blender.py` (o'zgaradi) | `permissions.py` nusxasi |
| `desktop/blender/sath/core/registry.py` (yangi, sof) | manifest, imzo, topish, tartib, hayot sikli |
| `desktop/blender/sath/core/tasks.py` (o'zgaradi, sof) | `cancel_prefix`, `on_finished` (`task.*` hodisalari) |
| `desktop/build/sign_module.py` (yangi) | modulni Ed25519 bilan imzolash (sof RFC 8032) |
| `desktop/blender/sath/core/perms.py` (yangi, sof) | faol loyiha ruxsatlari, `can/any_of/require/role/poll` |
| `desktop/blender/sath/core/panels.py` (yangi) | `SathPanel`, `draw_list`, `cur` |
| `desktop/blender/sath/core/host.py` (yangi) | reyestrning Blender ulagichi, prefs ro'yxati, operatorlar, menyu bandlari |
| `desktop/blender/sath/api.py` (yangi) | barqaror fasad `API_VERSION = (1, 0)` |
| `desktop/blender/sath/modules/__init__.py`, `modules/<id>/{sath_module.toml,__init__.py}` (yangi) | `legacy`, `review`, `sim`, `scada`, `twin`, `io`, `bim` |
| `desktop/blender/sath/__init__.py`, `prefs.py`, `props.py`, `flows.py`, `ui.py`, `ops_server.py`, `ops_review.py`, `ops_sim.py`, `ops_monitor.py`, `ops_twin.py`, `ges_objects.py`, `core/ui_tasks.py`, `core/events.py` (o'zgaradi) | ulash, ruxsat tekshiruvi, panellar ko'chishi |
| `desktop/tests/test_sath_registry.py`, `test_sath_perms.py` (yangi), `test_sath_tasks.py`, `test_sath_flows.py` (o'zgaradi) | sof testlar |
| `desktop/tests/sath_tests/modules.py` (yangi), `smoke.py`, `run_blender_tests.ps1` (o'zgaradi) | headless `modules` |
| `desktop/blender/README.md` (o'zgaradi) | hujjat |

---

### Task 1: Server — `ProjectOut.permissions`

**Model:** haiku — to'liq kod ko'chirish, bitta fayl + test.

**Files:**
- Modify: `server/ges_server/projects/router.py:12` (import), `:42-54` (`ProjectOut`), `:73-85` (`_out`)
- Test: `server/tests/test_projects.py` (oxiriga yangi test)

**Interfaces:**
- Consumes: `ges_server.auth.deps.role_permissions(role: Role | None) -> frozenset[str]`.
- Produces: `GET /api/projects` va `GET /api/projects/{id}` (hamda `POST`/`PATCH` javobi) da `permissions: list[str]` = `sorted(role_permissions(my_role))`; a'zo bo'lmasa `[]`. Desktop Task 4 shu maydonni o'qiydi.

- [ ] **Step 1: Yiqiluvchi test** — `server/tests/test_projects.py` oxiriga:

```python
def test_project_permissions_follow_role(client, users):
    """Desktop P3 (FEAT-ROLE): ProjectOut.permissions = sorted(role_permissions(my_role)) — ro'yxatda ham,
    bitta loyihada ham; admin — tasdiqlovchi ruxsatlari."""
    from ges_server.auth.deps import role_permissions
    from ges_server.orm import Role

    pid = users["project_id"]
    for name in ("viewer", "engineer", "approver", "admin"):
        expected = sorted(role_permissions(Role.approver if name == "admin" else Role(name)))
        listed = next(p for p in client.get("/api/projects", headers=users[name]).json() if p["id"] == pid)
        one = client.get(f"/api/projects/{pid}", headers=users[name]).json()
        assert listed["permissions"] == expected == one["permissions"], name
    viewer = client.get(f"/api/projects/{pid}", headers=users["viewer"]).json()["permissions"]
    assert "scada.read" in viewer and "model.write" not in viewer and "sim.run" not in viewer
```

Run: `.venv\Scripts\python.exe -m pytest -q server/tests/test_projects.py -k permissions`
Expected: FAIL (`KeyError: 'permissions'`).

- [ ] **Step 2: `ProjectOut` ga maydon** (`crs` qatoridan keyin):

```python
    permissions: list[str] = Field(default_factory=list)  # desktop P3: rolga sezgir UI (auth/deps ROLE_PERMISSIONS)
```

- [ ] **Step 3: Import va `_out`**

Import qatori: `from ..auth.deps import DB, AdminUser, CurrentUser, get_project_role, has_role, require_project_role, role_permissions`

`_out` ni almashtiring:

```python
def _out(db, project: Project, user: User, role: Role | None = None, model_count: int | None = None) -> ProjectOut:
    if model_count is None:  # bitta loyiha: rol shu yerda aniqlanadi (ro'yxat uni agregat so'rov bilan beradi)
        role = get_project_role(db, project.id, user)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        location=project.location,
        my_role=role,
        permissions=sorted(role_permissions(role)),
        model_count=model_count if model_count is not None else sum(1 for m in project.models if m.deleted_at is None),
        ids_required=bool(project.ids_required),
        naming_template=project.naming_template or "",
        naming_required=bool(project.naming_required),
        crs=(c.as_dict() if (c := crs_mod.from_project(project)) else None),
    )
```

- [ ] **Step 4: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q server/tests/test_projects.py` → PASS
Run: `.venv\Scripts\python.exe -m pytest -q server/tests -k "project or role"` → PASS
Run: `.venv\Scripts\ruff.exe check server` → toza

- [ ] **Step 5: Commit**

```bash
git add server/ges_server/projects/router.py server/tests/test_projects.py
git commit -m "feat(ROLE): ProjectOut.permissions — loyihadagi rol ruxsatlari ro'yxati (desktop rolga sezgir UI uchun)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Rol ruxsatlari ko'zgusi `common/sath_common/permissions.py` + paritet testi

**Model:** haiku — to'liq kod, nusxalash skriptiga bitta nom.

**Files:**
- Create: `common/sath_common/permissions.py`
- Modify: `desktop/build/sync_blender.py` (`FILES` ro'yxatiga `"permissions.py"`)
- Create (sync natijasi): `desktop/blender/sath/shared/permissions.py`
- Test: `server/tests/test_permissions_mirror.py`

**Interfaces:**
- Produces (`sath_common.permissions`, nusxasi `sath.shared.permissions`): konstantalar (`MODEL_WRITE = "model.write"` …), `ROLE_PERMISSIONS: dict[str, frozenset[str]]`, `ALL: frozenset[str]`, `role_permissions(role: str | None) -> frozenset[str]`.
- Eslatma: `web/src/api/permissions.ts` dagi `sensor.oos` serverda yo'q — Python ko'zgusi **serverga** tenglashadi, web ga emas (web tafovuti bu rejadan tashqarida).

- [ ] **Step 1: Yiqiluvchi paritet testi** `server/tests/test_permissions_mirror.py`:

```python
"""Desktop rol zaxirasi (common/sath_common/permissions.py) — server ROLE_PERMISSIONS ning aniq ko'zgusi (P3).
Server ruxsatlari o'zgarsa test yiqiladi: ko'zguni yangilang va `python desktop/build/sync_blender.py`."""

import importlib.util
from pathlib import Path

import pytest
from ges_server.auth.deps import ROLE_PERMISSIONS, role_permissions
from ges_server.orm import Role

MIRROR = Path(__file__).resolve().parents[2] / "common" / "sath_common" / "permissions.py"


@pytest.fixture(scope="module")
def mirror():
    if not MIRROR.is_file():
        pytest.skip("common/sath_common yo'q (faqat server obrazi)")
    spec = importlib.util.spec_from_file_location("sath_common_permissions", MIRROR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mirror_equals_server_role_permissions(mirror):
    assert {r.value: set(p) for r, p in ROLE_PERMISSIONS.items()} == {k: set(v) for k, v in mirror.ROLE_PERMISSIONS.items()}


def test_every_role_mirrored_and_lookup_matches(mirror):
    assert {r.value for r in Role} == set(mirror.ROLE_PERMISSIONS)
    for r in Role:
        assert mirror.role_permissions(r.value) == role_permissions(r)
    assert mirror.role_permissions(None) == frozenset() == role_permissions(None)
    assert mirror.role_permissions("yoq") == frozenset()
    assert mirror.ALL == frozenset().union(*ROLE_PERMISSIONS.values())
```

Run: `.venv\Scripts\python.exe -m pytest -q server/tests/test_permissions_mirror.py`
Expected: `2 skipped` (ko'zgu fayli hali yo'q). Step 2 dan keyin aynan shu buyruq `2 passed` bo'lishi shart (skip qabul qilinmaydi).

- [ ] **Step 2: `common/sath_common/permissions.py`**

```python
"""Loyiha rollari ruxsatlari — server `ges_server/auth/deps.py::ROLE_PERMISSIONS` ning ko'zgusi (FEAT-ROLE, P3).

Desktop ruxsatlarni serverdan oladi (`ProjectOut.permissions`); eski server bu maydonni yubormasa shu xarita
ishlatiladi. Tenglik `server/tests/test_permissions_mirror.py` da tekshiriladi. Nusxa:
desktop/blender/sath/shared/permissions.py (`python desktop/build/sync_blender.py`) — nusxani qo'lda tahrirlamang.
Python 3.10 mos, bog'liqliksiz.
"""

from __future__ import annotations

PROJECT_READ = "project.read"
SCADA_READ = "scada.read"
SCADA_ACK = "scada.ack"
SCADA_COMMAND = "scada.command"
SCADA_COMMAND_APPROVE = "scada.command.approve"
SCADA_INTERLOCK_OVERRIDE = "scada.interlock.override"
SCADA_MANUAL_ENTRY = "scada.manual_entry"
SENSOR_CONFIGURE = "sensor.configure"
MODEL_WRITE = "model.write"
VERSION_RESTORE = "version.restore"
CR_CREATE = "cr.create"
CR_REVIEW = "cr.review"
CR_APPROVE = "cr.approve"
CR_MERGE = "cr.merge"
ISSUE_WRITE = "issue.write"
SIM_RUN = "sim.run"
SIM_CFD = "sim.cfd"
MEMBER_MANAGE = "member.manage"
AUDIT_READ = "audit.read"
GATEWAY_KEYS = "gateway.keys"

_VIEW = frozenset({PROJECT_READ, SCADA_READ})
_OPERATE = _VIEW | {SCADA_ACK, SCADA_COMMAND}
_DESIGN = _VIEW | {SCADA_ACK, MODEL_WRITE, CR_CREATE, ISSUE_WRITE, SIM_RUN, SIM_CFD, SENSOR_CONFIGURE}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": _VIEW,
    "operator": frozenset(_OPERATE),
    "shift_supervisor": frozenset(_OPERATE | {SCADA_COMMAND_APPROVE, SCADA_INTERLOCK_OVERRIDE, SCADA_MANUAL_ENTRY}),
    "engineer": frozenset(_DESIGN),
    "approver": frozenset(
        _DESIGN | {VERSION_RESTORE, CR_REVIEW, CR_APPROVE, CR_MERGE, MEMBER_MANAGE, AUDIT_READ, GATEWAY_KEYS}
    ),
}

ALL: frozenset[str] = frozenset().union(*ROLE_PERMISSIONS.values())


def role_permissions(role: str | None) -> frozenset[str]:
    """Rol nomi bo'yicha ruxsatlar; noma'lum yoki yo'q rol — bo'sh to'plam."""
    return ROLE_PERMISSIONS.get(role or "", frozenset())
```

- [ ] **Step 3: Nusxalash** — `desktop/build/sync_blender.py` dagi `FILES = [...]` ro'yxatining oxiriga `"permissions.py"` qo'shing (P2 dan keyingi ro'yxat qanday bo'lsa ham — faqat shu nom qo'shiladi). Keyin:

Run: `.venv\Scripts\python.exe desktop/build/sync_blender.py; .venv\Scripts\python.exe desktop/build/sync_blender.py --check`
Expected: `desktop/blender/sath/shared/permissions.py` paydo bo'ladi, `--check` exit 0.

- [ ] **Step 4: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q server/tests/test_permissions_mirror.py desktop/tests/test_sath_pure.py` → PASS (2 passed + pure)
Run: `.venv\Scripts\ruff.exe check common desktop server` → toza

- [ ] **Step 5: Commit**

```bash
git add common/sath_common/permissions.py desktop/build/sync_blender.py desktop/blender/sath/shared/permissions.py server/tests/test_permissions_mirror.py
git commit -m "feat(ROLE): rol ruxsatlari ko'zgusi common/sath_common/permissions.py (eski server zaxirasi) + server bilan paritet testi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Sof reyestr `core/registry.py`, `TaskManager.cancel_prefix/on_finished`, `sign_module.py`

**Model:** opus — hayot sikli nozikliklari (LIFO teardown, kaskad, qayta skanerda holatni saqlash, xato izolyatsiyasi).

**Files:**
- Create: `desktop/blender/sath/core/registry.py`
- Modify: `desktop/blender/sath/core/tasks.py` (`__init__`, `run` ning inline bloki, `pump`, yangi `_finished`, `cancel_prefix`)
- Create: `desktop/build/sign_module.py`
- Test: `desktop/tests/test_sath_registry.py` (yangi), `desktop/tests/test_sath_tasks.py` (oxiriga 2 test)

**Interfaces:**
- Produces (`sath.core.registry`, bpy siz):
  - `API_VERSION = (1, 0)`, `MANIFEST = "sath_module.toml"`, `SIGNATURE = "sath_module.sig"`, `CAPABILITIES = {"network","files","subprocess","ifc.write"}`
  - `class ManifestError(ValueError)`
  - `@dataclass(frozen=True) class Manifest`: `id, name, version, api, path: Path, origin="bundled"|"user", requires, permissions, visible_if_any, workspaces: tuple[str, ...], category="Sath", default_enabled=True, order=100`
  - `parse_range(spec) -> list[tuple[str, tuple[int,int]]]`, `api_ok(spec, version=API_VERSION) -> bool`, `parse_manifest(text, path, origin="bundled") -> Manifest`
  - `module_message(path, manifest) -> bytes`, `verify_signature(path, manifest, trusted_keys) -> None`, `decode_keys(texts) -> list[bytes]`
  - `discover(bundled: Path, user: Path | None = None, trusted_keys=()) -> tuple[list[Manifest], list[tuple[str, str]]]`
  - `resolve(manifests) -> tuple[list[Manifest], dict[str, str]]`
  - `@dataclass class Record`: `manifest, state ("disabled"|"enabled"|"failed"), error: str, module, classes: list, ms: float`
  - `class Registry(*, import_module, register_class, unregister_class, log=print)`: `records: dict[str, Record]` (topologik tartibda), `broken: list[tuple[str, str]]`, `api`, `load(manifests, errors=())`, `start(wanted)`, `stop()`, `enable(id) -> list[str]`, `disable(id) -> list[str]`, `dependents(id) -> list[str]`, `is_enabled(id) -> bool`, `owner(id) -> Record`, `add_classes(id, classes)`, `add_cleanup(id, fn)`
- Produces (`sath.core.tasks.TaskManager`): `on_finished: Callable[[Task, str], None] | None` (`"done"|"failed"|"cancelled"`), `cancel_prefix(prefix: str) -> int` (cancellable=False ni ham bekor qiladi — modul o'chirilishi uchun).
- Produces (`desktop/build/sign_module.py`): `public_key(seed32) -> bytes`, `sign(seed32, msg) -> bytes`, `sign_module(path, seed32) -> Path`, CLI.

- [ ] **Step 1: Yiqiluvchi testlar** `desktop/tests/test_sath_registry.py`:

```python
"""core.registry (P3): manifest, API oralig'i, topologik tartib, imzo, hayot sikli (soxta bpy bilan)."""

import base64
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
sys.path.insert(0, str(ROOT / "desktop" / "build"))

import sign_module  # noqa: E402
from sath.core import registry  # noqa: E402
from sath.core.registry import Manifest, ManifestError, Registry  # noqa: E402

SEED = bytes(range(32))
TOML = """id = "{id}"
name = "{id} moduli"
version = "1.0.0"
api = "{api}"
requires = {requires}
permissions = ["network"]
visible_if_any = ["sim.run"]
workspaces = ["Simulation"]
category = "Sath"
order = {order}
"""


def _write(root: Path, mid: str, *, api=">=1.0,<2", requires=(), order=100) -> Path:
    d = root / mid
    d.mkdir(parents=True)
    reqs = "[" + ", ".join(f'"{r}"' for r in requires) + "]"
    (d / registry.MANIFEST).write_text(TOML.format(id=mid, api=api, requires=reqs, order=order), encoding="utf-8")
    (d / "__init__.py").write_text("def register(api):\n    pass\n", encoding="utf-8")
    return d


def _m(mid, requires=(), order=100, origin="bundled", api=">=1.0,<2"):
    return Manifest(id=mid, name=mid, version="1.0.0", api=api, path=Path(mid), origin=origin, requires=tuple(requires), order=order)


# ---------- manifest ----------


def test_parse_manifest_fields(tmp_path):
    d = _write(tmp_path, "sim", requires=["bim"], order=30)
    m = registry.parse_manifest((d / registry.MANIFEST).read_text(encoding="utf-8"), d)
    assert (m.id, m.version, m.requires, m.permissions, m.visible_if_any, m.workspaces, m.order) == (
        "sim", "1.0.0", ("bim",), ("network",), ("sim.run",), ("Simulation",), 30)
    assert m.default_enabled is True and m.category == "Sath" and m.origin == "bundled"


HEAD = 'id = "sim"\nname = "x"\nversion = "1.0.0"\napi = ">=1.0"\n'


@pytest.mark.parametrize("text, msg", [
    ('id = "Sim"\nname = "x"\nversion = "1.0.0"\napi = ">=1.0"', "id"),
    ('id = "sim"\nname = "x"\nversion = "1.0"\napi = ">=1.0"', "version"),
    ('id = "sim"\nname = "x"\nversion = "1.0.0"\napi = "1.0+"', "api"),
    (HEAD + 'permissions = ["root"]', "ruxsat"),
    (HEAD + 'requires = ["sim"]', "o'ziga"),
    (HEAD + 'order = "1"', "order"),
    (HEAD + "default_enabled = 1", "default_enabled"),
    ('id = "sim"\nversion = "1.0.0"\napi = ">=1.0"', "name"),
    ("id = ", "TOML"),
])  # fmt: skip
def test_parse_manifest_rejects(text, msg):
    with pytest.raises(ManifestError, match=msg):
        registry.parse_manifest(text, Path("sim"))


def test_folder_must_match_id():
    with pytest.raises(ManifestError, match="papka"):
        registry.parse_manifest(HEAD, Path("boshqa"))


def test_api_range():
    assert registry.api_ok(">=1.0,<2") and registry.api_ok(">=1") and registry.api_ok("==1.0")
    assert not registry.api_ok(">=1.1") and not registry.api_ok("<1") and not registry.api_ok(">=2.0,<3")
    assert registry.api_ok(">=1.0,<2", (1, 7)) and not registry.api_ok(">=1.0,<2", (2, 0))


# ---------- tartib ----------


def test_resolve_dependencies_first_then_order_and_id():
    out, bad = registry.resolve([_m("twin", ["sim", "scada"], 50), _m("sim", ["bim"], 30), _m("scada", order=40),
                                 _m("bim", order=70), _m("review", order=20)])  # fmt: skip
    assert [m.id for m in out] == ["review", "scada", "bim", "sim", "twin"] and bad == {}


def test_resolve_missing_dependency_cascades():
    out, bad = registry.resolve([_m("twin", ["sim"]), _m("sim", ["yoq"]), _m("io")])
    assert [m.id for m in out] == ["io"]
    assert "topilmadi: yoq" in bad["sim"] and "ishlamaydi: sim" in bad["twin"]


def test_resolve_cycle_and_api_mismatch():
    out, bad = registry.resolve([_m("a", ["b"]), _m("b", ["a"]), _m("c", api=">=2.0"), _m("d")])
    assert [m.id for m in out] == ["d"]
    assert "halqa" in bad["a"] and "halqa" in bad["b"] and "API" in bad["c"]


def test_bundled_cannot_require_user_module():
    out, bad = registry.resolve([_m("bim"), _m("ext", origin="user"), _m("sim", ["ext"])])
    assert [m.id for m in out] == ["bim", "ext"] and "foydalanuvchi" in bad["sim"]


# ---------- topish va imzo ----------


def test_discover_bundled_and_signed_user_modules(tmp_path):
    bundled, user = tmp_path / "b", tmp_path / "u"
    _write(bundled, "review")
    (bundled / "__pycache__").mkdir()
    (bundled / "bosh").mkdir()  # manifest yo'q — e'tiborsiz
    _write(bundled, "broken").joinpath(registry.MANIFEST).write_text('id = "broken"', encoding="utf-8")
    sign_module.sign_module(_write(user, "ext"), SEED)
    _write(user, "unsigned")
    bad = _write(user, "tampered")
    sign_module.sign_module(bad, SEED)
    (bad / "__init__.py").write_text("def register(api):\n    raise SystemExit\n", encoding="utf-8")
    sign_module.sign_module(_write(user, "review"), SEED)

    found, errors = registry.discover(bundled, user, [sign_module.public_key(SEED)])
    assert sorted(m.id for m in found) == ["ext", "review"]
    assert next(m for m in found if m.id == "ext").origin == "user"
    assert next(m for m in found if m.id == "review").origin == "bundled"
    msgs = dict(errors)
    assert "version" in msgs["broken"]
    assert "imzolanmagan" in msgs["unsigned (foydalanuvchi)"]
    assert "imzo noto'g'ri" in msgs["tampered (foydalanuvchi)"]
    assert "band" in msgs["review (foydalanuvchi)"]


def test_user_modules_need_trusted_key(tmp_path):
    d = _write(tmp_path / "u", "ext")
    sign_module.sign_module(d, SEED)
    found, errors = registry.discover(tmp_path / "yoq", tmp_path / "u", [])
    assert found == [] and "kalit" in dict(errors)["ext (foydalanuvchi)"]
    found, errors = registry.discover(tmp_path / "yoq", tmp_path / "u", [sign_module.public_key(bytes(32))])
    assert found == [] and "imzo noto'g'ri" in dict(errors)["ext (foydalanuvchi)"]


def test_pycache_does_not_break_signature(tmp_path):
    d = _write(tmp_path / "u", "ext")
    sign_module.sign_module(d, SEED)
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
    found, _ = registry.discover(tmp_path / "yoq", tmp_path / "u", [sign_module.public_key(SEED)])
    assert [m.id for m in found] == ["ext"]


def test_decode_keys_accepts_base64_hex_lists_and_skips_garbage():
    pub = sign_module.public_key(SEED)
    assert registry.decode_keys([base64.b64encode(pub).decode() + ", yaroqsiz", pub.hex(), ""]) == [pub]


def test_sign_matches_cryptography():
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    sk = ed.Ed25519PrivateKey.from_private_bytes(SEED)
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert sign_module.public_key(SEED) == pub
    for msg in (b"", b"sath", bytes(range(256))):
        assert sign_module.sign(SEED, msg) == sk.sign(msg)


# ---------- hayot sikli ----------


class Fake:
    """Soxta bpy: ro'yxatdagi klasslar + modul jurnali."""

    def __init__(self):
        self.registered: list = []
        self.log: list[str] = []
        self.errors: list[str] = []
        self.modules: dict[str, SimpleNamespace] = {}

    def register_class(self, c):
        assert c not in self.registered, f"ikki marta: {c}"
        self.registered.append(c)

    def unregister_class(self, c):
        self.registered.remove(c)

    def make(self, mid, *, fail=False, classes=1, unreg_fail=False):
        cls = [type(f"{mid}_{i}", (), {}) for i in range(classes)]

        def register(api):
            self.log.append(f"+{mid}")
            api.register_classes(mid, cls)
            api.on_unregister(mid, lambda: self.log.append(f"cleanup {mid}"))
            if fail:
                raise RuntimeError(f"{mid} ataylab yiqildi")

        def unregister(api):
            self.log.append(f"-{mid}")
            if unreg_fail:
                raise RuntimeError("unregister xatosi")

        self.modules[mid] = SimpleNamespace(register=register, unregister=unregister, CLASSES=cls)


def _reg(fake, manifests):
    reg = Registry(import_module=lambda m: fake.modules[m.id], register_class=fake.register_class,
                   unregister_class=fake.unregister_class, log=fake.errors.append)  # fmt: skip
    reg.api = SimpleNamespace(register_classes=reg.add_classes, on_unregister=reg.add_cleanup)
    reg.load(manifests)
    return reg


def test_start_respects_wanted_and_dependencies():
    f = Fake()
    for mid in ("bim", "sim", "twin", "io"):
        f.make(mid)
    reg = _reg(f, [_m("bim"), _m("sim", ["bim"]), _m("twin", ["sim"]), _m("io")])
    reg.start(lambda m: m.id != "sim")
    assert {i for i, r in reg.records.items() if r.state == "enabled"} == {"bim", "io"}
    assert reg.records["twin"].state == "disabled"  # sim o'chiq — twin yoqilmaydi
    assert len(f.registered) == 2 and reg.records["bim"].ms >= 0.0


def test_failed_register_is_isolated():
    f = Fake()
    f.make("ok")
    f.make("bad", fail=True, classes=2)
    reg = _reg(f, [_m("bad", order=1), _m("ok", order=2)])
    reg.start(lambda m: True)
    bad, ok = reg.records["bad"], reg.records["ok"]
    assert bad.state == "failed" and "ataylab yiqildi" in bad.error and "Traceback" in bad.error
    assert ok.state == "enabled"
    assert f.registered == f.modules["ok"].CLASSES  # «bad» ning 2 klassi qaytarildi
    assert "cleanup bad" in f.log and any("bad" in e for e in f.errors)


def test_disable_cascades_in_reverse_and_enable_pulls_dependencies():
    f = Fake()
    for mid in ("bim", "sim", "twin"):
        f.make(mid)
    reg = _reg(f, [_m("bim"), _m("sim", ["bim"]), _m("twin", ["sim", "bim"])])
    reg.start(lambda m: True)
    f.log.clear()
    assert reg.dependents("bim") == ["sim", "twin"]
    assert reg.disable("bim") == ["twin", "sim", "bim"]
    assert f.log == ["-twin", "cleanup twin", "-sim", "cleanup sim", "-bim", "cleanup bim"]
    assert f.registered == []
    assert reg.enable("twin") == ["bim", "sim", "twin"]
    assert all(r.state == "enabled" for r in reg.records.values())


def test_unregister_error_still_tears_down():
    f = Fake()
    f.make("x", unreg_fail=True)
    reg = _reg(f, [_m("x")])
    reg.start(lambda m: True)
    assert reg.disable("x") == ["x"]
    assert f.registered == [] and reg.records["x"].state == "disabled"
    assert any("unregister xatosi" in e for e in f.errors)


def test_failed_module_can_be_disabled_and_retried_after_fix():
    f = Fake()
    f.make("x", fail=True)
    reg = _reg(f, [_m("x")])
    reg.start(lambda m: True)
    assert reg.records["x"].state == "failed"
    assert reg.disable("x") == [] and reg.records["x"].state == "disabled"
    f.make("x")  # tuzatilgan modul: yiqilgandan keyin qayta import qilinadi
    assert reg.enable("x") == ["x"] and reg.records["x"].state == "enabled" and reg.records["x"].error == ""


def test_add_classes_outside_register_is_rejected():
    f = Fake()
    reg = _reg(f, [_m("y")])
    with pytest.raises(ValueError):
        reg.add_classes("y", [type("Z", (), {})])
    with pytest.raises(ValueError):
        reg.add_classes("yoq", [])


def test_load_rescan_keeps_unchanged_and_drops_removed():
    f = Fake()
    for mid in ("a", "b"):
        f.make(mid)
    reg = _reg(f, [_m("a"), _m("b", origin="user")])
    reg.start(lambda m: True)
    rec_a = reg.records["a"]
    reg.load([_m("a")], [("b (foydalanuvchi)", "imzo noto'g'ri")])
    assert reg.records["a"] is rec_a and rec_a.state == "enabled"
    assert "b" not in reg.records and f.registered == f.modules["a"].CLASSES
    assert reg.broken == [("b (foydalanuvchi)", "imzo noto'g'ri")]
```

`desktop/tests/test_sath_tasks.py` oxiriga:

```python
def test_cancel_prefix_cancels_only_module_tasks():
    tm = TaskManager()
    ev = threading.Event()
    a = tm.run("a", lambda ctx: ev.wait(5), key="review.diff")
    b = tm.run("b", lambda ctx: ev.wait(5), key="sim.catalog", cancellable=False)
    c = tm.run("c", lambda ctx: ev.wait(5), key="server.open")
    assert tm.cancel_prefix("review.") == 1 and a.cancelled and not c.cancelled
    assert tm.cancel_prefix("sim.") == 1 and b.cancelled  # modul o'chirilganda cancellable=False ham
    ev.set()
    tm.drain(5)


def test_on_finished_reports_outcome():
    tm = TaskManager()
    seen = []
    tm.on_finished = lambda task, outcome: seen.append((task.title, outcome))
    tm.run("ok", lambda ctx: 1)
    tm.run("xato", lambda ctx: 1 / 0, on_error=lambda e: None)
    t = tm.run("bekor", lambda ctx: ctx.sleep(5))
    t.cancel()
    tm.drain(5)
    assert sorted(seen) == [("bekor", "cancelled"), ("ok", "done"), ("xato", "failed")]
    tm.inline = True
    tm.run("inline", lambda ctx: 2)
    assert seen[-1] == ("inline", "done")
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_registry.py desktop/tests/test_sath_tasks.py`
Expected: FAIL (`ModuleNotFoundError: sign_module`, `sath.core.registry`; `cancel_prefix` yo'q).

- [ ] **Step 2: `desktop/blender/sath/core/registry.py`**

```python
"""Sath modul reyestri — bpy siz (pytest): manifest, topish, imzo, tartib va hayot sikli (spec §1).

Modul — papka: `sath_module.toml` + `__init__.py` (`register(api)`, ixtiyoriy `unregister(api)`).
Birinchi tomon: sath/modules/<id>/ (bundle ichida, imzo talab qilinmaydi). Uchinchi tomon:
<user config>/sath_modules/<id>/ — faqat prefs.allow_user_modules yoqilgan va papka ishonchli Ed25519 kalit bilan
imzolangan (`sath_module.sig`, tekshiruv update.py dagi) bo'lsa; imzosiz/o'zgartirilgan modul import qilinmaydi.
Manifestdagi `permissions` — deklaratsiya (Sozlamalarda ko'rsatiladi), Python kodini cheklamaydi.
Blender ulagichi — core/host.py; bu fayl bpy ni import qilmaydi.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import operator
import re
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..update import UpdateError, decode_public_key, ed25519_verify

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 (pytest .venv): tomli — pytest ning 3.11 dan pastdagi majburiy bog'liqligi
    import tomli as tomllib

API_VERSION = (1, 0)
MANIFEST = "sath_module.toml"
SIGNATURE = "sath_module.sig"
CAPABILITIES = frozenset({"network", "files", "subprocess", "ifc.write"})
_ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_CONSTRAINT = re.compile(r"^(>=|<=|==|>|<)\s*(\d+)(?:\.(\d+))?$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt, "<": operator.lt}


class ManifestError(ValueError):
    """Manifest yoki imzo yaroqsiz — modul yuklanmaydi (sabab Sozlamalarda ko'rsatiladi)."""


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    version: str
    api: str
    path: Path
    origin: str = "bundled"  # bundled | user
    requires: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    visible_if_any: tuple[str, ...] = ()
    workspaces: tuple[str, ...] = ()
    category: str = "Sath"
    default_enabled: bool = True
    order: int = 100


def parse_range(spec: str) -> list[tuple[str, tuple[int, int]]]:
    out = []
    for part in spec.split(","):
        m = _CONSTRAINT.match(part.strip())
        if m is None:
            raise ManifestError(f'api oralig\'i noto\'g\'ri: «{spec}» (namuna: ">=1.0,<2")')
        out.append((m.group(1), (int(m.group(2)), int(m.group(3) or 0))))
    return out


def api_ok(spec: str, version: tuple[int, int] = API_VERSION) -> bool:
    return all(_OPS[op](version, v) for op, v in parse_range(spec))


def parse_manifest(text: str, path: Path, origin: str = "bundled") -> Manifest:
    try:
        d = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"{MANIFEST}: TOML xatosi — {e}") from None

    def text_field(key: str, default: str | None = None) -> str:
        v = d.get(key, default)
        if not isinstance(v, str) or not v.strip():
            raise ManifestError(f"«{key}» bo'sh bo'lmagan satr bo'lishi kerak")
        return v.strip()

    def list_field(key: str) -> tuple[str, ...]:
        v = d.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
            raise ManifestError(f"«{key}» satrlar ro'yxati bo'lishi kerak")
        return tuple(v)

    mid = text_field("id")
    if not _ID.match(mid):
        raise ManifestError(f"id «{mid}» noto'g'ri: kichik lotin harf, raqam, «_» (2–32 belgi)")
    if path.name != mid:
        raise ManifestError(f"papka nomi «{path.name}» id «{mid}» ga teng emas")
    version = text_field("version")
    if not _SEMVER.match(version):
        raise ManifestError(f"version «{version}» X.Y.Z ko'rinishida bo'lishi kerak")
    api = text_field("api")
    parse_range(api)
    requires = list_field("requires")
    if mid in requires:
        raise ManifestError("modul o'ziga bog'liq bo'lolmaydi")
    permissions = list_field("permissions")
    unknown = sorted(set(permissions) - CAPABILITIES)
    if unknown:
        raise ManifestError(f"noma'lum ruxsat(lar): {', '.join(unknown)} (mumkin: {', '.join(sorted(CAPABILITIES))})")
    default_enabled = d.get("default_enabled", True)
    if not isinstance(default_enabled, bool):
        raise ManifestError("«default_enabled» true/false bo'lishi kerak")
    order = d.get("order", 100)
    if isinstance(order, bool) or not isinstance(order, int):
        raise ManifestError("«order» butun son bo'lishi kerak")
    return Manifest(
        id=mid, name=text_field("name"), version=version, api=api, path=path, origin=origin, requires=requires,
        permissions=permissions, visible_if_any=list_field("visible_if_any"), workspaces=list_field("workspaces"),
        category=text_field("category", "Sath"), default_enabled=default_enabled, order=order,
    )  # fmt: skip


# ---------- imzo (uchinchi tomon modullari) ----------


def module_message(path: Path, manifest: Manifest) -> bytes:
    """Imzolanadigan kanonik xabar: papkadagi har fayl sha256 (imzo fayli, __pycache__, .pyc dan tashqari) + id + version."""
    files = {}
    for f in sorted(path.rglob("*")):
        rel = f.relative_to(path)
        if not f.is_file() or rel.as_posix() == SIGNATURE or "__pycache__" in rel.parts or f.suffix == ".pyc":
            continue
        files[rel.as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    payload = {"files": files, "id": manifest.id, "version": manifest.version}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verify_signature(path: Path, manifest: Manifest, trusted_keys: list[bytes]) -> None:
    if not trusted_keys:
        raise ManifestError("ishonchli kalit yo'q — Sozlamalar → Sath → «Modul kalitlari»")
    sig_path = path / SIGNATURE
    if not sig_path.is_file():
        raise ManifestError(f"imzolanmagan ({SIGNATURE} yo'q)")
    try:
        sig = base64.b64decode(sig_path.read_text(encoding="ascii").strip(), validate=True)
    except (ValueError, binascii.Error):
        raise ManifestError("imzo fayli buzilgan") from None
    msg = module_message(path, manifest)
    if not any(ed25519_verify(k, msg, sig) for k in trusted_keys):
        raise ManifestError("imzo noto'g'ri yoki kalit ishonchli emas — modul o'zgartirilgan bo'lishi mumkin")


def decode_keys(texts: Iterable[str]) -> list[bytes]:
    """Vergul/bo'shliq bilan ajratilgan base64 yoki hex ochiq kalitlar; yaroqsizi tashlanadi, takror yo'q."""
    out: list[bytes] = []
    for t in texts:
        for part in re.split(r"[\s,;]+", t or ""):
            if not part:
                continue
            try:
                k = decode_public_key(part)
            except UpdateError:
                continue
            if k not in out:
                out.append(k)
    return out


# ---------- topish va tartib ----------


def discover(bundled: Path, user: Path | None = None, trusted_keys: Iterable[bytes] = ()) -> tuple[list[Manifest], list[tuple[str, str]]]:
    """Manifestlarni topadi. Qaytaradi: (yaroqli manifestlar, [(belgi, sabab)] — yuklanmaganlar)."""
    keys = list(trusted_keys)
    found: list[Manifest] = []
    errors: list[tuple[str, str]] = []
    for origin, root in (("bundled", bundled), ("user", user)):
        if root is None or not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            if not (d / MANIFEST).is_file():
                continue
            label = d.name if origin == "bundled" else f"{d.name} (foydalanuvchi)"
            try:
                m = parse_manifest((d / MANIFEST).read_text(encoding="utf-8"), d, origin)
                if not (d / "__init__.py").is_file():
                    raise ManifestError("__init__.py yo'q")
                if origin == "user":
                    verify_signature(d, m, keys)
                if any(x.id == m.id for x in found):
                    raise ManifestError(f"id «{m.id}» band (birinchi tomon moduli)")
                found.append(m)
            except (ManifestError, OSError, UnicodeDecodeError) as e:
                errors.append((label, str(e)))
    return found, errors


def resolve(manifests: Iterable[Manifest]) -> tuple[list[Manifest], dict[str, str]]:
    """Topologik tartib (bog'liqlik avval; teng holatda order, id). Qaytaradi: (tartib, {id: sabab})."""
    ms = list(manifests)
    by_id = {m.id: m for m in ms}
    bad: dict[str, str] = {}
    for m in ms:
        if not api_ok(m.api):
            bad[m.id] = f"API {m.api} talab qilinadi, ilovada {API_VERSION[0]}.{API_VERSION[1]}"
            continue
        for r in m.requires:
            if r not in by_id:
                bad[m.id] = f"bog'liqlik topilmadi: {r}"
                break
            if m.origin == "bundled" and by_id[r].origin != "bundled":
                bad[m.id] = f"birinchi tomon moduli foydalanuvchi moduliga bog'liq bo'lolmaydi: {r}"
                break
    changed = True
    while changed:
        changed = False
        for m in ms:
            if m.id not in bad:
                dep = next((r for r in m.requires if r in bad), None)
                if dep is not None:
                    bad[m.id] = f"bog'liqlik ishlamaydi: {dep}"
                    changed = True
    ok = [m for m in ms if m.id not in bad]
    indeg = {m.id: len(set(m.requires)) for m in ok}
    users: dict[str, list[Manifest]] = {m.id: [] for m in ok}
    for m in ok:
        for r in set(m.requires):
            users[r].append(m)
    ready = [m for m in ok if indeg[m.id] == 0]
    out: list[Manifest] = []
    while ready:
        ready.sort(key=lambda m: (m.order, m.id))
        m = ready.pop(0)
        out.append(m)
        for u in users[m.id]:
            indeg[u.id] -= 1
            if indeg[u.id] == 0:
                ready.append(u)
    for m in ok:
        if m not in out:
            bad[m.id] = "bog'liqliklar halqasi (requires aylanib qolgan)"
    return out, bad


# ---------- hayot sikli ----------


@dataclass(eq=False)
class Record:
    manifest: Manifest
    state: str = "disabled"  # disabled | enabled | failed
    error: str = ""
    module: Any = None
    classes: list = field(default_factory=list)
    ms: float = 0.0
    undo: list[Callable[[], None]] = field(default_factory=list, repr=False)  # LIFO: klasslar va tozalashlar


class Registry:
    """Modullar hayot sikli. Blender amallari tashqaridan (pytest — soxtalari): import_module(manifest) → modul,
    register_class / unregister_class (bpy.utils ...), log(matn)."""

    def __init__(self, *, import_module: Callable[[Manifest], Any], register_class: Callable[[type], None],
                 unregister_class: Callable[[type], None], log: Callable[[str], None] = print) -> None:  # fmt: skip
        self._import = import_module
        self._register_class = register_class
        self._unregister_class = unregister_class
        self._log = log
        self.records: dict[str, Record] = {}  # topologik tartibda
        self.broken: list[tuple[str, str]] = []  # yuklanmagan modullar: (belgi, sabab)
        self.api: Any = None
        self._current: str | None = None

    def load(self, manifests: Iterable[Manifest], errors: Iterable[tuple[str, str]] = ()) -> None:
        """Topilgan modullarni o'rnatadi (qayta skanerda ham): manifesti o'zgarmagan yozuv holati bilan qoladi;
        yo'qolgan yoki o'zgargan yoqilgan modul (va unga bog'liqlar) avval o'chiriladi."""
        ordered, bad = resolve(manifests)
        new = {m.id: m for m in ordered}
        for rid in reversed(list(self.records)):
            if new.get(rid) != self.records[rid].manifest:
                self.disable(rid)
        old = self.records
        self.records = {m.id: old[m.id] if m.id in old and old[m.id].manifest == m else Record(m) for m in ordered}
        self.broken = [*errors, *bad.items()]

    def start(self, wanted: Callable[[Manifest], bool]) -> None:
        """Yoqilishi kerak bo'lgan o'chiq modullarni tartib bilan yoqadi; bog'liqligi yoqilmagani o'tkazib yuboriladi.
        Yiqilgan (failed) modul bu yerda qayta urinilmaydi — faqat foydalanuvchi qayta yoqsa."""
        for rid, rec in self.records.items():
            if rec.state == "disabled" and wanted(rec.manifest) and all(self.is_enabled(r) for r in rec.manifest.requires):
                self._enable_one(rid)

    def stop(self) -> None:
        for rid in reversed(list(self.records)):
            self._disable_one(rid)

    def is_enabled(self, rid: str) -> bool:
        rec = self.records.get(rid)
        return rec is not None and rec.state == "enabled"

    def dependents(self, rid: str) -> list[str]:
        """rid ga (bevosita yoki bilvosita) bog'liq modullar — topologik tartibda."""
        hit, out = {rid}, []
        for r in self.records.values():
            if r.manifest.id != rid and any(x in hit for x in r.manifest.requires):
                hit.add(r.manifest.id)
                out.append(r.manifest.id)
        return out

    def enable(self, rid: str) -> list[str]:
        """Yoqadi; avval o'chiq bog'liqliklarini. Qaytaradi: yoqilganlar (tartib bilan)."""
        rec = self.records[rid]
        done: list[str] = []
        for dep in rec.manifest.requires:
            if not self.is_enabled(dep):
                done += self.enable(dep)
                if not self.is_enabled(dep):
                    rec.error = f"bog'liqlik yoqilmadi: {dep}"
                    return done
        if rec.state != "enabled" and self._enable_one(rid):
            done.append(rid)
        return done

    def disable(self, rid: str) -> list[str]:
        """O'chiradi; avval unga bog'liq yoqilganlarini (teskari tartibda). Qaytaradi: o'chirilganlar."""
        done: list[str] = []
        for d in reversed(self.dependents(rid)):
            if self.is_enabled(d):
                self._disable_one(d)
                done.append(d)
        rec = self.records[rid]
        if rec.state == "enabled":
            self._disable_one(rid)
            done.append(rid)
        elif rec.state == "failed":
            rec.state = "disabled"
        return done

    def owner(self, rid: str) -> Record:
        """Hozir register() i ishlayotgan yoki yoqilgan modul yozuvi; aks holda ValueError."""
        rec = self.records.get(rid)
        if rec is None or (rid != self._current and rec.state != "enabled"):
            raise ValueError(f"«{rid}» moduli faol emas — register_classes/tozalash faqat modulning register() ichida")
        return rec

    def add_classes(self, rid: str, classes: Iterable[type]) -> None:
        rec = self.owner(rid)
        for c in classes:
            self._register_class(c)
            rec.classes.append(c)
            rec.undo.append(lambda c=c: self._unregister_class(c))

    def add_cleanup(self, rid: str, fn: Callable[[], None]) -> None:
        self.owner(rid).undo.append(fn)

    def _enable_one(self, rid: str) -> bool:
        rec = self.records[rid]
        t0 = time.perf_counter()
        rec.error = ""
        self._current = rid
        try:
            if rec.module is None:
                rec.module = self._import(rec.manifest)
            rec.module.register(self.api)
            rec.state = "enabled"
            return True
        except Exception:
            rec.error = traceback.format_exc()
            self._teardown(rec)
            rec.module = None  # tuzatilgandan keyin qayta yoqishda qayta import qilinsin
            rec.state = "failed"
            self._log(f"[sath] «{rid}» moduli yuklanmadi:\n{rec.error}")
            return False
        finally:
            self._current = None
            rec.ms = (time.perf_counter() - t0) * 1000.0

    def _disable_one(self, rid: str) -> None:
        rec = self.records[rid]
        if rec.state != "enabled":
            return
        fn = getattr(rec.module, "unregister", None)
        if fn is not None:
            self._current = rid
            try:
                fn(self.api)
            except Exception:
                self._log(f"[sath] «{rid}» moduli unregister xatosi:\n{traceback.format_exc()}")
            finally:
                self._current = None
        self._teardown(rec)
        rec.state = "disabled"

    def _teardown(self, rec: Record) -> None:
        while rec.undo:
            fn = rec.undo.pop()
            try:
                fn()
            except Exception:
                self._log(f"[sath] «{rec.manifest.id}» tozalashda xato:\n{traceback.format_exc()}")
        rec.classes.clear()
```

- [ ] **Step 3: `core/tasks.py` — `on_finished`, `cancel_prefix`**

`TaskManager.__init__` oxiriga: `self.on_finished: Callable[[Task, str], None] | None = None  # task.* hodisalari (ui_tasks ulaydi)`

`run()` dagi `if self.inline:` blokini almashtiring:

```python
        if self.inline:
            try:
                result = fn(TaskContext(task))
            except Cancelled:
                if on_cancel is not None:
                    on_cancel()
                self._finished(task, "cancelled")
                return task
            except Exception as e:
                if on_error is None:
                    self._finished(task, "failed")
                    raise
                on_error(e)
                self._finished(task, "failed")
                return task
            if on_done is not None:
                on_done(result)
            self._finished(task, "done")
            return task
```

`pump()` ni almashtiring va `_finished`, `cancel_prefix` ni qo'shing (`cancel_all` dan keyin):

```python
    def pump(self) -> int:
        """Asosiy oqimda: tugagan vazifalarning callbacklarini chaqiradi. Qaytaradi: nechta vazifa yakunlandi."""
        n = 0
        while True:
            try:
                task, on_done, on_error, on_cancel, result, exc = self._q.get_nowait()
            except queue.Empty:
                return n
            n += 1
            if task in self._active:
                self._active.remove(task)
            if task.dropped:
                continue
            if task.cancelled or isinstance(exc, Cancelled):
                outcome = "cancelled"
            elif exc is not None:
                outcome = "failed"
            else:
                outcome = "done"
            try:
                if outcome == "cancelled":
                    if on_cancel is not None:
                        on_cancel()
                elif outcome == "failed":
                    if on_error is not None:
                        on_error(exc)
                    else:
                        self.on_error_default(task, exc)
                elif on_done is not None:
                    on_done(result)
            except Exception as cb_exc:  # noqa: BLE001 — bitta callback xatosi pompani to'xtatmasin
                self.on_error_default(task, cb_exc)
            self._finished(task, outcome)

    def _finished(self, task: Task, outcome: str) -> None:
        if self.on_finished is None:
            return
        try:
            self.on_finished(task, outcome)
        except Exception as e:  # noqa: BLE001 — hodisa obunachisi pompani to'xtatmasin
            self.on_error_default(task, e)
```

```python
    def cancel_prefix(self, prefix: str) -> int:
        """Kaliti `prefix` bilan boshlanadigan vazifalarni bekor qiladi (modul o'chirilganda: `<mod_id>.`).
        cancellable=False ham — modul kodi endi ro'yxatda emas, natijasi qo'llanmasligi kerak. Qaytaradi: nechta."""
        n = 0
        for t in self._active:
            if t.key is not None and t.key.startswith(prefix) and not t.cancelled:
                t.cancel()
                n += 1
        return n
```

- [ ] **Step 4: `desktop/build/sign_module.py`**

```python
"""Uchinchi tomon Sath modulini Ed25519 bilan imzolash: <papka>/sath_module.sig yoziladi (sof Python, RFC 8032).

  python desktop/build/sign_module.py --new-key kalit.txt          # yangi maxfiy kalit + ochiq kalitni chiqaradi
  python desktop/build/sign_module.py <modul_papkasi> --key kalit.txt

Imzolangan xabar — sath.core.registry.module_message (fayllar sha256 + id + version). Ochiq kalit (base64) ilovada
Sozlamalar → Sath → «Modul kalitlari» ga yoziladi. Maxfiy kalit faylini repo ga qo'shmang.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import update  # noqa: E402
from sath.core import registry  # noqa: E402


def _h(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _compress(pt: tuple) -> bytes:
    zinv = update._inv(pt[2])
    x, y = pt[0] * zinv % update._P, pt[1] * zinv % update._P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _expand(seed: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _compress(update._mul(a, update._G))


def sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(seed)
    pub = _compress(update._mul(a, update._G))
    r = _h(prefix + msg) % update._Q
    big_r = _compress(update._mul(r, update._G))
    h = _h(big_r + pub + msg) % update._Q
    s = (r + h * a) % update._Q
    return big_r + int.to_bytes(s, 32, "little")


def sign_module(path: Path, seed: bytes) -> Path:
    m = registry.parse_manifest((path / registry.MANIFEST).read_text(encoding="utf-8"), path, "user")
    out = path / registry.SIGNATURE
    out.write_text(base64.b64encode(sign(seed, registry.module_message(path, m))).decode("ascii") + "\n", encoding="ascii")
    return out


def _read_seed(path: Path) -> bytes:
    t = path.read_text(encoding="ascii").strip()
    raw = bytes.fromhex(t) if len(t) == 64 else base64.b64decode(t, validate=True)
    if len(raw) != 32:
        raise SystemExit("maxfiy kalit 32 bayt bo'lishi kerak (hex yoki base64)")
    return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module_dir", type=Path, nargs="?")
    ap.add_argument("--key", type=Path, help="maxfiy kalit fayli (32 bayt: hex yoki base64)")
    ap.add_argument("--new-key", type=Path, help="yangi maxfiy kalit yaratib shu faylga yozish")
    a = ap.parse_args(argv)
    if a.new_key:
        if a.new_key.exists():
            ap.error(f"{a.new_key} allaqachon bor — ustidan yozilmaydi")
        seed = os.urandom(32)
        a.new_key.write_text(seed.hex() + "\n", encoding="ascii")
        print("ochiq kalit:", base64.b64encode(public_key(seed)).decode())
        return 0
    if a.module_dir is None or a.key is None:
        ap.error("modul papkasi va --key kerak")
    seed = _read_seed(a.key)
    print("imzo:", sign_module(a.module_dir, seed))
    print("ochiq kalit:", base64.b64encode(public_key(seed)).decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(`sign`: RFC 8032 §6 — `s = (r + H(R‖A‖M)·a) mod L`; `update._mul/_G/_P/_Q/_inv` — o'sha fayldagi tekshiruv bilan bir xil egri arifmetikasi.)

- [ ] **Step 5: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_registry.py desktop/tests/test_sath_tasks.py desktop/tests/test_update_verify.py`
Expected: PASS (registry ~20, tasks oldingilari + 2).
Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests` → PASS; `.venv\Scripts\ruff.exe check desktop` → toza.
Run: `.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'desktop/blender'); import sath.core.registry as r; print(r.tomllib.__name__)"` → `tomli` (3.10 da); Blender da `tomllib`.

- [ ] **Step 6: Commit**

```bash
git add desktop/blender/sath/core/registry.py desktop/blender/sath/core/tasks.py desktop/build/sign_module.py desktop/tests/test_sath_registry.py desktop/tests/test_sath_tasks.py
git commit -m "feat(MOD): sof modul reyestri — manifest, API oralig'i, Ed25519 imzo, topologik tartib, izolyatsiyali hayot sikli; TaskManager.cancel_prefix/on_finished; sign_module.py

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `core/perms.py`, `SathPanel`, `api.py`, minimal `core/host.py`; yadro operatorlarida ruxsat

**Model:** sonnet — ko'p faylli integratsiya (bpy ulagichi, props, flows, ops_server, ui).

**Files:**
- Create: `desktop/blender/sath/core/perms.py`, `core/panels.py`, `core/host.py`, `api.py`, `modules/__init__.py`
- Modify: `desktop/blender/sath/props.py` (`GesListItem.perms`, `LIST_FIELDS`, `GROUPS`, `snapshot_scene/restore_scene`, `_on_project` hodisasi)
- Modify: `desktop/blender/sath/flows.py:34-38` (`project_rows`; fayl **mixed EOL** — faqat shu qatorlar)
- Modify: `desktop/blender/sath/ops_server.py` (commit/submit/create_model `poll`; open_version/pull_head `snapshot_scene`)
- Modify: `desktop/blender/sath/ui.py` (yordamchilar → `core.panels`, Model paneli ruxsatlari, `bl_order`, menyu bandlari)
- Modify: `desktop/blender/sath/core/ui_tasks.py` (`task.*` hodisalari), `core/events.py` (docstring)
- Modify: `desktop/blender/sath/__init__.py` (**CRLF**; `host` ni `MODULES` oxiriga)
- Test: `desktop/tests/test_sath_perms.py` (yangi), `desktop/tests/test_sath_flows.py` (bitta assert), `desktop/tests/sath_tests/smoke.py`

**Interfaces:**
- Consumes: Task 1 `permissions`, Task 2 `sath.shared.permissions.role_permissions`, Task 3 `registry`, `TASKS.on_finished`.
- Produces:
  - `sath.core.perms`: `resolve(role, server_perms) -> frozenset[str]`, `clear()`, `active_project_id(ges) -> int`, `current(context=None, project_id=None) -> tuple[str, frozenset[str]]`, `can(perm, context=None, project_id=None) -> bool`, `any_of(perms, context=None, project_id=None) -> bool`, `role(context=None) -> str`, `require(perm, context=None, project_id=None)` (PermissionError), `poll(cls, perm, context=None, project_id=None) -> bool` (poll_message_set bilan)
  - `sath.core.panels`: `SathPanel` (`sath_module`, `sath_needs`, `sath_perm`, `poll`, `sath_poll`), `visible(cls, context) -> bool`, `draw_list(layout, s, coll, idx, rows=4, refresh_op=None)`, `cur(coll, idx)`
  - `sath.core.host`: `REG`, `BUNDLED`, `record(id)`, `is_enabled(id)`, `wanted(m)`, `scan()`, `add_menu(id, draw)`, `draw_menus(layout, context)`, `register()/unregister()`
  - `sath.api`: `API_VERSION`, `register_classes(mod_id, classes)`, `adopt(mod_id, *files)`, `on_unregister(mod_id, fn)`, `module_enabled(id)`, `session`, `events.subscribe(topic, fn, *, owner=None)/publish`, `tasks.run/run_op/drain`, `perms.can/any_of/require/role/poll`, `ui.SathPanel/draw_list/cur/main_menu(mod_id, draw)/keymap(mod_id, idname, key, …)`, `props.scene_group(mod_id, cls) -> str`, dangasa `ifc` (+`IfcOperator`, `restore_ges` agar P2 da bor), `geom`, `kinds`
  - `props`: `GesListItem.perms: str` (loyiha qatori: server ruxsatlari, bo'sh — eski server), `GROUPS: dict[str, str]`, `snapshot_scene(scene) -> dict`, `restore_scene(scene, snap)`
  - Hodisalar: `project.changed {project_id}`, `task.done|task.failed|task.cancelled {id, key, title}`

- [ ] **Step 1: Yiqiluvchi sof test** `desktop/tests/test_sath_perms.py`:

```python
"""core.perms (P3, rolga sezgir UI): server ruxsatlari, eski server uchun rol zaxirasi, faol loyiha, so'rab olish."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath import session  # noqa: E402
from sath.core import perms  # noqa: E402
from sath.core.tasks import TASKS  # noqa: E402


def _ctx(rows=(), project_id=0, index=-1):
    projects = [NS(item_id=i, state=role, perms=p) for i, role, p in rows]
    return NS(scene=NS(ges=NS(projects=projects, projects_index=index, project_id=project_id)))


class FakeClient:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def project(self, pid):
        self.calls.append(pid)
        if self.exc:
            raise self.exc
        return self.reply


@pytest.fixture
def logged_in(monkeypatch):
    def login(client=None):
        client = client or FakeClient({})
        monkeypatch.setattr(session, "_client", client)
        return client

    perms.clear()
    monkeypatch.setattr(TASKS, "inline", True)
    yield login
    perms.clear()


def test_resolve_prefers_server_list_and_falls_back_to_role():
    assert perms.resolve("viewer", ["model.write"]) == {"model.write"}
    assert perms.resolve("viewer", None) == {"project.read", "scada.read"}
    assert "cr.merge" in perms.resolve("approver", None)
    assert perms.resolve(None, None) == frozenset() == perms.resolve("yoq", None)


def test_logged_out_has_nothing():
    perms.clear()
    ctx = _ctx([(1, "approver", "")], project_id=1)
    assert not perms.can("model.write", ctx) and perms.role(ctx) == ""


def test_server_permissions_and_old_server_fallback(logged_in):
    logged_in()
    new = _ctx([(1, "viewer", "project.read scada.read")], project_id=1)
    assert perms.can("scada.read", new) and not perms.can("sim.run", new)
    old = _ctx([(1, "engineer", "")], project_id=1)  # eski server: permissions maydoni yo'q
    assert perms.can("sim.run", old) and perms.can("model.write", old) and not perms.can("cr.approve", old)
    assert perms.role(old) == "engineer"
    assert perms.any_of(["cr.merge", "sim.run"], old) and not perms.any_of(["cr.merge"], old)


def test_active_project_open_model_else_selected_row(logged_in):
    logged_in()
    ctx = _ctx([(1, "viewer", ""), (2, "approver", "")], project_id=0, index=1)
    assert perms.active_project_id(ctx.scene.ges) == 2 and perms.can("cr.merge", ctx)
    ctx.scene.ges.project_id = 1  # ochiq model loyihasi ustun
    assert not perms.can("cr.merge", ctx)
    assert perms.can("cr.merge", ctx, project_id=2)  # aniq loyiha (yangi model yaratish)


def test_missing_row_is_fetched_once(logged_in):
    c = logged_in(FakeClient({"my_role": "engineer", "permissions": ["model.write", "project.read"]}))
    ctx = _ctx([], project_id=42)
    assert perms.can("model.write", ctx) and not perms.can("sim.run", ctx)
    assert perms.role(ctx) == "engineer" and c.calls == [42]


def test_fetch_error_means_no_permissions(logged_in):
    c = logged_in(FakeClient(exc=RuntimeError("403")))
    ctx = _ctx([], project_id=7)
    assert not perms.can("project.read", ctx) and not perms.can("project.read", ctx)
    assert c.calls == [7]


def test_require_and_poll_reason(logged_in):
    logged_in()
    msgs = []
    cls = NS(poll_message_set=msgs.append)
    viewer = _ctx([(1, "viewer", "")], project_id=1)
    assert not perms.poll(cls, "sim.run", viewer)
    assert not perms.poll(cls, "sim.run", _ctx())
    assert msgs == ["Ruxsat yo'q: sim.run", "Avval loyihani tanlang"]
    assert perms.poll(cls, "sim.run", _ctx([(1, "engineer", "")], project_id=1)) and len(msgs) == 2
    with pytest.raises(PermissionError, match="sim.run"):
        perms.require("sim.run", viewer)
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_perms.py` → FAIL (`sath.core.perms` yo'q).

- [ ] **Step 2: `desktop/blender/sath/core/perms.py`**

```python
"""Rolga sezgir UI (spec §2): faol loyihadagi ruxsatlar. Manba — server `ProjectOut.permissions` (loyiha qatorining
`perms` maydoni); bo'sh bo'lsa (eski server) `shared/permissions.py` — server ROLE_PERMISSIONS ko'zgusi. Loyiha
ro'yxatda bo'lmasa (masalan skript s.project_id ni o'zi qo'ygan) — bir marta fonda `GET /api/projects/{id}`.
Haqiqiy tekshiruv baribir serverda; bu faqat UI: panel yashiriladi, operator sababi bilan kulrang.

Faol loyiha: ochiq model loyihasi (`scene.ges.project_id`), bo'lmasa ro'yxatda tanlangani. bpy siz import qilinadi.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..shared.permissions import role_permissions

_memo: dict[tuple[str, str], frozenset[str]] = {}
_fetched: dict[int, tuple[str, frozenset[str]]] = {}
_pending: set[int] = set()
_NONE: tuple[str, frozenset[str]] = ("", frozenset())


def resolve(role: str | None, server_perms: Iterable[str] | None) -> frozenset[str]:
    """Server ro'yxati bo'lsa — o'sha; yo'q bo'lsa (eski server) rol bo'yicha zaxira xarita."""
    if server_perms is not None:
        return frozenset(server_perms)
    return role_permissions(role)


def clear() -> None:
    """Sessiya almashganda (session.login/logout): so'rab olingan loyihalar unutiladi."""
    _fetched.clear()
    _pending.clear()


def _ges(context):
    if context is None:
        import bpy

        context = bpy.context
    return context.scene.ges


def active_project_id(s) -> int:
    if s.project_id:
        return s.project_id
    i = s.projects_index
    return s.projects[i].item_id if 0 <= i < len(s.projects) else 0


def _entry(s, pid: int) -> tuple[str, frozenset[str]] | None:
    row = next((r for r in s.projects if r.item_id == pid), None)
    if row is not None:
        key = (row.state, row.perms)
        hit = _memo.get(key)
        if hit is None:
            hit = _memo[key] = resolve(row.state or None, row.perms.split() if row.perms else None)
        return row.state, hit
    if pid not in _fetched:
        _fetch(pid)
    return _fetched.get(pid)


def current(context=None, project_id: int | None = None) -> tuple[str, frozenset[str]]:
    """(rol, ruxsatlar) — kirilmagan yoki loyiha yo'q bo'lsa bo'sh."""
    from .. import session

    if not session.is_logged_in():
        return _NONE
    s = _ges(context)
    pid = project_id if project_id is not None else active_project_id(s)
    if not pid:
        return _NONE
    return _entry(s, pid) or _NONE


def can(perm: str, context=None, project_id: int | None = None) -> bool:
    return perm in current(context, project_id)[1]


def any_of(perms: Iterable[str], context=None, project_id: int | None = None) -> bool:
    have = current(context, project_id)[1]
    return any(p in have for p in perms)


def role(context=None) -> str:
    return current(context)[0]


def require(perm: str, context=None, project_id: int | None = None) -> None:
    if not can(perm, context, project_id):
        raise PermissionError(f"Ruxsat yo'q: {perm}")


def poll(cls, perm: str, context=None, project_id: int | None = None) -> bool:
    """Operator poll uchun: ruxsat bo'lmasa sababi tooltipda («Ruxsat yo'q: cr.approve»)."""
    if can(perm, context, project_id):
        return True
    pid = project_id if project_id is not None else active_project_id(_ges(context))
    cls.poll_message_set(f"Ruxsat yo'q: {perm}" if pid else "Avval loyihani tanlang")
    return False


def _fetch(pid: int) -> None:
    from .. import session
    from .tasks import TASKS

    if pid in _pending or not session.is_logged_in():
        return
    _pending.add(pid)
    client = session.client()

    def same_session() -> bool:
        return session.is_logged_in() and session.client() is client

    def done(d: dict) -> None:
        _pending.discard(pid)
        if same_session():
            _fetched[pid] = (d.get("my_role") or "", resolve(d.get("my_role"), d.get("permissions")))
            _redraw()

    def failed(_e: BaseException) -> None:
        _pending.discard(pid)
        if same_session():
            _fetched[pid] = _NONE  # 403/404: loyihada roli yo'q

    TASKS.run("Ruxsatlar", lambda ctx: client.project(pid), done, failed, key=f"perms.{pid}", quiet=True, cancellable=False)
    if not TASKS.inline:
        from .ui_tasks import ensure_pump

        ensure_pump()


def _redraw() -> None:
    try:
        import bpy

        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except Exception:  # noqa: BLE001 — pytest (bpy yo'q) yoki oyna yo'q
        pass
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_perms.py` → PASS (7).

- [ ] **Step 3: `props.py` — `perms` maydoni, modul guruhlari, `project.changed`**

`GesListItem` ga (`number` dan keyin): `perms: bpy.props.StringProperty()  # loyiha qatori: server ruxsatlari (bo'sh — eski server, rol zaxirasi)`

`LIST_FIELDS = ("item_id", "name", "col2", "col3", "col4", "guid", "state", "number", "perms")`

`_on_project` ni almashtiring:

```python
def _on_project(self, context):
    if session.is_logged_in():
        bpy.ops.sath.refresh_models()
        from .core import events

        i = self.projects_index
        events.publish("project.changed", project_id=self.projects[i].item_id if 0 <= i < len(self.projects) else 0)
```

`restore()` dan keyin qo'shing:

```python
GROUPS: dict[str, str] = {}  # Scene atributi → modul id (api.props.scene_group)


def _scalars(g) -> dict:
    return {
        p.identifier: getattr(g, p.identifier)
        for p in g.bl_rna.properties
        if p.identifier not in ("rna_type", "name")
        and p.type in ("STRING", "INT", "FLOAT", "BOOLEAN", "ENUM")
        and not getattr(p, "is_array", False)
        and not getattr(p, "is_enum_flag", False)
    }


def snapshot_scene(scene) -> dict:
    """Scene.ges + modul guruhlari (Bonsai yangi sessiyasi — read_homefile — dan oldin)."""
    out = {"ges": snapshot(scene.ges)}
    for attr in GROUPS:
        g = getattr(scene, attr, None)
        if g is not None:
            out[attr] = _scalars(g)
    return out


def restore_scene(scene, snap: dict) -> None:
    restore(scene.ges, snap.get("ges", {}))
    for attr, vals in snap.items():
        g = getattr(scene, attr, None) if attr in GROUPS else None
        if g is None:
            continue
        for k, v in vals.items():
            try:
                setattr(g, k, v)
            except (AttributeError, TypeError, ValueError):
                pass
```

- [ ] **Step 4: `flows.project_rows`** (mixed EOL — faqat shu funksiya qatorlari Edit bilan):

```python
def project_rows(client: GesClient) -> list[dict]:
    return [
        {"item_id": p["id"], "name": p["name"], "state": p.get("my_role") or "",
         "perms": " ".join(p.get("permissions") or [])}
        for p in client.projects()
    ]  # fmt: skip
```

`desktop/tests/test_sath_flows.py::test_rows_and_commit_roundtrip` da `pid = …` qatoridan keyin:

```python
    row = next(p for p in projects if p["name"] == "Flows GES")
    assert {"model.write", "cr.approve"} <= set(row["perms"].split())  # admin — tasdiqlovchi ruxsatlari (P3)
```

- [ ] **Step 5: `core/panels.py`**

```python
"""SathPanel — modul panellari uchun yagona poll (spec §1): modul yoqilgan + workspace tegi + ruxsat + holat.
Atributlarga tip annotatsiyasi yozilmaydi (Blender ularni property deb o'qiydi)."""

from __future__ import annotations

from .. import session
from . import host, perms


class SathPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sath"
    sath_module = ""  # api.register_classes to'ldiradi; "" — yadro paneli
    sath_needs = frozenset()  # {"login", "model"}
    sath_perm = ""  # masalan "sim.run" — bo'lmasa panel yashiriladi

    @classmethod
    def poll(cls, context):
        return visible(cls, context) and cls.sath_poll(context)

    @classmethod
    def sath_poll(cls, context) -> bool:
        """Modulga xos qo'shimcha shart (o'z poll i o'rniga shuni qayta yozing)."""
        return True


def visible(cls, context) -> bool:
    m = None
    if cls.sath_module:
        rec = host.record(cls.sath_module)
        if rec is None or rec.state != "enabled":
            return False
        m = rec.manifest
        ws = getattr(context, "workspace", None)
        tag = ws.get("sath_ws") if ws is not None else None
        if tag and m.workspaces and tag not in m.workspaces:  # tegsiz workspace (P4 gacha) — hammasi ko'rinadi
            return False
    needs = cls.sath_needs
    if ("login" in needs or "model" in needs or cls.sath_perm or (m is not None and m.visible_if_any)) and not session.is_logged_in():
        return False
    if "model" in needs and context.scene.ges.model_id <= 0:
        return False
    if m is not None and m.visible_if_any and not perms.any_of(m.visible_if_any, context):
        return False
    return not cls.sath_perm or perms.can(cls.sath_perm, context)


def draw_list(layout, s, coll: str, idx: str, rows: int = 4, refresh_op: str | None = None) -> None:
    """SATH_UL_simple ro'yxati + yangilash tugmasi."""
    row = layout.row()
    row.template_list("SATH_UL_simple", coll, s, coll, s, idx, rows=rows)
    if refresh_op:
        row.operator(refresh_op, text="", icon="FILE_REFRESH")


def cur(coll, idx: int):
    return coll[idx] if 0 <= idx < len(coll) else None
```

- [ ] **Step 6: `core/host.py` (minimal — Task 5 kengaytiradi) va `modules/__init__.py`**

`desktop/blender/sath/modules/__init__.py`: `"""Birinchi tomon Sath modullari (core/host.py topadi): har biri <id>/sath_module.toml + __init__.py."""`

`desktop/blender/sath/core/host.py`:

```python
"""Modul reyestrining Blender ulagichi (P3): sath/modules/ dagi modullarni topadi, tartib bilan yoqadi, o'chirishda
klass/menyu/obunalarni qaytaradi; 3D View «Sath» menyusiga modul bandlari. Sof qism — core/registry.py."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import bpy

from . import events, perms, registry

ROOT_PKG = __package__.rpartition(".")[0]  # "sath" (headless) yoki "bl_ext.user_default.sath"
BUNDLED = Path(__file__).resolve().parents[1] / "modules"
REG: registry.Registry | None = None
_menus: list[tuple[str, Callable]] = []
_offs: list[Callable[[], None]] = []


def record(mod_id: str) -> registry.Record | None:
    return REG.records.get(mod_id) if REG is not None else None


def is_enabled(mod_id: str) -> bool:
    return REG is not None and REG.is_enabled(mod_id)


def _import(m: registry.Manifest):
    if m.origin == "bundled":
        return importlib.import_module(f"{ROOT_PKG}.modules.{m.id}")
    name = f"_sath_user_{m.id}"
    spec = importlib.util.spec_from_file_location(name, m.path / "__init__.py", submodule_search_locations=[str(m.path)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def wanted(m: registry.Manifest) -> bool:
    return m.default_enabled  # Task 5: Sozlamalardagi tanlov


def scan() -> None:
    if REG is None:
        return
    manifests, errors = registry.discover(BUNDLED)
    REG.load(manifests, errors)
    REG.start(wanted)
    _redraw()


def add_menu(mod_id: str, draw: Callable) -> None:
    entry = (mod_id, draw)
    REG.add_cleanup(mod_id, lambda: _menus.remove(entry) if entry in _menus else None)
    _menus.append(entry)


def draw_menus(layout, context) -> None:
    for mod_id, draw in list(_menus):
        if is_enabled(mod_id):
            layout.separator()
            draw(layout, context)


def _redraw() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    for w in getattr(wm, "windows", ()):
        for a in w.screen.areas:
            a.tag_redraw()


def register() -> None:
    global REG
    from .. import api

    REG = registry.Registry(
        import_module=_import, register_class=bpy.utils.register_class, unregister_class=bpy.utils.unregister_class
    )
    REG.api = api
    _offs.append(events.subscribe("session.login", lambda _p: perms.clear()))
    _offs.append(events.subscribe("session.logout", lambda _p: perms.clear()))
    scan()


def unregister() -> None:
    global REG
    if REG is not None:
        REG.stop()
    for off in _offs:
        off()
    _offs.clear()
    _menus.clear()
    REG = None
```

- [ ] **Step 7: `api.py`**

```python
"""Sath modullari uchun barqaror fasad (spec §1). Modul `register(api)` / `unregister(api)` da faqat shu nomlardan
foydalanadi — ichki fayllar (ops_*.py, ui.py) o'zgarsa ham modul buzilmasin. Mos kelmaydigan o'zgarish
API_VERSION[0] ni oshiradi (manifestda `api = ">=1.0,<2"`).

  register_classes(mod_id, classes)  klasslar (SathPanel lar manifestdan bl_category/bl_order oladi), o'chirishda qaytadi
  adopt(mod_id, *fayllar)            mavjud faylning register()/unregister() juftini modulga biriktirish
  on_unregister(mod_id, fn)          o'chirishda chaqiriladigan tozalash
  session, tasks, perms, events, ui, props; dangasa: ifc, geom, kinds
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterable
from types import SimpleNamespace

import bpy

from . import props as _props
from . import session
from .core import events as _events
from .core import host as _host
from .core import perms as _perms
from .core.panels import SathPanel, cur, draw_list
from .core.registry import API_VERSION
from .core.tasks import TASKS
from .core.ui_tasks import ensure_pump, run_op

__all__ = ["API_VERSION", "adopt", "events", "module_enabled", "on_unregister", "perms", "props", "register_classes",
           "session", "tasks", "ui"]  # fmt: skip


def register_classes(mod_id: str, classes: Iterable[type]) -> None:
    rec = _host.REG.owner(mod_id)
    classes = list(classes)
    panels_open = bool(os.environ.get("SATH_PANELS_OPEN"))  # GUI sinovi: hammasi ochiq, «Item» yorlig'ida
    for c in classes:
        if issubclass(c, SathPanel):
            c.sath_module = mod_id
            c.bl_category = "Item" if panels_open else rec.manifest.category
            if "bl_order" not in c.__dict__:
                c.bl_order = rec.manifest.order
            if panels_open and "DEFAULT_CLOSED" in getattr(c, "bl_options", set()):
                c.bl_options = set(c.bl_options) - {"DEFAULT_CLOSED"}
    _host.REG.add_classes(mod_id, classes)


def adopt(mod_id: str, *files) -> None:
    """Mavjud fayllarni (ops_*.py, ges_objects …) modulga biriktiradi: register() hozir, unregister() o'chirishda
    (teskari tartibda). Fayl register() i yarim yiqilsa — o'z unregister() i bilan tozalanadi."""
    _host.REG.owner(mod_id)
    for f in files:
        try:
            f.register()
        except Exception:
            try:
                f.unregister()
            except Exception:  # noqa: BLE001 — qisman ro'yxatdan o'tgan bo'lishi mumkin
                pass
            raise
        _host.REG.add_cleanup(mod_id, f.unregister)


def on_unregister(mod_id: str, fn: Callable[[], None]) -> None:
    _host.REG.add_cleanup(mod_id, fn)


def module_enabled(mod_id: str) -> bool:
    return _host.is_enabled(mod_id)


class events:
    publish = staticmethod(_events.publish)

    @staticmethod
    def subscribe(topic: str, fn: Callable[[dict], None], *, owner: str | None = None) -> Callable[[], None]:
        """owner berilsa — modul o'chirilganda obuna avtomatik bekor bo'ladi."""
        if owner:
            _host.REG.owner(owner)
        off = _events.subscribe(topic, fn)
        if owner:
            _host.REG.add_cleanup(owner, off)
        return off


class tasks:
    run_op = staticmethod(run_op)
    drain = staticmethod(TASKS.drain)

    @staticmethod
    def run(title, fn, on_done=None, on_error=None, *, key=None, cancellable=True, quiet=False):
        """Fon vazifasi + pompa. fn ishchi oqimda (bpy ga TEGMAYDI). Kalit `<mod_id>.` bilan boshlansin —
        modul o'chirilganda shunday vazifalar bekor qilinadi."""
        t = TASKS.run(title, fn, on_done, on_error, key=key, cancellable=cancellable, quiet=quiet)
        ensure_pump()
        return t


class perms:
    can = staticmethod(_perms.can)
    any_of = staticmethod(_perms.any_of)
    require = staticmethod(_perms.require)
    role = staticmethod(_perms.role)
    poll = staticmethod(_perms.poll)


class ui:
    SathPanel = SathPanel
    draw_list = staticmethod(draw_list)
    cur = staticmethod(cur)

    @staticmethod
    def main_menu(mod_id: str, draw: Callable) -> None:
        """3D View «Sath» menyusiga band: draw(layout, context)."""
        _host.add_menu(mod_id, draw)

    @staticmethod
    def keymap(mod_id: str, idname: str, key: str, *, ctrl=False, shift=False, alt=False, km_name="3D View",
               space_type="VIEW_3D", **properties):  # fmt: skip
        kc = bpy.context.window_manager.keyconfigs.addon
        if kc is None:  # fon rejimi
            return None
        km = kc.keymaps.new(name=km_name, space_type=space_type)
        kmi = km.keymap_items.new(idname, key, "PRESS", ctrl=ctrl, shift=shift, alt=alt)
        for k, v in properties.items():
            setattr(kmi.properties, k, v)
        _host.REG.add_cleanup(mod_id, lambda: km.keymap_items.remove(kmi))
        return kmi


class props:
    @staticmethod
    def scene_group(mod_id: str, cls: type) -> str:
        """Modul holati: Scene.sath_<mod_id> (PointerProperty); props.snapshot_scene/restore_scene ga avtomatik
        kiradi (Bonsai yangi sessiyasidan omon qoladi). Qaytaradi: atribut nomi."""
        attr = f"sath_{mod_id}"
        _host.REG.add_classes(mod_id, [cls])
        setattr(bpy.types.Scene, attr, bpy.props.PointerProperty(type=cls))
        _props.GROUPS[attr] = mod_id

        def off() -> None:
            _props.GROUPS.pop(attr, None)
            if hasattr(bpy.types.Scene, attr):
                delattr(bpy.types.Scene, attr)

        _host.REG.add_cleanup(mod_id, off)
        return attr


def __getattr__(name: str):
    """Dangasa: api.ifc (+ IfcOperator, restore_ges — P2 da bo'lsa), api.geom, api.kinds (numpy)."""
    if name == "ifc":
        from . import ifc as m

        ns = SimpleNamespace(file=m.file, load=m.load, save=m.save, entity=m.entity, guid=m.guid, guid_map=m.guid_map,
                             object_for_guid=m.object_for_guid, select_guids=m.select_guids)  # fmt: skip
        try:
            from .core.ifc_ops import IfcOperator

            ns.IfcOperator = IfcOperator
        except ImportError:
            pass
        try:
            from .ges_objects import restore_from_ifc

            ns.restore_ges = restore_from_ifc
        except ImportError:
            pass
        globals()["ifc"] = ns
        return ns
    if name in ("geom", "kinds"):
        mod = importlib.import_module(".shared." + ("geom" if name == "geom" else "ges_kinds"), __package__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

Boshlashdan oldin P2 nomlarini tekshiring: `rg -n "class IfcOperator|def restore_from_ifc" desktop/blender/sath` — boshqa nom bo'lsa `__getattr__` dagi importni moslang.

- [ ] **Step 8: `task.*` hodisalari** — `core/ui_tasks.py`: importga `from . import events`; funksiya:

```python
def _task_finished(task: Task, outcome: str) -> None:
    events.publish(f"task.{outcome}", id=task.id, key=task.key or "", title=task.title)
```

`register()` da `TASKS.on_error_default = _default_error` dan keyin `TASKS.on_finished = _task_finished`; `unregister()` da `TASKS.on_error_default = _DEFAULT_ON_ERROR` dan keyin `TASKS.on_finished = None`.

`core/events.py` docstringidagi mavzular qatori: `Mavzular: session.login {user}, session.logout {}, project.changed {project_id}, ifc.loaded {path}, scada.snapshot {data}, task.done|task.failed|task.cancelled {id, key, title}.`

- [ ] **Step 9: Yadro operatorlarida ruxsat** — `ops_server.py` importiga `from .core import perms`.

`SATH_OT_commit.poll`:

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and ifc.file() is not None and perms.poll(cls, "model.write", context)
```

`SATH_OT_submit.poll`:

```python
    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and bool(s.model_id and s.version_id) and perms.poll(cls, "cr.create", context)
```

`SATH_OT_create_model` ga (bl_label dan keyin):

```python
    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        return session.is_logged_in() and p is not None and perms.poll(cls, "model.write", context, project_id=p.item_id)
```

`open_version.apply` va `pull_head.apply` da: `snap = props.snapshot(bpy.context.scene.ges)` → `snap = props.snapshot_scene(bpy.context.scene)`; `props.restore(bpy.context.scene.ges, snap)` → `props.restore_scene(bpy.context.scene, snap)`.

- [ ] **Step 10: `ui.py`**

- Importlar: `from .core import host, perms` va `from .core.panels import cur, draw_list`; mahalliy `_list` va `_cur` funksiyalarini o'chiring, fayldagi barcha `_list(` → `draw_list(`, `_cur(` → `cur(`.
- `SATH_PT_server`: `bl_order = 0`; `SATH_PT_model`: `bl_order = 1`; `SATH_PT_notifications`: `bl_order = 1000` (modul panellari manifest `order` i bilan 20…70 oralig'ida turadi).
- `SATH_PT_model.draw` dagi tugma qatorlari:

```python
        row = lay.row(align=True)
        row.operator("sath.open_version", icon="IMPORT")
        if perms.can("model.write", context):  # spec §2: viewer da commit ko'rinmaydi
            row.operator("sath.commit", icon="EXPORT")
```

```python
        row = lay.row(align=True)
        if perms.can("cr.create", context):
            row.operator("sath.submit", icon="CHECKMARK")
        row.operator("sath.open_web", icon="URL")
```

  (`sath.create_model` tugmasi qoladi — poll sababi bilan kulrang.)
- `SATH_MT_main.draw`: `lay.operator("sath.notifications")` ni `lay.operator("sath.open_web")` dan keyinga ko'chiring (yadro bloki) va metod oxiriga `host.draw_menus(lay, context)`. Qolgan modul bandlari (add_object, import, sim, monitor) hozircha joyida — har migratsiya o'zinikini oladi.

- [ ] **Step 11: `sath/__init__.py`** (CRLF!): `from .core import ui_tasks` → `from .core import host, ui_tasks`; `MODULES` ro'yxati oxiriga `, host` (`ui` dan keyin). Commit oldidan `git ls-files --eol desktop/blender/sath/__init__.py` → `i/crlf w/crlf`.

- [ ] **Step 12: `smoke.py`** oxiriga:

```python
    from sath import api
    from sath.core import host

    assert api.API_VERSION == (1, 0) and host.REG is not None and host.REG.broken == []
    assert "perms" in bpy.types.GesListItem.bl_rna.properties
```

- [ ] **Step 13: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests` → PASS (perms 7 + flows assert)
Run: `.venv\Scripts\ruff.exe check desktop` → toza
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0` (smoke, ops_async — engineer roli zaxiradan; review_ops, sim_ops, monitor_ops o'zgarishsiz)
Server bilan (`$env:GES_TEST_SERVER`): `e2e_server`, `commit_conflict` OK (commit_conflict: loyiha ro'yxatda yo'q → `perms._fetch` inline so'raydi).

- [ ] **Step 14: Commit**

```bash
git add desktop/blender/sath/core/perms.py desktop/blender/sath/core/panels.py desktop/blender/sath/core/host.py desktop/blender/sath/api.py desktop/blender/sath/modules/__init__.py desktop/blender/sath/props.py desktop/blender/sath/flows.py desktop/blender/sath/ops_server.py desktop/blender/sath/ui.py desktop/blender/sath/core/ui_tasks.py desktop/blender/sath/core/events.py desktop/blender/sath/__init__.py desktop/tests/test_sath_perms.py desktop/tests/test_sath_flows.py desktop/tests/sath_tests/smoke.py
git commit -m "feat(ROLE,MOD): core/perms (server ruxsatlari + rol zaxirasi), SathPanel, api.py fasadi, modul xosti; commit/submit/yangi model ruxsat bilan, task.* va project.changed hodisalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Sozlamalardagi modullar ro'yxati, jonli yoqish/o'chirish, uchinchi tomon modullari; headless `modules`

**Model:** opus — jonli unregister nozikliklari (PointerProperty/menyu/obuna qaytishi, vazifa bekor qilish, qayta skanerda imzo).

**Files:**
- Modify: `desktop/blender/sath/core/host.py` (foydalanuvchi papkasi, kalitlar, holat, `set_enabled`, operatorlar, `draw_prefs`)
- Modify: `desktop/blender/sath/prefs.py` (`allow_user_modules`, `module_public_keys`, `module_states`, `draw`)
- Create: `desktop/tests/sath_tests/modules.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`@("modules", "--bonsai")`)

**Interfaces:**
- Consumes: Task 3 `registry.discover/decode_keys`, `TASKS.cancel_prefix`, `sign_module`; Task 4 host/api.
- Produces: `host.PINNED: frozenset[str]`, `host.user_dir() -> Path | None` (env `SATH_USER_MODULES` ustun), `host.wanted(m)`, `host.set_enabled(id, on) -> list[str]`, `host.draw_prefs(layout)`; operatorlar `sath.module_toggle(module_id)`, `sath.modules_rescan`; prefs `allow_user_modules: bool`, `module_public_keys: str` (env `SATH_MODULE_PUBLIC_KEYS`), `module_states: str` (JSON `{id: bool}`).

- [ ] **Step 1: Ro'yxatdan chiqqan operatorni aniqlash usulini tasdiqlang**

Run: `& $env:GES_BLENDER -b --python-expr "import bpy; bpy.ops.sath.yoq_test.get_rna_type()" 2>&1 | Select-String "Error"`
Expected: `KeyError` (yoki boshqa xato). Agar xato chiqmasa, quyidagi `_registered` ni `hasattr(bpy.types, "SATH_OT_" + op)` ga almashtiring.

- [ ] **Step 2: Yiqiluvchi headless test** `desktop/tests/sath_tests/modules.py`:

```python
"""P3 modul tizimi (headless): imzolangan foydalanuvchi moduli jonli yoqiladi/o'chiriladi (panel, operator, sahna
guruhi, hodisa, menyu qaytadi; fon vazifasi bekor qilinadi), yiqilgan modul izolyatsiya qilinadi, imzosiz yoki
o'zgartirilgan modul yuklanmaydi. Keyingi vazifalar birinchi tomon modullari va rolga sezgir UI tekshiruvlarini qo'shadi."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]

HELLO_PY = '''"""Test moduli (P3)."""
import bpy

HITS = []


class HelloProps(bpy.types.PropertyGroup):
    count: bpy.props.IntProperty()


class SATH_OT_hello_test(bpy.types.Operator):
    bl_idname = "sath.hello_test"
    bl_label = "Salom"

    def execute(self, context):
        context.scene.sath_hello.count += 1
        return {"FINISHED"}


def register(api):
    class SATH_PT_hello_test(api.ui.SathPanel, bpy.types.Panel):
        bl_label = "Salom"

        def draw(self, context):
            self.layout.operator("sath.hello_test")

    api.props.scene_group("hello", HelloProps)
    api.register_classes("hello", [SATH_OT_hello_test, SATH_PT_hello_test])
    api.events.subscribe("project.changed", HITS.append, owner="hello")
    api.ui.main_menu("hello", lambda layout, context: layout.operator("sath.hello_test"))
'''

BROKEN_PY = '''import bpy


class SATH_OT_broken_test(bpy.types.Operator):
    bl_idname = "sath.broken_test"
    bl_label = "Yiqiluvchi"

    def execute(self, context):
        return {"FINISHED"}


def register(api):
    api.register_classes("broken", [SATH_OT_broken_test])
    raise RuntimeError("ataylab yiqildi")
'''


def _toml(mid: str) -> str:
    return f'id = "{mid}"\nname = "{mid} (test)"\nversion = "1.0.0"\napi = ">=1.0,<2"\norder = 900\n'


def _registered(op: str) -> bool:
    """bpy.ops.sath.<op> ro'yxatdami (ro'yxatdan chiqqanda get_rna_type xato beradi)."""
    try:
        getattr(bpy.ops.sath, op).get_rna_type()
    except Exception:  # noqa: BLE001
        return False
    return True


def _user_modules():
    from sath import props
    from sath.core import events, host
    from sath.core.tasks import TASKS
    from sath.prefs import prefs

    sys.path.insert(0, str(ROOT / "desktop" / "build"))
    import sign_module

    seed = bytes(range(32))
    tmp = Path(tempfile.mkdtemp(prefix="sath_mod_"))
    for mid, code in (("hello", HELLO_PY), ("broken", BROKEN_PY), ("unsigned", HELLO_PY)):
        d = tmp / mid
        d.mkdir()
        (d / "sath_module.toml").write_text(_toml(mid), encoding="utf-8")
        (d / "__init__.py").write_text(code, encoding="utf-8")
        if mid != "unsigned":
            sign_module.sign_module(d, seed)
    p = prefs()
    os.environ["SATH_USER_MODULES"] = str(tmp)
    p.module_public_keys = base64.b64encode(sign_module.public_key(seed)).decode()
    p.allow_user_modules = True  # update callback skanerlaydi; quyidagi scan — aniq bo'lishi uchun
    host.scan()
    s = bpy.context.scene
    try:
        rec = host.record("hello")
        assert rec is not None and rec.state == "enabled", (rec, host.REG.broken)
        assert rec.manifest.origin == "user"
        pt = bpy.types.SATH_PT_hello_test
        assert pt.bl_category == "Sath" and pt.bl_order == 900 and _registered("hello_test")
        assert bpy.ops.sath.hello_test() == {"FINISHED"} and s.sath_hello.count == 1
        snap = props.snapshot_scene(s)
        s.sath_hello.count = 7
        props.restore_scene(s, snap)
        assert s.sath_hello.count == 1
        events.publish("project.changed", project_id=1)
        assert rec.module.HITS == [{"project_id": 1}]
        assert "hello" in [m for m, _ in host._menus]

        bad = host.record("broken")
        assert bad.state == "failed" and "ataylab yiqildi" in bad.error and not _registered("broken_test")
        assert any(label.startswith("unsigned") and "imzolanmagan" in msg for label, msg in host.REG.broken)

        TASKS.inline = False  # Review Focus 1: modul o'chganda uning fon vazifasi bekor qilinadi
        try:
            t = TASKS.run("uzun", lambda c: c.sleep(5), key="hello.uzun")
            assert host.set_enabled("hello", False) == ["hello"]
            assert t.cancelled
            TASKS.drain(5)
        finally:
            TASKS.inline = True
        assert not hasattr(bpy.types, "SATH_PT_hello_test") and not _registered("hello_test")
        assert not hasattr(bpy.types.Scene, "sath_hello") and "hello" not in [m for m, _ in host._menus]
        events.publish("project.changed", project_id=2)
        assert rec.module.HITS == [{"project_id": 1}]  # obuna bekor bo'ldi
        assert json.loads(p.module_states)["hello"] is False

        assert bpy.ops.sath.module_toggle(module_id="hello") == {"FINISHED"}
        assert host.is_enabled("hello") and _registered("hello_test")
        assert s.sath_hello.count == 1  # sahnadagi ma'lumot o'chirib-yoqishdan omon qoldi

        (tmp / "hello" / "__init__.py").write_text(HELLO_PY + "\n# o'zgartirildi\n", encoding="utf-8")
        assert bpy.ops.sath.modules_rescan() == {"FINISHED"}
        assert host.record("hello") is None and not _registered("hello_test")
        assert any(label.startswith("hello") and "imzo" in msg for label, msg in host.REG.broken)
    finally:
        p.allow_user_modules = False
        host.scan()
        os.environ.pop("SATH_USER_MODULES", None)
        shutil.rmtree(tmp, ignore_errors=True)
    assert host.record("broken") is None and host.REG.broken == []


def run(ctx):
    _user_modules()
```

`run_blender_tests.ps1` dagi `$tests` ro'yxatiga `@("modules", "--bonsai")` (`ops_async` dan keyin).

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai 2>&1 | Select-String "OK|FAIL|Error"`
Expected: `[FAIL] modules` (`allow_user_modules` yo'q).

- [ ] **Step 3: `prefs.py`** — `GesPrefs` dan oldin:

```python
def _on_allow_user(self, context):
    from .core import host

    host.scan()
```

`update_public_key` dan keyin:

```python
    # P3: uchinchi tomon modullari — faqat ishonchli kalit bilan imzolanganlari (yangilanish kaliti ham ishonchli)
    allow_user_modules: bpy.props.BoolProperty(
        name="Uchinchi tomon modullari",
        default=False,
        description="Foydalanuvchi papkasidagi (sath_modules) modullarni yuklash — faqat imzolanganlari",
        update=_on_allow_user,
    )
    module_public_keys: bpy.props.StringProperty(
        name="Modul kalitlari",
        default=os.environ.get("SATH_MODULE_PUBLIC_KEYS", ""),
        description="Ishonchli modul nashriyotchilarining Ed25519 ochiq kalitlari (base64, vergul bilan)",
    )
    module_states: bpy.props.StringProperty(default="{}", options={"HIDDEN"})  # {"review": false, …}
```

`draw()` oxiriga:

```python
        from .core import host

        host.draw_prefs(self.layout)
```

- [ ] **Step 4: `core/host.py` kengaytmasi** — importlarga `import json`, `import os`, `from .tasks import TASKS`; `REG` dan keyin `PINNED: frozenset[str] = frozenset()  # o'chirib bo'lmaydigan (Task 6: legacy)`. Task 4 dagi `wanted` va `scan` ni almashtiring va qo'shing:

```python
def user_dir() -> Path | None:
    env = os.environ.get("SATH_USER_MODULES")
    if env:
        return Path(env)
    p = bpy.utils.user_resource("CONFIG", path="sath_modules")
    return Path(p) if p else None


def _states() -> dict[str, bool]:
    from ..prefs import prefs

    try:
        d = json.loads(prefs().module_states or "{}")
    except ValueError:
        return {}
    return {str(k): bool(v) for k, v in d.items()} if isinstance(d, dict) else {}


def _save_states(changes: dict[str, bool]) -> None:
    from ..prefs import prefs

    d = _states()
    d.update(changes)
    prefs().module_states = json.dumps(d, sort_keys=True)


def wanted(m: registry.Manifest) -> bool:
    return m.id in PINNED or _states().get(m.id, m.default_enabled)


def scan() -> None:
    """Bundle + (ruxsat bo'lsa) foydalanuvchi papkasini qayta ko'radi; o'zgarmagan modullar holati saqlanadi."""
    if REG is None:
        return
    from ..prefs import prefs

    p = prefs()
    keys = registry.decode_keys([p.update_public_key, p.module_public_keys, os.environ.get("SATH_MODULE_PUBLIC_KEYS", "")])
    manifests, errors = registry.discover(BUNDLED, user_dir() if p.allow_user_modules else None, keys)
    REG.load(manifests, errors)
    REG.start(wanted)
    _redraw()


def set_enabled(mod_id: str, on: bool) -> list[str]:
    """Jonli yoqish/o'chirish (bog'liqliklar bilan kaskad). Qaytaradi: holati o'zgargan modullar."""
    if REG is None or mod_id not in REG.records or mod_id in PINNED:
        return []
    changed = REG.enable(mod_id) if on else REG.disable(mod_id)
    if not on:
        for i in changed:
            TASKS.cancel_prefix(f"{i}.")
    _save_states({**dict.fromkeys(changed, on), mod_id: on})
    _redraw()
    return changed


class SATH_OT_module_toggle(bpy.types.Operator):
    """Sath modulini yoqish yoki o'chirish (Blender qayta ishga tushmaydi)"""

    bl_idname = "sath.module_toggle"
    bl_label = "Modulni yoqish/o'chirish"
    bl_options = {"INTERNAL"}
    module_id: bpy.props.StringProperty()

    def execute(self, context):
        rec = record(self.module_id)
        if rec is None or self.module_id in PINNED:
            return {"CANCELLED"}
        on = not wanted(rec.manifest)
        changed = set_enabled(self.module_id, on)
        if on and rec.state != "enabled":
            self.report({"ERROR"}, f"{rec.manifest.name}: yuklanmadi — sababi modullar ro'yxatida")
            return {"CANCELLED"}
        others = [REG.records[i].manifest.name for i in changed if i != self.module_id]
        if others:
            self.report({"INFO"}, ("Birga yoqildi: " if on else "Birga o'chirildi: ") + ", ".join(others))
        return {"FINISHED"}


class SATH_OT_modules_rescan(bpy.types.Operator):
    """Modul papkalarini qayta ko'rib chiqish (yangi yoki o'zgargan uchinchi tomon modullari)"""

    bl_idname = "sath.modules_rescan"
    bl_label = "Qayta skanerlash"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        scan()
        return {"FINISHED"}


CLASSES = (SATH_OT_module_toggle, SATH_OT_modules_rescan)


def draw_prefs(layout) -> None:
    """Sozlamalar → Sath: Blender Add-ons ro'yxati kabi (belgi, versiya, ruxsatlar, register vaqti, xato)."""
    from ..prefs import prefs

    box = layout.box()
    box.label(text="Modullar", icon="PLUGIN")
    if REG is None:
        box.label(text="Modul reyestri ishlamayapti", icon="ERROR")
        return
    for rid, rec in REG.records.items():
        m = rec.manifest
        row = box.row(align=True)
        if rid in PINNED:
            row.label(text="", icon="LOCKED")
        else:
            on = wanted(m)
            row.operator("sath.module_toggle", text="", icon="CHECKBOX_HLT" if on else "CHECKBOX_DEHLT",
                         emboss=False).module_id = rid  # fmt: skip
        row.label(text=f"{m.name}  {m.version}", icon={"enabled": "CHECKMARK", "failed": "ERROR"}.get(rec.state, "BLANK1"))
        row.label(text=("foydalanuvchi · " if m.origin == "user" else "") + f"{m.category} · {rec.ms:.0f} ms")
        info = []
        if m.permissions:
            info.append("Ruxsatlar: " + ", ".join(m.permissions))
        if m.requires:
            info.append("Talab: " + ", ".join(m.requires))
        if info:
            box.label(text="      " + "   ".join(info))
        if rec.error:
            err = box.box()
            for line in rec.error.strip().splitlines()[-12:]:
                err.label(text=line[:140])
    for label, msg in REG.broken:
        box.label(text=f"{label}: {msg}"[:160], icon="CANCEL")
    p = prefs()
    col = layout.column()
    col.prop(p, "allow_user_modules")
    if p.allow_user_modules:
        col.prop(p, "module_public_keys")
        d = user_dir()
        col.label(text=f"Papka: {d}" if d else "Papka: aniqlanmadi")
        col.operator("sath.modules_rescan", icon="FILE_REFRESH")
```

`register()` da `REG.api = api` dan keyin: `for c in CLASSES: bpy.utils.register_class(c)`; `unregister()` da `_menus.clear()` dan keyin: `for c in reversed(CLASSES): bpy.utils.unregister_class(c)`.

- [ ] **Step 5: Tekshiring**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai 2>&1 | Select-String "OK|FAIL"` → `[OK] modules`
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0`
Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests; .venv\Scripts\ruff.exe check desktop` → PASS, toza

- [ ] **Step 6: Commit**

```bash
git add desktop/blender/sath/core/host.py desktop/blender/sath/prefs.py desktop/tests/sath_tests/modules.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(MOD): Sozlamalarda modullar ro'yxati — jonli yoqish/o'chirish (kaskad, vazifalar bekor), xato izolyatsiyasi va traceback, imzolangan uchinchi tomon modullari; headless modules testi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `legacy` psevdo-modul (strangler A qadam — xatti-harakat o'zgarmaydi)

**Model:** sonnet — P2 dan keyingi `MODULES` ro'yxatiga moslash kerak, ko'p faylli ulash.

**Files:**
- Create: `desktop/blender/sath/modules/legacy/sath_module.toml`, `modules/legacy/__init__.py`
- Modify: `desktop/blender/sath/__init__.py` (**CRLF**; `MODULES` = yadro + host)
- Modify: `desktop/blender/sath/core/host.py` (`PINNED = frozenset({"legacy"})`)
- Test: `desktop/tests/sath_tests/modules.py` (`_legacy_pinned`), `desktop/tests/test_sath_registry.py` (`test_bundled_manifests_valid`)

**Interfaces:**
- Produces: `sath.modules.legacy.FILES: list` — hali modulga ko'chirilmagan fayllar (avvalgi `MODULES` tartibida); keyingi har vazifa o'z faylini shu ro'yxatdan oladi.

- [ ] **Step 1: Joriy ro'yxatni oling** — `sath/__init__.py` dagi `MODULES` (P2 dan keyin). Kutilgan (P2 qo'shgan fayllar bo'lsa — ularni ham, o'sha tartibda): `[ui_tasks, prefs, props, ges_objects, ops_server, ops_review, ops_sim, ops_twin, demo_plant, ops_monitor, ops_import, ui, host]`. `FILES` = shundan `ui_tasks, prefs, props, host` olib tashlanganlari.

- [ ] **Step 2: Yiqiluvchi testlar** — `modules.py` ga:

```python
def _legacy_pinned():
    from sath.core import host

    assert host.is_enabled("legacy") and host.set_enabled("legacy", False) == [] and host.is_enabled("legacy")
    assert hasattr(bpy.types, "SATH_PT_server") and _registered("commit") and _registered("connect")
```

`run()` ga `_user_modules()` dan keyin `_legacy_pinned()`.

`test_sath_registry.py` oxiriga:

```python
def test_bundled_manifests_valid():
    """Bundle dagi har modul manifesti yaroqli, bog'liqliklari yechiladi, ko'rinish ruxsatlari serverda bor."""
    from sath.shared.permissions import ALL

    found, errors = registry.discover(ROOT / "desktop" / "blender" / "sath" / "modules")
    assert errors == []
    ordered, bad = registry.resolve(found)
    assert bad == {} and len(ordered) == len(found) >= 1
    for m in found:
        assert set(m.visible_if_any) <= ALL, m.id
        assert set(m.workspaces) <= {"BIM", "Compare", "Simulation", "SCADA"}, m.id
```

Run: pytest → FAIL (`found` bo'sh); headless `modules` → FAIL.

- [ ] **Step 3: `modules/legacy/sath_module.toml`**

```toml
id = "legacy"
name = "Sath (o'tish davri: hali modulga ko'chirilmagan qismlar)"
version = "0.3.0"
api = ">=1.0,<2"
requires = []
permissions = ["network", "files", "subprocess", "ifc.write"]
visible_if_any = []
workspaces = []
category = "Sath"
default_enabled = true
order = 0
```

- [ ] **Step 4: `modules/legacy/__init__.py`**

```python
"""O'tish davri psevdo-moduli (spec §1 strangler, A qadam): hali modulga ko'chirilmagan fayllar — o'zgarishsiz va
avvalgi tartibda ro'yxatga olinadi. B qadamda har modul o'z faylini FILES dan oladi; ro'yxatda faqat yadro fayllari
(ops_server, ui) qolganda ular sath/__init__.py ga qaytadi va bu modul o'chiriladi (Task 13)."""

from __future__ import annotations

from ... import demo_plant, ges_objects, ops_import, ops_monitor, ops_review, ops_server, ops_sim, ops_twin, ui

FILES = [ges_objects, ops_server, ops_review, ops_sim, ops_twin, demo_plant, ops_monitor, ops_import, ui]


def register(api):
    api.adopt("legacy", *FILES)  # o'chirishda unregister() teskari tartibda — avvalgi sath.unregister bilan bir xil
```

(Step 1 da P2 qo'shgan fayl bo'lsa — import va `FILES` ga xuddi `MODULES` dagi o'rnida qo'shing.)

- [ ] **Step 5: `sath/__init__.py`** (CRLF) — `if bpy is not None:` blokini almashtiring:

```python
if bpy is not None:
    from . import prefs, props
    from .core import host, ui_tasks

    # P3: qolgan hammasi sath/modules/ da — host topadi va yoqadi (legacy — o'tish davri)
    MODULES = [ui_tasks, prefs, props, host]
```

Modul docstringidagi tavsifni saqlang. `host.py`: `PINNED = frozenset({"legacy"})  # o'tish davri: o'chirib bo'lmaydi (Task 13 da bo'shaydi)`.

- [ ] **Step 6: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_registry.py` → PASS
Run: `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0` (barcha eski testlar o'zgarishsiz o'tadi — A qadamning mezoni)
Run: `git ls-files --eol desktop/blender/sath/__init__.py` → `i/crlf w/crlf`

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/modules/legacy desktop/blender/sath/__init__.py desktop/blender/sath/core/host.py desktop/tests/sath_tests/modules.py desktop/tests/test_sath_registry.py
git commit -m "refactor(MOD): legacy psevdo-modul (strangler A) — eski fayllar reyestr orqali o'zgarishsiz ro'yxatga olinadi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `review` moduli

**Model:** sonnet — panel ko'chishi + ruxsat mantiqi + jonli test.

**Ko'chadi:** `ui.py::SATH_PT_review` → `modules/review/__init__.py` (SathPanel, ruxsatga sezgir tugmalar); `ops_review` (12 operator: `refresh_issues, show_issue, goto_view, comment_issue, new_issue, refresh_crs, show_cr, decide, merge_cr, reject_cr, diff, clear_diff`) — `api.adopt`. Menyu bandi yo'q.

**Files:**
- Create: `desktop/blender/sath/modules/review/sath_module.toml`, `modules/review/__init__.py`
- Modify: `desktop/blender/sath/ui.py` (`SATH_PT_review` va `CLASSES` dan o'chiriladi)
- Modify: `desktop/blender/sath/ops_review.py` (ruxsatlar; `my_role` — `perms.role`)
- Modify: `desktop/blender/sath/modules/legacy/__init__.py` (`ops_review` olib tashlanadi)
- Test: `desktop/tests/sath_tests/modules.py` (`_review_live`)

**Interfaces:**
- Consumes: `api.adopt`, `api.register_classes`, `perms.can/role/poll`, `SathPanel`.
- Produces: modul `review` (order 20, `visible_if_any = ["project.read"]`); vazifa kaliti `review.diff` (mavjud).

- [ ] **Step 1: Yiqiluvchi test** — `modules.py`:

```python
def _review_live():
    """Spec P3 mezoni: review jonli o'chadi va yonadi; yadro tegilmaydi."""
    from sath.core import host

    s = bpy.context.scene.ges
    assert host.is_enabled("review") and hasattr(bpy.types, "SATH_PT_review") and _registered("diff")
    s.diff_note = "v1: eski"
    assert host.set_enabled("review", False) == ["review"]
    assert not hasattr(bpy.types, "SATH_PT_review") and not _registered("diff") and not _registered("decide")
    assert s.diff_note == ""  # modul unregister: diff ranglari tiklandi, izoh tozalandi
    assert _registered("commit") and hasattr(bpy.types, "SATH_PT_model")
    assert host.set_enabled("review", True) == ["review"]
    assert hasattr(bpy.types, "SATH_PT_review") and bpy.ops.sath.clear_diff() == {"FINISHED"}
```

`run()` ga `_review_live()`. Run headless `modules` → FAIL (`review` yo'q).

- [ ] **Step 2: `modules/review/sath_module.toml`**

```toml
id = "review"
name = "Taqriz va issue lar"
version = "1.0.0"
api = ">=1.0,<2"
requires = []
permissions = ["network"]
visible_if_any = ["project.read"]
workspaces = ["BIM", "Compare"]
category = "Sath"
default_enabled = true
order = 20
```

- [ ] **Step 3: `modules/review/__init__.py`**

```python
"""Taqriz moduli: versiyalar farqi (3D rang), issue lar (BCF ko'rinish), tasdiqlash so'rovlari (CR) — rolga sezgir."""

from __future__ import annotations

import bpy

from ... import ifc, ops_review
from ...core import perms
from ...core.panels import SathPanel, cur, draw_list


class SATH_PT_review(SathPanel, bpy.types.Panel):
    bl_label = "Taqriz va issue lar"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        box = lay.box()
        box.label(text="Versiyalar farqi", icon="SELECT_DIFFERENCE")
        row = box.row(align=True)
        row.operator("sath.diff")
        row.operator("sath.clear_diff", text="", icon="X")
        if s.diff_note:
            box.label(text=s.diff_note)

        box = lay.box()
        box.label(text="Issue lar", icon="ERROR")
        draw_list(box, s, "issues", "issues_index", 4, "sath.refresh_issues")
        for line in s.issue_detail.splitlines()[:8]:
            box.label(text=line)
        row = box.row(align=True)
        row.operator("sath.goto_view", icon="CAMERA_DATA")
        if perms.can("issue.write", context):
            row.operator("sath.new_issue", icon="ADD")
            row = box.row(align=True)
            row.prop(s, "comment_text", text="")
            row.operator("sath.comment_issue", text="", icon="PLAY")

        box = lay.box()
        role = perms.role(context)
        box.label(text="Tasdiqlash so'rovlari" + (f" · {role}" if role else ""), icon="CHECKMARK")
        draw_list(box, s, "crs", "crs_index", 4, "sath.refresh_crs")
        for line in s.cr_detail.splitlines()[:8]:
            box.label(text=line)
        cr = cur(s.crs, s.crs_index)
        st = cr.col4 if cr else ""
        open_ = st in ("open", "changes_requested", "approved")
        can_approve, can_review = perms.can("cr.approve", context), perms.can("cr.review", context)
        if can_approve or can_review:  # spec §2: viewer/engineer da qaror tugmalari ko'rinmaydi
            row = box.row(align=True)
            r1 = row.row()
            r1.enabled = can_approve and open_ and st != "approved"
            r1.operator("sath.decide", text="Ma'qullash").decision = "approve"
            r2 = row.row()
            r2.enabled = can_review and open_
            r2.operator("sath.decide", text="O'zgartirish so'rash").decision = "request_changes"
        row = box.row(align=True)
        if perms.can("cr.merge", context):
            r1 = row.row()
            r1.enabled = st == "approved"
            r1.operator("sath.merge_cr")
        r2 = row.row()
        r2.enabled = bool(cr) and st not in ("merged", "rejected")
        r2.operator("sath.reject_cr")  # muallif o'z CR ini qaytarib olishi mumkin — ruxsat serverda
        box.operator("sath.decide", text="Faqat izoh qoldirish").decision = "comment"


def register(api):
    api.adopt("review", ops_review)
    api.register_classes("review", [SATH_PT_review])


def unregister(api):
    ifc.DIFF_STATE.restore()  # o'chirilgan modulning 3D ranglari qolmasin
    bpy.context.scene.ges.diff_note = ""
```

- [ ] **Step 4: `ops_review.py`** — importga `from .core import perms`.

`SATH_OT_new_issue` va `SATH_OT_comment_issue` ga (bl_label/bl_idname dan keyin):

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and perms.poll(cls, "issue.write", context)
```

`SATH_OT_merge_cr` ga:

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and perms.poll(cls, "cr.merge", context)
```

`SATH_OT_decide.execute` boshida (`s = context.scene.ges` dan oldin):

```python
        need = {"approve": "cr.approve", "request_changes": "cr.review"}.get(self.decision)
        if need and not perms.can(need, context):  # izoh qoldirish hammaga ochiq
            self.report({"ERROR"}, f"Ruxsat yo'q: {need}")
            return {"CANCELLED"}
```

`SATH_OT_refresh_crs.execute::do` dagi `s.my_role = flows.model_role(session.client(), s.model_id) or ""` → `s.my_role = perms.role(context)` (tarmoq so'rovi yo'q; `flows.model_role` faylda qoladi — `test_sath_flows` ishlatadi).

- [ ] **Step 5: `ui.py`** — `SATH_PT_review` klassini va `CLASSES` dagi nomini o'chiring. `legacy/__init__.py` — `ops_review` ni import va `FILES` dan olib tashlang.

- [ ] **Step 6: Tekshiring**

Run headless `modules` → `[OK] modules`; `.\desktop\tests\run_blender_tests.ps1` → `FAIL soni: 0` (`review_ops`: `SATH_PT_review` va operatorlar bor; `ops_async`: `review.diff` ishlaydi).
Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_registry.py; .venv\Scripts\ruff.exe check desktop`
Server bilan: `e2e_server` (`new_issue`, `refresh_crs` → `s.my_role` = approver) OK.

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/modules/review desktop/blender/sath/ui.py desktop/blender/sath/ops_review.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): review moduli — taqriz paneli ui.py dan, qaror/merge/issue tugmalari ruxsatga sezgir, jonli o'chirishda diff ranglari tiklanadi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `sim` moduli + «viewer sim/commit ni ko'rmaydi» testi

**Model:** sonnet — panel ko'chishi, menyu, operator ruxsatlari, rol testi.

**Ko'chadi:** `ui.py::SATH_PT_sim` → `modules/sim/__init__.py` (so'zma-so'z, egizak bloki ham — Task 10 gacha); `ops_sim` (8 operator: `sim_catalog, sim_pick, sim_prefill, sim_run, sim_water, safety_check, sim_hydro, sim_clear_anim`) — `api.adopt`; `SATH_MT_main` dagi `sim_catalog`, `safety_check` bandlari → `api.ui.main_menu`.

**Files:**
- Create: `desktop/blender/sath/modules/sim/sath_module.toml`, `modules/sim/__init__.py`
- Modify: `desktop/blender/sath/ui.py`, `desktop/blender/sath/ops_sim.py` (**CRLF**), `modules/legacy/__init__.py`
- Test: `desktop/tests/sath_tests/modules.py` (`_viewer_hides`)

- [ ] **Step 1: Yiqiluvchi test** — `modules.py`:

```python
def _viewer_hides():
    """Spec P3 mezoni: viewer roli sim panelini va commit ni yashiradi; engineer (eski server — rol zaxirasi) ko'radi.
    IFC yuklaydi (Bonsai yangi sessiya) — run() da oxirgi."""
    from sath import ifc, props, session

    ifc.load(ROOT / "docs" / "samples" / "namuna_ges_v1.ifc")
    s = bpy.context.scene.ges
    session.set_session(object(), {"username": "test"})  # tarmoqsiz «kirgan» holat
    try:
        for role, perms_str, sees in (("viewer", "project.read scada.read", False), ("engineer", "", True)):
            props.fill(s.projects, [{"item_id": 9, "name": "P", "state": role, "perms": perms_str}])
            s.project_id, s.model_id = 9, 5
            assert bpy.types.SATH_PT_sim.poll(bpy.context) is sees, role
            assert bpy.ops.sath.commit.poll() is sees, role
            assert bpy.ops.sath.sim_hydro.poll() is sees, role
            assert bpy.ops.sath.safety_check.poll() is sees, role
    finally:
        session.logout()
        s.project_id = s.model_id = 0
        s.projects.clear()
```

`run()` oxiriga `_viewer_hides()` (bundan keyingi vazifalar o'z funksiyasini **undan oldin** qo'shadi). Run headless `modules` → FAIL.

- [ ] **Step 2: `modules/sim/sath_module.toml`**

```toml
id = "sim"
name = "Simulyatsiya"
version = "1.0.0"
api = ">=1.0,<2"
requires = []
permissions = ["network"]
visible_if_any = ["sim.run"]
workspaces = ["Simulation", "BIM"]
category = "Sath"
default_enabled = true
order = 30
```

- [ ] **Step 3: `modules/sim/__init__.py`**

```python
"""Simulyatsiya moduli: suv ombori rejimi → timeline, server katalogidagi hisoblar, xavfsizlik tekshiruvi."""

from __future__ import annotations

import bpy

from ... import ops_sim
from ...core.panels import SathPanel, cur, draw_list


class SATH_PT_sim(SathPanel, bpy.types.Panel):
    bl_label = "Simulyatsiya"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        ...  # ui.py dagi SATH_PT_sim.draw tanasi SO'ZMA-SO'Z; faqat `_list(` → `draw_list(`, `_cur(` → `cur(`


def _menu(layout, context):
    layout.operator("sath.sim_catalog")
    layout.operator("sath.safety_check")


def register(api):
    api.adopt("sim", ops_sim)
    api.register_classes("sim", [SATH_PT_sim])
    api.ui.main_menu("sim", _menu)
```

(`...` o'rniga — haqiqiy tana; `poll` ko'chirilmaydi, uning o'rnini `sath_needs` + manifest `visible_if_any` oladi.)

- [ ] **Step 4: `ops_sim.py`** (CRLF) — importga `from .core import perms`. Quyidagilarga poll (`bl_label` dan keyin):

`SATH_OT_sim_catalog`, `SATH_OT_sim_prefill`, `SATH_OT_sim_run`, `SATH_OT_safety_check`:

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and perms.poll(cls, "sim.run", context)
```

`SATH_OT_sim_hydro.poll`:

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0 and perms.poll(cls, "sim.run", context)
```

(`sim_pick`, `sim_water`, `sim_clear_anim` — lokal amallar, o'zgarmaydi; vazifa kalitlari `sim.*` — mavjud.)

- [ ] **Step 5: `ui.py`** — `SATH_PT_sim` klassi va `CLASSES` dagi nomi o'chadi; `SATH_MT_main.draw` dan `lay.operator("sath.sim_catalog")`, `lay.operator("sath.safety_check")` qatorlari o'chadi. `legacy/__init__.py` — `ops_sim` olib tashlanadi (`ops_twin` hali legacy da — `ops_sim` ni Python importi bilan ishlatadi, bu yetarli).

- [ ] **Step 6: Tekshiring**

Headless `modules` → `[OK]`; to'liq to'plam → `FAIL soni: 0` (`sim_ops`: `SATH_PT_sim` bor, `sim_pick.poll() is False`; `ops_async`: `safety_check` engineer bilan o'tadi).
Server bilan: `e2e_server` (`sim_catalog` admin), `sim_hydro`, `sim_twin` OK.
`git ls-files --eol desktop/blender/sath/ops_sim.py` → `i/crlf w/crlf`.

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/modules/sim desktop/blender/sath/ui.py desktop/blender/sath/ops_sim.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): sim moduli — simulyatsiya paneli va menyu bandlari modulda, operatorlar sim.run ruxsati bilan; viewer sim/commit ni ko'rmaydi (headless)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `scada` moduli

**Model:** sonnet — panel/menyu ko'chishi, timer va alarm ranglarini tozalash, hodisa.

**Ko'chadi:** `ui.py::SATH_PT_monitor` → `modules/scada/__init__.py`; `ops_monitor` (`monitor_toggle, show_sensor, show_asset, monitor_refresh` + `_tick` timer) — `api.adopt`; `SATH_MT_main` dagi `monitor_toggle` bandi → `api.ui.main_menu`.

**Files:**
- Create: `desktop/blender/sath/modules/scada/sath_module.toml`, `modules/scada/__init__.py`
- Modify: `desktop/blender/sath/ops_monitor.py` (**CRLF**: ruxsat, kalit `scada.tick`, `scada.snapshot` hodisasi), `ui.py`, `modules/legacy/__init__.py`
- Test: `desktop/tests/sath_tests/modules.py` (`_scada_off`, `_viewer_hides` ga monitoring)

- [ ] **Step 1: Yiqiluvchi test** — `modules.py`:

```python
def _scada_off():
    from sath.core import host

    s = bpy.context.scene.ges
    s.monitor_on = True
    off = host.set_enabled("scada", False)
    assert off[-1] == "scada", off  # twin (Task 10 dan keyin) birga o'chadi
    assert not s.monitor_on and not hasattr(bpy.types, "SATH_PT_monitor") and not _registered("monitor_toggle")
    for mid in reversed(off):
        assert host.set_enabled(mid, True) == [mid]
    assert hasattr(bpy.types, "SATH_PT_monitor")
```

`_viewer_hides` tsikliga: `assert bpy.types.SATH_PT_monitor.poll(bpy.context), role  # scada.read — hamma rolda`. `run()` da `_scada_off()` ni `_viewer_hides()` dan oldin. Run → FAIL.

- [ ] **Step 2: `modules/scada/sath_module.toml`**

```toml
id = "scada"
name = "Monitoring (SCADA)"
version = "1.0.0"
api = ">=1.0,<2"
requires = []
permissions = ["network"]
visible_if_any = ["scada.read"]
workspaces = ["SCADA"]
category = "Sath"
default_enabled = true
order = 40
```

- [ ] **Step 3: `modules/scada/__init__.py`**

```python
"""Monitoring (SCADA) moduli: sensorlar (5 s tik), 3D alarm/sog'liq ranglari, suv sathi tekisligi. Har tikda
`scada.snapshot` hodisasi (2-quyi-loyihada manba WebSocket ga almashadi)."""

from __future__ import annotations

import bpy

from ... import ifc, ops_monitor
from ...core.panels import SathPanel, draw_list


class SATH_PT_monitor(SathPanel, bpy.types.Panel):
    bl_label = "Monitoring (SCADA)"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        row = lay.row(align=True)
        row.operator(
            "sath.monitor_toggle",
            text="To'xtatish" if s.monitor_on else "Boshlash",
            icon="PAUSE" if s.monitor_on else "PLAY",
            depress=s.monitor_on,
        )
        row.operator("sath.monitor_refresh", text="", icon="FILE_REFRESH")
        row = lay.row(align=True)
        row.prop(s, "monitor_color")
        row.prop(s, "monitor_color_mode", text="")
        lay.prop(s, "monitor_water")
        if s.monitor_status:
            lay.label(text=s.monitor_status, icon="INFO")
        draw_list(lay, s, "sensors", "sensors_index", 5)
        row = lay.row(align=True)
        row.operator("sath.show_sensor", icon="RESTRICT_SELECT_OFF")
        row.operator("sath.open_web", text="Webda (HMI)", icon="URL").tab = "mon"


def _menu(layout, context):
    layout.operator("sath.monitor_toggle")


def register(api):
    api.adopt("scada", ops_monitor)  # ops_monitor.unregister _tick timerini ham to'xtatadi
    api.register_classes("scada", [SATH_PT_monitor])
    api.ui.main_menu("scada", _menu)


def unregister(api):
    bpy.context.scene.ges.monitor_on = False
    ifc.ALARM_STATE.restore()  # o'chirilgan monitoringning 3D ranglari qolmasin
```

- [ ] **Step 4: `ops_monitor.py`** (CRLF) — importga `from .core import events, perms`.
- `SATH_OT_monitor_toggle.poll`: `return session.is_logged_in() and context.scene.ges.model_id > 0 and perms.poll(cls, "scada.read", context)`
- `SATH_OT_monitor_refresh.poll`: `return session.is_logged_in() and context.scene.ges.monitor_on and perms.poll(cls, "scada.read", context)`
- `_tick` dagi `key="monitor.tick"` → `key="scada.tick"` (modul o'chirilganda `cancel_prefix("scada.")` ushlaydi).
- `_apply(d, hours)` oxiriga: `events.publish("scada.snapshot", data=d)`.

- [ ] **Step 5: `ui.py`** — `SATH_PT_monitor` va `CLASSES` dagi nomi, `SATH_MT_main` dagi `lay.operator("sath.monitor_toggle")` o'chadi. `legacy` — `ops_monitor` olib tashlanadi.

- [ ] **Step 6: Tekshiring** — headless `modules` OK; to'liq to'plam `FAIL soni: 0` (`monitor_ops`: `monitor_toggle.poll() is False` login siz, `SATH_PT_monitor` bor; `ops_async` dagi `_apply` chaqiruvi); server bilan `e2e_server` (monitor tick). `git ls-files --eol desktop/blender/sath/ops_monitor.py` → crlf.

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/modules/scada desktop/blender/sath/ops_monitor.py desktop/blender/sath/ui.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): scada moduli — monitoring paneli/menyusi modulda, scada.read ruxsati, scada.snapshot hodisasi; o'chirilganda timer va alarm ranglari tozalanadi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `twin` moduli (sim + scada ga bog'liq)

**Model:** sonnet — ikki panel (biri sim panelidan ajraladi), kaskad testi.

**Ko'chadi:** `ui.py::SATH_PT_twin` → `modules/twin/__init__.py`; `SATH_PT_sim` dagi «Egizak simulyatsiyalari» bloki → yangi `SATH_PT_twin_sims` (shu modulda, `sath_perm = "sim.run"`); `ops_twin` (`sim_hammer, sim_governor, sim_transformer, sim_seismic`) — `api.adopt`.

**Files:**
- Create: `desktop/blender/sath/modules/twin/sath_module.toml`, `modules/twin/__init__.py`
- Modify: `desktop/blender/sath/modules/sim/__init__.py` (egizak bloki olib tashlanadi), `ops_twin.py` (ruxsat), `ui.py`, `modules/legacy/__init__.py`
- Test: `desktop/tests/sath_tests/modules.py` (`_twin_cascade`)

- [ ] **Step 1: Yiqiluvchi test**

```python
def _twin_cascade():
    """Bog'liqlik: sim o'chsa twin ham o'chadi; twin yoqilsa sim ham yonadi."""
    from sath.core import host

    assert host.is_enabled("twin") and hasattr(bpy.types, "SATH_PT_twin_sims")
    assert host.set_enabled("sim", False) == ["twin", "sim"]
    assert not hasattr(bpy.types, "SATH_PT_twin") and not _registered("sim_hammer")
    assert host.set_enabled("twin", True) == ["sim", "twin"]
    assert hasattr(bpy.types, "SATH_PT_sim") and hasattr(bpy.types, "SATH_PT_twin") and _registered("sim_hammer")
```

`run()` da `_viewer_hides()` dan oldin. `_viewer_hides` tsikliga: `assert bpy.types.SATH_PT_twin_sims.poll(bpy.context) is sees, role` va `assert bpy.ops.sath.sim_hammer.poll() is sees, role`. Run → FAIL.

- [ ] **Step 2: `modules/twin/sath_module.toml`**

```toml
id = "twin"
name = "Raqamli egizak"
version = "1.0.0"
api = ">=1.0,<2"
requires = ["sim", "scada"]
permissions = ["network"]
visible_if_any = ["scada.read"]
workspaces = ["SCADA", "Simulation"]
category = "Sath"
default_enabled = true
order = 50
```

- [ ] **Step 3: `modules/twin/__init__.py`**

```python
"""Raqamli egizak moduli: jonli egizak holati (monitoring tikidan), sog'liq indeksi, vaqt mashinasi va egizak
simulyatsiyalari (gidrozarba, rostlagich, transformator, seysmik) → timeline."""

from __future__ import annotations

import bpy

from ... import ops_twin
from ...core.panels import SathPanel, draw_list


class SATH_PT_twin(SathPanel, bpy.types.Panel):
    bl_label = "Raqamli egizak"
    bl_options = {"DEFAULT_CLOSED"}
    sath_needs = frozenset({"login", "model"})

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        if not s.monitor_on:
            lay.label(text="Monitoringni yoqing — egizak jonli holatdan hisoblanadi", icon="INFO")
        if s.twin_head:
            lay.label(text=s.twin_head, icon="LIGHT_SUN")
        box = lay.box()
        box.label(text="Agregatlar: o'lchangan / kutilgan, og'ish", icon="MOD_BUILD")
        for r in s.twin_rows:
            icon = "CHECKMARK" if r.state == "ok" else "ERROR" if r.state == "warn" else "PAUSE"
            box.label(text=f"{r.name}: {r.col2} {r.col3} {r.col4}".strip(), icon=icon)
        if len(s.twin_safety):
            box = lay.box()
            box.label(text="Xavfsizlik (jonli)", icon="FAKE_USER_ON")
            for r in s.twin_safety:
                box.label(text=f"{r.name}: {r.col2}", icon="CHECKMARK" if r.state == "ok" else "ERROR")
        box = lay.box()
        box.label(text=s.health_head or "Sog'liq indeksi", icon="HEART")
        draw_list(box, s, "health_rows", "health_index", 4)
        box.operator("sath.show_asset", icon="RESTRICT_SELECT_OFF")
        box = lay.box()
        box.label(text="Vaqt mashinasi", icon="TIME")
        box.prop(s, "time_hours")
        if s.time_note:
            box.label(text=s.time_note)
        lay.operator("sath.open_web", text="Dispetcher paneli (web)", icon="URL").tab = "mon"


class SATH_PT_twin_sims(SathPanel, bpy.types.Panel):
    bl_label = "Egizak simulyatsiyalari"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 51
    sath_needs = frozenset({"login", "model"})
    sath_perm = "sim.run"

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.label(text="Natija → timeline (namuna GES: «GES obyektlari»)", icon="OUTLINER_OB_GROUP_INSTANCE")
        col = lay.column(align=True)
        row = col.row(align=True)
        row.prop(s, "hammer_close_s")
        row.operator("sath.sim_hammer", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "gov_event", text="")
        row.prop(s, "gov_step")
        row.operator("sath.sim_governor", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "tr_load")
        row.prop(s, "tr_days")
        row.operator("sath.sim_transformer", icon="PLAY")
        row = col.row(align=True)
        row.prop(s, "seis_intensity", text="")
        row.prop(s, "seis_ground", text="")
        row.prop(s, "seis_scale")
        row.operator("sath.sim_seismic", icon="PLAY")
        if s.twin_note:
            lay.label(text=s.twin_note, icon="INFO")


def register(api):
    api.adopt("twin", ops_twin)
    api.register_classes("twin", [SATH_PT_twin, SATH_PT_twin_sims])
```

- [ ] **Step 4: `modules/sim/__init__.py`** — `SATH_PT_sim.draw` dan `box = lay.box()` + `box.label(text="Egizak simulyatsiyalari → timeline …")` qatoridan boshlab `if s.twin_note: box.label(text=s.twin_note, icon="INFO")` gacha bo'lgan blokni o'chiring (u endi `SATH_PT_twin_sims` da).

- [ ] **Step 5: `ops_twin.py`** — importga `from .core import perms`; `_TwinSim.poll`:

```python
    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0 and perms.poll(cls, "sim.run", context)
```

`ui.py` — `SATH_PT_twin` va `CLASSES` dagi nomi o'chadi. `legacy` — `ops_twin` olib tashlanadi.

- [ ] **Step 6: Tekshiring** — headless `modules` OK (`_scada_off` endi `["twin", "scada"]` qaytaradi va ikkalasini qayta yoqadi); to'liq to'plam `FAIL soni: 0`; server bilan `sim_twin`, `gui_twin` (agar ishlatilsa) OK.

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/modules/twin desktop/blender/sath/modules/sim/__init__.py desktop/blender/sath/ops_twin.py desktop/blender/sath/ui.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): twin moduli (sim + scada ga bog'liq) — egizak paneli va alohida «Egizak simulyatsiyalari» paneli, sim.run ruxsati; kaskad testi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: `io` moduli

**Model:** haiku — to'liq kod, mexanik ko'chirish.

**Ko'chadi:** `ui.py::SATH_PT_import` → `modules/io/__init__.py`; `ops_import` (`import_dxf`, `import_mesh` + File → Import menyusi) — `api.adopt`; `SATH_MT_main` dagi `import_dxf`, `import_mesh` bandlari → `api.ui.main_menu`.

**Files:**
- Create: `desktop/blender/sath/modules/io/sath_module.toml`, `modules/io/__init__.py`
- Modify: `desktop/blender/sath/ui.py`, `modules/legacy/__init__.py`
- Test: `desktop/tests/sath_tests/modules.py` (`_io_live`)

- [ ] **Step 1: Yiqiluvchi test**

```python
def _io_live():
    from sath.core import host

    assert _registered("import_dxf") and hasattr(bpy.types, "SATH_PT_import")
    assert host.set_enabled("io", False) == ["io"]
    assert not _registered("import_dxf") and not _registered("import_mesh") and not hasattr(bpy.types, "SATH_PT_import")
    assert host.set_enabled("io", True) == ["io"] and _registered("import_mesh")
```

`run()` da `_viewer_hides()` dan oldin. Run → FAIL.

- [ ] **Step 2: `modules/io/sath_module.toml`**

```toml
id = "io"
name = "Import (DWG/DXF, mesh)"
version = "1.0.0"
api = ">=1.0,<2"
requires = []
permissions = ["files", "subprocess"]
visible_if_any = []
workspaces = ["BIM"]
category = "Sath"
default_enabled = true
order = 60
```

- [ ] **Step 3: `modules/io/__init__.py`**

```python
"""Fayl I/O moduli: DWG/DXF (ezdxf, LibreDWG/ODA) va mesh (assimp) import — serverga ulanmasdan ishlaydi.
4-quyi-loyihada ochiq formatlar round-trip va konnektorlar shu modulga qo'shiladi."""

from __future__ import annotations

import bpy

from ... import ops_import
from ...core.panels import SathPanel


class SATH_PT_import(SathPanel, bpy.types.Panel):
    bl_label = "Import"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("sath.import_dxf", icon="GREASEPENCIL")
        col.operator("sath.import_mesh", icon="MESH_DATA")


def _menu(layout, context):
    layout.operator("sath.import_dxf")
    layout.operator("sath.import_mesh")


def register(api):
    api.adopt("io", ops_import)  # File → Import bandlari ham (ops_import.register)
    api.register_classes("io", [SATH_PT_import])
    api.ui.main_menu("io", _menu)
```

- [ ] **Step 4: `ui.py`** — `SATH_PT_import`, `CLASSES` dagi nomi va `SATH_MT_main` dagi `import_dxf`/`import_mesh` qatorlari o'chadi. `legacy` — `ops_import` olib tashlanadi.

- [ ] **Step 5: Tekshiring** — headless `modules` OK; to'liq to'plam (`import_*` testlari `from sath import ops_import` — o'zgarmaydi) `FAIL soni: 0`.

- [ ] **Step 6: Commit**

```bash
git add desktop/blender/sath/modules/io desktop/blender/sath/ui.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): io moduli — import paneli va menyu bandlari modulda, jonli o'chadi/yonadi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: `bim` moduli (Object.ges; sim va twin unga bog'lanadi)

**Model:** opus — PointerProperty ni jonli unregister qilish va ma'lumot saqlanishi, P2 natijasiga moslash, commit yo'lini himoyalash.

**Ko'chadi:** `ges_objects.py::SATH_PT_objects` → `modules/bim/__init__.py` (SathPanel); `ges_objects` (PropertyGroup lar, `add_object`, `rebuild_object`, P2 qo'shgan `sync_ifc` va boshqalar, `Object.ges`) va `demo_plant` (`build_demo_plant`) — `api.adopt`; `SATH_MT_main` dagi «GES obyekti» bandi → `api.ui.main_menu`.

**Files:**
- Create: `desktop/blender/sath/modules/bim/sath_module.toml`, `modules/bim/__init__.py`
- Modify: `desktop/blender/sath/ges_objects.py` (**CRLF**: panel klassi chiqariladi, `CLASSES` va `SATH_PANELS_OPEN` bloki), `ui.py`, `ops_server.py` (bim siz commit), `modules/sim/sath_module.toml`, `modules/twin/sath_module.toml` (`requires` ga `"bim"`), `modules/legacy/__init__.py`
- Test: `desktop/tests/sath_tests/modules.py` (`_bim_keeps_data`)

- [ ] **Step 1: P2 holatini o'qing**

Run: `rg -n "class SATH_PT_objects|def poll|^CLASSES|def register|def unregister|SATH_PANELS_OPEN|def add\(" desktop/blender/sath/ges_objects.py desktop/blender/sath/demo_plant.py`
Run: `rg -n "ges_objects\.|sync_ifc|demo_plant\." desktop/blender/sath/ops_server.py desktop/blender/sath/ops_import.py desktop/blender/sath/ui.py`
Natijani yozib oling: panel klassi qayerda, `add()` imzosi, `ops_server` qaysi `ges_objects`/`sync_ifc` chaqiruvlarini qiladi.

- [ ] **Step 2: Yiqiluvchi test**

```python
def _bim_keeps_data():
    """Review Focus 5: bim o'chib-yonsa GES obyekt parametrlari saqlanadi; sim/twin birga o'chadi."""
    from sath import ges_objects
    from sath.core import host

    obj = ges_objects.add(bpy.context, "GES_Dam")  # P2 dagi imzo (sath_tests/objects.py dagidek)
    name = obj.name
    off = host.set_enabled("bim", False)
    assert off[-1] == "bim" and {"sim", "twin"} <= set(off), off
    assert not hasattr(bpy.types.Object, "ges") and not hasattr(bpy.types, "SATH_PT_objects") and not _registered("add_object")
    for mid in reversed(off):
        assert host.set_enabled(mid, True) == [mid]
    assert bpy.data.objects[name].ges.kind == "GES_Dam" and hasattr(bpy.types, "SATH_PT_objects")
```

`run()` da `_viewer_hides()` dan oldin. Run → FAIL.

- [ ] **Step 3: `modules/bim/sath_module.toml`**

```toml
id = "bim"
name = "GES obyektlari (BIM)"
version = "1.0.0"
api = ">=1.0,<2"
requires = []
permissions = ["files", "ifc.write"]
visible_if_any = []
workspaces = ["BIM"]
category = "Sath"
default_enabled = true
order = 70
```

`modules/sim/sath_module.toml`: `requires = ["bim"]` (sim_anim `obj.ges` orqali ishlaydi). `modules/twin/sath_module.toml`: `requires = ["sim", "scada", "bim"]`.

- [ ] **Step 4: `modules/bim/__init__.py`**

```python
"""BIM moduli: parametrik GES obyektlari (Object.ges, IFC + Pset_GES_*), «Namuna GES». O'chirilganda Object.ges
ro'yxatdan chiqadi, lekin obyektlardagi ma'lumot saqlanadi (qayta yoqilganda qaytadi)."""

from __future__ import annotations

import bpy

from ... import demo_plant, ges_objects
from ...core.panels import SathPanel


class SATH_PT_objects(SathPanel, bpy.types.Panel):
    bl_label = "GES obyektlari"

    def draw(self, context):
        ...  # ges_objects.py dagi SATH_PT_objects.draw (P2 dan keyingi) SO'ZMA-SO'Z; modul nomlari `ges_objects.` bilan


def _menu(layout, context):
    layout.operator_menu_enum("sath.add_object", "kind", text="GES obyekti")


def register(api):
    api.adopt("bim", ges_objects, demo_plant)
    api.register_classes("bim", [SATH_PT_objects])
    api.ui.main_menu("bim", _menu)
```

Panel tanasini ko'chirishda: `KIND_ITEMS`, `KIND_LABEL` va boshqa `ges_objects` nomlari → `ges_objects.KIND_ITEMS` …; agar P2 panelida `poll` bo'lsa — `sath_poll` deb qayta nomlang; `bl_space_type/bl_region_type/bl_category` qatori kerak emas (SathPanel + manifest).

- [ ] **Step 5: `ges_objects.py`** (CRLF) — `class SATH_PT_objects …` klassini o'chiring; `CLASSES` dan nomini olib tashlang; `register()` dagi `if os.environ.get("SATH_PANELS_OPEN"): SATH_PT_objects.bl_category = "Item"` blokini o'chiring (`api.register_classes` buni qiladi); `os` importi ishlatilmay qolsa — o'chiring. Boshqa hech narsa o'zgarmaydi.

- [ ] **Step 6: Yadro `bim` siz** — `ops_server.py` dagi Step 1 da topilgan `ges_objects.*` / `bpy.ops.sath.sync_ifc()` chaqiruvlarini (masalan commit dagi `ges_objects.flush_pending()`) `host.is_enabled("bim")` bilan o'rang:

```python
        if host.is_enabled("bim"):  # P3: bim o'chiq bo'lsa Object.ges yo'q — sinxronlanadigan narsa ham yo'q
            ges_objects.flush_pending()  # (P2 dagi haqiqiy chaqiruv)
```

importga `from .core import host`. `unassigned()` dagi `demo_plant.GROUND` — oddiy konstanta, o'zgarmaydi.

- [ ] **Step 7: `ui.py`** — `SATH_MT_main` dagi `lay.operator_menu_enum("sath.add_object", "kind", text="GES obyekti")` qatori o'chadi. `legacy` — `ges_objects`, `demo_plant` olib tashlanadi (endi `FILES = [ops_server, ui]`).

- [ ] **Step 8: Tekshiring** — headless `modules` OK; `pytest desktop/tests/test_sath_registry.py::test_bundled_manifests_valid` PASS; to'liq to'plam `FAIL soni: 0` (`objects`, `demo_plant`, `roundtrip_ges`, `undo_ifc` (P2), `ops_async`); server bilan `e2e_server`, `commit_conflict`, `sim_hydro`, `sim_twin` OK. GUI: `set SATH_PANELS_OPEN=1 && blender --python desktop/tests/blender_gui_check.py` — «GES obyektlari» «Item» yorlig'ida chiziladi. `git ls-files --eol desktop/blender/sath/ges_objects.py` → crlf.

- [ ] **Step 9: Commit**

```bash
git add desktop/blender/sath/modules/bim desktop/blender/sath/modules/sim/sath_module.toml desktop/blender/sath/modules/twin/sath_module.toml desktop/blender/sath/ges_objects.py desktop/blender/sath/ops_server.py desktop/blender/sath/ui.py desktop/blender/sath/modules/legacy/__init__.py desktop/tests/sath_tests/modules.py
git commit -m "feat(MOD): bim moduli — GES obyektlari paneli va menyusi modulda, sim/twin unga bog'liq; o'chirib-yoqishda obyekt parametrlari saqlanadi, commit bim siz ishlaydi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: `legacy` ni olib tashlash — yadro fayllari `sath/__init__.py` ga

**Model:** haiku — mexanik: ro'yxat, papka o'chirish, test yangilash.

**Files:**
- Delete: `desktop/blender/sath/modules/legacy/`
- Modify: `desktop/blender/sath/__init__.py` (**CRLF**), `core/host.py` (`PINNED = frozenset()`)
- Test: `desktop/tests/sath_tests/modules.py` (`_legacy_pinned` → `_core_only`)

- [ ] **Step 1: Test** — `_legacy_pinned` ni almashtiring:

```python
def _core_only():
    """Yadro (Server, Model, bildirishnomalar, menyu, update, status bar) modul emas — doim ro'yxatda."""
    from sath.core import host

    assert host.record("legacy") is None
    assert hasattr(bpy.types, "SATH_PT_server") and hasattr(bpy.types, "SATH_MT_main") and _registered("commit")
    assert sorted(host.REG.records) == ["bim", "io", "review", "scada", "sim", "twin"]
```

`run()` dagi chaqiruvni `_core_only()` ga almashtiring.

- [ ] **Step 2: `sath/__init__.py`** (CRLF) — blok:

```python
if bpy is not None:
    from . import ops_server, prefs, props, ui
    from .core import host, ui_tasks

    # Yadro: fon vazifalari, sozlamalar, Scene.ges, server/login/commit, yadro panellari va menyu; qolgani — modules/
    MODULES = [ui_tasks, prefs, props, ops_server, ui, host]
```

Modul docstringini yangilang: `"""Sath Blender addoni: yadro (server, versiyalar, rolga sezgir UI, fon vazifalari) + modullar (sath/modules/:
review, sim, scada, twin, io, bim; Sozlamalarda yoqiladi/o'chiriladi). IFC — Bonsai."""`

- [ ] **Step 3:** `git rm -r desktop/blender/sath/modules/legacy`; `host.py`: `PINNED: frozenset[str] = frozenset()  # hozircha yo'q (mexanizm keyingi yadro-modullar uchun)`.

- [ ] **Step 4: Tekshiring** — pytest (`test_bundled_manifests_valid`) PASS; headless `modules` va to'liq to'plam `FAIL soni: 0`; `rg -n "legacy" desktop/blender/sath` → faqat izohlar (yoki hech narsa). `git ls-files --eol desktop/blender/sath/__init__.py` → crlf.

- [ ] **Step 5: Commit**

```bash
git add -A desktop/blender/sath/__init__.py desktop/blender/sath/core/host.py desktop/blender/sath/modules desktop/tests/sath_tests/modules.py
git commit -m "refactor(MOD): legacy psevdo-modul olib tashlandi — ops_server va ui yadroga, barcha funksiyalar modullarda

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Hujjat

**Model:** haiku — matn.

**Files:**
- Modify: `desktop/blender/README.md` (**CRLF**: Ishlatish, Tuzilma, Testlar)

- [ ] **Step 1: «Ishlatish» bo'limiga** qo'shing:

```markdown
- **Modullar:** Edit → Preferences → Add-ons → Sath → «Modullar» — har modul (Taqriz, Simulyatsiya, Monitoring,
  Raqamli egizak, Import, GES obyektlari) belgi bilan jonli yoqiladi/o'chiriladi; bog'liqlari birga (masalan sim
  o'chsa egizak ham). Yuklanmagan modul sababi va traceback shu yerda.
- **Uchinchi tomon modullari:** «Uchinchi tomon modullari» ni yoqing, nashriyotchining ochiq kalitini «Modul kalitlari»
  ga yozing, modul papkasini `<Blender config>/sath_modules/<id>/` ga qo'ying. Faqat imzolangan modul yuklanadi:
  `python desktop/build/sign_module.py --new-key kalit.txt`, `python desktop/build/sign_module.py <papka> --key kalit.txt`.
- **Rollar:** panel va tugmalar loyihadagi ruxsatga qarab — ko'ruvchi commit/simulyatsiyani ko'rmaydi, kulrang
  tugma ustida sababi («Ruxsat yo'q: cr.approve»). Haqiqiy tekshiruv serverda.
```

- [ ] **Step 2: «Tuzilma»** — `core/` qatorini almashtiring va yangilarini qo'shing:

```markdown
  - `core/` — `tasks.py` (fon vazifalari, bpy siz), `events.py` (hodisalar shinasi), `ui_tasks.py` (pompa, status bar,
    `run_op`), `registry.py` (modul reyestri: manifest, imzo, tartib, hayot sikli — bpy siz), `host.py` (reyestrning
    Blender ulagichi, Sozlamalardagi ro'yxat), `perms.py` (rolga sezgir UI), `panels.py` (`SathPanel`)
  - `api.py` — modullar uchun barqaror fasad (`API_VERSION`); `modules/<id>/` — `sath_module.toml` + `__init__.py`
    (`review`, `sim`, `scada`, `twin`, `io`, `bim`); `ops_*.py` o'z joyida, modul ularni `api.adopt` bilan oladi
```

`shared/` qatoriga `permissions` ni qo'shing.

- [ ] **Step 3: «Testlar»** — pytest ro'yxatiga `registry, perms`; headless ga `modules` (jonli yoqish/o'chirish, imzo, viewer roli) va sinovlar sonini yangilang (`run_blender_tests.ps1` dagi haqiqiy son).

- [ ] **Step 4: Tekshiring** — `git ls-files --eol desktop/blender/README.md` → `i/crlf w/crlf`; `git diff --stat` faqat qo'shilgan qatorlar.

- [ ] **Step 5: Commit**

```bash
git add desktop/blender/README.md
git commit -m "docs(MOD): addon README — modullar (Sozlamalar, imzolash), rolga sezgir UI, core/ tuzilmasi va testlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Yakuniy tekshiruv

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe -m pytest -q desktop/tests                       # registry, perms, tasks, flows (permissions), pure
.venv\Scripts\python.exe -m pytest -q server/tests -k "project or permissions"
.venv\Scripts\ruff.exe check server sim desktop
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; .\desktop\tests\run_blender_tests.ps1   # FAIL soni: 0
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai     # [OK] modules
# server bilan (dev server ishlab turganda):
$env:GES_TEST_SERVER="http://127.0.0.1:8765"; .\desktop\tests\run_blender_tests.ps1             # e2e_server, commit_conflict, sim_hydro, sim_twin OK
.venv\Scripts\python.exe desktop/build/build_blender_addon.py; tar -tf (Get-ChildItem desktop/dist/sath-*.zip | Select-Object -Last 1) | Select-String "sath_module.toml"   # 6 ta manifest zip da
```

Qo'lda (GUI): Sozlamalar → Sath → «Modullar» da `review` belgisini olib tashlang — N-paneldagi «Taqriz va issue lar» darhol yo'qoladi, qayta qo'ying — qaytadi; `sim` ni o'chiring — «Raqamli egizak» ham o'chadi va xabar chiqadi; viewer foydalanuvchi bilan kiring — Model panelida Commit/Tasdiqqa yuborish yo'q, «Simulyatsiya» paneli yo'q, «Yangi model» kulrang va ustida «Ruxsat yo'q: model.write».

## O'z-o'zini tekshirish (spec bo'yicha)

**Qamrov:**
- §1 yagona extension ichida ichki reyestr → Task 3–5; `sath_module.toml` barcha maydonlari (`id, name, version, api, requires, permissions, visible_if_any, workspaces, category, default_enabled, order`) → Task 3 `parse_manifest`.
- Topish: bundle + foydalanuvchi papkasi, `allow_user_modules` + Ed25519 (`update.py` tekshiruvi qayta ishlatiladi) → Task 3 `discover/verify_signature`, Task 5.
- Hayot sikli `discover → API/bog'liqlik → topologik tartib → module.register(api)`; `register_classes` yozib boradi → jonli unregister; yiqilgan modul izolyatsiyasi + traceback prefs da → Task 3, Task 5.
- Public API: `session`, `tasks.run`, `perms.can/require`, `ifc` (+`IfcOperator`, `restore_ges`), `events.subscribe/publish`, `ui.SathPanel` (manifestdan `bl_category`; `sath_needs`, `sath_perm`; yagona poll), `ui.keymap()`, `props.scene_group()` (snapshot/restore ga avtomatik), `geom`/`kinds` → Task 4.
- Hodisalar: `session.*` (P1), `project.changed`, `ifc.loaded` (P1), `scada.snapshot`, `task.*` → Task 4, Task 9.
- Strangler: A (`legacy`) → Task 6; B `review → sim → scada → twin → io → bim` → Task 7–12; `bl_idname` lar o'zgarmaydi; yadroda Server/login, bildirishnomalar, update, status bar, prefs, `Scene.ges` → Task 13.
- §2 server `ProjectOut.permissions` + test → Task 1; `core/perms.py` (model_role o'rniga) → Task 4/7; zaxira `common/sath_common/permissions.py` + sync + paritet pytest → Task 2; moslik jadvali (commit→model.write, submit→cr.create, approve→cr.approve, merge→cr.merge, review→cr.review, issue→issue.write, sim/twin/xavfsizlik→sim.run, monitoring→scada.read) → Task 4, 7, 8, 9, 10; panel `visible_if_any` yashiradi, operator `poll_message_set` → Task 4 `panels.visible`, `perms.poll`.
- «Bosqichlar» P3 mezoni: headless `modules` — `review` jonli o'chadi/yonadi (Task 7), viewer sim/commit ni yashiradi (Task 8).

**Placeholder tekshiruvi:** ikki joyda kod ataylab «so'zma-so'z ko'chiring» deb berilgan — `SATH_PT_sim.draw` (Task 8, joriy `ui.py` dagi tana + 2 ta mexanik almashtirish) va `SATH_PT_objects.draw` (Task 12, P2 dan keyingi tana — oldindan ma'lum emas). Qolgan barcha kod to'liq.

**Tiplar va nomlar izchilligi:** `Registry.owner/add_classes/add_cleanup` (Task 3) ↔ `api.register_classes/adopt/on_unregister/props.scene_group/ui.keymap` (Task 4) ↔ `host.add_menu` (Task 4); `host.set_enabled -> list[str]` (Task 5) ↔ testlardagi kutilgan ro'yxatlar (`dependents` topologik tartibda, `disable` teskari); `perms.poll(cls, perm, context, project_id=None)` — barcha operatorlarda bir xil; `GesListItem.perms` (Task 4) ↔ `flows.project_rows["perms"]` ↔ `perms._entry`; vazifa kalitlari `review.diff`, `sim.*`, `scada.tick` ↔ `cancel_prefix(f"{id}.")`; `props.snapshot_scene/restore_scene` (Task 4) ↔ `ops_server` va `modules.py`.

## Keyingi rejalar (shu spec bo'yicha)

- **P4** — workspace lar (`ws["sath_ws"]` tegi — `SathPanel` allaqachon tekshiradi; manifest `workspaces` qiymatlari `BIM/Compare/Simulation/SCADA`), tema, `core/tokens.py`, keymap konflikt testi (`api.ui.keymap`), FreeCAD siz bundle, byudjetlar (`Record.ms` — har modul register vaqti Sozlamalarda allaqachon ko'rinadi).
- Web: `web/src/api/permissions.ts` dagi `sensor.oos` serverda yo'q — alohida kichik ish (server ruxsati qo'shish yoki web ni `sensor.configure` ga moslash).
