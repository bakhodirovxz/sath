# Sath Blender addoni — amalga oshirish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FreeCAD workbench imkoniyatlarini (server, GES obyektlari, versiyalar, sim, monitoring, DXF/DWG) Blender 5.2 addoni sifatida — IFC Bonsai'da, FreeCAD dvigatel sifatida.

**Architecture:** Blender extension `desktop/blender/sath/`; `fc_engine` FreeCAD'ni in-process yuklaydi (spike retsepti) va stateless geometriya beradi; `ifc.py` Bonsai ko'prigi (element↔obyekt, pset, save/load); `flows.py` bpy'siz server oqimlari (pytest bilan real server ustida sinaladi); operatorlar/panellar yupqa qatlam.

**Tech Stack:** Blender 5.2 LTS (Python 3.13, bpy), Bonsai 0.8.5 (`bonsai.tool`, ifcopenshell 0.8.5), FreeCAD 1.1.3 conda-forge py313, numpy, stdlib `urllib`; testlar: pytest (monorepo `.venv`, Python 3.10) + `blender -b --python`.

**Spec:** `docs/superpowers/specs/2026-09-17-blender-addon-design.md`

## Global Constraints

- Blender ≥ 5.2 (manifest `blender_version_min = "5.2.0"`), Bonsai ≥ 0.8.5, FreeCAD 1.1.3 py313 (`GES_FC_HOME` env yoki prefs `fc_home`; sukut `%USERPROFILE%\Tools\fc-py313`).
- Kod izohlari, UI matnlari — **o'zbek (lotin)**; identifikatorlar ingliz. Mavjud uslub: docstring birinchi qator qisqa, `# noqa: BLE001` keng `except` uchun.
- ruff: line-length 100, `select = E,F,I,UP,B`, target py310 (monorepo `ruff.toml`) — addon fayllari ham `ruff check desktop` dan o'tishi kerak. Addon ichida `from __future__ import annotations` majburiy (py3.10 sintaksisi).
- `bpy` faqat asosiy oqimda; tarmoq so'rovlari qisqa bo'lsa sinxron, uzun bo'lsa `threading.Thread` + `bpy.app.timers`.
- Birlik: Blender/IFC metr; FreeCAD mm — faqat `fc_engine` ichida ×0.001.
- `sath/shared/*.py` — manba `desktop/GesWorkbench/ges_workbench/`; faqat `sync_blender.py` orqali o'zgaradi.
- Har vazifa oxirida: `cd C:\Users\uge226\Desktop\BIM && .venv\Scripts\ruff check desktop && git add ... && git commit`.
- Headless Blender ishga tushirish: `%USERPROFILE%\Tools\blender-5.2\blender.exe -b --python <script>`; addon yo'li `SATH_ADDON_DIR` env (repo `desktop/blender/sath`) — test runner uni `bpy.utils.script_paths` ga qo'shmasdan `sys.path` + `importlib` bilan yuklaydi (pastda `blender_headless.py`).

## Fayl tuzilmasi

```
desktop/blender/sath/
  blender_manifest.toml   id="sath", version, blender_version_min, wheels (9-vazifa)
  __init__.py             register()/unregister(): barcha modullar ro'yxati
  prefs.py                GesPrefs(AddonPreferences): server, username, fc_home; prefs() yordamchi
  props.py                Scene.ges PropertyGroup: model_id, version_id, model_name, project_id, status,
                          ro'yxatlar (projects/models/versions/crs/issues/notifications/sensors/sim kinds) + indekslar
  session.py              login/logout/client()/user(); token xotirada; prefs ga server/login yozadi
  fc_engine.py            load(), available(), shape_to_mesh(), ges_schema(kind), ges_build(kind, params)
  ifc.py                  ensure_project(), load(path), save(path), guid_map(), object_for_guid(),
                          assign_class(obj, ifc_class), write_psets(entity, props), ColorState
  flows.py                bpy'siz: open_version(), commit(), diff_colors(), check_update(), web_url() ...
  ges_objects.py          GesParam/GesObject PropertyGroup, GES_OT_add, rebuild(), GES_PT_objects
  viewpoint.py            capture(context), apply(context, vp)
  ops_server.py           GES_OT_connect/logout/refresh_projects/refresh_models/refresh_versions/open/
                          commit/submit/open_web/notifications/mark_read/create_model
  ops_review.py           GES_OT_refresh_issues/show_issue/goto_view/comment_issue/new_issue,
                          GES_OT_refresh_crs/decide/merge/reject, GES_OT_refresh_versions_tab/diff/clear_diff
  ops_sim.py              GES_OT_sim_catalog/sim_pick/sim_prefill/sim_run/sim_water/safety_check
  ops_monitor.py          GES_OT_monitor_start/stop/show_sensor; timer; water plane
  ops_import.py           GES_OT_import_dxf (DWG/DXF), GES_OT_import_mesh (assimp)
  water.py                place_water_plane(level_m)
  ui.py                   GES_PT_server, GES_PT_model, GES_PT_review, GES_PT_sim, GES_PT_monitor, GES_PT_import,
                          UIList lar, header menyu
  shared/__init__.py, server_client.py, dxf_prepare.py, assimp_load.py   (sync nusxa)
desktop/build/sync_blender.py
desktop/tests/blender_headless.py            umumiy runner: addon yuklash + `--test <nom>`
desktop/tests/test_sath_pure.py           pytest: pset guruhlash, ifc class xaritasi, viewpoint matematika, sync --check
desktop/tests/test_sath_flows.py          pytest: flows real server bilan (test_server_client fixture)
desktop/blender/README.md                    (mavjud) yangilanadi
```

---

### Task 1: Extension skeleti, prefs, session, sync, headless runner

**Files:**
- Create: `desktop/blender/sath/blender_manifest.toml`, `__init__.py`, `prefs.py`, `props.py`, `session.py`, `ui.py`, `shared/__init__.py`
- Create: `desktop/build/sync_blender.py`
- Create: `desktop/tests/blender_headless.py`, `desktop/tests/sath_tests/smoke.py`, `desktop/tests/test_sath_pure.py`

**Interfaces:**
- Produces: `sath.prefs.prefs() -> GesPrefs` (`.server`, `.username`, `.fc_home`);
  `sath.session.login(server, username, password) -> dict`, `logout()`, `client() -> GesClient`, `user() -> dict|None`, `is_logged_in() -> bool`;
  `bpy.context.scene.ges` (`GesScene`: `status`, `project_id`, `model_id`, `version_id`, `version_number`, `model_name`, `password`, ro'yxatlar `projects/models/versions` + `_index`);
  `props.fill(coll, rows)`; `props.GesListItem` (`item_id, name, col2, col3, col4, guid, state, number`);
  runner: `blender -b --python desktop/tests/blender_headless.py -- --test <nom> [--bonsai]` → `desktop/tests/sath_tests/<nom>.py::run(ctx)`.

- [ ] **Step 1: `desktop/build/sync_blender.py` va pytest**

```python
"""GesWorkbench dagi FreeCAD siz modullarni Blender addoniga nusxalaydi (yagona manba — workbench).

python desktop/build/sync_blender.py          # nusxalash
python desktop/build/sync_blender.py --check  # CI: farq bo'lsa exit 1
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "desktop" / "GesWorkbench" / "ges_workbench"
DST = ROOT / "desktop" / "blender" / "sath" / "shared"
FILES = ["server_client.py", "dxf_prepare.py", "assimp_load.py"]
WB_FILES = ["ges_objects.py"]  # fc_engine uchun: sath/wb/
WB_DST = ROOT / "desktop" / "blender" / "sath" / "wb"


def check() -> list[str]:
    """Farq qilgan yoki yo'q fayllar."""
    bad = [f for f in FILES if not (DST / f).exists() or not filecmp.cmp(SRC / f, DST / f, shallow=False)]
    bad += [
        "wb/" + f
        for f in WB_FILES
        if not (WB_DST / f).exists() or not filecmp.cmp(SRC / f, WB_DST / f, shallow=False)
    ]
    return bad


def sync() -> None:
    for dst, files in ((DST, FILES), (WB_DST, WB_FILES)):
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "__init__.py").write_text(
            '"""GesWorkbench dan nusxa (desktop/build/sync_blender.py). Qo\'lda tahrirlamang."""\n',
            encoding="utf-8",
        )
        for f in files:
            shutil.copyfile(SRC / f, dst / f)


if __name__ == "__main__":
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("sath nusxalari eskirgan:", ", ".join(bad), "-> python desktop/build/sync_blender.py")
            sys.exit(1)
        print("sath/shared va wb sinxron")
    else:
        sync()
        print("nusxalandi:", ", ".join(FILES + WB_FILES))
```

`desktop/tests/test_sath_pure.py`:
```python
"""sath addonining bpy siz qismlari: sync, pset guruhlash, IFC klass xaritasi, viewpoint matematikasi."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "build"))
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

import sync_blender  # noqa: E402


def test_shared_is_synced():
    assert sync_blender.check() == [], "python desktop/build/sync_blender.py ni ishga tushiring"
```

- [ ] **Step 2: FAIL** — `cd C:\Users\uge226\Desktop\BIM && .venv\Scripts\pytest -q desktop/tests/test_sath_pure.py` → AssertionError

- [ ] **Step 3: `.venv\Scripts\python desktop/build/sync_blender.py`** → pytest PASS

- [ ] **Step 4: Manifest, `__init__`, prefs, props, session, ui**

`blender_manifest.toml`:
```toml
schema_version = "1.0.0"
id = "sath"
version = "0.3.0"
name = "Sath"
tagline = "Sath serveri, GES obyektlari, DXF/DWG — Blender ichida"
maintainer = "Sath jamoasi"
type = "add-on"
blender_version_min = "5.2.0"
license = ["SPDX:MIT"]
tags = ["Import-Export", "Object"]
```

`__init__.py`:
```python
"""Sath Blender addoni: server (versiyalar, taqriz, sim, monitoring), GES obyektlari (FreeCAD dvigatel),
DXF/DWG import. IFC — Bonsai."""

from __future__ import annotations

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

MODULES: list = []
if bpy is not None:
    from . import prefs, props, ui

    MODULES = [prefs, props, ui]


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
```

`prefs.py`:
```python
"""Addon sozlamalari: server manzili, login, FreeCAD yo'li. Parol saqlanmaydi (faqat sessiya)."""

from __future__ import annotations

import os

import bpy

PKG = __package__  # "bl_ext.user_default.sath" yoki headless da "sath"
DEFAULT_FC_HOME = os.path.join(os.path.expanduser("~"), "Tools", "fc-py313")


class GesPrefs(bpy.types.AddonPreferences):
    bl_idname = PKG
    server: bpy.props.StringProperty(name="Server", default="http://localhost:8000")
    username: bpy.props.StringProperty(name="Login", default="")
    fc_home: bpy.props.StringProperty(
        name="FreeCAD papkasi",
        subtype="DIR_PATH",
        default=os.environ.get("GES_FC_HOME", DEFAULT_FC_HOME),
        description="FreeCAD 1.1 (conda-forge py313 yoki rasmiy installer) — DXF/DWG va GES obyektlari uchun",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "server")
        col.prop(self, "username")
        col.prop(self, "fc_home")


def prefs() -> GesPrefs:
    a = bpy.context.preferences.addons.get(PKG)
    if a is None:  # headless test: addon ro'yxatda yo'q
        a = bpy.context.preferences.addons.new()
        a.module = PKG
    return a.preferences


def register():
    bpy.utils.register_class(GesPrefs)


def unregister():
    bpy.utils.unregister_class(GesPrefs)
```

`props.py`:
```python
"""Sahna holati: joriy model/versiya, ro'yxat keshlari (loyihalar, modellar, versiyalar, ...)."""

from __future__ import annotations

import bpy


class GesListItem(bpy.types.PropertyGroup):
    """Universal ro'yxat elementi: server obyekti id + ustunlar."""

    item_id: bpy.props.IntProperty()
    name: bpy.props.StringProperty()
    col2: bpy.props.StringProperty()
    col3: bpy.props.StringProperty()
    col4: bpy.props.StringProperty()
    guid: bpy.props.StringProperty()
    state: bpy.props.StringProperty()
    number: bpy.props.IntProperty()


class GesScene(bpy.types.PropertyGroup):
    status: bpy.props.StringProperty(name="Holat", default="")
    project_id: bpy.props.IntProperty(default=0)
    model_id: bpy.props.IntProperty(default=0)
    version_id: bpy.props.IntProperty(default=0)
    version_number: bpy.props.IntProperty(default=0)
    model_name: bpy.props.StringProperty(default="")
    password: bpy.props.StringProperty(name="Parol", subtype="PASSWORD", default="")
    projects: bpy.props.CollectionProperty(type=GesListItem)
    projects_index: bpy.props.IntProperty(default=-1)
    models: bpy.props.CollectionProperty(type=GesListItem)
    models_index: bpy.props.IntProperty(default=-1)
    versions: bpy.props.CollectionProperty(type=GesListItem)
    versions_index: bpy.props.IntProperty(default=-1)


CLASSES = (GesListItem, GesScene)


def fill(coll, rows: list[dict]) -> None:
    """CollectionProperty ni qayta to'ldiradi."""
    coll.clear()
    for r in rows:
        it = coll.add()
        for k, v in r.items():
            setattr(it, k, v)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.ges = bpy.props.PointerProperty(type=GesScene)


def unregister():
    del bpy.types.Scene.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

`session.py`:
```python
"""Server sessiyasi: GesClient + token xotirada; server/login prefs da saqlanadi."""

from __future__ import annotations

from .shared.server_client import GesClient

_client: GesClient | None = None
_user: dict | None = None


def login(server: str, username: str, password: str) -> dict:
    global _client, _user
    c = GesClient(server)
    c.login(username, password)
    _user = c.me()
    _client = c
    from .prefs import prefs

    p = prefs()
    p.server, p.username = server, username
    return _user


def logout() -> None:
    global _client, _user
    _client = None
    _user = None


def client() -> GesClient:
    if _client is None:
        raise RuntimeError("Avval serverga kiring (Sath → Server → Ulanish)")
    return _client


def user() -> dict | None:
    return _user


def is_logged_in() -> bool:
    return _client is not None
```

`ui.py` (hozircha faqat Server paneli, operatorlar 5-vazifada):
```python
"""N-panel «Sath» yorliqlari."""

from __future__ import annotations

import bpy

from . import session


class GesPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sath"


class GES_PT_server(GesPanel, bpy.types.Panel):
    bl_label = "Server"

    def draw(self, context):
        from .prefs import prefs

        p, s = prefs(), context.scene.ges
        col = self.layout.column()
        if session.is_logged_in():
            u = session.user() or {}
            col.label(text=f"{u.get('username', '')} @ {p.server}", icon="LINKED")
            col.operator("ges.logout", icon="UNLINKED")
        else:
            col.prop(p, "server")
            col.prop(p, "username")
            col.prop(s, "password")
            col.operator("ges.connect", icon="LINKED")
        if s.status:
            col.label(text=s.status, icon="INFO")


CLASSES = [GES_PT_server]


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 5: Headless runner + smoke test**

`desktop/tests/blender_headless.py`:
```python
"""Blender headless test runner: addonni repo dan yuklaydi, testni ishga tushiradi.

  blender -b --python desktop/tests/blender_headless.py -- --test smoke [--bonsai]
Testlar: desktop/tests/sath_tests/<nom>.py, `run(ctx)`; ctx = {"addon": modul}. Exit 0 = OK.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = ROOT / "desktop" / "blender" / "sath"


def load_addon():
    """sath ni oddiy paket sifatida (extension bo'lmasdan) ro'yxatga oladi."""
    sys.path.insert(0, str(ADDON_DIR.parent))
    mod = importlib.import_module("sath")
    mod.register()
    return mod


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    name = argv[argv.index("--test") + 1] if "--test" in argv else "smoke"
    if "--bonsai" in argv:
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.bonsai")
    os.environ.setdefault("GES_FC_HOME", os.path.join(os.path.expanduser("~"), "Tools", "fc-py313"))
    addon = load_addon()
    sys.path.insert(0, str(ROOT / "desktop" / "tests" / "sath_tests"))
    try:
        importlib.import_module(name).run({"addon": addon})
        print(f"[OK] {name}", flush=True)
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print(f"[FAIL] {name}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

`desktop/tests/sath_tests/smoke.py`:
```python
"""Addon ro'yxatga olinadi, prefs/scene props bor, panel mavjud."""

import bpy


def run(ctx):
    from sath import prefs, session

    assert prefs.prefs().server.startswith("http")
    s = bpy.context.scene.ges
    assert s.model_id == 0 and s.status == ""
    assert not session.is_logged_in()
    assert hasattr(bpy.types, "GES_PT_server")
    try:
        session.client()
        raise AssertionError("client() login siz RuntimeError berishi kerak")
    except RuntimeError:
        pass
```

- [ ] **Step 6: Run** `%USERPROFILE%\Tools\blender-5.2\blender.exe -b --python desktop/tests/blender_headless.py -- --test smoke` → `[OK] smoke`, exit 0.

- [ ] **Step 7: ruff + pytest + commit**

```bash
cd C:\Users\uge226\Desktop\BIM && .venv\Scripts\ruff check desktop && .venv\Scripts\pytest -q desktop/tests/test_sath_pure.py
git add desktop/blender/sath desktop/build/sync_blender.py desktop/tests/blender_headless.py desktop/tests/sath_tests desktop/tests/test_sath_pure.py
git commit -m "sath: Blender addon skeleti (prefs, session, sync_blender, headless runner)"
```

---

### Task 2: fc_engine — FreeCAD dvigatel

**Files:**
- Create: `desktop/blender/sath/fc_engine.py`
- Test: `desktop/tests/sath_tests/engine.py`, `desktop/tests/test_sath_pure.py` (qo'shimcha)

**Interfaces:**
- Produces: `fc_engine.available() -> bool`; `fc_engine.load()` → `FreeCAD` moduli (RuntimeError agar yo'q); `fc_engine.doc()` — yashirin hujjat `GES_Engine`;
  `fc_engine.shape_to_mesh(shape, mesh, tol=0.5)` — bpy Mesh ni to'ldiradi (metr); `fc_engine.last_shape()`;
  `fc_engine.ges_kinds() -> list[tuple[str, str]]`; `fc_engine.ges_schema(kind) -> list[dict]` (`{name, label, type: length|float|int|enum, default, items}`, uzunlik metrda);
  `fc_engine.ges_build(kind, params) -> GesBuild(verts, faces, ifc_class, psets)`; `fc_engine.ifc_class(freecad_type) -> str`; `fc_engine._parse_props(raw) -> dict`.
- Consumes: `sath/wb/ges_objects.py` (sync nusxa, 1-vazifadagi `sync_blender.py` `WB_FILES`).

- [ ] **Step 1: Test** `desktop/tests/sath_tests/engine.py`

```python
"""FreeCAD yuklanadi, GES sxemasi va build ishlaydi, mesh metrda, hujjat bo'sh qoladi."""

import bpy


def run(ctx):
    from sath import fc_engine

    assert fc_engine.available(), "FreeCAD topilmadi (GES_FC_HOME)"
    assert fc_engine.load().Version()[0] == "1"
    kinds = dict(fc_engine.ges_kinds())
    assert set(kinds) == {
        "GES_Dam", "GES_Penstock", "GES_Turbine", "GES_Spillway",
        "GES_Powerhouse", "GES_Transformer", "GES_Intake",
    }  # fmt: skip
    schema = {f["name"]: f for f in fc_engine.ges_schema("GES_Dam")}
    assert schema["Height"]["type"] == "length" and abs(schema["Height"]["default"] - 20.0) < 1e-6
    assert schema["DamType"]["type"] == "enum" and "Gravitatsion" in schema["DamType"]["items"]
    b = fc_engine.ges_build("GES_Dam", {"Height": 30.0, "Length": 100.0})
    assert b.ifc_class == "IfcWall"
    assert b.psets["Pset_GES_Dam"]["Balandlik_m"] == 30.0
    assert b.psets["Pset_GES_Dam"]["Uzunlik_m"] == 100.0
    assert abs(max(v[2] for v in b.verts) - 30.0) < 1e-6
    me = bpy.data.meshes.new("t")
    fc_engine.shape_to_mesh(fc_engine.last_shape(), me)
    assert len(me.polygons) == len(b.faces)
    for kind in kinds:
        bb = fc_engine.ges_build(kind, {})
        assert bb.verts and bb.faces and bb.ifc_class.startswith("Ifc"), kind
    assert len(fc_engine.doc().Objects) == 0
```

- [ ] **Step 2: FAIL** — `blender -b --python desktop/tests/blender_headless.py -- --test engine` → `ImportError ... fc_engine`

- [ ] **Step 3: `fc_engine.py`**

```python
"""FreeCAD ni Blender jarayoniga yuklash (retsept: docs/spike-blender-freecad.md) va stateless geometriya.

Qoida: FreeCAD site-packages sys.path OXIRIDA (Blender numpy, Bonsai ifcopenshell ustun). QApplication yo'q.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MM = 1000.0
WB_DIR = Path(__file__).resolve().parent / "wb"
_fc = None
_doc = None
_last_shape = None


def fc_home() -> str:
    env = os.environ.get("GES_FC_HOME")
    if env:
        return env
    try:
        from .prefs import prefs

        return prefs().fc_home
    except Exception:  # noqa: BLE001 — bpy kontekstisiz (pytest)
        return os.path.join(os.path.expanduser("~"), "Tools", "fc-py313")


def _layout(home: str) -> tuple[str, str]:
    """(root, site-packages): conda-forge (`Library/bin`) yoki rasmiy installer (`bin/Lib/site-packages`)."""
    if os.path.isdir(os.path.join(home, "Library", "bin")):
        return os.path.join(home, "Library"), os.path.join(home, "Lib", "site-packages")
    return home, os.path.join(home, "bin", "Lib", "site-packages")


def available() -> bool:
    root, _ = _layout(fc_home())
    return os.path.isfile(os.path.join(root, "bin", "FreeCAD.pyd")) or os.path.isfile(
        os.path.join(root, "lib", "FreeCAD.so")
    )


def load():
    """`import FreeCAD` — bir marta. RuntimeError: topilmadi."""
    global _fc
    if _fc is not None:
        return _fc
    home = fc_home()
    if not available():
        raise RuntimeError(f"FreeCAD topilmadi: {home} (Sozlamalar → Sath → FreeCAD papkasi)")
    root, site = _layout(home)
    fc_bin, fc_lib = os.path.join(root, "bin"), os.path.join(root, "lib")
    if hasattr(os, "add_dll_directory"):
        for d in (fc_bin, fc_lib):
            os.add_dll_directory(d)
    for d in (fc_bin, fc_lib, os.path.join(root, "Ext"), site, str(WB_DIR)):
        if d not in sys.path:
            sys.path.append(d)
    import FreeCAD

    _fc = FreeCAD
    return _fc


def doc():
    """Yashirin ishchi hujjat (obyektlar build dan keyin o'chiriladi)."""
    global _doc
    FreeCAD = load()
    if _doc is None or _doc.Name not in FreeCAD.listDocuments():
        _doc = FreeCAD.newDocument("GES_Engine")
    FreeCAD.setActiveDocument(_doc.Name)
    return _doc


def last_shape():
    return _last_shape


def shape_to_mesh(shape, mesh, tol: float = 0.5) -> None:
    """Part.Shape (mm) → bpy Mesh (m)."""
    import numpy as np

    verts, faces = shape.tessellate(tol)
    co = np.array([(v.x, v.y, v.z) for v in verts], dtype=np.float64) / MM
    mesh.clear_geometry()
    mesh.from_pydata(co.tolist(), [], faces)
    mesh.update()


def _wb():
    load()
    import ges_objects  # sath/wb (workbench nusxasi)

    return ges_objects


def ges_kinds() -> list[tuple[str, str]]:
    return [(k, v[0]) for k, v in _wb().OBJECTS.items()]


def ifc_class(freecad_ifc_type: str) -> str:
    """FreeCAD IfcType ("Pipe Segment") → IFC klass ("IfcPipeSegment")."""
    return "Ifc" + freecad_ifc_type.replace(" ", "")


def ges_schema(kind: str) -> list[dict]:
    """GES guruhidagi xususiyatlar: nom, izoh, tur, sukut (uzunlik metrda), enum variantlari."""
    d = doc()
    obj = _wb().make(kind)
    try:
        out = []
        for p in obj.PropertiesList:
            if obj.getGroupOfProperty(p) != "GES":
                continue
            t = obj.getTypeIdOfProperty(p)
            f: dict = {"name": p, "label": obj.getDocumentationOfProperty(p) or p, "items": []}
            if t == "App::PropertyLength":
                f.update(type="length", default=float(getattr(obj, p).Value) / MM)
            elif t == "App::PropertyEnumeration":
                f.update(type="enum", default=str(getattr(obj, p)), items=list(obj.getEnumerationsOfProperty(p)))
            elif t == "App::PropertyInteger":
                f.update(type="int", default=int(getattr(obj, p)))
            else:
                f.update(type="float", default=float(getattr(obj, p)))
            out.append(f)
        return out
    finally:
        d.removeObject(obj.Name)


@dataclass
class GesBuild:
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    ifc_class: str = "IfcBuildingElementProxy"
    psets: dict = field(default_factory=dict)


def _parse_props(raw: dict) -> dict[str, dict]:
    """IfcProperties "Pset;;IfcType;;value" → {pset: {name: value}} (workbench ifc_io._write_psets kabi)."""
    grouped: dict[str, dict] = {}
    for name, s in dict(raw).items():
        parts = str(s).split(";;")
        if len(parts) != 3:
            continue
        pset, ptype, value = parts
        if ptype in ("IfcReal", "IfcLengthMeasure", "IfcPositiveLengthMeasure"):
            try:
                value = float(value)
            except ValueError:
                pass
        elif ptype in ("IfcInteger", "IfcCountMeasure"):
            try:
                value = int(float(value))
            except ValueError:
                pass
        elif ptype == "IfcBoolean":
            value = str(value).lower() in ("true", "1", "yes")
        grouped.setdefault(pset, {})[name] = value
    return grouped


def ges_build(kind: str, params: dict) -> GesBuild:
    """Parametrlar (metr) → FreeCAD obyekt → tessellate (metr) + IFC klass + psetlar. Hujjat bo'sh qoladi."""
    global _last_shape
    d = doc()
    obj = _wb().make(kind)
    try:
        for p, v in params.items():
            if p not in obj.PropertiesList:
                continue
            t = obj.getTypeIdOfProperty(p)
            if t == "App::PropertyLength":
                setattr(obj, p, float(v) * MM)
            elif t == "App::PropertyInteger":
                setattr(obj, p, int(v))
            elif t == "App::PropertyEnumeration":
                setattr(obj, p, str(v))
            else:
                setattr(obj, p, float(v))
        d.recompute()
        shape = obj.Shape.copy()
        _last_shape = shape
        verts, faces = shape.tessellate(0.5)
        return GesBuild(
            verts=[(v.x / MM, v.y / MM, v.z / MM) for v in verts],
            faces=[tuple(f) for f in faces],
            ifc_class=ifc_class(obj.IfcType),
            psets=_parse_props(obj.IfcProperties),
        )
    finally:
        d.removeObject(obj.Name)
```

- [ ] **Step 4: PASS** — `--test engine` → `[OK] engine`

- [ ] **Step 5: pytest (bpy siz)** — `test_sath_pure.py` ga:

```python
from sath import fc_engine  # noqa: E402


def test_parse_props_groups_by_pset_and_casts():
    raw = {
        "Balandlik_m": "Pset_GES_Dam;;IfcReal;;20.0",
        "Turi": "Pset_GES_Dam;;IfcLabel;;Gravitatsion",
        "Soni": "Pset_GES_Turbine;;IfcInteger;;3",
        "Buzuq": "faqat-bitta-qism",
    }
    assert fc_engine._parse_props(raw) == {
        "Pset_GES_Dam": {"Balandlik_m": 20.0, "Turi": "Gravitatsion"},
        "Pset_GES_Turbine": {"Soni": 3},
    }


def test_ifc_class_from_freecad_type():
    assert fc_engine.ifc_class("Pipe Segment") == "IfcPipeSegment"
    assert fc_engine.ifc_class("Wall") == "IfcWall"
    assert fc_engine.ifc_class("Building Element Proxy") == "IfcBuildingElementProxy"
```

- [ ] **Step 6: ruff, pytest, commit** — `git commit -m "sath: fc_engine — FreeCAD in-process, GES sxema/build"`

---

### Task 3: ifc.py — Bonsai ko'prigi

**Files:**
- Create: `desktop/blender/sath/ifc.py`
- Test: `desktop/tests/sath_tests/ifc_bridge.py` (`--bonsai`)

**Interfaces:**
- Produces: `ifc.file()` → ifcopenshell file yoki None; `ifc.ensure_project()`; `ifc.load(path: Path)`; `ifc.save(path: Path) -> Path`;
  `ifc.entity(obj)` / `ifc.guid(obj) -> str|None`; `ifc.guid_map() -> dict[str, bpy.types.Object]`; `ifc.object_for_guid(guid)`;
  `ifc.assign_class(obj, ifc_class: str, psets: dict[str, dict] | None = None)`; `ifc.write_psets(entity, psets)`; `ifc.update_representation(obj)`;
  `ifc.ColorState` (`paint(colors: dict[str, tuple]) -> int`, `restore()`), `ifc.DIFF_STATE`, `ifc.ALARM_STATE`, `ifc.DIFF_COLORS`, `ifc.ALARM_COLORS`;
  `ifc.select_guids(guids: list[str]) -> int`.
- Consumes: Bonsai `bonsai.tool.Ifc`, `bpy.ops.bim.*`.

- [ ] **Step 1: Test** `desktop/tests/sath_tests/ifc_bridge.py`

```python
"""Bonsai: loyiha ochish/yaratish, mesh → IFC element + Pset_GES_*, guid xaritasi, rang holati, saqlash."""

import os
import tempfile
from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def _cube(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)],
    )
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def run(ctx):
    from sath import ifc

    assert ifc.file() is None
    ifc.load(SAMPLE)
    f = ifc.file()
    assert f is not None and len(f.by_type("IfcProduct")) == 20
    gm = ifc.guid_map()
    assert len(gm) >= 16 and all(len(g) == 22 for g in gm)
    dam = next(o for g, o in gm.items() if ifc.entity(o).is_a("IfcWall"))
    assert ifc.guid(dam) == ifc.entity(dam).GlobalId
    assert ifc.object_for_guid(ifc.guid(dam)) is dam

    ob = _cube("Yangi_togon")
    ifc.assign_class(ob, "IfcWall", {"Pset_GES_Dam": {"Balandlik_m": 12.5, "Turi": "Tuproq"}})
    e = ifc.entity(ob)
    assert e.is_a("IfcWall")
    import ifcopenshell.util.element as ue

    assert ue.get_psets(e)["Pset_GES_Dam"]["Balandlik_m"] == 12.5
    ob.data.vertices[4].co.z = 3.0
    ifc.update_representation(ob)

    st = ifc.ColorState()
    n = st.paint({ifc.guid(dam): (1, 0, 0, 1), "yoq_guid": (0, 1, 0, 1)})
    assert n == 1 and tuple(dam.color)[:3] == (1.0, 0.0, 0.0)
    st.restore()
    assert tuple(dam.color) == (1.0, 1.0, 1.0, 1.0)
    assert ifc.select_guids([ifc.guid(dam)]) == 1 and dam.select_set

    out = Path(tempfile.gettempdir()) / "sath_test.ifc"
    ifc.save(out)
    import ifcopenshell

    f2 = ifcopenshell.open(str(out))
    walls = {w.Name: w for w in f2.by_type("IfcWall")}
    assert "Yangi_togon" in walls and ue.get_psets(walls["Yangi_togon"])["Pset_GES_Dam"]["Turi"] == "Tuproq"
    assert e.GlobalId in {p.GlobalId for p in f2.by_type("IfcProduct")}
    os.remove(out)
```

- [ ] **Step 2: FAIL** — `blender -b --python desktop/tests/blender_headless.py -- --test ifc_bridge --bonsai` → ImportError

- [ ] **Step 3: `ifc.py`**

```python
"""Bonsai (IFC) ko'prigi: loyiha ochish/saqlash, obyekt ↔ IFC element, Pset_GES_*, rang holati (diff/alarm)."""

from __future__ import annotations

from pathlib import Path

import bpy

DIFF_COLORS = {"added": (0.25, 0.7, 0.35, 1.0), "changed": (0.9, 0.7, 0.2, 1.0), "deleted": (0.85, 0.3, 0.3, 1.0)}
ALARM_COLORS = {
    "ok": (0.23, 0.66, 0.39, 1.0),
    "low": (0.88, 0.4, 0.42, 1.0),
    "high": (0.88, 0.4, 0.42, 1.0),
    "stale": (0.42, 0.43, 0.46, 1.0),
}


def _tool():
    try:
        import bonsai.tool as tool
    except ImportError as e:
        raise RuntimeError("Bonsai addoni yoqilmagan (Edit → Preferences → Extensions → Bonsai)") from e
    return tool


def file():
    """Joriy IFC fayl (ifcopenshell) yoki None."""
    try:
        return _tool().Ifc.get()
    except RuntimeError:
        return None


def ensure_project():
    """Bonsai loyihasi yo'q bo'lsa — yangi (IFC4, My Site/Building/Storey)."""
    if file() is None:
        bpy.ops.bim.create_project()
    return file()


def load(path: Path) -> None:
    bpy.ops.bim.load_project(filepath=str(path), should_start_fresh_session=True)


def save(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.bim.save_project(filepath=str(path), should_save_as=True)
    return path


def entity(obj):
    return _tool().Ifc.get_entity(obj)


def guid(obj) -> str | None:
    e = entity(obj)
    return getattr(e, "GlobalId", None) if e is not None else None


def guid_map() -> dict[str, bpy.types.Object]:
    out = {}
    for o in bpy.data.objects:
        g = guid(o)
        if g:
            out[g] = o
    return out


def object_for_guid(g: str):
    f = file()
    if f is None:
        return None
    try:
        return _tool().Ifc.get_object(f.by_guid(g))
    except RuntimeError:
        return None


def write_psets(e, psets: dict[str, dict]) -> None:
    """{pset: {name: value}} → IfcPropertySet lar (mavjud bo'lsa yangilanadi)."""
    import ifcopenshell.api.pset as api
    import ifcopenshell.util.element as ue

    f = file()
    existing = ue.get_psets(e)
    for name, values in psets.items():
        if name in existing:
            ps = f.by_id(existing[name]["id"])
        else:
            ps = api.add_pset(f, product=e, name=name)
        api.edit_pset(f, pset=ps, properties=values)


def _activate(obj) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def assign_class(obj, ifc_class: str, psets: dict[str, dict] | None = None):
    """Mesh obyektni IFC element qiladi (Bonsai konteynerga o'zi joylaydi), psetlarni yozadi."""
    ensure_project()
    _activate(obj)
    bpy.ops.bim.assign_class(ifc_class=ifc_class)
    e = entity(obj)
    if psets:
        write_psets(e, psets)
    return e


def update_representation(obj) -> None:
    bpy.ops.bim.update_representation(obj=obj.name)


def select_guids(guids: list[str]) -> int:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    n = 0
    for g in guids:
        o = object_for_guid(g)
        if o is not None:
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            n += 1
    return n


class ColorState:
    """Obyekt ranglarini vaqtincha almashtirish (diff / alarm) va qaytarish. Viewport: Object color."""

    def __init__(self):
        self.saved: dict[str, tuple] = {}

    def paint(self, colors: dict[str, tuple]) -> int:
        n = 0
        for g, rgba in colors.items():
            o = object_for_guid(g)
            if o is None:
                continue
            if o.name not in self.saved:
                self.saved[o.name] = tuple(o.color)
            o.color = rgba
            n += 1
        if n:
            for area in getattr(bpy.context.screen, "areas", []):
                if area.type == "VIEW_3D":
                    area.spaces.active.shading.color_type = "OBJECT"
        return n

    def restore(self) -> None:
        for name, rgba in self.saved.items():
            o = bpy.data.objects.get(name)
            if o is not None:
                o.color = rgba
        self.saved.clear()


DIFF_STATE = ColorState()
ALARM_STATE = ColorState()
```

- [ ] **Step 4: PASS** — `--test ifc_bridge --bonsai` → `[OK]`. `write_psets` da `existing[name]["id"]` — Bonsai `get_psets` har psetga `id` qo'shadi (spike S5d shuni ko'rsatdi).

- [ ] **Step 5: ruff, commit** — `git commit -m "sath: ifc — Bonsai ko'prigi (load/save, element, psetlar, rang holati)"`

---

### Task 4: GES parametrik obyektlari

**Files:**
- Create: `desktop/blender/sath/ges_objects.py`
- Modify: `desktop/blender/sath/__init__.py` (MODULES ga `ges_objects`), `ui.py` (`GES_PT_objects`)
- Test: `desktop/tests/sath_tests/objects.py` (`--bonsai`)

**Interfaces:**
- Produces: `Object.ges` (`GesObject`: `kind: str`, `params: Collection[GesParam]`, `busy: bool`); `GesParam` (`name, label, ptype, value_float, value_int, value_enum(items dinamik), items(";" bilan)`);
  `ges_objects.add(context, kind, name=None) -> Object`; `ges_objects.rebuild(obj)`; `ges_objects.params_dict(obj) -> dict`; operator `ges.add_object` (`kind` enum prop); `ges.rebuild_object`.

- [ ] **Step 1: Test** `desktop/tests/sath_tests/objects.py`

```python
"""7 GES obyekt yaratiladi: mesh, IFC klass, Pset_GES_*; parametr o'zgarsa mesh va pset yangilanadi."""

import bpy


def run(ctx):
    import ifcopenshell.util.element as ue

    from sath import fc_engine, ges_objects, ifc

    kinds = [k for k, _ in fc_engine.ges_kinds()]
    made = {}
    for k in kinds:
        ob = ges_objects.add(bpy.context, k)
        assert ob.ges.kind == k and len(ob.data.polygons) > 0, k
        e = ifc.entity(ob)
        assert e is not None and e.is_a().startswith("Ifc"), k
        made[k] = ob
    dam = made["GES_Dam"]
    ps = ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]
    assert ps["Balandlik_m"] == 20.0
    h = next(p for p in dam.ges.params if p.name == "Height")
    assert h.ptype == "length" and h.value_float == 20.0
    h.value_float = 35.0  # update callback → rebuild
    assert abs(dam.dimensions.z - 35.0) < 1e-3, dam.dimensions.z
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Balandlik_m"] == 35.0
    t = next(p for p in dam.ges.params if p.name == "DamType")
    assert t.ptype == "enum" and "Arkali" in t.items.split(";")
    t.value_enum = "Arkali"
    assert ue.get_psets(ifc.entity(dam))["Pset_GES_Dam"]["Turi"] == "Arkali"
    assert bpy.ops.ges.add_object(kind="GES_Turbine") == {"FINISHED"}
    assert sum(1 for o in bpy.data.objects if o.ges.kind == "GES_Turbine") == 2
```

- [ ] **Step 2: FAIL** — `--test objects --bonsai`

- [ ] **Step 3: `ges_objects.py`**

```python
"""GES parametrik obyektlari Blender da: parametrlar obyektda (Object.ges), geometriya FreeCAD dan (fc_engine),
IFC element + Pset_GES_* Bonsai da. Parametr o'zgarsa mesh va psetlar qayta quriladi."""

from __future__ import annotations

import bpy

from . import fc_engine, ifc

KIND_ITEMS = [
    ("GES_Dam", "To'g'on", ""),
    ("GES_Penstock", "Bosimli quvur", ""),
    ("GES_Turbine", "Turbina agregati", ""),
    ("GES_Spillway", "Suv tashlagich", ""),
    ("GES_Powerhouse", "Mashina zali", ""),
    ("GES_Transformer", "Transformator", ""),
    ("GES_Intake", "Suv qabul qilgich", ""),
]
KIND_LABEL = {k: v for k, v, _ in KIND_ITEMS}


def _enum_items(self, context):
    return [(x, x, "") for x in self.items.split(";") if x]


def _changed(self, context):
    obj = self.id_data
    if getattr(obj, "ges", None) is not None and obj.ges.kind and not obj.ges.busy:
        rebuild(obj)


class GesParam(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ptype: bpy.props.StringProperty()  # length | float | int | enum
    items: bpy.props.StringProperty()  # enum: "a;b;c"
    value_float: bpy.props.FloatProperty(precision=3, update=_changed)
    value_int: bpy.props.IntProperty(update=_changed)
    value_enum: bpy.props.EnumProperty(items=_enum_items, update=_changed)


class GesObject(bpy.types.PropertyGroup):
    kind: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty(default=False)
    params: bpy.props.CollectionProperty(type=GesParam)


def params_dict(obj) -> dict:
    out = {}
    for p in obj.ges.params:
        if p.ptype == "enum":
            out[p.name] = p.value_enum
        elif p.ptype == "int":
            out[p.name] = p.value_int
        else:
            out[p.name] = p.value_float
    return out


def _fill_schema(obj, kind: str) -> None:
    g = obj.ges
    g.busy = True
    try:
        g.kind = kind
        g.params.clear()
        for f in fc_engine.ges_schema(kind):
            p = g.params.add()
            p.name, p.label, p.ptype = f["name"], f["label"], f["type"]
            if f["type"] == "enum":
                p.items = ";".join(f["items"])
                p.value_enum = f["default"]
            elif f["type"] == "int":
                p.value_int = f["default"]
            else:
                p.value_float = f["default"]
    finally:
        g.busy = False


def rebuild(obj) -> None:
    """FreeCAD dan geometriya, mesh ni almashtirish, IFC representation + psetlarni yangilash."""
    g = obj.ges
    b = fc_engine.ges_build(g.kind, params_dict(obj))
    me = obj.data
    me.clear_geometry()
    me.from_pydata(b.verts, [], b.faces)
    me.update()
    e = ifc.entity(obj)
    if e is None:
        ifc.assign_class(obj, b.ifc_class, b.psets)
    else:
        ifc.update_representation(obj)
        ifc.write_psets(e, b.psets)


def add(context, kind: str, name: str | None = None):
    me = bpy.data.meshes.new(kind)
    obj = bpy.data.objects.new(name or KIND_LABEL[kind], me)
    context.scene.collection.objects.link(obj)
    _fill_schema(obj, kind)
    rebuild(obj)
    return obj


class GES_OT_add_object(bpy.types.Operator):
    """GES obyekti qo'shish (FreeCAD geometriya, IFC element + Pset_GES_*)"""

    bl_idname = "ges.add_object"
    bl_label = "GES obyekti"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(name="Turi", items=KIND_ITEMS)

    @classmethod
    def poll(cls, context):
        return fc_engine.available()

    def execute(self, context):
        try:
            obj = add(context, self.kind)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Obyekt yaratilmadi: {e}")
            return {"CANCELLED"}
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"{KIND_LABEL[self.kind]} qo'shildi")
        return {"FINISHED"}


class GES_OT_rebuild_object(bpy.types.Operator):
    """Tanlangan GES obyektlarini qayta hisoblash"""

    bl_idname = "ges.rebuild_object"
    bl_label = "Qayta qurish"

    def execute(self, context):
        n = 0
        for o in context.selected_objects:
            if o.ges.kind:
                rebuild(o)
                n += 1
        self.report({"INFO"}, f"{n} obyekt qayta qurildi")
        return {"FINISHED"}


class GES_PT_objects(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Sath"
    bl_label = "GES obyektlari"

    def draw(self, context):
        lay = self.layout
        if not fc_engine.available():
            lay.label(text="FreeCAD topilmadi — Sozlamalar → Sath", icon="ERROR")
            return
        grid = lay.grid_flow(columns=2, align=True)
        for k, label, _ in KIND_ITEMS:
            grid.operator("ges.add_object", text=label).kind = k
        obj = context.active_object
        if obj is None or not obj.ges.kind:
            return
        box = lay.box()
        box.label(text=f"{KIND_LABEL.get(obj.ges.kind, obj.ges.kind)}: {obj.name}", icon="MOD_BUILD")
        for p in obj.ges.params:
            row = box.row()
            if p.ptype == "enum":
                row.prop(p, "value_enum", text=p.label)
            elif p.ptype == "int":
                row.prop(p, "value_int", text=p.label)
            else:
                row.prop(p, "value_float", text=p.label + (", m" if p.ptype == "length" else ""))
        box.operator("ges.rebuild_object", icon="FILE_REFRESH")


CLASSES = (GesParam, GesObject, GES_OT_add_object, GES_OT_rebuild_object, GES_PT_objects)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.ges = bpy.props.PointerProperty(type=GesObject)


def unregister():
    del bpy.types.Object.ges
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

`__init__.py`: `from . import ges_objects, prefs, props, ui` → `MODULES = [prefs, props, ges_objects, ui]`.

- [ ] **Step 4: PASS** — `--test objects --bonsai`. Agar `update` callback headless da `dimensions` yangilanmasa — testda `bpy.context.view_layer.update()` chaqirish.

- [ ] **Step 5: ruff, commit** — `git commit -m "sath: GES parametrik obyektlari (Object.ges, FreeCAD build, IFC+pset)"`

---

### Task 5: Server oqimlari — flows.py, ops_server.py, UI (Server/Model)

**Files:**
- Create: `desktop/blender/sath/flows.py`, `ops_server.py`
- Modify: `ui.py` (GES_PT_model, UIList lar), `__init__.py`, `props.py` (`notifications` ro'yxati, `commit_message`, `submit_after_commit`)
- Test: `desktop/tests/test_sath_flows.py` (pytest, real server), `desktop/tests/sath_tests/server_ops.py` (headless, server stub siz — faqat ro'yxat to'ldirish)

**Interfaces:**
- Produces (`flows`, bpy siz, `client` argumenti `GesClient`): `cache_dir() -> Path` (`%TEMP%/sath`); `project_rows(client) -> list[dict]`; `model_rows(client, project_id)`; `version_rows(client, model_id)`;
  `download_version(client, model, version) -> Path`; `commit(client, model_id, ifc_path, message, parent_id, submit) -> dict` (`{"version": v, "cr": cr|None}`);
  `check_update(client, current_version: str) -> str|None` (xabar matni); `unread_summary(client) -> str|None`; `web_url(client, saved_server, path) -> str`; `model_role(client, model_id) -> str|None`; `ADDON_VERSION`.
- Produces (`ops_server`): `ges.connect`, `ges.logout`, `ges.refresh_projects`, `ges.refresh_models`, `ges.refresh_versions`, `ges.open_version`, `ges.commit`, `ges.submit`, `ges.open_web`, `ges.create_model`, `ges.notifications`, `ges.mark_read`;
  yordamchi `ops_server.guard(op, fn)` — ServerError/RuntimeError → `op.report`.

- [ ] **Step 1: pytest** `desktop/tests/test_sath_flows.py` (server fixture `test_server_client.py` dagi kabi; `make_ifc` server/tests/conftest.py dan)

```python
"""sath.flows — real server bilan (uvicorn alohida oqim), bpy siz."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
sys.path.insert(0, str(ROOT / "server" / "tests"))

_TMP = Path(tempfile.mkdtemp(prefix="sath_flows_"))
os.environ["GES_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GES_DATA_DIR"] = str(_TMP)
os.environ["GES_SECRET_KEY"] = "desktop-test-secret-key-at-least-32-bytes"
os.environ["GES_ADMIN_PASSWORD"] = "admin123"

import uvicorn  # noqa: E402
from conftest import make_ifc  # noqa: E402
from ges_server.main import app  # noqa: E402

from sath import flows  # noqa: E402
from sath.shared.server_client import GesClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        try:
            c = GesClient(f"http://127.0.0.1:{port}")
            c.health()
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    c.login("admin", "admin123")
    yield c
    server.should_exit = True


def test_rows_and_commit_roundtrip(client, tmp_path):
    projects = flows.project_rows(client)
    assert projects, "serverda kamida bitta loyiha (admin seed) bo'lishi kerak"
    pid = projects[0]["item_id"]
    m = client.create_model(pid, "flows-test")
    ifc_path = tmp_path / "a.ifc"
    make_ifc(ifc_path)
    r = flows.commit(client, m["id"], ifc_path, "birinchi", None, submit=True)
    assert r["version"]["number"] == 1 and r["cr"] is not None
    rows = flows.version_rows(client, m["id"])
    assert rows[0]["number"] == 1 and rows[0]["item_id"] == r["version"]["id"]
    dest = flows.download_version(client, {"id": m["id"]}, r["version"])
    assert dest.exists() and dest.name == f"m{m['id']}_v1.ifc"
    assert flows.model_rows(client, pid)[0]["name"].startswith("flows-test")


def test_check_update_and_web_url(client):
    assert flows.check_update(client, "999.0.0") is None
    assert flows.web_url(client, client.base_url, "/models/1").startswith("http://127.0.0.1")
    assert flows.model_role(client, 1) in ("viewer", "engineer", "approver", None)
```
Agar `projects` bo'sh bo'lsa (seed yo'q) — testda `client._json("POST", "/api/projects", {"name": "P"})` bilan yaratish (server API `POST /api/projects` bor — `server/ges_server` da tekshirib, kerak bo'lsa moslash).

- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest -q desktop/tests/test_sath_flows.py` → ImportError flows

- [ ] **Step 3: `flows.py`**

```python
"""Server oqimlari — bpy siz (pytest bilan real server ustida sinaladi). Operatorlar shularni chaqiradi."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .shared.server_client import GesClient, ServerError

ADDON_VERSION = "0.3.0"  # blender_manifest.toml bilan bir xil (10-vazifa: manifestdan o'qish)


def cache_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "sath"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dt(s: str | None) -> str:
    return str(s or "")[:16].replace("T", " ")


def project_rows(client: GesClient) -> list[dict]:
    return [{"item_id": p["id"], "name": p["name"], "state": p.get("my_role") or ""} for p in client.projects()]


def model_rows(client: GesClient, project_id: int) -> list[dict]:
    return [
        {"item_id": m["id"], "name": m["name"], "col2": f"{m.get('version_count', 0)} versiya"}
        for m in client.models(project_id)
    ]


def version_rows(client: GesClient, model_id: int) -> list[dict]:
    rows = []
    for v in sorted(client.versions(model_id), key=lambda x: -x["number"]):
        rows.append(
            {
                "item_id": v["id"],
                "number": v["number"],
                "name": f"v{v['number']}",
                "state": v.get("state", ""),
                "col2": v.get("message", ""),
                "col3": v.get("author_username", ""),
                "col4": _dt(v.get("created_at")),
            }
        )
    return rows


def download_version(client: GesClient, model: dict, version: dict) -> Path:
    dest = cache_dir() / f"m{model['id']}_v{version['number']}.ifc"
    client.download_version(version["id"], dest)
    return dest


def commit(
    client: GesClient, model_id: int, ifc_path: Path, message: str, parent_id: int | None, submit: bool
) -> dict:
    v = client.upload_version(model_id, ifc_path, message, parent_id)
    cr = None
    if submit:
        cr = client.create_change_request(model_id, v["id"], message[:200] or f"v{v['number']}")
    return {"version": v, "cr": cr}


def check_update(client: GesClient, current: str) -> str | None:
    """Serverda yangiroq desktop paketi bo'lsa — xabar matni."""
    try:
        latest = client.desktop_latest()
    except ServerError:
        return None
    if not latest:
        return None
    try:
        if tuple(int(x) for x in latest["version"].split(".")) <= tuple(int(x) for x in current.split(".")):
            return None
    except ValueError:
        return None
    return f"Yangi Sath versiyasi: {latest['version']} (sizda {current}) — {client.base_url}{latest['url']}"


def unread_summary(client: GesClient) -> str | None:
    try:
        n = client.notifications(unread=True, limit=5)
    except ServerError:
        return None
    return f"{len(n)} ta o'qilmagan bildirishnoma — {n[0]['title']}" if n else None


def web_url(client: GesClient, saved_server: str, path: str) -> str:
    """Prod da web shu serverdan; dev da (health.web = False, :8000) Vite :5173."""
    base = saved_server.rstrip("/")
    try:
        if not client.health().get("web", True) and base.endswith(":8000"):
            base = base[: -len(":8000")] + ":5173"
    except ServerError:
        pass
    return f"{base}{path}"


def model_role(client: GesClient, model_id: int) -> str | None:
    try:
        return client.project(client.model(model_id)["project_id"]).get("my_role")
    except ServerError:
        return None


def notification_rows(client: GesClient) -> list[dict]:
    return [
        {
            "item_id": n["id"],
            "name": n["title"],
            "col2": n["kind"],
            "col3": _dt(n.get("created_at")),
            "col4": n.get("body") or "",
            "state": "read" if n.get("read_at") else "unread",
        }
        for n in client.notifications(unread=False, limit=50)
    ]
```

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: `props.py` ga qo'shish**

```python
    commit_message: bpy.props.StringProperty(name="Izoh", default="")
    submit_after_commit: bpy.props.BoolProperty(name="Darhol tasdiqqa yuborish", default=False)
    new_model_name: bpy.props.StringProperty(name="Yangi model nomi", default="")
    notifications: bpy.props.CollectionProperty(type=GesListItem)
    notifications_index: bpy.props.IntProperty(default=-1)
```

- [ ] **Step 6: `ops_server.py`**

```python
"""Server operatorlari: ulanish, loyiha/model/versiya ro'yxatlari, ochish, commit, tasdiqqa yuborish, web, bildirishnomalar."""

from __future__ import annotations

import webbrowser

import bpy

from . import flows, ifc, props, session
from .prefs import prefs
from .shared.server_client import ServerError


def guard(op, fn):
    """ServerError/RuntimeError → op.report; muvaffaqiyat → True."""
    try:
        fn()
        return True
    except (ServerError, RuntimeError) as e:
        op.report({"ERROR"}, str(getattr(e, "message", e)))
        return False


def _sel(coll, index):
    return coll[index] if 0 <= index < len(coll) else None


class GES_OT_connect(bpy.types.Operator):
    """Sath serveriga kirish"""

    bl_idname = "ges.connect"
    bl_label = "Ulanish"

    def execute(self, context):
        p, s = prefs(), context.scene.ges

        def do():
            u = session.login(p.server, p.username, s.password)
            s.password = ""
            s.status = f"{u['username']} sifatida kirildi"
            msg = flows.check_update(session.client(), flows.ADDON_VERSION)
            if msg:
                self.report({"WARNING"}, msg)
            n = flows.unread_summary(session.client())
            if n:
                s.status += f" · {n}"
            props.fill(s.projects, flows.project_rows(session.client()))
            s.projects_index = 0 if len(s.projects) else -1

        if not guard(self, do):
            return {"CANCELLED"}
        bpy.ops.ges.refresh_models()
        return {"FINISHED"}


class GES_OT_logout(bpy.types.Operator):
    bl_idname = "ges.logout"
    bl_label = "Chiqish"

    def execute(self, context):
        session.logout()
        s = context.scene.ges
        for c in (s.projects, s.models, s.versions):
            c.clear()
        s.status = ""
        return {"FINISHED"}


class GES_OT_refresh_projects(bpy.types.Operator):
    bl_idname = "ges.refresh_projects"
    bl_label = "Loyihalarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        ok = guard(self, lambda: props.fill(s.projects, flows.project_rows(session.client())))
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_refresh_models(bpy.types.Operator):
    bl_idname = "ges.refresh_models"
    bl_label = "Modellarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        s.models.clear()
        s.versions.clear()
        if p is None:
            return {"FINISHED"}
        ok = guard(self, lambda: props.fill(s.models, flows.model_rows(session.client(), p.item_id)))
        s.models_index = 0 if len(s.models) else -1
        if ok and s.models_index == 0:
            bpy.ops.ges.refresh_versions()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_refresh_versions(bpy.types.Operator):
    bl_idname = "ges.refresh_versions"
    bl_label = "Versiyalarni yangilash"

    def execute(self, context):
        s = context.scene.ges
        m = _sel(s.models, s.models_index)
        s.versions.clear()
        if m is None:
            return {"FINISHED"}
        ok = guard(self, lambda: props.fill(s.versions, flows.version_rows(session.client(), m.item_id)))
        s.versions_index = 0 if len(s.versions) else -1
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_create_model(bpy.types.Operator):
    """Tanlangan loyihada yangi model"""

    bl_idname = "ges.create_model"
    bl_label = "Yangi model"

    def execute(self, context):
        s = context.scene.ges
        p = _sel(s.projects, s.projects_index)
        if p is None or not s.new_model_name.strip():
            self.report({"ERROR"}, "Loyiha va model nomini tanlang")
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().create_model(p.item_id, s.new_model_name.strip()))
        if ok:
            s.new_model_name = ""
            bpy.ops.ges.refresh_models()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_open_version(bpy.types.Operator):
    """Tanlangan versiyani yuklab, Bonsai da ochish"""

    bl_idname = "ges.open_version"
    bl_label = "Ochish"

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and _sel(s.versions, s.versions_index) is not None

    def execute(self, context):
        s = context.scene.ges
        p, m, v = _sel(s.projects, s.projects_index), _sel(s.models, s.models_index), _sel(s.versions, s.versions_index)

        def do():
            path = flows.download_version(session.client(), {"id": m.item_id}, {"id": v.item_id, "number": v.number})
            ifc.load(path)
            s.project_id, s.model_id, s.version_id, s.version_number = p.item_id, m.item_id, v.item_id, v.number
            s.model_name = m.name
            s.status = f"{p.name} — {m.name} v{v.number} ochildi"

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_commit(bpy.types.Operator):
    """Joriy IFC ni serverga yangi versiya sifatida yuklash"""

    bl_idname = "ges.commit"
    bl_label = "Commit (yangi versiya)"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and ifc.file() is not None

    def invoke(self, context, event):
        s = context.scene.ges
        if not s.model_id:
            m = _sel(s.models, s.models_index)
            if m is None:
                self.report({"ERROR"}, "Qaysi modelga yuklash? Model panelida modelni tanlang")
                return {"CANCELLED"}
            s.model_id, s.model_name = m.item_id, m.name
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        s = context.scene.ges
        self.layout.label(text=f"Model: {s.model_name}" + (f" (ota: v{s.version_number})" if s.version_id else ""))
        self.layout.prop(s, "commit_message")
        self.layout.prop(s, "submit_after_commit")

    def execute(self, context):
        s = context.scene.ges

        def do():
            path = ifc.save(flows.cache_dir() / f"commit_m{s.model_id}.ifc")
            r = flows.commit(
                session.client(), s.model_id, path, s.commit_message.strip(), s.version_id or None, s.submit_after_commit
            )
            v = r["version"]
            s.version_id, s.version_number = v["id"], v["number"]
            s.status = f"v{v['number']} yuklandi" + (" va tasdiqqa yuborildi" if r["cr"] else "")
            s.commit_message = ""
            self.report({"INFO"}, s.status)

        if not guard(self, do):
            return {"CANCELLED"}
        bpy.ops.ges.refresh_versions()
        return {"FINISHED"}


class GES_OT_submit(bpy.types.Operator):
    """Joriy versiya uchun tasdiqlash so'rovi"""

    bl_idname = "ges.submit"
    bl_label = "Tasdiqqa yuborish"
    title: bpy.props.StringProperty(name="Sarlavha")

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and bool(s.model_id and s.version_id)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        s = context.scene.ges
        if not self.title.strip():
            self.report({"ERROR"}, "Sarlavha kiriting")
            return {"CANCELLED"}

        def do():
            cr = session.client().create_change_request(s.model_id, s.version_id, self.title.strip())
            self.report({"INFO"}, f"So'rov #{cr['id']} ochildi. Tasdiqlovchi webda ko'rib chiqadi.")

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_open_web(bpy.types.Operator):
    """Joriy model (tanlangan element bilan) brauzerda"""

    bl_idname = "ges.open_web"
    bl_label = "Webda ochish"
    tab: bpy.props.StringProperty(default="")

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def execute(self, context):
        s = context.scene.ges
        q = f"?v={s.version_id}" if s.version_id else "?"
        if self.tab:
            q += f"&tab={self.tab}"
        sel = [g for g in (ifc.guid(o) for o in context.selected_objects) if g]
        if sel:
            q += f"&sel={sel[0]}"
        webbrowser.open(flows.web_url(session.client(), prefs().server, f"/models/{s.model_id}{q}"))
        return {"FINISHED"}


class GES_OT_notifications(bpy.types.Operator):
    bl_idname = "ges.notifications"
    bl_label = "Bildirishnomalar"

    def execute(self, context):
        s = context.scene.ges
        ok = guard(self, lambda: props.fill(s.notifications, flows.notification_rows(session.client())))
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_mark_read(bpy.types.Operator):
    """Hammasini (yoki tanlanganini) o'qilgan qilish"""

    bl_idname = "ges.mark_read"
    bl_label = "O'qilgan"
    all: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        s = context.scene.ges
        n = _sel(s.notifications, s.notifications_index)
        ids = None if self.all or n is None else [n.item_id]
        ok = guard(self, lambda: session.client().mark_notifications_read(ids))
        if ok:
            bpy.ops.ges.notifications()
        return {"FINISHED"} if ok else {"CANCELLED"}


CLASSES = (
    GES_OT_connect, GES_OT_logout, GES_OT_refresh_projects, GES_OT_refresh_models, GES_OT_refresh_versions,
    GES_OT_create_model, GES_OT_open_version, GES_OT_commit, GES_OT_submit, GES_OT_open_web,
    GES_OT_notifications, GES_OT_mark_read,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 7: `ui.py` — UIList va Model paneli**

```python
class GES_UL_simple(bpy.types.UIList):
    """name | state | col2 ... (bo'sh ustunlar ko'rsatilmaydi)."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text=item.name)
        for c in (item.state, item.col2, item.col3, item.col4):
            if c:
                row.label(text=c)


def _list(layout, s, coll, idx, rows=4, refresh_op=None):
    """UIList + yangilash tugmasi. `props` ni ro'yxat o'zgarganda qayta chaqirish uchun `refresh_op`."""
    row = layout.row()
    row.template_list("GES_UL_simple", coll, s, coll, s, idx, rows=rows)
    if refresh_op:
        row.operator(refresh_op, text="", icon="FILE_REFRESH")


class GES_PT_model(GesPanel, bpy.types.Panel):
    bl_label = "Model"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.label(text="Loyihalar")
        _list(lay, s, "projects", "projects_index", 3, "ges.refresh_projects")
        lay.label(text="Modellar")
        _list(lay, s, "models", "models_index", 3, "ges.refresh_models")
        row = lay.row(align=True)
        row.prop(s, "new_model_name", text="")
        row.operator("ges.create_model", text="", icon="ADD")
        lay.label(text="Versiyalar")
        _list(lay, s, "versions", "versions_index", 4, "ges.refresh_versions")
        row = lay.row(align=True)
        row.operator("ges.open_version", icon="IMPORT")
        row.operator("ges.commit", icon="EXPORT")
        row = lay.row(align=True)
        row.operator("ges.submit", icon="CHECKMARK")
        row.operator("ges.open_web", icon="URL")
        if s.model_id:
            lay.label(text=f"Ochiq: {s.model_name} v{s.version_number}", icon="FILE_TICK")


class GES_PT_notifications(GesPanel, bpy.types.Panel):
    bl_label = "Bildirishnomalar"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        _list(lay, s, "notifications", "notifications_index", 5, "ges.notifications")
        n = s.notifications[s.notifications_index] if 0 <= s.notifications_index < len(s.notifications) else None
        if n:
            lay.label(text=n.col4 or n.name)
        row = lay.row(align=True)
        row.operator("ges.mark_read", text="Tanlangan o'qildi").all = False
        row.operator("ges.mark_read", text="Hammasi").all = True
```
`CLASSES = [GES_UL_simple, GES_PT_server, GES_PT_model, GES_PT_notifications]`. Ro'yxatda tanlov o'zgarganda modellar/versiyalar avtomatik yangilanishi uchun `props.py` da `projects_index`/`models_index` ga `update=` callback:
```python
def _on_project(self, context):
    if session_ok():
        bpy.ops.ges.refresh_models()
```
(`props.py` da `session_ok = lambda: __import__("sath.session", fromlist=["x"]).is_logged_in()` o'rniga oddiy `from . import session` — `props` `session` ni import qilishi mumkin, `session` `bpy` ga bog'liq emas.) `projects_index: IntProperty(default=-1, update=_on_project)`, `models_index: ... update=_on_model` (→ `ges.refresh_versions`). `refresh_models` ichida `s.models_index = 0` yozish `_on_model` ni chaqiradi — rekursiya yo'q, chunki u faqat versiyalarni yangilaydi; `refresh_models` dagi yakuniy `bpy.ops.ges.refresh_versions()` ni olib tashlash.

`__init__.py`: `MODULES = [prefs, props, ges_objects, ops_server, ui]`.

- [ ] **Step 8: Headless smoke** `desktop/tests/sath_tests/server_ops.py`

```python
"""Operatorlar ro'yxatga olingan; login siz connect xatoni report qiladi (crash yo'q)."""

import bpy


def run(ctx):
    for op in ("connect", "logout", "refresh_projects", "refresh_models", "refresh_versions", "open_version",
               "commit", "submit", "open_web", "create_model", "notifications", "mark_read"):  # fmt: skip
        assert hasattr(bpy.ops.ges, op), op
    from sath.prefs import prefs

    prefs().server = "http://127.0.0.1:9"  # yopiq port
    assert bpy.ops.ges.connect() == {"CANCELLED"}
    assert bpy.ops.ges.logout() == {"FINISHED"}
```
Run `--test server_ops` → OK.

- [ ] **Step 9: ruff, pytest, commit** — `git commit -m "sath: server oqimlari (flows), operatorlar va Model/Bildirishnomalar panellari"`

---

### Task 6: Viewpoint, issue lar, taqriz (CR), versiyalar farqi

**Files:**
- Create: `desktop/blender/sath/viewpoint.py`, `ops_review.py`
- Modify: `props.py` (`issues`, `crs`, `issue_detail`, `cr_detail`, `comment_text`, `my_role`, `diff_note`), `ui.py` (`GES_PT_review`), `__init__.py`
- Test: `desktop/tests/test_sath_pure.py` (viewpoint matematika), `desktop/tests/sath_tests/review_ops.py` (`--bonsai`, diff bo'yash `flows.diff_colors` bilan)

**Interfaces:**
- Produces: `viewpoint.from_view(view_matrix_inv_translation, view_dir, distance, is_ortho, guids) -> dict` (sof); `viewpoint.capture(context) -> dict`; `viewpoint.apply(context, vp: dict) -> None`;
  `flows.diff_colors(diff: dict) -> tuple[dict[str, tuple], str]` (sof: guid→rgba, xulosa matni); `flows.issue_rows`, `flows.cr_rows`, `flows.issue_text(full) -> str`, `flows.cr_text(full) -> str`, `flows.STATUS_UZ`;
  operatorlar: `ges.refresh_issues`, `ges.show_issue`, `ges.goto_view`, `ges.comment_issue`, `ges.new_issue`, `ges.refresh_crs`, `ges.decide` (`decision` enum: approve/request_changes/comment), `ges.merge_cr`, `ges.reject_cr`, `ges.diff`, `ges.clear_diff`.

- [ ] **Step 1: pytest — viewpoint va diff_colors (sof)**

```python
from sath import flows, viewpoint  # noqa: E402


def test_viewpoint_from_view_ifc_space_metres():
    vp = viewpoint.from_view(position=(10.0, 20.0, 5.0), direction=(0.0, 1.0, 0.0), distance=4.0, is_ortho=False, guids=["a"])
    assert vp["camera"]["space"] == "ifc"
    assert vp["camera"]["position"] == [10.0, 20.0, 5.0]
    assert vp["camera"]["target"] == [10.0, 24.0, 5.0]
    assert vp["camera"]["projection"] == "Perspective" and vp["selected_guids"] == ["a"] and vp["section"] == []


def test_viewpoint_view_params_from_camera():
    loc, rot_dir, dist = viewpoint.view_params({"position": [0, 0, 0], "target": [0, 0, -3]})
    assert loc == (0.0, 0.0, -3.0) and dist == 3.0 and tuple(round(x, 6) for x in rot_dir) == (0.0, 0.0, -1.0)


def test_diff_colors_maps_added_changed_and_summary():
    colors, text = flows.diff_colors(
        {"added": [{"guid": "A"}], "changed": [{"guid": "B"}], "deleted": [{"guid": "C", "name": "Devor"}],
         "summary": {"added": 1, "changed": 1, "deleted": 1}}
    )  # fmt: skip
    assert colors == {"A": flows.DIFF_COLORS["added"], "B": flows.DIFF_COLORS["changed"]}
    assert "+1" in text and "~1" in text and "Devor" in text
```

- [ ] **Step 2: FAIL**, keyin **Step 3: `viewpoint.py`**

```python
"""BCF uslubidagi ko'rinish: kamera + tanlangan IFC GUID lar. Format web bilan bir xil: space="ifc", metr, Z yuqoriga."""

from __future__ import annotations

import math


def from_view(position, direction, distance: float, is_ortho: bool, guids: list[str]) -> dict:
    """Sof: kamera pozitsiyasi (m), yo'nalish (birlik vektor), fokus masofasi → viewpoint dict."""
    p = [float(x) for x in position]
    t = [p[i] + float(direction[i]) * float(distance) for i in range(3)]
    return {
        "camera": {"space": "ifc", "position": p, "target": t, "projection": "Orthographic" if is_ortho else "Perspective"},
        "selected_guids": list(guids),
        "section": [],
    }


def view_params(cam: dict) -> tuple[tuple, tuple, float]:
    """Sof: camera dict → (view_location=target, direction birlik vektor, distance)."""
    p, t = [float(x) for x in cam["position"]], [float(x) for x in cam["target"]]
    d = [t[i] - p[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in d)) or 1.0
    return tuple(t), tuple(x / n for x in d), n


def _region3d(context):
    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            return area.spaces.active.region_3d
    return None


def capture(context) -> dict:
    from . import ifc

    r3d = _region3d(context)
    guids = [g for g in (ifc.guid(o) for o in context.selected_objects) if g]
    if r3d is None:  # headless
        return from_view((0, 0, 0), (0, 1, 0), 10.0, False, guids)
    inv = r3d.view_matrix.inverted()
    pos = inv.translation
    direction = (inv.to_3x3() @ __import__("mathutils").Vector((0.0, 0.0, -1.0))).normalized()
    return from_view(tuple(pos), tuple(direction), float(r3d.view_distance), r3d.view_perspective == "ORTHO", guids)


def apply(context, vp: dict) -> None:
    from mathutils import Vector

    from . import ifc

    cam = (vp or {}).get("camera") or {}
    r3d = _region3d(context)
    if r3d is not None and cam.get("position") and cam.get("space") in ("ifc", "freecad"):
        k = 1.0 if cam.get("space") == "ifc" else 0.001
        c = {"position": [x * k for x in cam["position"]], "target": [x * k for x in cam["target"]]}
        loc, d, dist = view_params(c)
        r3d.view_location = Vector(loc)
        r3d.view_rotation = Vector((0.0, 0.0, -1.0)).rotation_difference(Vector(d))
        r3d.view_distance = dist
        r3d.view_perspective = "ORTHO" if cam.get("projection") == "Orthographic" else "PERSP"
    ifc.select_guids(list(vp.get("selected_guids") or []))
```
`view_rotation` — `Quaternion`; `Vector.rotation_difference` Quaternion qaytaradi.

- [ ] **Step 4: `flows.py` ga qo'shish**

```python
DIFF_COLORS = {"added": (0.25, 0.7, 0.35, 1.0), "changed": (0.9, 0.7, 0.2, 1.0)}
STATUS_UZ = {
    "open": "Ochiq", "changes_requested": "O'zgartirish so'ralgan", "approved": "Ma'qullangan",
    "rejected": "Rad etilgan", "merged": "Tasdiqlangan",
}  # fmt: skip


def diff_colors(d: dict) -> tuple[dict[str, tuple], str]:
    colors = {e["guid"]: DIFF_COLORS[k] for k in ("added", "changed") for e in d.get(k, [])}
    s = d.get("summary", {})
    deleted = ", ".join((e.get("name") or e["guid"]) for e in d.get("deleted", [])[:20])
    text = (
        f"+{s.get('added', 0)} qo'shilgan (yashil), ~{s.get('changed', 0)} o'zgargan (sariq), "
        f"−{s.get('deleted', 0)} o'chirilgan{': ' + deleted if deleted else ''}"
    )
    return colors, text


def issue_rows(client, model_id: int) -> list[dict]:
    return [
        {"item_id": i["id"], "name": f"#{i['id']} {i['title']}", "state": i["status"], "col2": i.get("assignee_username") or "—"}
        for i in client.issues(model_id)
    ]


def issue_text(full: dict) -> str:
    lines = [f"#{full['id']} {full['title']} — {full.get('author_username', '')} · {full.get('priority', '')} · {full['status']}"]
    if full.get("description"):
        lines.append(full["description"])
    for c in full.get("comments", []):
        lines.append(f"  {c.get('author_username', '')}: {c['body']}")
    return "\n".join(lines)


def cr_rows(client, model_id: int) -> list[dict]:
    return [
        {
            "item_id": cr["id"],
            "name": f"#{cr['id']} {cr['title']}",
            "state": STATUS_UZ.get(cr["status"], cr["status"]),
            "col2": f"v{cr['version_number']}" if cr.get("version_number") else str(cr["version_id"]),
            "col3": cr.get("author_username", ""),
            "col4": cr["status"],
        }
        for cr in client.change_requests(model_id)
    ]


def cr_text(full: dict) -> str:
    lines = [f"#{full['id']} {full['title']} — {full.get('author_username', '')} · {STATUS_UZ.get(full['status'], full['status'])}"]
    if full.get("description"):
        lines.append(full["description"])
    for r in full.get("reviews", []):
        lines.append(f"  {r.get('reviewer_username', '')} — {r['decision']}: {r.get('comment', '')}")
    return "\n".join(lines)
```
pytest PASS.

- [ ] **Step 5: `props.py` ga**

```python
    issues: bpy.props.CollectionProperty(type=GesListItem)
    issues_index: bpy.props.IntProperty(default=-1, update=lambda s, c: bpy.ops.ges.show_issue())
    issue_detail: bpy.props.StringProperty(default="")
    crs: bpy.props.CollectionProperty(type=GesListItem)
    crs_index: bpy.props.IntProperty(default=-1, update=lambda s, c: bpy.ops.ges.show_cr())
    cr_detail: bpy.props.StringProperty(default="")
    comment_text: bpy.props.StringProperty(name="Izoh", default="")
    my_role: bpy.props.StringProperty(default="")
    diff_note: bpy.props.StringProperty(default="")
```
(`update` lambda ichida `bpy.ops` chaqirish — operator `poll` bilan himoyalangan.)

- [ ] **Step 6: `ops_review.py`**

```python
"""Issue lar (ko'rinish bilan), tasdiqlash so'rovlari (qarorlar), versiyalar farqi (3D rang)."""

from __future__ import annotations

import bpy

from . import flows, ifc, props, session, viewpoint
from .ops_server import _sel, guard


def _need_model(op, s) -> bool:
    if not s.model_id:
        op.report({"ERROR"}, "Avval serverdagi modelni oching (Model → Ochish)")
        return False
    return True


class GES_OT_refresh_issues(bpy.types.Operator):
    bl_idname = "ges.refresh_issues"
    bl_label = "Issue lar"

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s):
            return {"CANCELLED"}
        ok = guard(self, lambda: props.fill(s.issues, flows.issue_rows(session.client(), s.model_id)))
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_show_issue(bpy.types.Operator):
    bl_idname = "ges.show_issue"
    bl_label = "Issue tafsiloti"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None:
            s.issue_detail = ""
            return {"FINISHED"}

        def do():
            s.issue_detail = flows.issue_text(session.client().issue(i.item_id))

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_goto_view(bpy.types.Operator):
    """Issue ko'rinishiga o'tish (kamera + tanlov)"""

    bl_idname = "ges.goto_view"
    bl_label = "Ko'rinishga o'tish"

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: viewpoint.apply(context, session.client().issue(i.item_id).get("viewpoint") or {}))
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_comment_issue(bpy.types.Operator):
    bl_idname = "ges.comment_issue"
    bl_label = "Izoh qoldirish"

    def execute(self, context):
        s = context.scene.ges
        i = _sel(s.issues, s.issues_index)
        if i is None or not s.comment_text.strip():
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().comment_issue(i.item_id, s.comment_text.strip()))
        if ok:
            s.comment_text = ""
            bpy.ops.ges.show_issue()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_new_issue(bpy.types.Operator):
    """Yangi issue — joriy ko'rinish (kamera, tanlangan elementlar) bilan"""

    bl_idname = "ges.new_issue"
    bl_label = "Yangi issue"
    title: bpy.props.StringProperty(name="Sarlavha")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s) or not self.title.strip():
            return {"CANCELLED"}
        ok = guard(
            self,
            lambda: session.client().create_issue(
                s.model_id, self.title.strip(), version_id=s.version_id or None, viewpoint=viewpoint.capture(context)
            ),
        )
        if ok:
            bpy.ops.ges.refresh_issues()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_refresh_crs(bpy.types.Operator):
    bl_idname = "ges.refresh_crs"
    bl_label = "Tasdiqlash so'rovlari"

    def execute(self, context):
        s = context.scene.ges
        if not _need_model(self, s):
            return {"CANCELLED"}

        def do():
            props.fill(s.crs, flows.cr_rows(session.client(), s.model_id))
            s.my_role = flows.model_role(session.client(), s.model_id) or ""

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_show_cr(bpy.types.Operator):
    bl_idname = "ges.show_cr"
    bl_label = "CR tafsiloti"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in()

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            s.cr_detail = ""
            return {"FINISHED"}
        ok = guard(self, lambda: setattr(s, "cr_detail", flows.cr_text(session.client().change_request(cr.item_id))))
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_decide(bpy.types.Operator):
    """Qaror: ma'qullash / o'zgartirish so'rash / faqat izoh"""

    bl_idname = "ges.decide"
    bl_label = "Qaror"
    decision: bpy.props.EnumProperty(
        items=[("approve", "Ma'qullash", ""), ("request_changes", "O'zgartirish so'rash", ""), ("comment", "Faqat izoh", "")]
    )

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().review_change_request(cr.item_id, self.decision, s.comment_text.strip()))
        if ok:
            s.comment_text = ""
            bpy.ops.ges.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_merge_cr(bpy.types.Operator):
    bl_idname = "ges.merge_cr"
    bl_label = "Tasdiqlash (merge)"

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().merge_change_request(cr.item_id))
        if ok:
            bpy.ops.ges.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_reject_cr(bpy.types.Operator):
    bl_idname = "ges.reject_cr"
    bl_label = "Rad etish"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.ges
        cr = _sel(s.crs, s.crs_index)
        if cr is None:
            return {"CANCELLED"}
        ok = guard(self, lambda: session.client().reject_change_request(cr.item_id))
        if ok:
            bpy.ops.ges.refresh_crs()
        return {"FINISHED"} if ok else {"CANCELLED"}


class GES_OT_diff(bpy.types.Operator):
    """Tanlangan versiyaning ota bilan farqi — 3D da rang (yashil qo'shilgan, sariq o'zgargan)"""

    bl_idname = "ges.diff"
    bl_label = "Ota bilan farq (3D rang)"

    @classmethod
    def poll(cls, context):
        s = context.scene.ges
        return session.is_logged_in() and _sel(s.versions, s.versions_index) is not None

    def execute(self, context):
        s = context.scene.ges
        v = _sel(s.versions, s.versions_index)

        def do():
            d = session.client().diff(v.item_id)
            ifc.DIFF_STATE.restore()
            colors, text = flows.diff_colors(d)
            n = ifc.DIFF_STATE.paint(colors)
            note = "" if s.version_id == v.item_id else "(diqqat: boshqa versiya ochiq) "
            s.diff_note = f"{note}v{v.number}: {text}. 3D da {n} obyekt bo'yaldi."

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_clear_diff(bpy.types.Operator):
    bl_idname = "ges.clear_diff"
    bl_label = "Rangni tozalash"

    def execute(self, context):
        ifc.DIFF_STATE.restore()
        context.scene.ges.diff_note = ""
        return {"FINISHED"}


CLASSES = (
    GES_OT_refresh_issues, GES_OT_show_issue, GES_OT_goto_view, GES_OT_comment_issue, GES_OT_new_issue,
    GES_OT_refresh_crs, GES_OT_show_cr, GES_OT_decide, GES_OT_merge_cr, GES_OT_reject_cr,
    GES_OT_diff, GES_OT_clear_diff,
)  # fmt: skip


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 7: `ui.py` — `GES_PT_review`** (Model panelidan keyin)

```python
class GES_PT_review(GesPanel, bpy.types.Panel):
    bl_label = "Taqriz va issue lar"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        box = lay.box()
        box.label(text="Versiyalar farqi", icon="MOD_DIFFERENCE")
        row = box.row(align=True)
        row.operator("ges.diff")
        row.operator("ges.clear_diff", text="", icon="X")
        if s.diff_note:
            box.label(text=s.diff_note)
        box = lay.box()
        box.label(text="Issue lar", icon="ERROR")
        _list(box, s, "issues", "issues_index", 4, "ges.refresh_issues")
        for line in s.issue_detail.splitlines()[:8]:
            box.label(text=line)
        row = box.row(align=True)
        row.operator("ges.goto_view", icon="CAMERA_DATA")
        row.operator("ges.new_issue", icon="ADD")
        row = box.row(align=True)
        row.prop(s, "comment_text", text="")
        row.operator("ges.comment_issue", text="", icon="PLAY")
        box = lay.box()
        box.label(text=f"Tasdiqlash so'rovlari{' · ' + s.my_role if s.my_role else ''}", icon="CHECKMARK")
        _list(box, s, "crs", "crs_index", 4, "ges.refresh_crs")
        for line in s.cr_detail.splitlines()[:8]:
            box.label(text=line)
        cr = s.crs[s.crs_index] if 0 <= s.crs_index < len(s.crs) else None
        approver = s.my_role == "approver"
        st = cr.col4 if cr else ""
        open_ = st in ("open", "changes_requested", "approved")
        row = box.row(align=True)
        row.enabled = approver and open_ and st != "approved"
        row.operator("ges.decide", text="Ma'qullash").decision = "approve"
        row2 = row.row(align=True)
        row2.enabled = approver and open_
        row2.operator("ges.decide", text="O'zgartirish so'rash").decision = "request_changes"
        row = box.row(align=True)
        r1 = row.row()
        r1.enabled = approver and st == "approved"
        r1.operator("ges.merge_cr")
        r2 = row.row()
        r2.enabled = bool(cr) and st not in ("merged", "rejected")
        r2.operator("ges.reject_cr")
        box.operator("ges.decide", text="Faqat izoh qoldirish").decision = "comment"
```

- [ ] **Step 8: Headless** `desktop/tests/sath_tests/review_ops.py`

```python
"""Viewpoint capture/apply headless da ishlaydi; diff bo'yash guid bo'yicha rang beradi."""

from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def run(ctx):
    from sath import flows, ifc, viewpoint

    ifc.load(SAMPLE)
    g = next(iter(ifc.guid_map()))
    vp = viewpoint.capture(bpy.context)
    assert vp["camera"]["space"] == "ifc"
    viewpoint.apply(bpy.context, {"camera": {"space": "ifc", "position": [1, 2, 3], "target": [1, 2, 0]}, "selected_guids": [g]})
    assert ifc.object_for_guid(g).select_set
    colors, _ = flows.diff_colors({"added": [{"guid": g}], "summary": {"added": 1}})
    assert ifc.DIFF_STATE.paint(colors) == 1
    ifc.DIFF_STATE.restore()
    for op in ("refresh_issues", "goto_view", "new_issue", "refresh_crs", "decide", "merge_cr", "reject_cr", "diff", "clear_diff"):
        assert hasattr(bpy.ops.ges, op), op
```
Run `--test review_ops --bonsai` → OK.

- [ ] **Step 9: ruff, pytest, commit** — `git commit -m "sath: viewpoint, issue lar, taqriz, versiyalar farqi"`

---

### Task 7: Simulyatsiya katalogi, xavfsizlik tekshiruvi, suv sathi

**Files:**
- Create: `desktop/blender/sath/water.py`, `ops_sim.py`
- Modify: `props.py` (`sim_kinds`, `sim_kind_index`, `sim_fields` (GesSimField), `sim_status`, `sim_results`, `sim_water_level`, `safety_rows`, `safety_head`), `ui.py` (`GES_PT_sim`), `__init__.py`, `flows.py` (`sim_values`, `sim_result_rows`, `safety_rows`)
- Test: pytest (sof `flows.sim_values`, `flows.sim_result_rows`), headless `sim_ops.py` (water plane)

**Interfaces:**
- Produces: `water.place_water_plane(context, level_m: float) -> Object` (nomi `GES_SuvSathi`, sahna bbox ×1.2, ko'k yarim shaffof material);
  `flows.sim_values(fields: list[dict], raw: dict[str, str|bool]) -> dict` (matnlarni turga qarab float/list/bool qiladi);
  `flows.sim_result_rows(kind: dict, result: dict) -> tuple[list[dict], float|None]` (ko'rsatkichlar + suv sathi);
  `flows.safety_rows(res: dict) -> tuple[str, list[dict]]`;
  `GesSimField` (`key, label, ftype, hint, value_str, value_bool, options`), operatorlar `ges.sim_catalog`, `ges.sim_pick`, `ges.sim_prefill` (`src`: site|model), `ges.sim_run` (timer poll), `ges.sim_water`, `ges.safety_check`.

- [ ] **Step 1: pytest (sof)**

```python
def test_sim_values_casts_by_field_type():
    fields = [
        {"key": "q", "type": "number"}, {"key": "n", "type": "int"}, {"key": "b", "type": "bool"},
        {"key": "s", "type": "series"}, {"key": "sel", "type": "select"}, {"key": "t", "type": "text"},
    ]  # fmt: skip
    raw = {"q": "12,5", "n": "3", "b": True, "s": "1, 2;3", "sel": "x", "t": " ab "}
    assert flows.sim_values(fields, raw) == {"q": 12.5, "n": 3.0, "b": True, "s": [1.0, 2.0, 3.0], "sel": "x", "t": "ab"}


def test_sim_result_rows_and_water_level():
    kind = {"outputs": [{"key": "max_level", "label": "Maks sath", "unit": "m"}], "viz": {"water_level": "level"}}
    rows, lvl = flows.sim_result_rows(kind, {"summary": {"verdict": "OK", "ok": True, "max_level": 101.234}, "series": {"level": [99.0, 101.2]}})
    assert rows[0] == {"name": "Xulosa", "col2": "OK", "state": "ok"}
    assert rows[1] == {"name": "Maks sath", "col2": "101.23 m", "state": ""}
    assert lvl == 101.2


def test_safety_rows():
    head, rows = flows.safety_rows({"score": 80, "verdict": "yaxshi", "counts": {"ok": 10, "warn": 1, "fail": 1, "skip": 0},
                                    "rows": [{"title": "Toshqin", "status": "warn", "message": "chegara", "metrics": {"k": 1.234}}]})  # fmt: skip
    assert head.startswith("80 / 100") and rows[0]["state"] == "ogohlantirish" and "k = 1.23" in rows[0]["col3"]
```

- [ ] **Step 2: FAIL**, **Step 3: `flows.py` ga**

```python
SAFETY_UZ = {"ok": "bajarildi", "warn": "ogohlantirish", "fail": "bajarilmadi", "skip": "hisoblanmadi"}


def sim_values(fields: list[dict], raw: dict) -> dict:
    out = {}
    for f in fields:
        v = raw.get(f["key"])
        t = f["type"]
        if t == "bool":
            out[f["key"]] = bool(v)
        elif t == "select":
            out[f["key"]] = v
        else:
            txt = str(v or "").strip()
            if t == "series":
                out[f["key"]] = [float(x) for x in txt.replace(";", ",").split(",") if x.strip()]
            elif t in ("number", "int"):
                if txt:
                    out[f["key"]] = float(txt.replace(",", "."))
            else:
                out[f["key"]] = txt
    return out


def sim_result_rows(kind: dict, r: dict) -> tuple[list[dict], float | None]:
    s = r.get("summary", {})
    rows = [{"name": "Xulosa", "col2": str(s.get("verdict", "")), "state": "fail" if s.get("ok") is False else "ok"}]
    for o in kind.get("outputs", []):
        v = s.get(o["key"])
        if v is None:
            continue
        txt = f"{v:,.2f}" if isinstance(v, float) else str(v)
        rows.append({"name": o["label"], "col2": f"{txt} {o.get('unit', '')}".strip(), "state": ""})
    level = None
    key = (kind.get("viz") or {}).get("water_level")
    if key:
        ser = r.get("series", {}).get(key)
        if isinstance(ser, list) and ser:
            level = float(max(ser))
        elif isinstance(s.get(key), int | float):
            level = float(s[key])
    return rows, level


def safety_rows(res: dict) -> tuple[str, list[dict]]:
    c = res["counts"]
    head = f"{res['score']} / 100 — {res['verdict']} · {c['ok']} ok · {c['warn']} ogohlantirish · {c['fail']} bajarilmadi · {c['skip']} hisoblanmadi"
    rows = [
        {
            "name": r["title"],
            "state": SAFETY_UZ.get(r["status"], r["status"]),
            "col2": r.get("message", ""),
            "col3": " · ".join(f"{k} = {v:.2f}" if isinstance(v, float) else f"{k} = {v}" for k, v in (r.get("metrics") or {}).items()),
        }
        for r in res["rows"]
    ]
    return head, rows
```
pytest PASS.

- [ ] **Step 4: `water.py`**

```python
"""GES_SuvSathi — yarim shaffof ko'k tekislik, model bbox ini qoplaydi, z = sath (m)."""

from __future__ import annotations

import bpy

NAME = "GES_SuvSathi"


def _material():
    m = bpy.data.materials.get(NAME)
    if m is None:
        m = bpy.data.materials.new(NAME)
        m.diffuse_color = (0.22, 0.72, 0.79, 0.4)
        m.blend_method = "BLEND" if hasattr(m, "blend_method") else m.blend_method
    return m


def place_water_plane(context, level_m: float):
    objs = [o for o in context.scene.objects if o.type == "MESH" and o.name != NAME]
    if not objs:
        return None
    xs, ys = [], []
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ __import__("mathutils").Vector(c)
            xs.append(w.x)
            ys.append(w.y)
    size = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.2 or 10.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    ob = bpy.data.objects.get(NAME)
    if ob is None:
        me = bpy.data.meshes.new(NAME)
        me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(NAME, me)
        context.scene.collection.objects.link(ob)
        ob.data.materials.append(_material())
        ob.color = (0.22, 0.72, 0.79, 0.4)
        ob.show_transparent = True
    ob.location = (cx, cy, level_m)
    ob.scale = (size, size, 1.0)
    return ob
```

- [ ] **Step 5: `props.py` ga**

```python
class GesSimField(bpy.types.PropertyGroup):
    key: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    ftype: bpy.props.StringProperty()
    hint: bpy.props.StringProperty()
    options: bpy.props.StringProperty()  # "val=label;val=label"
    value_str: bpy.props.StringProperty()
    value_bool: bpy.props.BoolProperty()
    value_sel: bpy.props.EnumProperty(items=lambda self, c: [(v.split("=", 1)[0], v.split("=", 1)[-1], "") for v in self.options.split(";") if v])
```
`GesScene` ga: `sim_kinds` (GesListItem: `item_id`=indeks, `name`=title, `col2`=group, `col4`=description, `guid`=kind id), `sim_kind_index` (update → `bpy.ops.ges.sim_pick()`), `sim_fields: Collection[GesSimField]`, `sim_status`, `sim_results: Collection[GesListItem]`, `sim_water_level: FloatProperty(default=-1e9)`, `safety_head`, `safety_rows: Collection[GesListItem]`, `sim_job_id: IntProperty`. `CLASSES = (GesListItem, GesSimField, GesScene)`.

- [ ] **Step 6: `ops_sim.py`**

```python
"""Simulyatsiya katalogi (server), forma pasport/modeldan, hisob (timer poll), natija, 3D suv sathi, xavfsizlik tekshiruvi."""

from __future__ import annotations

import bpy

from . import flows, props, session, water
from .ops_server import _sel, guard
from .shared.server_client import ServerError

_catalog: dict = {}


def _kind(s) -> dict | None:
    k = _sel(s.sim_kinds, s.sim_kind_index)
    return next((x for x in _catalog.get("kinds", []) if x["id"] == k.guid), None) if k else None


class GES_OT_sim_catalog(bpy.types.Operator):
    """Barcha simulyatsiya turlari (server katalogi)"""

    bl_idname = "ges.sim_catalog"
    bl_label = "Katalogni yuklash"

    def execute(self, context):
        s = context.scene.ges

        def do():
            global _catalog
            _catalog = session.client().sim_catalog()
            groups = _catalog.get("groups", {})
            rows = [
                {"item_id": i, "name": k["title"], "col2": groups.get(k["group"], k["group"]), "col4": k.get("description", ""), "guid": k["id"]}
                for i, k in enumerate(_catalog["kinds"])
                if not k.get("custom_ui")
            ]
            props.fill(s.sim_kinds, rows)
            s.sim_kind_index = 0 if rows else -1

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


class GES_OT_sim_pick(bpy.types.Operator):
    bl_idname = "ges.sim_pick"
    bl_label = "Turni tanlash"

    @classmethod
    def poll(cls, context):
        return bool(_catalog)

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        s.sim_fields.clear()
        s.sim_results.clear()
        s.sim_water_level = -1e9
        if not k:
            return {"FINISHED"}
        for f in k["fields"]:
            it = s.sim_fields.add()
            it.key, it.label, it.ftype, it.hint = f["key"], f["label"] + (f", {f['unit']}" if f.get("unit") else ""), f["type"], f.get("hint", "")
            d = f.get("default")
            if f["type"] == "bool":
                it.value_bool = bool(d)
            elif f["type"] == "select":
                it.options = ";".join(f"{v}={lb}" for v, lb in f.get("options", []))
                if d is not None and any(str(v) == str(d) for v, _ in f.get("options", [])):
                    it.value_sel = str(d)
            elif f["type"] == "series":
                it.value_str = ", ".join(str(x) for x in d) if isinstance(d, list) else str(d or "")
            else:
                it.value_str = "" if d is None else str(d)
        bpy.ops.ges.sim_prefill(src="site", quiet=True)
        return {"FINISHED"}


class GES_OT_sim_prefill(bpy.types.Operator):
    """Maydonlarni pasportdan yoki modeldan (Pset_GES_*) to'ldirish"""

    bl_idname = "ges.sim_prefill"
    bl_label = "To'ldirish"
    src: bpy.props.EnumProperty(items=[("site", "Pasportdan", ""), ("model", "Modeldan", "")])
    quiet: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        if not k or not s.model_id:
            return {"CANCELLED"}
        try:
            pf = session.client().sim_prefill(s.model_id, k["id"], s.version_id or None)
        except ServerError as e:
            if not self.quiet:
                self.report({"ERROR"}, e.message)
            return {"CANCELLED"}
        vals = pf.get(self.src) or {}
        n = 0
        for it in s.sim_fields:
            if it.key not in vals:
                continue
            v = vals[it.key]
            if it.ftype == "bool":
                it.value_bool = bool(v)
            elif it.ftype == "select":
                if any(o.split("=", 1)[0] == str(v) for o in it.options.split(";")):
                    it.value_sel = str(v)
            else:
                it.value_str = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
            n += 1
        if not self.quiet:
            s.sim_status = f"{n} maydon {'pasportdan' if self.src == 'site' else 'modeldan'}"
            if not vals and self.src == "site":
                self.report({"WARNING"}, "Maydon pasporti to'ldirilmagan — webda loyiha sahifasida kiriting")
        return {"FINISHED"}


def _raw(s) -> dict:
    return {
        it.key: (it.value_bool if it.ftype == "bool" else it.value_sel if it.ftype == "select" else it.value_str)
        for it in s.sim_fields
    }


class GES_OT_sim_run(bpy.types.Operator):
    """Hisob serverda; natija 0.6 s da tekshiriladi"""

    bl_idname = "ges.sim_run"
    bl_label = "Hisoblash"

    def execute(self, context):
        s = context.scene.ges
        k = _kind(s)
        if not k or not s.model_id:
            self.report({"ERROR"}, "Model va simulyatsiya turini tanlang")
            return {"CANCELLED"}
        try:
            job = session.client().create_sim(s.model_id, k["title"], s.version_id or None, flows.sim_values(k["fields"], _raw(s)), kind=k["id"])
        except (ServerError, ValueError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.sim_job_id = job["id"]
        s.sim_status = "Hisoblanmoqda…"
        bpy.app.timers.register(_poll_factory(k, job["id"]), first_interval=0.6)
        return {"FINISHED"}


def _poll_factory(kind: dict, job_id: int):
    def poll():
        s = bpy.context.scene.ges
        try:
            j = session.client().sim_job(job_id)
        except (ServerError, RuntimeError) as e:
            s.sim_status = f"Xato: {e}"
            return None
        if j["status"] == "done":
            rows, level = flows.sim_result_rows(kind, session.client().sim_result(job_id))
            props.fill(s.sim_results, rows)
            s.sim_water_level = level if level is not None else -1e9
            s.sim_status = "Tayyor"
            return None
        if j["status"] == "failed":
            s.sim_status = f"Xato: {j.get('error') or 'hisob xatosi'}"
            return None
        return 0.6

    return poll


class GES_OT_sim_water(bpy.types.Operator):
    """Natijadagi suv sathini 3D tekislik sifatida ko'rsatish"""

    bl_idname = "ges.sim_water"
    bl_label = "3D: suv sathi"

    @classmethod
    def poll(cls, context):
        return context.scene.ges.sim_water_level > -1e8

    def execute(self, context):
        lvl = context.scene.ges.sim_water_level
        water.place_water_plane(context, lvl)
        self.report({"INFO"}, f"Suv sathi tekisligi: {lvl:.2f} m (GES_SuvSathi)")
        return {"FINISHED"}


class GES_OT_safety_check(bpy.types.Operator):
    """12 ssenariy: toshqin, N−1 darvoza, zilzila, barqarorlik, filtratsiya, gidrozarba… (serverda, ~1 daqiqa)"""

    bl_idname = "ges.safety_check"
    bl_label = "Xavfsizlik tekshiruvi"

    def execute(self, context):
        s = context.scene.ges
        if not s.model_id:
            self.report({"ERROR"}, "Avval modelni oching")
            return {"CANCELLED"}

        def do():
            head, rows = flows.safety_rows(session.client().safety_check(s.model_id, s.version_id or None))
            s.safety_head = head
            props.fill(s.safety_rows, rows)

        return {"FINISHED"} if guard(self, do) else {"CANCELLED"}


CLASSES = (GES_OT_sim_catalog, GES_OT_sim_pick, GES_OT_sim_prefill, GES_OT_sim_run, GES_OT_sim_water, GES_OT_safety_check)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 7: `ui.py` — `GES_PT_sim`**

```python
class GES_PT_sim(GesPanel, bpy.types.Panel):
    bl_label = "Simulyatsiya"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        row = lay.row(align=True)
        row.operator("ges.sim_catalog", icon="FILE_REFRESH")
        row.operator("ges.safety_check", icon="CHECKMARK")
        _list(lay, s, "sim_kinds", "sim_kind_index", 4)
        k = s.sim_kinds[s.sim_kind_index] if 0 <= s.sim_kind_index < len(s.sim_kinds) else None
        if k and k.col4:
            lay.label(text=k.col4[:90])
        for f in s.sim_fields:
            if f.ftype == "bool":
                lay.prop(f, "value_bool", text=f.label)
            elif f.ftype == "select":
                lay.prop(f, "value_sel", text=f.label)
            else:
                lay.prop(f, "value_str", text=f.label)
        row = lay.row(align=True)
        row.operator("ges.sim_prefill", text="Pasportdan").src = "site"
        row.operator("ges.sim_prefill", text="Modeldan").src = "model"
        row.operator("ges.sim_run", icon="PLAY")
        if s.sim_status:
            lay.label(text=s.sim_status, icon="INFO")
        for r in s.sim_results:
            lay.label(text=f"{r.name}: {r.col2}", icon="CHECKMARK" if r.state == "ok" else "ERROR" if r.state == "fail" else "DOT")
        row = lay.row(align=True)
        row.operator("ges.sim_water", icon="MOD_FLUIDSIM")
        row.operator("ges.open_web", text="Webda (grafik, hisobot)", icon="URL").tab = "sim"
        if s.safety_head:
            box = lay.box()
            box.label(text=s.safety_head, icon="SHIELD")
            for r in s.safety_rows:
                box.label(text=f"{r.name} — {r.state}: {r.col2}"[:100])
```
`__init__.py` MODULES ga `ops_sim`.

- [ ] **Step 8: Headless** `desktop/tests/sath_tests/sim_ops.py`

```python
"""Suv sathi tekisligi sahna bbox ini qoplaydi va qayta chaqirilganda yangilanadi."""

import bpy


def run(ctx):
    from sath import water

    bpy.ops.mesh.primitive_cube_add(size=10, location=(5, 5, 0))
    ob = water.place_water_plane(bpy.context, 3.5)
    assert ob.name == "GES_SuvSathi" and abs(ob.location.z - 3.5) < 1e-6 and ob.scale.x >= 12.0
    ob2 = water.place_water_plane(bpy.context, 7.0)
    assert ob2 is ob and abs(ob.location.z - 7.0) < 1e-6
    assert sum(1 for o in bpy.data.objects if o.name.startswith("GES_SuvSathi")) == 1
    for op in ("sim_catalog", "sim_pick", "sim_prefill", "sim_run", "sim_water", "safety_check"):
        assert hasattr(bpy.ops.ges, op), op
```
Run `--test sim_ops` → OK.

- [ ] **Step 9: ruff, pytest, commit** — `git commit -m "sath: simulyatsiya katalogi, xavfsizlik tekshiruvi, suv sathi"`

---

### Task 8: Monitoring (SCADA)

**Files:**
- Create: `desktop/blender/sath/ops_monitor.py`
- Modify: `props.py` (`sensors`, `sensors_index`, `monitor_on`, `monitor_status`, `monitor_color`, `monitor_water`), `ui.py` (`GES_PT_monitor`), `__init__.py`, `flows.py` (`sensor_rows`, `alarm_colors`, `water_sensor_level`)
- Test: pytest (sof), headless `monitor_ops.py`

**Interfaces:**
- Produces: `flows.sensor_rows(sensors) -> list[dict]`; `flows.alarm_colors(sensors) -> dict[guid, rgba]`; `flows.water_sensor_level(sensors) -> float|None`;
  `ges.monitor_toggle` (timer 5 s: `client.sensors(project_id, model_id)` → ro'yxat, alarm rang, suv sathi), `ges.show_sensor` (element tanlash).

- [ ] **Step 1: pytest (sof)**

```python
def test_sensor_rows_alarm_colors_and_water():
    sensors = [
        {"id": 1, "name": "Sath", "key": "lvl", "kind": "level", "unit": "m", "last_value": 101.5, "alarm": "ok", "enabled": True, "element_guid": "G1", "last_ts": "2026-09-17T10:00:00"},
        {"id": 2, "name": "Bosim", "key": "p", "kind": "pressure", "unit": "bar", "last_value": None, "alarm": "stale", "enabled": True, "element_guid": "G2"},
        {"id": 3, "name": "O'chiq", "key": "x", "kind": "level", "last_value": 5.0, "alarm": "high", "enabled": False, "element_guid": "G3"},
    ]  # fmt: skip
    rows = flows.sensor_rows(sensors)
    assert rows[0]["col2"] == "101.50 m" and rows[0]["state"] == "normal" and rows[0]["guid"] == "G1"
    assert rows[1]["col2"] == "—" and rows[1]["state"] == "uzilgan"
    assert flows.alarm_colors(sensors) == {"G1": flows.ALARM_COLORS["ok"], "G2": flows.ALARM_COLORS["stale"]}
    assert flows.water_sensor_level(sensors) == 101.5
```

- [ ] **Step 2: FAIL**, **Step 3: `flows.py` ga**

```python
ALARM_COLORS = {
    "ok": (0.23, 0.66, 0.39, 1.0), "low": (0.88, 0.4, 0.42, 1.0),
    "high": (0.88, 0.4, 0.42, 1.0), "stale": (0.42, 0.43, 0.46, 1.0),
}  # fmt: skip
ALARM_UZ = {"ok": "normal", "low": "past", "high": "yuqori", "stale": "uzilgan"}


def sensor_rows(sensors: list[dict]) -> list[dict]:
    rows = []
    for s in sensors:
        v = s.get("last_value")
        rows.append(
            {
                "item_id": s["id"],
                "name": s["name"],
                "col2": f"{v:.2f} {s.get('unit', '')}".strip() if isinstance(v, int | float) else "—",
                "state": ALARM_UZ.get(s.get("alarm"), str(s.get("alarm"))),
                "col3": _dt(s.get("last_ts")),
                "col4": "bog'langan" if s.get("element_guid") else "",
                "guid": s.get("element_guid") or "",
            }
        )
    return rows


def alarm_colors(sensors: list[dict]) -> dict[str, tuple]:
    return {
        s["element_guid"]: ALARM_COLORS.get(s.get("alarm"), (1.0, 1.0, 1.0, 1.0))
        for s in sensors
        if s.get("element_guid") and s.get("enabled")
    }


def water_sensor_level(sensors: list[dict]) -> float | None:
    for s in sensors:
        if s.get("kind") == "level" and s.get("enabled") and isinstance(s.get("last_value"), int | float) and s.get("alarm") != "stale":
            return float(s["last_value"])
    return None
```

- [ ] **Step 4: `props.py` ga** — `sensors: Collection[GesListItem]`, `sensors_index: IntProperty(default=-1)`, `monitor_on: BoolProperty(default=False)`, `monitor_status: StringProperty`, `monitor_color: BoolProperty(name="3D alarm rangi", default=True)`, `monitor_water: BoolProperty(name="suv sathi sensoridan 3D tekislik", default=True)`.

- [ ] **Step 5: `ops_monitor.py`**

```python
"""SCADA monitoring: 5 s da sensorlar (REST), obyektlar alarm rangi, suv sathi tekisligi, sensor → 3D."""

from __future__ import annotations

import bpy

from . import flows, ifc, props, session, water
from .ops_server import _sel
from .shared.server_client import ServerError

INTERVAL = 5.0
_sensors: list[dict] = []


def _tick():
    global _sensors
    s = bpy.context.scene.ges
    if not s.monitor_on or not session.is_logged_in():
        ifc.ALARM_STATE.restore()
        return None
    try:
        _sensors = session.client().sensors(s.project_id, s.model_id)
    except (ServerError, RuntimeError) as e:
        s.monitor_status = f"Xato: {e}"
        return INTERVAL
    alarms = [x for x in _sensors if x.get("enabled") and x.get("alarm") != "ok"]
    s.monitor_status = f"{len(_sensors)} sensor · {len(alarms)} alarm · yangilanish {INTERVAL:.0f} s"
    sel = s.sensors_index
    props.fill(s.sensors, flows.sensor_rows(_sensors))
    s.sensors_index = min(sel, len(s.sensors) - 1)
    if s.monitor_color:
        ifc.ALARM_STATE.paint(flows.alarm_colors(_sensors))
    else:
        ifc.ALARM_STATE.restore()
    if s.monitor_water:
        lvl = flows.water_sensor_level(_sensors)
        if lvl is not None:
            water.place_water_plane(bpy.context, lvl)
    return INTERVAL


class GES_OT_monitor_toggle(bpy.types.Operator):
    """Monitoringni yoqish/o'chirish (jonli qiymatlar)"""

    bl_idname = "ges.monitor_toggle"
    bl_label = "Monitoring"

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def execute(self, context):
        s = context.scene.ges
        s.monitor_on = not s.monitor_on
        if s.monitor_on:
            if not s.project_id:
                s.project_id = session.client().model(s.model_id)["project_id"]
            if not bpy.app.timers.is_registered(_tick):
                bpy.app.timers.register(_tick, first_interval=0.0)
        else:
            ifc.ALARM_STATE.restore()
            s.monitor_status = ""
        return {"FINISHED"}


class GES_OT_show_sensor(bpy.types.Operator):
    """Tanlangan sensor elementini 3D da tanlash"""

    bl_idname = "ges.show_sensor"
    bl_label = "3D da ko'rsatish"

    def execute(self, context):
        s = context.scene.ges
        it = _sel(s.sensors, s.sensors_index)
        if it is None:
            return {"CANCELLED"}
        if not it.guid:
            self.report({"INFO"}, "Bu sensor elementga bog'lanmagan (webda «Tanlanganga bog'lash»)")
            return {"CANCELLED"}
        if ifc.select_guids([it.guid]) == 0:
            self.report({"INFO"}, "Element sahnada topilmadi")
            return {"CANCELLED"}
        bpy.ops.view3d.view_selected() if context.area and context.area.type == "VIEW_3D" else None
        return {"FINISHED"}


CLASSES = (GES_OT_monitor_toggle, GES_OT_show_sensor)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```

- [ ] **Step 6: `ui.py` — `GES_PT_monitor`**

```python
class GES_PT_monitor(GesPanel, bpy.types.Panel):
    bl_label = "Monitoring (SCADA)"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session.is_logged_in() and context.scene.ges.model_id > 0

    def draw(self, context):
        s = context.scene.ges
        lay = self.layout
        lay.operator("ges.monitor_toggle", text="To'xtatish" if s.monitor_on else "Boshlash", icon="PAUSE" if s.monitor_on else "PLAY", depress=s.monitor_on)
        row = lay.row(align=True)
        row.prop(s, "monitor_color")
        row.prop(s, "monitor_water")
        if s.monitor_status:
            lay.label(text=s.monitor_status, icon="INFO")
        _list(lay, s, "sensors", "sensors_index", 6)
        row = lay.row(align=True)
        row.operator("ges.show_sensor", icon="RESTRICT_SELECT_OFF")
        row.operator("ges.open_web", text="Webda (HMI)", icon="URL").tab = "mon"
```
`__init__.py` MODULES ga `ops_monitor`.

- [ ] **Step 7: Headless** `desktop/tests/sath_tests/monitor_ops.py`

```python
"""Alarm ranglari va suv sathi flows dan sahnaga tushadi (server siz: _tick ni to'g'ridan emas, qismlarini)."""

from pathlib import Path

import bpy

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "namuna_ges_v1.ifc"


def run(ctx):
    from sath import flows, ifc, water

    ifc.load(SAMPLE)
    g = next(iter(ifc.guid_map()))
    sensors = [{"id": 1, "name": "S", "key": "k", "kind": "level", "last_value": 4.0, "alarm": "high", "enabled": True, "element_guid": g}]
    assert ifc.ALARM_STATE.paint(flows.alarm_colors(sensors)) == 1
    assert tuple(ifc.object_for_guid(g).color)[:3] == flows.ALARM_COLORS["high"][:3]
    ifc.ALARM_STATE.restore()
    assert water.place_water_plane(bpy.context, flows.water_sensor_level(sensors)).location.z == 4.0
    assert hasattr(bpy.ops.ges, "monitor_toggle") and hasattr(bpy.ops.ges, "show_sensor")
```
Run `--test monitor_ops --bonsai` → OK.

- [ ] **Step 8: ruff, pytest, commit** — `git commit -m "sath: monitoring (SCADA) — timer, alarm rang, suv sathi"`

---

### Task 9: DXF/DWG va mesh import (FreeCAD dvigatel, assimp)

**Files:**
- Create: `desktop/blender/sath/ops_import.py`, `desktop/blender/sath/converters.py` (workbench `converters.py` dan FreeCAD siz variant), `desktop/blender/sath/wheels/` (ezdxf, assimp-py — `pip download`)
- Modify: `blender_manifest.toml` (`wheels = [...]`), `ui.py` (`GES_PT_import`), `__init__.py`, `desktop/build/sync_blender.py` (agar `converters.py` ni ham nusxalash oson bo'lsa — yo'q: u `FreeCAD.getHomePath()` ishlatadi, addon uchun alohida yoziladi)
- Test: headless `import_ops.py` (Namuna.dwg, Namuna.fbx)

**Interfaces:**
- Produces: `converters.find_dwg2dxf() -> str|None` (PATH, `%GES_TOOLS_DIR%`, `~/Tools`, `C:/Tools`, `fc_home/tools`, `C:/Program Files/ODA`);
  `ops_import.import_dxf(context, path: Path, prepare: bool = True) -> int` (obyekt soni; qatlam → collection, 2D → curve, 3D → mesh);
  `ops_import.import_mesh(context, path: Path) -> int` (assimp; Y-up → Z-up);
  operatorlar `ges.import_dxf` (fayl dialogi `.dxf;.dwg`), `ges.import_mesh` (`.fbx;.3ds;.obj;.lwo;.x;.dae;.blend`).

- [ ] **Step 1: Test** `desktop/tests/sath_tests/import_ops.py`

```python
"""DWG → DXF → FreeCAD → Blender curve/mesh (qatlam collection); FBX → assimp → mesh."""

from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parents[1]


def run(ctx):
    from sath import converters, ops_import

    assert converters.find_dwg2dxf(), "dwg2dxf topilmadi (~/Tools/libredwg)"
    n = ops_import.import_dxf(bpy.context, TESTS / "Namuna.dwg")
    assert n >= 1, n
    assert any(c.name.startswith("DXF") for c in bpy.data.collections), [c.name for c in bpy.data.collections]
    assert any(o.type == "CURVE" for o in bpy.data.objects)
    m = ops_import.import_mesh(bpy.context, TESTS / "Namuna.fbx")
    assert m >= 1 and any(o.type == "MESH" and o.name.startswith("FBX") for o in bpy.data.objects)
    assert hasattr(bpy.ops.ges, "import_dxf") and hasattr(bpy.ops.ges, "import_mesh")
```

- [ ] **Step 2: FAIL**, **Step 3: wheels** — `.venv\Scripts\pip download ezdxf assimp-py --dest desktop/blender/sath/wheels --only-binary=:all: --python-version 3.13 --platform win_amd64 --no-deps` (ezdxf `pyparsing`, `typing_extensions` ga bog'liq — ularni ham `--no-deps` siz yuklab, manifest `wheels` ga qo'shish; assimp-py wheel bo'lmasa `assimp_load` mesh import "mavjud emas" deb report qiladi — test faqat DXF qismini majburiy qiladi). Manifest:
```toml
wheels = ["./wheels/ezdxf-1.4.2-py3-none-any.whl", "./wheels/pyparsing-3.2.3-py3-none-any.whl", "./wheels/typing_extensions-4.14.0-py3-none-any.whl", "./wheels/assimp_py-1.0.8-cp313-cp313-win_amd64.whl"]
```
(aniq nomlar `pip download` natijasidan olinadi). Headless testda wheel lar o'rnatilmaydi — `blender_headless.py` `load_addon` da `sys.path` ga `sath/wheels/*.whl` ni qo'shadi (zip import; ezdxf sof python — ishlaydi; assimp-py `.pyd` — zip dan yuklanmaydi, test `try/except ImportError` bilan mesh qismini `skip` qiladi va `[OK]` da "(assimp yo'q)" yozadi).

- [ ] **Step 4: `converters.py`** (addon)

```python
"""DWG → DXF konverter (LibreDWG dwg2dxf yoki ODA File Converter) ni topish — FreeCAD siz."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""


def _candidate_dirs() -> list[Path]:
    dirs = []
    for env in ("GES_TOOLS_DIR", "GES_FC_HOME"):
        v = os.environ.get(env)
        if v:
            dirs += [Path(v), Path(v) / "tools", Path(v) / "tools" / "libredwg"]
    dirs += [Path.home() / "Tools", Path("C:/Tools"), Path("C:/Program Files/ODA"), Path("/opt/tools"), Path("/usr/local/bin")]
    return [d for d in dirs if d.is_dir()]


def _find(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in _candidate_dirs():
        for p in (d / (name + EXE), *d.glob(f"*/{name}{EXE}"), *d.glob(f"*/*/{name}{EXE}")):
            if p.is_file():
                return str(p)
    return None


def find_dwg2dxf() -> str | None:
    return _find("dwg2dxf")


def find_oda() -> str | None:
    return _find("ODAFileConverter")


def dwg_to_dxf(dwg: Path, out_dir: Path) -> Path:
    """DWG → DXF (dwg2dxf, bo'lmasa ODA). RuntimeError: konverter yo'q / xato."""
    import subprocess

    out_dir.mkdir(parents=True, exist_ok=True)
    dxf = out_dir / (dwg.stem + ".dxf")
    exe = find_dwg2dxf()
    if exe:
        r = subprocess.run([exe, "-y", "-o", str(dxf), str(dwg)], capture_output=True, text=True, timeout=300)
        if not dxf.exists():
            raise RuntimeError(f"dwg2dxf xatosi: {r.stderr[-300:]}")
        return dxf
    oda = find_oda()
    if oda:
        subprocess.run([oda, str(dwg.parent), str(out_dir), "ACAD2018", "DXF", "0", "1", dwg.name], capture_output=True, timeout=600)
        if dxf.exists():
            return dxf
        raise RuntimeError("ODA File Converter DXF yaratmadi")
    raise RuntimeError("DWG konverter topilmadi: LibreDWG dwg2dxf ni ~/Tools/libredwg ga qo'ying")
```

- [ ] **Step 5: `ops_import.py`**

```python
"""DXF/DWG (FreeCAD Import/Draft orqali, qatlam → collection) va mesh (assimp) import."""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import converters, fc_engine

MM = 0.001


def _collection(name: str):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def _edges_to_curve(name: str, shape, coll):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for e in shape.Edges:
        pts = e.discretize(Deflection=0.5)
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p.x * MM, p.y * MM, p.z * MM, 1.0)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def import_dxf(context, path: Path, prepare: bool = True) -> int:
    """DWG/DXF → FreeCAD (importDXF, ezdxf bilan tekislangan) → Blender. Qaytaradi: obyekt soni."""
    FreeCAD = fc_engine.load()
    path = Path(path)
    work = Path(tempfile.gettempdir()) / "sath" / "dxf"
    if path.suffix.lower() == ".dwg":
        path = converters.dwg_to_dxf(path, work)
    if prepare:
        try:
            from .shared import dxf_prepare

            path = Path(dxf_prepare.prepare(str(path), str(work / (path.stem + "_prep.dxf"))))
        except ImportError:
            pass  # ezdxf yo'q — FreeCAD ning o'zi
    import importDXF

    doc = FreeCAD.newDocument("GES_DXF")
    FreeCAD.setActiveDocument(doc.Name)
    n = 0
    try:
        importDXF.insert(str(path), doc.Name)
        doc.recompute()
        root = _collection(f"DXF {Path(path).stem}")
        for o in doc.Objects:
            sh = getattr(o, "Shape", None)
            if sh is None or sh.isNull():
                continue
            layer = next((p for p in o.InList if p.TypeId == "App::FeaturePython" and "Layer" in p.Name), None)
            coll = _collection(f"{root.name} / {layer.Label}") if layer else root
            if coll is not root and coll.name not in root.children:
                context.scene.collection.children.unlink(coll) if coll.name in context.scene.collection.children else None
                root.children.link(coll)
            name = f"DXF_{o.Label}"
            if sh.Faces:
                me = bpy.data.meshes.new(name)
                fc_engine.shape_to_mesh(sh, me)
                ob = bpy.data.objects.new(name, me)
                coll.objects.link(ob)
            else:
                ob = _edges_to_curve(name, sh, coll)
            n += 1
    finally:
        FreeCAD.closeDocument(doc.Name)
    return n


def import_mesh(context, path: Path) -> int:
    """FBX/3DS/OBJ/... → assimp → mesh (Y-up → Z-up)."""
    from .shared import assimp_load

    meshes = assimp_load.load(str(path))
    coll = _collection(f"{Path(path).suffix[1:].upper()} {Path(path).stem}")
    n = 0
    for m in meshes:
        me = bpy.data.meshes.new(m["name"])
        verts = [(v[0], -v[2], v[1]) for v in m["vertices"]]  # Y-up → Z-up
        me.from_pydata(verts, [], m["faces"])
        me.update()
        ob = bpy.data.objects.new(f"{Path(path).suffix[1:].upper()}_{m['name']}", me)
        if m.get("color"):
            ob.color = (*m["color"][:3], 1.0)
        coll.objects.link(ob)
        n += 1
    return n


class GES_OT_import_dxf(bpy.types.Operator, ImportHelper):
    """DWG/DXF chizmani ochish (FreeCAD importeri, qatlamlar collection sifatida)"""

    bl_idname = "ges.import_dxf"
    bl_label = "DWG/DXF import"
    filename_ext = ".dxf"
    filter_glob: bpy.props.StringProperty(default="*.dxf;*.dwg", options={"HIDDEN"})
    prepare: bpy.props.BoolProperty(name="Tekislash (bloklar, o'lchamlar, shtrix)", default=True)

    @classmethod
    def poll(cls, context):
        return fc_engine.available()

    def execute(self, context):
        try:
            n = import_dxf(context, Path(self.filepath), self.prepare)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{n} obyekt import qilindi")
        return {"FINISHED"}


class GES_OT_import_mesh(bpy.types.Operator, ImportHelper):
    """FBX/3DS/OBJ/LWO/X/DAE mesh import (assimp)"""

    bl_idname = "ges.import_mesh"
    bl_label = "Mesh import (assimp)"
    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(default="*.fbx;*.3ds;*.obj;*.lwo;*.x;*.dae;*.blend", options={"HIDDEN"})

    def execute(self, context):
        try:
            n = import_mesh(context, Path(self.filepath))
        except ImportError:
            self.report({"ERROR"}, "assimp-py o'rnatilmagan (extension wheel)")
            return {"CANCELLED"}
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import xatosi: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{n} mesh import qilindi")
        return {"FINISHED"}


CLASSES = (GES_OT_import_dxf, GES_OT_import_mesh)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
```
`dxf_prepare.prepare(src, dst)` va `assimp_load.load(path)` — workbench manbasidagi haqiqiy funksiya nomlarini tekshirib (`grep "^def " desktop/GesWorkbench/ges_workbench/dxf_prepare.py assimp_load.py`) moslash. `import_dxf` dagi qatlam aniqlash: `importDXF` Draft `Layer` obyektlari `Group` ga elementlarni qo'shadi — `o.InList` da qatlam bor.

- [ ] **Step 6: `ui.py` — `GES_PT_import`** + File → Import menyu

```python
class GES_PT_import(GesPanel, bpy.types.Panel):
    bl_label = "Import"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("ges.import_dxf", icon="GREASEPENCIL")
        col.operator("ges.import_mesh", icon="MESH_DATA")


def _menu_import(self, context):
    self.layout.operator("ges.import_dxf", text="Sath: DWG/DXF (.dwg, .dxf)")
    self.layout.operator("ges.import_mesh", text="Sath: Mesh (assimp)")
```
`register()` da `bpy.types.TOPBAR_MT_file_import.append(_menu_import)`, `unregister()` da `remove`. `__init__.py` MODULES ga `ops_import`.

- [ ] **Step 7: PASS** — `--test import_ops`; ruff; commit `git commit -m "sath: DWG/DXF (FreeCAD) va mesh (assimp) import, wheels"`

---

### Task 10: Header menyu, CI, README, versiya

**Files:**
- Modify: `ui.py` (`GES_MT_main` — `VIEW3D_MT_editor_menus` ga «Sath» menyu, `Ctrl+Shift+G`), `flows.py` (`ADDON_VERSION` manifestdan), `.github/workflows/*.yml` (sync `--check`, headless smoke), `desktop/blender/README.md`, `desktop/README.md` (Blender bo'limi)
- Create: `desktop/build/build_blender_addon.py` (extension zip: `blender --command extension build --source-dir sath --output-dir dist`)

- [ ] **Step 1: Header menyu**

```python
class GES_MT_main(bpy.types.Menu):
    bl_label = "Sath"
    bl_idname = "GES_MT_main"

    def draw(self, context):
        lay = self.layout
        lay.operator("ges.connect" if not session.is_logged_in() else "ges.logout")
        lay.separator()
        lay.operator("ges.open_version")
        lay.operator("ges.commit")
        lay.operator("ges.submit")
        lay.operator("ges.open_web")
        lay.separator()
        lay.operator_menu_enum("ges.add_object", "kind", text="GES obyekti")
        lay.operator("ges.import_dxf")
        lay.operator("ges.import_mesh")
        lay.separator()
        lay.operator("ges.sim_catalog")
        lay.operator("ges.safety_check")
        lay.operator("ges.monitor_toggle")
        lay.operator("ges.notifications")


def _menu_header(self, context):
    self.layout.menu("GES_MT_main")
```
`register()`: `bpy.types.VIEW3D_MT_editor_menus.append(_menu_header)`; keymap: `wm.keyconfigs.addon.keymaps.new(name="3D View", space_type="VIEW_3D")` → `kmi = km.keymap_items.new("wm.call_menu", "G", "PRESS", ctrl=True, shift=True)`, `kmi.properties.name = "GES_MT_main"`; `unregister` da olib tashlash.

- [ ] **Step 2: `ADDON_VERSION` manifestdan**

```python
def _manifest_version() -> str:
    try:
        text = (Path(__file__).resolve().parent / "blender_manifest.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


ADDON_VERSION = _manifest_version()
```
pytest: `assert re.match(r"\d+\.\d+\.\d+", flows.ADDON_VERSION)`.

- [ ] **Step 3: CI** — monorepo workflow ga: `python desktop/build/sync_blender.py --check` (ruff/pytest qatoridan oldin). Headless Blender testlari CI da yo'q (Blender + FreeCAD + Bonsai yuklab olish og'ir) — `desktop/tests/run_blender_tests.ps1` lokal skript: `smoke engine ifc_bridge objects server_ops review_ops sim_ops monitor_ops import_ops` ni ketma-ket, `[FAIL]` bo'lsa exit 1.

- [ ] **Step 4: `build_blender_addon.py`**

```python
"""Sath Blender extension zip: desktop/dist/sath-<ver>.zip (wheels bilan)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "desktop" / "blender" / "sath"
DIST = ROOT / "desktop" / "dist"
BLENDER = os.environ.get("GES_BLENDER", os.path.join(os.path.expanduser("~"), "Tools", "blender-5.2", "blender.exe"))

if __name__ == "__main__":
    subprocess.run([sys.executable, str(ROOT / "desktop" / "build" / "sync_blender.py")], check=True)
    DIST.mkdir(exist_ok=True)
    subprocess.run([BLENDER, "--command", "extension", "build", "--source-dir", str(SRC), "--output-dir", str(DIST)], check=True)
    print("tayyor:", [p.name for p in DIST.glob("sath-*.zip")])
```
Run → `desktop/dist/sath-0.3.0.zip`; o'rnatib tekshirish: `blender --command extension install-file --repo user_default --enable desktop/dist/sath-0.3.0.zip` → GUI da N-panel «Sath» ko'rinadi.

- [ ] **Step 5: README** — `desktop/blender/README.md` ni qayta yozish: o'rnatish (extension zip, Bonsai, FreeCAD py313 conda muhiti `micromamba create -p ~/Tools/fc-py313 -c conda-forge "freecad=1.1.3=py313*"`), panellar ro'yxati, headless testlar, `sync_blender.py`. `desktop/README.md` ga «Blender addoni» bo'limi (2 xatboshi + havola). Eski `desktop/blender/sath_blender.py` — o'chirish (o'rnini addon egallaydi).

- [ ] **Step 6: Qo'lda GUI tekshiruv (server bilan)** — `server` ni ishga tushirib (`README` bo'yicha), Blender 5.2 GUI: Ulanish → Model → ochish (namuna) → GES obyekt qo'shish → parametr o'zgartirish → Commit → Webda ochish → Taqriz → Sim katalogi → Monitoring. Natijani `docs/superpowers/plans/…` fayliga emas, `desktop/blender/README.md` «Sinalgan» qatoriga sana bilan yozish.

- [ ] **Step 7: commit** — `git commit -m "sath: menyu, CI sync tekshiruvi, extension build, README"`

---

## Self-review (reja yozilgandan keyin)

- Spec qamrovi: Server/Model ✔ (5), GES obyektlari ✔ (2, 4), IFC Bonsai ✔ (3), viewpoint/issue/CR/diff ✔ (6), sim/xavfsizlik/suv ✔ (7), monitoring ✔ (8), import ✔ (9), UI/menyu ✔ (5–10), sync/CI ✔ (1, 10). Ko'lam tashqarisi (dxf_edit, preset, matplotlib) — yo'q, spec bo'yicha.
- Nomlar izchilligi: `ops_server.guard`, `ops_server._sel` — 6/7/8 shularni import qiladi; `props.fill`; `ifc.DIFF_STATE/ALARM_STATE`; `flows.DIFF_COLORS` (rgba) va `ifc.DIFF_COLORS` — **bitta manba**: `ifc.py` `from .flows import ALARM_COLORS, DIFF_COLORS` qilsin (3-vazifada `flows` hali yo'q → 3-vazifada `ifc.py` ranglarni o'zida e'lon qiladi, 5-vazifada `flows` `from .ifc import ...` emas — `flows` bpy siz bo'lishi kerak; shuning uchun ranglar `flows.py` da (sof) yashaydi va 5-vazifada `ifc.py` `from .flows import ALARM_COLORS, DIFF_COLORS` ga o'tkaziladi).
- `props.py` `session` ni import qiladi (index update callback) — `session` bpy siz, aylanma import yo'q.
