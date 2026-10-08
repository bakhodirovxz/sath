# Poydevor P4: ish joylari (workspace lar), tema, tokenlar, keymap, byudjetlar — amalga oshirish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sath ilovasi o'z ish joylarida ochiladi: BIM (asosiy), Compare, Simulation, SCADA; keraksiz Blender ish joylari olib tashlanadi; Sath ish joylarida faqat Sath va Bonsai interfeysi; tema Blender Dark asosida; 3D diff/alarm ranglari web bilan aynan bir xil (yagona manba `web/src/ui/tokens.ts`, CI sinxronni tekshiradi); Ctrl+Shift+G Blender/Bonsai yorliqlari bilan to'qnashmasligi headless tekshiriladi; spec §5 byudjetlari (register < 150 ms, og'ir importlar dangasa, sovuq start ≤ 1.2×, RSS ≤ +50 MB) o'lchanadi, logda ko'rinadi va bajariladi; FreeCAD siz bundle yig'iladi va «BIM ish joyida ochiladi» tekshiriladi.

**Architecture:** Ish joylari app template ichida (`template/Sath/workspaces.py`): `load_factory_startup_post` ilgagi har factory startup da `ensure()` ni idempotent chaqiradi — Layout nusxasidan teg (`ws["sath_ws"]`) bilan to'rt ish joyi, Blender ish joylarini olib tashlash, egasi bo'yicha filtr, tab tartibi, BIM ni faollashtirish. Blender ko'rinmayotgan ekranda area turini almashtirmaydi — Simulation dagi Graph editor ish joyi birinchi ochilganda `msgbus` (Window.workspace) orqali `finish()` bilan yakunlanadi. Addon tomonda `SathPanel` tegni modul manifestidagi `workspaces` bilan solishtiradi (P3 da tayyor; P4 da `panels.in_workspace` ga ajratiladi). Tokenlar: `desktop/build/gen_tokens.py` (sof Python, node siz) `tokens.ts` va `palette.ts` dan `sath/core/tokens.py` (sRGB → chiziqli) va `template/Sath/theme_sath.xml` (Blender Dark ustiga farqlar) ni yasaydi, CI `--check`. Keymap: `sath/core/keys.py` — barcha Sath yorliqlari ro'yxati + sof `conflicts()`; headless test Blender ning `blender_default.py` keymapini generatsiya qilib va Bonsai addon keymaplari bilan solishtiradi. Byudjetlar: `sath/core/budget.py` (yagona chegaralar), `sath/__init__.register()` har yadro qismi va modul vaqtini bitta qatorda logga yozadi, `numpy` (`ges_kinds` → `geom`, `ges_objects`) funksiya ichiga ko'chadi, `perf_baseline.py --check` natijani `docs/benchmark-desktop.md` ga P0 bilan yonma-yon yozadi.

**Tech Stack:** Blender 5.2.2 LTS (Python 3.13, bpy, `bpy.msgbus`, `script.execute_preset`), Bonsai 0.9.0; stdlib (`re`, `json`, `importlib`, `subprocess`); pytest (Python 3.10+ `.venv`, CI 3.12); PowerShell runner `run_blender_tests.ps1`.

**Spec:** `docs/superpowers/specs/2026-10-08-sath-foundation-design.md` (§5 App template va workspace lar, «Bosqichlar» P4: «bundle ~0.9 GB kichik, BIM workspace da ochiladi; byudjetlar log da va bajarilgan»)

## Global Constraints

- **P0–P3 bajarilgan.** FreeCAD bundle da yo'q (P2, stage ≈1568–1611 MB); modul reyestri, `SathPanel` (tegsiz ish joyi — hamma panel ko'rinadi), `api.ui.keymap`, `Record.ms` (har modul import+register vaqti) mavjud. Manifestlardagi `workspaces` qiymatlari: `bim`, `io` → `BIM`; `review` → `BIM, Compare`; `sim` → `Simulation, BIM`; `scada` → `SCADA`; `twin` → `SCADA, Simulation`.
- **Qator oxirlari (EOL) saqlanadi.** Har faylni tahrirlashdan oldin va commit oldidan `git ls-files --eol <fayl>` — `i/` va `w/` o'zgarmasin. CRLF: `desktop/blender/sath/__init__.py`, `ges_objects.py`, `ifc.py`, `desktop/build/build_blender_bundle.py`, `desktop/blender/template/make_splash.py`, `sath_boot.py`, `desktop/tests/blender_gui_check.py`, `desktop/blender/README.md`. `flows.py` — **mixed** (butun faylni normallashtirmang; tahrir qilinadigan 158-, 304–311-, 352–357- qatorlar LF — faqat Edit bilan). Qolganlari (template `__init__.py`, `setup_bundle.py`, `ui.py`, `api.py`, `core/*.py`, `perf_*.py`, `run_blender_tests.ps1`, `ci.yml`, `tokens.ts`, `benchmark-desktop.md`) — LF. Yangi fayllar — LF. `git diff --stat` da butun fayl qayta yozilgandek ko'rinsa — EOL buzilgan, qaytaring.
- **UTF-8 xavfsiz tahrir:** faqat Edit/Write yoki `python` (`encoding="utf-8"`, `newline="\n"`). PowerShell `Get-Content`/`Set-Content`/`Out-File` bilan fayl yozish **taqiqlangan** (cp1251 mojibake bo'lgan). O'zbekcha matnda apostrof — ASCII `'`.
- **Sof modullar Python 3.10 da ishlaydi** (`.venv` 3.10.11): `sath/core/tokens.py`, `keys.py`, `budget.py`, `registry.py`, `desktop/build/gen_tokens.py`, `template/Sath/workspaces.py` ning modul darajasi (bpy faqat funksiyalar ichida). `ExceptionGroup`, `typing.Self`, `datetime.UTC` yo'q.
- **Generatsiya qilingan fayllar qo'lda tahrirlanmaydi:** `sath/core/tokens.py`, `template/Sath/theme_sath.xml` — faqat `python desktop/build/gen_tokens.py`; `sath/shared/*` — faqat `python desktop/build/sync_blender.py` (kanonik manba `common/sath_common/*`).
- Ishchi oqim bpy ga tegmaydi; `bl_idname` lar o'zgarmaydi. Yangi: `sath.reset_workspaces` (app template ro'yxatga oladi).
- Blender klassi atributlariga (property bo'lmagan) tip annotatsiyasi yozilmaydi.
- **Blender 5.2.2 da tekshirilgan faktlar (reja yozilishida sinalgan):** `load_factory_startup_post` template o'z `startup.blend` i bilan ham ishlaydi va `-b` da ham oyna (`context.window`) bor; `--factory-startup` app template Python ini yuklamaydi; `WorkSpace.copy()` ishlaydi, `bpy.data.workspaces.remove` yo'q — `bpy.data.batch_remove(ids=[...])`; `workspace.delete` operatori kechiktiriladi (ishlatilmaydi); `Window.workspace = …` kechiktiriladi (GUI da keyingi siklda, `-b` da umuman); `screen.area_split` ko'rinmayotgan ekranda ham ishlaydi (gorizontal bo'lishda yangi area — **pastda**); `area.ui_type` ni almashtirish faqat oynada ko'rinayotgan ekranda haqiqatda qo'llanadi (GUI da jim e'tiborsiz) → `msgbus` `(bpy.types.Window, "workspace")` almashganda ishlaydi va o'sha paytda tur almashadi; `presets/interface_theme/Blender_Dark.xml` bo'sh (= sukut tema), `script.execute_preset` avval `reset_default_theme`, XML da `<ThemeStyle>` elementi **shart**; `keyconfigs.addon` `-b` da bor, lekin standart keymaplar `-b` da bo'sh → standart yorliqlar `scripts/presets/keyconfig/keymap_data/blender_default.py` dan `generate_keymaps(Params())` bilan olinadi (bpy siz); standart «Object Mode» keymapida Ctrl+Shift+G = `collection.objects_add_active`; addon keymap elementlari o'sha keymap boshiga qo'shiladi (Bonsai ham «Object Mode» dagi standartlarni shu yo'l bilan yopadi); `Object.color` va `View3DShading.background_color` — chiziqli (`COLOR`), tema ranglari — sRGB; `BLENDER_USER_SCRIPTS` dagi `startup/bl_app_templates_user/<nom>` template sifatida topiladi; `-b` da ish joylari qurilgandan keyin chiqishda `Error: Not freed memory blocks: <N>` chiqadi (ko'rsatilmagan ekran region ma'lumoti, zararsiz) — testlar bu qatorga qaramaydi. Reja kodi yozilishida sinalgan: 17 ta sof test (tokens, keys, budget, workspaces) scratch nusxada o'tdi; Task 3 headless testi (panel qismisiz) Blender 5.2.2 da `[OK]`; keymap tekshiruvi real ma'lumotda 3095 standart + 24 Bonsai yorlig'i, ALLOWED bilan to'qnashuv 0; GUI da user keyconfig «Object Mode» da addon elementi standartdan oldin.
- **GUI testlari CI da emas** (oyna kerak; Windows runner GUI kafolatlanmagan): headless testlar ma'lumot modelini, `desktop/tests/run_gui_workspaces.py` esa oynali tekshiruvni beradi — lokal, hisobotga natija yoziladi.
- Foydalanuvchi matnlari o'zbekcha (lotin). Commit xabarlari o'zbekcha: `feat(UI): …`, `feat(PERF): …`, `test(UI): …`, `build(BUNDLE): …`, `docs(UI): …`; oxirida bo'sh qator va `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Har vazifa — bitta commit (push yo'q).
- `ruff check server sim desktop` toza (line-length 100, `--fix` faqat import tartibi, faqat tegilgan fayllarda).
- Tekshiruv muhiti: `$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"`; pytest — `.venv\Scripts\python.exe -m pytest`.

## Review Focus

1. **GUI da ish joylari:** Sath ochilganda BIM faol; Simulation dagi Graph editor faqat ish joyi ko'ringanda (msgbus `finish`) paydo bo'ladi va belgisi o'chadi; `reset_workspaces` ochiq ish joyini o'chirmaydi va tegni takrorlamaydi → Task 3 `_check`, Task 5 GUI zanjiri, Task 7 bundle GUI.
2. **`use_filter_by_owner` Sath/Bonsai panellarini yashirib qo'ymaydi** (egasi nomlari bundle dagi `bl_ext.user_default.sath/bonsai` ga va yoqilgan addonlarga mos) → Task 3 `owner_ids`, Task 7 skrinshot.
3. **Ctrl+Shift+G «Object Mode» da standart `collection.objects_add_active` ni ataylab yopadi** (ALLOWED da sabab bilan); to'qnashuv testi bo'sh emas (1000+ standart yorliq, ALLOWED eskirmagan), user keyconfig da Sath elementi birinchi → Task 4, Task 5.
4. **Dangasa importlar va byudjetlar halol:** register da `numpy/ifcopenshell/ezdxf/assimp_py` yuklanmaydi, `ges_kinds` da `tol=None` sukuti `geom.TOL` ga teng, byudjet chegaralari yumshatilmagan, natija o'lchovdan → Task 6, Task 8.
5. **Tokenlar yagona manba:** `tokens.ts`/`palette.ts` → `core/tokens.py` (sRGB → chiziqli) + sahna «Standard» view transform; alarm xaritasi web `MonitoringPanel.alarmHex` ga teng (ok — kulrang `text-muted`); web tokeni o'zgarsa CI `gen_tokens.py --check` yiqiladi → Task 1, Task 2.

---

## Fayl tuzilmasi

| Fayl | Mas'uliyat |
|---|---|
| `desktop/build/gen_tokens.py` (yangi) | web tokenlari → `core/tokens.py` + `theme_sath.xml`; `--check` |
| `desktop/blender/sath/core/tokens.py` (yangi, generatsiya) | `THEMES`, `PAL`, `parse/rgba/pal_rgba` (sRGB → chiziqli) |
| `desktop/blender/template/Sath/theme_sath.xml` (yangi, generatsiya) | Blender Dark + Sath farqlari (tanlov, viewport foni, gizmo o'qlari) |
| `desktop/blender/sath/flows.py` (o'zgaradi, mixed EOL) | diff/alarm/sog'liq ranglari tokenlardan, `alarm_rgba` |
| `desktop/blender/template/Sath/workspaces.py` (yangi) | `ensure()`, `finish()`, `tagged()`, `owner_ids()`, konstantalar |
| `desktop/blender/template/Sath/__init__.py` (o'zgaradi) | ilgaklar, msgbus, `sath.reset_workspaces`, «Standard» view transform |
| `desktop/blender/sath/core/registry.py`, `core/panels.py` (o'zgaradi) | `WORKSPACE_TAG`, `WORKSPACES`; `in_workspace()` |
| `desktop/blender/sath/core/keys.py` (yangi) | Sath yorliqlari ro'yxati, `add()`, `chord()`, sof `conflicts()` |
| `desktop/blender/sath/ui.py`, `api.py` (o'zgaradi) | Ctrl+Shift+G «3D View» + «Object Mode» `keys.add` orqali; menyuda «Ish joylarini tiklash» |
| `desktop/blender/sath/core/budget.py` (yangi) | spec §5 chegaralari, log qatori, `check()` |
| `desktop/blender/sath/__init__.py` (o'zgaradi, CRLF) | register perf logi |
| `common/sath_common/ges_kinds.py` → `sath/shared/ges_kinds.py` (sync); `sath/ges_objects.py` (CRLF) | numpy dangasa |
| `desktop/blender/template/setup_bundle.py`, `desktop/build/build_blender_bundle.py` (CRLF) | tema, ish joylari bilan startup.blend, stage tekshiruvi |
| `desktop/tests/perf_blender.py`, `perf_baseline.py` (o'zgaradi) | `--budget`, `--ws`, P0 ustuni, byudjet jadvali, `--check`, `--bundle` |
| `desktop/tests/test_sath_tokens.py`, `test_sath_workspaces.py`, `test_sath_keys.py`, `test_sath_budget.py` (yangi), `test_sath_pure.py` (o'zgaradi) | sof testlar |
| `desktop/tests/sath_tests/workspaces.py`, `keymap.py`, `budgets.py` (yangi), `run_blender_tests.ps1` (o'zgaradi) | headless (22 → 25) |
| `desktop/tests/run_gui_workspaces.py`, `blender_gui_workspaces.py`, `bundle_check.py` (yangi) | oynali va bundle tekshiruvlari (lokal) |
| `.github/workflows/ci.yml`, `web/src/ui/tokens.ts` (o'zgaradi) | `gen_tokens.py --check`; manba izohi |
| `docs/benchmark-desktop.md`, `desktop/blender/README.md` (o'zgaradi) | natija va hujjat |

---

### Task 1: Web tokenlari → `core/tokens.py` + `theme_sath.xml` (generator, CI `--check`)

**Model:** sonnet — regex parser + aniq chiqish formati; web fayllari formatiga chidamlilik.

**Files:**
- Create: `desktop/build/gen_tokens.py`
- Create (generatsiya): `desktop/blender/sath/core/tokens.py`, `desktop/blender/template/Sath/theme_sath.xml`
- Create: `desktop/tests/test_sath_tokens.py`
- Modify: `.github/workflows/ci.yml` (`server` va `desktop-blender` ishlari), `web/src/ui/tokens.ts` (sarlavha izohi)

**Interfaces:**
- Consumes: `web/src/ui/tokens.ts` (`export const THEMES … = {` → `  engineer: {` / `  "operator-hc": {` → `    "key": "value",`; 3 tema × 70 kalit), `web/src/viewer/palette.ts` (`export const PAL = {` → `  name: "value",`; 44 satr qiymat, ichki `draft` va massivlar o'tkazib yuboriladi).
- Produces: `sath.core.tokens.THEMES: dict[str, dict[str, str]]`, `PAL: dict[str, str]`, `parse(value) -> (r, g, b, a)` sRGB 0..1, `rgba(token, theme="engineer") -> (r, g, b, a)` chiziqli, `pal_rgba(name)` chiziqli. `gen_tokens.check() -> list[str]` (eskirgan fayllar), `gen_tokens.parse_themes/parse_palette` (format o'zgarsa `SystemExit`). Task 2, 3, 7 ishlatadi.

- [ ] **Step 1: Yiqiluvchi test** — `desktop/tests/test_sath_tokens.py`:

```python
"""Web dizayn tokenlari → desktop (P4, spec §5): core/tokens.py va theme_sath.xml generatsiyasi sinxron,
ranglar web bilan bir xil (sRGB → chiziqli)."""

import sys
import xml.dom.minidom
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "build"))
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

import gen_tokens  # noqa: E402
from sath.core import tokens  # noqa: E402


def test_generated_files_in_sync():
    assert gen_tokens.check() == [], "python desktop/build/gen_tokens.py ni ishga tushiring"


def test_themes_and_palette_parsed():
    assert list(tokens.THEMES) == ["engineer", "operator", "operator-hc"]
    keys = set(tokens.THEMES["engineer"])
    assert len(keys) >= 70
    assert keys == set(tokens.THEMES["operator"]) == set(tokens.THEMES["operator-hc"])
    need = {"diff-add", "diff-change", "alarm-critical", "alarm-medium", "alarm-stale", "text-muted", "canvas"}
    assert need <= keys
    assert tokens.THEMES["engineer"]["overlay"].startswith("rgba(")
    # palette.ts: «BIM versiya farqi (tokens --diff-* bilan bir xil)» — web 3D diff = tokenlar
    assert tokens.PAL["diffAdd"] == tokens.THEMES["engineer"]["diff-add"]
    assert tokens.PAL["diffChange"] == tokens.THEMES["engineer"]["diff-change"]
    assert "primitive" not in tokens.PAL and "heatRamp" not in tokens.PAL  # ichki obyekt/massiv emas


def test_parse_and_linear_conversion():
    assert tokens.parse("#ff8000") == (1.0, 128 / 255, 0.0, 1.0)
    assert tokens.parse("#fff") == (1.0, 1.0, 1.0, 1.0)
    assert tokens.parse("#00000080")[3] == pytest.approx(128 / 255)
    assert tokens.parse("rgba(48, 48, 48, 0.75)") == (48 / 255, 48 / 255, 48 / 255, 0.75)
    r, g, b, a = tokens.rgba("diff-add")  # #2ecc71
    assert r == pytest.approx(((0x2E / 255 + 0.055) / 1.055) ** 2.4) and a == 1.0
    assert tokens.pal_rgba("diffAdd") == tokens.rgba("diff-add")
    assert tokens.rgba("canvas", "operator") != tokens.rgba("canvas")
    with pytest.raises(ValueError):
        tokens.parse("red")
    with pytest.raises(KeyError):
        tokens.rgba("yoq-token")


def test_parser_fails_loudly_on_format_change():
    with pytest.raises(SystemExit):
        gen_tokens.parse_themes("export const OTHER = {\n};\n")
    with pytest.raises(SystemExit):
        gen_tokens.parse_palette("export const PAL = {\n} as const;\n")


def test_theme_xml_is_blender_dark_overrides_from_palette():
    text = gen_tokens.THEME_XML.read_text("utf-8")
    xml.dom.minidom.parseString(text)  # to'g'ri XML
    assert f'object_active="{tokens.PAL["highlight"]}"' in text
    assert f'high_gradient="{tokens.PAL["sceneBg"]}"' in text
    assert f'axis_x="{tokens.PAL["axisX"]}"' in text
    assert "<ThemeStyle>" in text  # Blender execute_preset ThemeStyle elementisiz yiqiladi
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_tokens.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'gen_tokens'`).

- [ ] **Step 2: `desktop/build/gen_tokens.py`**

```python
"""Dizayn tokenlari: web → desktop (spec §5). Yagona manba — web/src/ui/tokens.ts (THEMES) va
web/src/viewer/palette.ts (PAL). Bu skript ulardan yasaydi:
  * desktop/blender/sath/core/tokens.py — 3D diff/alarm/sog'liq ranglari web bilan bir xil (bpy siz)
  * desktop/blender/template/Sath/theme_sath.xml — Blender Dark ustiga Sath farqlari (setup_bundle.py)
Node kerak emas (CI desktop ishida ham ishlaydi).

python desktop/build/gen_tokens.py          # yozish
python desktop/build/gen_tokens.py --check  # CI: farq bo'lsa exit 1
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS_TS = ROOT / "web" / "src" / "ui" / "tokens.ts"
PALETTE_TS = ROOT / "web" / "src" / "viewer" / "palette.ts"
TOKENS_PY = ROOT / "desktop" / "blender" / "sath" / "core" / "tokens.py"
THEME_XML = ROOT / "desktop" / "blender" / "template" / "Sath" / "theme_sath.xml"

_THEME_OPEN = re.compile(r'^  "?([\w-]+)"?: \{\s*$')
_THEME_ENTRY = re.compile(r'^    "?([\w-]+)"?: "([^"]+)",?\s*(?://.*)?$')
_PAL_ENTRY = re.compile(r'^  (\w+): "([^"]+)",?\s*(?://.*)?$')
THEME_KEYS = ("axisX", "axisY", "axisZ", "highlight", "sceneBg")  # theme_sath.xml dagi PAL ranglari

PY_HEADER = '''"""Dizayn tokenlari — web/src/ui/tokens.ts (THEMES) va web/src/viewer/palette.ts (PAL, faqat
satr qiymatlar) dan avtomatik: `python desktop/build/gen_tokens.py` (CI: `--check`).
QO'LDA TAHRIRLAMANG. bpy siz (pytest).

Blender 3D ranglari (Object.color, View3DShading.background_color) chiziqli: rgba()/pal_rgba() sRGB
hex ni chiziqliga o'giradi — web (three.js: sRGB → linear) bilan bir xil ko'rinadi; Sath template
sahnasi «Standard» view transform da (AgX ranglarni o'zgartirmasin)."""

from __future__ import annotations

'''

PY_FUNCS = '''

def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def parse(value: str) -> tuple[float, float, float, float]:
    """'#rgb' | '#rrggbb' | '#rrggbbaa' | 'rgba(r, g, b, a)' → sRGB 0..1 va alfa."""
    v = value.strip()
    if v.startswith("#") and len(v) in (4, 7, 9):
        h = "".join(ch * 2 for ch in v[1:]) if len(v) == 4 else v[1:]
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, a)
    if v.startswith("rgba(") and v.endswith(")"):
        r, g, b, a = (float(x) for x in v[5:-1].split(","))
        return (r / 255.0, g / 255.0, b / 255.0, a)
    raise ValueError(f"rang tushunilmadi: {value!r}")


def rgba(token: str, theme: str = "engineer") -> tuple[float, float, float, float]:
    """Web tokeni → chiziqli RGBA (Object.color). Sukut «engineer» — web BIM sahifalari temasi."""
    r, g, b, a = parse(THEMES[theme][token])
    return (_linear(r), _linear(g), _linear(b), a)


def pal_rgba(name: str) -> tuple[float, float, float, float]:
    """web/src/viewer/palette.ts PAL rangi → chiziqli RGBA."""
    r, g, b, a = parse(PAL[name])
    return (_linear(r), _linear(g), _linear(b), a)
'''

THEME_TEMPLATE = """<!-- Sath temasi: Blender Dark + Sath farqlari. Avtomatik (desktop/build/gen_tokens.py, manba
     web/src/viewer/palette.ts), qo'lda tahrirlamang. setup_bundle.py qo'llaydi (script.execute_preset). -->
<bpy>
  <Theme>
    <user_interface>
      <ThemeUserInterface
        axis_x="{axisX}"
        axis_y="{axisY}"
        axis_z="{axisZ}"
        >
      </ThemeUserInterface>
    </user_interface>
    <view_3d>
      <ThemeView3D
        object_active="{highlight}"
        >
        <space>
          <ThemeSpaceGradient>
            <gradients>
              <ThemeGradientColors
                high_gradient="{sceneBg}"
                >
              </ThemeGradientColors>
            </gradients>
          </ThemeSpaceGradient>
        </space>
      </ThemeView3D>
    </view_3d>
  </Theme>
  <ThemeStyle>
  </ThemeStyle>
</bpy>
"""


def _block(text: str, start: str) -> list[str]:
    """`start` bilan boshlanadigan qatordan keyingi, birinchi `}` (ustun 0) gacha bo'lgan qatorlar."""
    lines = text.splitlines()
    i = next((n for n, ln in enumerate(lines) if ln.startswith(start)), None)
    if i is None:
        raise SystemExit(f"gen_tokens: {start!r} topilmadi (web fayli formati o'zgardimi?)")
    for j in range(i + 1, len(lines)):
        if lines[j].startswith("}"):
            return lines[i + 1 : j]
    raise SystemExit(f"gen_tokens: {start!r} bloki yopilmagan")


def parse_themes(text: str) -> dict[str, dict[str, str]]:
    themes: dict[str, dict[str, str]] = {}
    cur: dict[str, str] | None = None
    for ln in _block(text, "export const THEMES"):
        m = _THEME_OPEN.match(ln)
        if m:
            cur = themes.setdefault(m.group(1), {})
            continue
        if ln.startswith("  }"):
            cur = None
            continue
        m = _THEME_ENTRY.match(ln)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2)
    if not themes or not all(themes.values()):
        raise SystemExit("gen_tokens: tokens.ts THEMES o'qilmadi")
    return themes


def parse_palette(text: str) -> dict[str, str]:
    pal: dict[str, str] = {}
    for ln in _block(text, "export const PAL"):
        m = _PAL_ENTRY.match(ln)
        if m:
            pal[m.group(1)] = m.group(2)
    if not pal:
        raise SystemExit("gen_tokens: palette.ts PAL o'qilmadi")
    return pal


def render_py(themes: dict[str, dict[str, str]], pal: dict[str, str]) -> str:
    out = [PY_HEADER + "THEMES: dict[str, dict[str, str]] = {"]
    for name, vals in themes.items():
        out.append(f"    {json.dumps(name)}: {{")
        out += [f"        {json.dumps(k)}: {json.dumps(v)}," for k, v in vals.items()]
        out.append("    },")
    out.append("}")
    out.append("PAL: dict[str, str] = {")
    out += [f"    {json.dumps(k)}: {json.dumps(v)}," for k, v in pal.items()]
    out.append("}")
    return "\n".join(out) + "\n" + PY_FUNCS


def render_theme(pal: dict[str, str]) -> str:
    bad = [k for k in THEME_KEYS if not re.fullmatch(r"#[0-9a-fA-F]{6}", pal.get(k, ""))]
    if bad:
        raise SystemExit(f"gen_tokens: palette.ts da #rrggbb yo'q: {bad}")
    return THEME_TEMPLATE.format(**{k: pal[k] for k in THEME_KEYS})


def outputs() -> dict[Path, str]:
    themes = parse_themes(TOKENS_TS.read_text("utf-8"))
    pal = parse_palette(PALETTE_TS.read_text("utf-8"))
    return {TOKENS_PY: render_py(themes, pal), THEME_XML: render_theme(pal)}


def check() -> list[str]:
    """Eskirgan yoki yo'q fayllar (ROOT ga nisbatan). Qator oxiri farqi hisobga olinmaydi (Windows checkout)."""
    return [
        p.relative_to(ROOT).as_posix()
        for p, text in outputs().items()
        if not p.exists() or p.read_text("utf-8") != text
    ]


def main() -> int:
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("tokenlar eskirgan:", ", ".join(bad), "-> python desktop/build/gen_tokens.py")
            return 1
        print("web tokenlari va desktop nusxalari sinxron")
        return 0
    for p, text in outputs().items():
        p.write_text(text, encoding="utf-8", newline="\n")
        print("yozildi:", p.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Generatsiya**

Run: `.venv\Scripts\python.exe desktop/build/gen_tokens.py`
Expected: `yozildi: desktop/blender/sath/core/tokens.py` va `yozildi: desktop/blender/template/Sath/theme_sath.xml`.
Tekshiring: `tokens.py` da `"engineer": {` ostida 70 qator, `PAL` da 44 qator, `"highlight": "#f5a623"`; `theme_sath.xml` da `object_active="#f5a623"`, `high_gradient="#3d3d3d"`, `axis_x="#e0656a"`.

- [ ] **Step 4: Testlar va lint**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_tokens.py` → `5 passed`
Run: `.venv\Scripts\python.exe desktop/build/gen_tokens.py --check` → `web tokenlari va desktop nusxalari sinxron`
Run: `.venv\Scripts\ruff.exe check desktop/build/gen_tokens.py desktop/blender/sath/core/tokens.py desktop/tests/test_sath_tokens.py` → toza

- [ ] **Step 5: CI va manba izohi**

`.github/workflows/ci.yml` — `server` ishida `- run: python desktop/build/sync_blender.py --check` qatoridan keyin:

```yaml
      - run: python desktop/build/gen_tokens.py --check  # P4: web tokenlari → desktop (tokens.py, tema)
```

`desktop-blender` ishida ham `- run: python desktop/build/sync_blender.py --check` dan keyin xuddi shu qator.

`web/src/ui/tokens.ts` sarlavha izohidagi ` * CSS da xuddi shu qiymatlar `tokens.css` da …` qatoridan keyin (LF):

```
 * Desktop (Blender) nusxasi: `python desktop/build/gen_tokens.py` → desktop/blender/sath/core/tokens.py va
 * template/Sath/theme_sath.xml (CI `--check` — bu yerdagi rang o'zgarsa desktop ham yangilanadi).
```

Run: `cd web; npm test -- tokens` (web testi o'zgarmagan, faqat izoh) → PASS; `git ls-files --eol web/src/ui/tokens.ts .github/workflows/ci.yml` → `i/lf w/lf`.

- [ ] **Step 6: Commit**

```bash
git add desktop/build/gen_tokens.py desktop/blender/sath/core/tokens.py desktop/blender/template/Sath/theme_sath.xml desktop/tests/test_sath_tokens.py .github/workflows/ci.yml web/src/ui/tokens.ts
git commit -m "feat(UI): web tokenlari desktopga — core/tokens.py va theme_sath.xml generatsiyasi (gen_tokens.py, CI --check)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 3D diff/alarm/sog'liq ranglari tokenlardan (web bilan bir xil)

**Model:** haiku — tayyor kod, uchta joyni almashtirish va bitta test; mixed EOL faylda faqat Edit.

**Files:**
- Modify: `desktop/blender/sath/flows.py` (**mixed EOL** — faqat Edit; tahrir qatorlari LF): importlar (`:9`), `DIFF_COLORS` (`:158`), `ALARM_COLORS` bloki (`:304-310`), `alarm_colors` (`:331-336`), `HEALTH_COLORS` (`:352-357`)
- Test: `desktop/tests/test_sath_pure.py` (yangi test oxiriga)

**Interfaces:**
- Consumes: `sath.core.tokens.rgba(token, theme="engineer")` (Task 1).
- Produces: `flows.DIFF_COLORS` (`diff-add`, `diff-change`), `flows.ALARM_STATES`, `flows.ALARM_PRIORITIES`, `flows.alarm_rgba(alarm, priority=None)` — web `MonitoringPanel.alarmHex` (`tokens.alarmStyle`) bilan bir xil: noma'lum/`ok` → `text-muted`, `stale` → `alarm-stale`, qolgani → `alarm-<priority|medium>`; `flows.ALARM_COLORS` (ustuvorlik «medium», mavjud testlar uchun); `flows.HEALTH_COLORS` — web: yaxshi → `ok`, qoniqarli → `warn`, yomon/kritik → `danger`. `ops_monitor`/`ops_review`/`ifc.ColorState` o'zgarmaydi.

- [ ] **Step 1: Yiqiluvchi test** — `desktop/tests/test_sath_pure.py` oxiriga:

```python
def test_3d_colors_match_web_tokens():
    """P4: 3D diff/alarm/sog'liq ranglari web bilan bir xil (tokens.ts → core/tokens.py, chiziqli)."""
    from sath import flows
    from sath.core import tokens

    assert flows.DIFF_COLORS == {"added": tokens.rgba("diff-add"), "changed": tokens.rgba("diff-change")}
    assert flows.alarm_rgba("high", "critical") == tokens.rgba("alarm-critical")
    assert flows.alarm_rgba("lowlow") == tokens.rgba("alarm-medium")  # ustuvorlik yo'q — medium
    assert flows.alarm_rgba("ok") == flows.alarm_rgba("nomalum") == tokens.rgba("text-muted")
    assert flows.alarm_rgba("stale", "critical") == tokens.rgba("alarm-stale")
    sensors = [{"element_guid": "G", "enabled": True, "alarm": "high", "priority": "low"}]
    assert flows.alarm_colors(sensors) == {"G": tokens.rgba("alarm-low")}
    assert flows.ALARM_COLORS["high"] == tokens.rgba("alarm-medium")
    assert flows.HEALTH_COLORS == {
        "yaxshi": tokens.rgba("ok"), "qoniqarli": tokens.rgba("warn"),
        "yomon": tokens.rgba("danger"), "kritik": tokens.rgba("danger"),
    }  # fmt: skip
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_pure.py -k web_tokens`
Expected: FAIL (`AssertionError` — eski qattiq ranglar).

- [ ] **Step 2: `flows.py` — import** (`from .shared.server_client import GesClient, ServerError` qatoridan oldin):

```python
from .core import tokens
```

- [ ] **Step 3: `DIFF_COLORS`** (`:158`) qatorini almashtiring:

```python
DIFF_COLORS = {"added": tokens.rgba("diff-add"), "changed": tokens.rgba("diff-change")}  # = web (P4)
```

- [ ] **Step 4: Alarm bloki** — `ALARM_COLORS = {` … `}` (5 qator) ni almashtiring (`ALARM_UZ` qatori qoladi):

```python
# web MonitoringPanel.alarmHex / tokens.alarmStyle bilan bir xil (P4): normal — kulrang (rang faqat anomaliya
# uchun, ISA-101), uzilgan — alarm-stale, alarm — sensor ustuvorligi rangi (priority, sukut medium).
ALARM_STATES = ("ok", "low", "high", "stale", "lowlow", "highhigh", "roc", "deviation")
ALARM_PRIORITIES = ("low", "medium", "high", "critical")


def alarm_rgba(alarm: str | None, priority: str | None = None) -> tuple:
    if alarm not in ALARM_STATES or alarm == "ok":
        return tokens.rgba("text-muted")
    if alarm == "stale":
        return tokens.rgba("alarm-stale")
    return tokens.rgba(f"alarm-{priority if priority in ALARM_PRIORITIES else 'medium'}")


ALARM_COLORS = {a: alarm_rgba(a) for a in ALARM_STATES}  # ustuvorlik «medium» bo'yicha (testlar, eski chaqiruv)
```

`alarm_colors` tanasidagi `ALARM_COLORS.get(s.get("alarm"), (1.0, 1.0, 1.0, 1.0))` ni almashtiring:

```python
        s["element_guid"]: alarm_rgba(s.get("alarm"), s.get("priority"))
```

- [ ] **Step 5: `HEALTH_COLORS`** (4 qatorli lug'at) ni almashtiring:

```python
HEALTH_COLORS = {  # web MonitoringPanel: yaxshi — ok, qoniqarli — warn, yomon/kritik — danger (P4: tokenlar)
    "yaxshi": tokens.rgba("ok"),
    "qoniqarli": tokens.rgba("warn"),
    "yomon": tokens.rgba("danger"),
    "kritik": tokens.rgba("danger"),
}
```

- [ ] **Step 6: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_pure.py desktop/tests/test_sath_flows.py` → PASS
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test monitor_ops --bonsai` → `[OK] monitor_ops`
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test review_ops --bonsai` → `[OK] review_ops`
Run: `git ls-files --eol desktop/blender/sath/flows.py` → `i/mixed w/mixed`; `git diff --stat desktop/blender/sath/flows.py` — o'nlab qator, butun fayl emas.
Run: `.venv\Scripts\ruff.exe check desktop/blender/sath/flows.py desktop/tests/test_sath_pure.py` → toza

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/flows.py desktop/tests/test_sath_pure.py
git commit -m "feat(UI): 3D diff/alarm/sog'liq ranglari web tokenlaridan — alarm_rgba web alarmHex bilan bir xil (ok kulrang, ustuvorlik rangi)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Ish joylari — `template/Sath/workspaces.py`, template ilgaklari, `sath.reset_workspaces`, `SathPanel` tegi

**Model:** opus — Blender ekran/workspace API nozikliklari (ko'rinmayotgan ekran, kechiktirilgan faollashtirish, msgbus bilan yakunlash, idempotentlik, ochiq ish joyini o'chirmaslik).

**Files:**
- Modify: `desktop/blender/sath/core/registry.py` (`API_VERSION = (1, 0)` qatoridan keyin 2 konstanta)
- Modify: `desktop/blender/sath/core/panels.py` (`in_workspace`, `visible`)
- Create: `desktop/blender/template/Sath/workspaces.py`
- Modify: `desktop/blender/template/Sath/__init__.py` (to'liq qayta yoziladi, LF)
- Modify: `desktop/blender/sath/ui.py` (`SATH_MT_main.draw`)
- Create: `desktop/tests/test_sath_workspaces.py`, `desktop/tests/sath_tests/workspaces.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`$tests` ga `@("workspaces", "")`)

**Interfaces:**
- Consumes: `sath.core.tokens` (Task 1, faqat testlarda), `registry.discover`, `host.record(mod_id).manifest.workspaces`.
- Produces: `registry.WORKSPACE_TAG = "sath_ws"`, `registry.WORKSPACES = ("BIM", "Compare", "Simulation", "SCADA")`; `panels.in_workspace(manifest, workspace) -> bool`; template `workspaces`: `TAG, TODO, ORDER, KEEP, REMOVE, DEV_ONLY, OWNERS, DEFAULT_OWNER_IDS, ISA_GREY, BASE`, `srgb_to_linear(hex)`, `tagged(data) -> {teg: ws}`, `owner_ids(context) -> list[str]`, `ensure(context, *, rebuild=False, activate=True) -> {"created", "removed", "kept"}`, `finish(win) -> bool`; operator `sath.reset_workspaces(rebuild: bool)`. Task 5, 7, 8 ishlatadi.

- [ ] **Step 1: Yiqiluvchi sof test** — `desktop/tests/test_sath_workspaces.py`:

```python
"""Sath ish joylari (P4, spec §5): template/Sath/workspaces.py ma'lumot qismi — teglar reyestr va modul
manifestlariga mos, olib tashlanadiganlar, ISA kulrangi web tokeni, egalar. Blender qismi — headless
`workspaces` va GUI `run_gui_workspaces.py`."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import registry, tokens  # noqa: E402

TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"
MODULES = ROOT / "desktop" / "blender" / "sath" / "modules"


@pytest.fixture(scope="module")
def ws():
    spec = importlib.util.spec_from_file_location("sath_template_workspaces", TEMPLATE / "workspaces.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # bpy siz import bo'lishi shart (bpy faqat funksiyalar ichida)
    return mod


def test_tags_match_registry_and_module_manifests(ws):
    assert ws.TAG == registry.WORKSPACE_TAG and ws.ORDER == registry.WORKSPACES
    manifests, errors = registry.discover(MODULES)
    assert errors == []
    used = {w for m in manifests for w in m.workspaces}
    assert used == set(ws.ORDER), used ^ set(ws.ORDER)  # har ish joyida modul paneli bor, begona teg yo'q


def test_removed_kept_and_dev_only(ws):
    assert set(ws.REMOVE) == {
        "Sculpting", "UV Editing", "Texture Paint", "Shading", "Rendering", "Compositing", "Geometry Nodes",
    }  # fmt: skip
    assert ws.DEV_ONLY == ("Scripting",) and "Scripting" in ws.KEEP
    assert not set(ws.REMOVE) & set(ws.KEEP) and not set(ws.ORDER) & (set(ws.KEEP) | set(ws.REMOVE))
    assert ws.BASE in ws.KEEP


def test_scada_grey_is_web_operator_canvas(ws):
    assert ws.ISA_GREY == tokens.THEMES["operator"]["canvas"]
    assert ws.srgb_to_linear(ws.ISA_GREY) == pytest.approx(tokens.rgba("canvas", "operator")[:3])


def test_owner_ids_from_enabled_addons_plus_bundle_defaults(ws):
    addons = {"bl_ext.blender_org.bonsai": 1, "bl_ext.user_default.sath": 1, "boshqa_addon": 1}
    ctx = SimpleNamespace(preferences=SimpleNamespace(addons=addons))
    assert ws.owner_ids(ctx) == [
        "bl_ext.blender_org.bonsai", "bl_ext.user_default.bonsai", "bl_ext.user_default.sath",
    ]  # fmt: skip
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_workspaces.py`
Expected: FAIL (`FileNotFoundError` … `workspaces.py` / `AttributeError: … WORKSPACE_TAG`).

- [ ] **Step 2: `core/registry.py`** — `API_VERSION = (1, 0)` qatoridan keyin:

```python
WORKSPACE_TAG = "sath_ws"  # app template ish joyi tegi: ws["sath_ws"] (template/Sath/workspaces.py)
WORKSPACES = ("BIM", "Compare", "Simulation", "SCADA")  # Sath ish joylari = manifest `workspaces` qiymatlari
```

- [ ] **Step 3: `core/panels.py`** — import qatoriga `from .registry import WORKSPACE_TAG` qo'shing; `visible` dan oldin:

```python
def in_workspace(manifest, workspace) -> bool:
    """Modul paneli shu ish joyida ko'rinadimi: tegi (ws["sath_ws"], app template qo'yadi) manifest
    `workspaces` ida bo'lsa. Tegsiz ish joyi (Layout, Modeling …) yoki `workspaces` bo'sh modul — hamma joyda."""
    tag = workspace.get(WORKSPACE_TAG) if workspace is not None else None
    return not tag or not manifest.workspaces or tag in manifest.workspaces
```

`visible` ichidagi 4 qatorni (`ws = getattr(...)` … `return False`, izoh bilan) almashtiring:

```python
        if not in_workspace(m, getattr(context, "workspace", None)):
            return False
```

- [ ] **Step 4: `desktop/blender/template/Sath/workspaces.py`** (yangi, LF):

```python
"""Sath ish joylari (spec §5): BIM, Compare, Simulation, SCADA. App template ning load_factory_startup_post
ilgagida va `sath.reset_workspaces` operatorida idempotent quriladi (bor bo'lsa qayta yaratilmaydi).

* Har Sath ish joyi `ws["sath_ws"] = <teg>` bilan belgilanadi — addondagi SathPanel tegni modul manifestidagi
  `workspaces` bilan solishtiradi (tegsiz ish joyi — hamma panel). Nomi o'zgartirilsa ham teg qoladi.
* Blender ning Sculpting, UV Editing, Texture Paint, Shading, Rendering, Compositing, Geometry Nodes ish
  joylari olib tashlanadi; Scripting — faqat Preferences → Interface → Developer Extras yoqiq bo'lsa qoladi.
* Sath ish joylarida faqat Sath va Bonsai interfeysi (use_filter_by_owner); boshqa addonlar — Layout/Modeling.
* Blender ko'rinmayotgan ekranda area turini almashtirmaydi (rna_Area_type_update faqat oynadagi ekranda):
  Simulation dagi Graph editor ish joyi birinchi ochilganda finish() da (belgi `ws["sath_ws_todo"]`,
  template __init__ dagi msgbus obunasi).

bpy faqat funksiyalar ichida — pytest modulni Blender siz yuklaydi."""

from __future__ import annotations

TAG = "sath_ws"  # = sath.core.registry.WORKSPACE_TAG (test_sath_workspaces tekshiradi)
TODO = "sath_ws_todo"  # ish joyi ko'ringanda yakunlanadigan qadam bor
ORDER = ("BIM", "Compare", "Simulation", "SCADA")  # = registry.WORKSPACES; tab tartibi, keyin KEEP
KEEP = ("Layout", "Modeling", "Animation", "Scripting")
REMOVE = ("Sculpting", "UV Editing", "Texture Paint", "Shading", "Rendering", "Compositing", "Geometry Nodes")
DEV_ONLY = ("Scripting",)
OWNERS = ("sath", "bonsai")  # addon modul nomining oxirgi qismi: bl_ext.<repo>.sath / .bonsai
DEFAULT_OWNER_IDS = ("bl_ext.user_default.bonsai", "bl_ext.user_default.sath")  # bundle dagi nomlar
ISA_GREY = "#dcdddf"  # web tokens.ts operator.canvas — ISA-101 neytral kulrang (test tokens.py bilan solishtiradi)
BASE = "Layout"


def srgb_to_linear(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2])


def tagged(data) -> dict:
    """{teg: ish joyi} — har tegdan birinchisi."""
    out: dict = {}
    for ws in data.workspaces:
        tag = ws.get(TAG)
        if tag in ORDER and tag not in out:
            out[tag] = ws
    return out


def owner_ids(context) -> list[str]:
    names = {n for n in context.preferences.addons.keys() if n.rpartition(".")[2] in OWNERS}
    return sorted(names | set(DEFAULT_OWNER_IDS))


def _areas(screen, kind: str) -> list:
    return [a for a in screen.areas if a.type == kind]


def _split(context, win, screen, area, direction: str, factor: float):
    """area ni bo'ladi (ko'rinmayotgan ekranda ham ishlaydi); yangi area ni qaytaradi (gorizontalda — pastki)."""
    import bpy

    before = {a.as_pointer() for a in screen.areas}
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=win, screen=screen, area=area, region=region):
        bpy.ops.screen.area_split(direction=direction, factor=factor)
    return next((a for a in screen.areas if a.as_pointer() not in before), None)


def _bim(context, win, ws) -> None:
    """Outliner + Properties (Layout dan) + 3D, N-panel ochiq («Sath» yorlig'i: GES obyektlari, Import …)."""
    for a in _areas(ws.screens[0], "VIEW_3D"):
        a.spaces.active.show_region_ui = True


def _compare(context, win, ws) -> None:
    """Ikki 3D ko'rinish yonma-yon (sinxronlash va farq ro'yxati — 3-quyi-loyiha)."""
    screen = ws.screens[0]
    _split(context, win, screen, _areas(screen, "VIEW_3D")[0], "VERTICAL", 0.5)


def _simulation(context, win, ws) -> None:
    """Timeline (Layout dan) + 3D + Graph editor (pastki 35 %; turi ish joyi ko'ringanda — finish)."""
    screen = ws.screens[0]
    if _split(context, win, screen, _areas(screen, "VIEW_3D")[0], "HORIZONTAL", 0.35) is not None:
        ws[TODO] = 1


def _scada(context, win, ws) -> None:
    """ISA-101: neytral kulrang fon, obyekt rangi (alarm/sog'liq ranglari faqat anomaliyada)."""
    for a in _areas(ws.screens[0], "VIEW_3D"):
        sh = a.spaces.active.shading
        sh.type = "SOLID"
        sh.color_type = "OBJECT"
        sh.background_type = "VIEWPORT"
        sh.background_color = srgb_to_linear(ISA_GREY)


BUILDERS = {"BIM": _bim, "Compare": _compare, "Simulation": _simulation, "SCADA": _scada}


def _base(data):
    ws = data.workspaces.get(BASE)
    if ws is not None and ws.get(TAG) is None:
        return ws
    return next(
        (w for w in data.workspaces if w.get(TAG) is None and w.screens and _areas(w.screens[0], "VIEW_3D")),
        None,
    )


def ensure(context, *, rebuild: bool = False, activate: bool = True) -> dict:
    """Yo'q Sath ish joylarini yaratadi, Blender ish joylarini olib tashlaydi, egasi filtri va tab tartibi,
    BIM ni faollashtiradi (GUI da keyingi siklda). rebuild — teglilarni o'chirib qayta quradi (oynada ochig'i
    saqlanadi). Hech qachon oynada ochiq ish joyini o'chirmaydi."""
    import bpy

    data = bpy.data
    wm = context.window_manager
    win = context.window or (wm.windows[0] if wm is not None and wm.windows else None)
    report: dict[str, list[str]] = {"created": [], "removed": [], "kept": []}
    if win is None:
        return report
    in_use = {w.workspace.as_pointer() for w in wm.windows}
    have = tagged(data)
    if rebuild:
        old = [ws for ws in have.values() if ws.as_pointer() not in in_use]
        report["kept"] = [t for t, ws in have.items() if ws.as_pointer() in in_use]
        if old:
            data.batch_remove(ids=old)
        have = tagged(data)
    base = _base(data)
    for tag in ORDER:
        if tag in have or base is None:
            continue
        ws = base.copy()
        ws.name = tag
        ws[TAG] = tag
        if TODO in ws:
            del ws[TODO]
        BUILDERS[tag](context, win, ws)
        have[tag] = ws
        report["created"].append(tag)
    ids = owner_ids(context)
    for ws in have.values():
        ws.use_filter_by_owner = True
        cur = {o.name for o in ws.owner_ids}
        for n in ids:
            if n not in cur:
                ws.owner_ids.new(n)
    names = REMOVE + (() if context.preferences.view.show_developer_ui else DEV_ONLY)
    drop = [
        w for w in data.workspaces
        if w.name in names and w.get(TAG) is None and w.as_pointer() not in in_use
    ]  # fmt: skip
    if drop:
        report["removed"] = sorted(w.name for w in drop)
        data.batch_remove(ids=drop)
    order = [have[t] for t in ORDER if t in have] + [data.workspaces[n] for n in KEEP if n in data.workspaces]
    for ws in reversed(order):
        with context.temp_override(window=win, workspace=ws):
            bpy.ops.workspace.reorder_to_front()  # {'INTERFACE'} qaytaradi — bu normal
    if activate and "BIM" in have:
        win.workspace = have["BIM"]
    return report


def finish(win) -> bool:
    """Oynada ko'rinayotgan ish joyining kechiktirilgan qadamini bajaradi (msgbus: Window.workspace).
    True — o'zgardi. Area turi faqat ko'rinayotgan ekranda almashadi, shuning uchun aynan shu yerda."""
    ws = win.workspace
    if ws is None or not ws.get(TODO):
        return False
    if ws.get(TAG) == "Simulation":
        v = _areas(win.screen, "VIEW_3D")
        if len(v) >= 2:
            min(v, key=lambda a: a.y).ui_type = "FCURVES"  # pastki (split dagi yangi) area → Graph editor
        if not _areas(win.screen, "GRAPH_EDITOR"):
            return False  # hali qo'llanmadi — keyingi o'tishda yana urinadi
    del ws[TODO]
    return True
```

- [ ] **Step 5: `desktop/blender/template/Sath/__init__.py`** (to'liq, LF):

```python
"""Sath app template: Blender ochilganda GES-BIM ish muhiti — Sath ish joylari (BIM faol; workspaces.py),
N-panel ochiq (Sath yorlig'i), viewport Object-color rejimi (diff/alarm ranglari uchun), metr birliklari,
«Standard» view transform (3D ranglar web tokenlari bilan bir xil ko'rinsin)."""

import bpy
from bpy.app.handlers import persistent

from . import workspaces

_MSGBUS = object()  # msgbus obunasi egasi


def _setup_screens():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.show_region_ui = True
                space.shading.color_type = "OBJECT"
                space.overlay.show_relationship_lines = False


def _setup_scenes():
    for scene in bpy.data.scenes:
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.length_unit = "METERS"
        scene.unit_settings.scale_length = 1.0
        scene.view_settings.view_transform = "Standard"  # tokens.py ranglari (sRGB) web dagidek, AgX emas


def _on_workspace(*_args):
    wm = bpy.context.window_manager
    for win in getattr(wm, "windows", ()):
        workspaces.finish(win)


def _subscribe():
    bpy.msgbus.clear_by_owner(_MSGBUS)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Window, "workspace"), owner=_MSGBUS, args=(), notify=_on_workspace)


@persistent
def load_handler(_):
    _setup_screens()
    _setup_scenes()
    rep = workspaces.ensure(bpy.context)
    if rep["created"] or rep["removed"]:
        print("[sath] ish joylari:", rep, flush=True)


@persistent
def resubscribe(_):
    _subscribe()  # fayl yuklanganda msgbus obunalari tozalanadi


class SATH_OT_reset_workspaces(bpy.types.Operator):
    """Sath ish joylarini (BIM, Compare, Simulation, SCADA) tiklash va keraksiz Blender ish joylarini olib
    tashlash"""

    bl_idname = "sath.reset_workspaces"
    bl_label = "Ish joylarini tiklash"
    bl_options = {"REGISTER"}

    rebuild: bpy.props.BoolProperty(
        name="Qaytadan qurish",
        description="Mavjud Sath ish joylarini o'chirib yangidan yaratish (hozir ochiq ish joyi saqlanadi)",
        default=False,
    )

    def execute(self, context):
        rep = workspaces.ensure(context, rebuild=self.rebuild)
        parts = []
        if rep["created"]:
            parts.append("yaratildi: " + ", ".join(rep["created"]))
        if rep["removed"]:
            parts.append("olib tashlandi: " + ", ".join(rep["removed"]))
        if rep["kept"]:
            parts.append("ochiq bo'lgani uchun saqlandi: " + ", ".join(rep["kept"]))
        self.report({"INFO"}, "Ish joylari: " + ("; ".join(parts) or "o'zgarish yo'q"))
        return {"FINISHED"}


_HANDLERS = (
    (bpy.app.handlers.load_factory_startup_post, load_handler),
    (bpy.app.handlers.load_post, resubscribe),
)


def register():
    bpy.utils.register_class(SATH_OT_reset_workspaces)
    for lst, fn in _HANDLERS:
        if fn not in lst:
            lst.append(fn)
    _subscribe()


def unregister():
    bpy.msgbus.clear_by_owner(_MSGBUS)
    for lst, fn in _HANDLERS:
        if fn in lst:
            lst.remove(fn)
    bpy.utils.unregister_class(SATH_OT_reset_workspaces)
```

- [ ] **Step 6: `ui.py`** — `SATH_MT_main.draw` da `lay.operator("sath.notifications")` qatoridan keyin:

```python
        if hasattr(bpy.types, "SATH_OT_reset_workspaces"):  # Sath app template (bundle) faol bo'lsa
            lay.operator("sath.reset_workspaces", icon="WORKSPACE")
```

- [ ] **Step 7: Sof testlar**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_workspaces.py` → `4 passed`

- [ ] **Step 8: Headless test** — `desktop/tests/sath_tests/workspaces.py`:

```python
"""P4 ish joylari (headless): Sath app template (repo dan) factory startup da ish joylarini quradi — teglar,
olib tashlanganlar, Scripting faqat developer UI da, egasi filtri, area lar; qayta chaqirish idempotent,
`sath.reset_workspaces(rebuild=True)` qayta quradi; SathPanel tegi modul manifestiga mos; theme_sath.xml
qo'llanadi. Oynali qism (BIM faol, Graph editor yakunlanishi) — desktop/tests/run_gui_workspaces.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"


def _template():
    """App template paketi (Blender uni bl_app_templates_* dan yuklaydi; bu yerda — repo dan)."""
    name = "sath_app_template"
    spec = importlib.util.spec_from_file_location(
        name, TEMPLATE / "__init__.py", submodule_search_locations=[str(TEMPLATE)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _areas(ws, kind: str) -> list:
    return [a for a in ws.screens[0].areas if a.type == kind]


def _check(W, *, dev: bool) -> dict:
    names = {w.name for w in bpy.data.workspaces}
    tags = W.tagged(bpy.data)
    assert sorted(tags) == sorted(W.ORDER), sorted(tags)
    assert sum(1 for w in bpy.data.workspaces if w.get(W.TAG)) == len(W.ORDER), "teg takrorlandi"
    assert not names & set(W.REMOVE), sorted(names & set(W.REMOVE))
    assert ("Scripting" in names) is dev, (dev, sorted(names))
    assert {"Layout", "Modeling", "Animation"} <= names, sorted(names)
    for t, ws in tags.items():
        owners = {o.name for o in ws.owner_ids}
        assert ws.use_filter_by_owner and set(W.DEFAULT_OWNER_IDS) <= owners, (t, owners)
    assert _areas(tags["BIM"], "OUTLINER") and _areas(tags["BIM"], "PROPERTIES")
    assert all(a.spaces.active.show_region_ui for a in _areas(tags["BIM"], "VIEW_3D"))
    assert len(_areas(tags["Compare"], "VIEW_3D")) == 2
    sim = tags["Simulation"]
    assert any(a.ui_type == "TIMELINE" for a in sim.screens[0].areas)
    assert len(_areas(sim, "VIEW_3D")) == 2 and sim.get(W.TODO) == 1  # Graph — ish joyi ochilganda (GUI)
    sh = _areas(tags["SCADA"], "VIEW_3D")[0].spaces.active.shading
    assert sh.color_type == "OBJECT" and sh.background_type == "VIEWPORT"
    grey = W.srgb_to_linear(W.ISA_GREY)
    assert all(abs(x - y) < 1e-4 for x, y in zip(sh.background_color, grey, strict=True))
    return tags


def run(ctx):
    from sath.core import host, panels, tokens

    tpl = _template()
    W = tpl.workspaces
    view = bpy.context.preferences.view
    dev0 = view.show_developer_ui
    tpl.register()
    try:
        view.show_developer_ui = False
        bpy.ops.wm.read_homefile(use_factory_startup=True)  # load_factory_startup_post → template ilgagi
        _check(W, dev=False)
        assert bpy.context.scene.view_settings.view_transform == "Standard"
        rep = W.ensure(bpy.context)
        assert rep == {"created": [], "removed": [], "kept": []}, rep  # idempotent
        assert bpy.ops.sath.reset_workspaces(rebuild=True) == {"FINISHED"}
        tags = _check(W, dev=False)

        rec = {m: host.record(m).manifest for m in ("bim", "scada", "sim", "twin", "review", "io")}
        assert panels.in_workspace(rec["bim"], tags["BIM"])
        assert not panels.in_workspace(rec["bim"], tags["SCADA"])
        assert panels.in_workspace(rec["scada"], tags["SCADA"])
        assert not panels.in_workspace(rec["scada"], tags["BIM"])
        assert panels.in_workspace(rec["sim"], tags["Simulation"])
        assert panels.in_workspace(rec["twin"], tags["Simulation"])
        assert panels.in_workspace(rec["review"], tags["Compare"])
        assert not panels.in_workspace(rec["io"], tags["Compare"])
        layout = bpy.data.workspaces["Layout"]
        assert all(panels.in_workspace(m, layout) for m in rec.values())  # tegsiz — hammasi

        view.show_developer_ui = True
        bpy.ops.wm.read_homefile(use_factory_startup=True)
        _check(W, dev=True)

        theme = bpy.context.preferences.themes[0]
        r = bpy.ops.script.execute_preset(
            filepath=str(TEMPLATE / "theme_sath.xml"), menu_idname="USERPREF_MT_interface_theme_presets"
        )
        assert r == {"FINISHED"}, r
        for got, hex_ in (
            (theme.view_3d.object_active, tokens.PAL["highlight"]),
            (theme.user_interface.axis_x, tokens.PAL["axisX"]),
        ):
            want = tokens.parse(hex_)[:3]
            assert all(abs(a - b) < 1 / 255 for a, b in zip(got, want, strict=True)), (tuple(got), hex_)
    finally:
        bpy.ops.preferences.reset_default_theme()
        view.show_developer_ui = dev0
        tpl.unregister()
    assert not hasattr(bpy.types, "SATH_OT_reset_workspaces")
    assert tpl.load_handler not in bpy.app.handlers.load_factory_startup_post
```

`run_blender_tests.ps1` — `$tests` ro'yxatida `@("undo_ifc", "--bonsai")` dan keyin: `, @("workspaces", "")`.

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test workspaces`
Expected: `[OK] workspaces` (chiqishda `Not freed memory blocks` qatori bo'lishi mumkin — zararsiz, Global Constraints).

- [ ] **Step 9: Regressiya**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai` → `[OK] modules` (`visible` refaktori)
Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests` → PASS
Run: `.venv\Scripts\ruff.exe check desktop` → toza
Run: `git ls-files --eol desktop/blender/template/Sath/__init__.py desktop/blender/sath/ui.py desktop/blender/sath/core/panels.py` → `i/lf w/lf`

- [ ] **Step 10: Commit**

```bash
git add desktop/blender/sath/core/registry.py desktop/blender/sath/core/panels.py desktop/blender/template/Sath/workspaces.py desktop/blender/template/Sath/__init__.py desktop/blender/sath/ui.py desktop/tests/test_sath_workspaces.py desktop/tests/sath_tests/workspaces.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(UI): Sath ish joylari — BIM/Compare/Simulation/SCADA (teg, egasi filtri), Blender ish joylari olib tashlanadi, sath.reset_workspaces, Graph editor msgbus bilan yakunlanadi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Keymap — `core/keys.py`, Ctrl+Shift+G «Object Mode» da ham, headless to'qnashuv testi

**Model:** sonnet — sof algoritm + Blender keymap ma'lumotlari; to'qnashuv qoidalarini to'g'ri qo'llash.

**Files:**
- Create: `desktop/blender/sath/core/keys.py`
- Modify: `desktop/blender/sath/ui.py` (`_keymaps`, `_register_keymap`, `unregister`), `desktop/blender/sath/api.py` (`ui.keymap`)
- Create: `desktop/tests/test_sath_keys.py`, `desktop/tests/sath_tests/keymap.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`@("keymap", "--bonsai")`)

**Interfaces:**
- Produces: `keys.ITEMS: list[(egasi, km, kmi)]`; `keys.add(owner, idname, key, *, km_name="3D View", space_type="VIEW_3D", ctrl=False, shift=False, alt=False, **properties) -> (kmi | None, off)`; `keys.Chord` (NamedTuple: `keymap, type, value, ctrl, shift, alt, oskey, idname, owner, menu`; modifikator `-1` — ixtiyoriy); `keys.chord(kmi, keymap, owner)`, `keys.chord_from_event(keymap, idname, event: dict, props: dict | None, owner="blender")`, `keys.overlaps(a, b)`, `keys.scope(keymap)`, `keys.conflicts(ours, others, allowed=None) -> list[str]`; `keys.VIEW3D_KEYMAPS`, `keys.ALLOWED: {(keymap, idname): sabab}`. `api.ui.keymap` imzosi o'zgarmaydi (endi `keys.add` orqali, `REG.owner` tekshiruvi bilan).

- [ ] **Step 1: Yiqiluvchi sof test** — `desktop/tests/test_sath_keys.py`:

```python
"""core/keys.py (P4, spec §5): yorliqlar to'qnashuvi qoidalari — bpy siz."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import keys  # noqa: E402
from sath.core.keys import Chord  # noqa: E402


def C(keymap, type_, ctrl=0, shift=0, alt=0, idname="x.op", owner="blender", value="PRESS", menu=""):
    return Chord(keymap, type_, value, ctrl, shift, alt, 0, idname, owner, menu)


SATH = C("3D View", "G", 1, 1, idname="wm.call_menu", owner="sath:core", menu="SATH_MT_main")


def test_overlap_rules():
    assert keys.overlaps(SATH, C("Object Mode", "G", 1, 1))
    assert not keys.overlaps(SATH, C("Object Mode", "G", 1, 0))
    assert keys.overlaps(SATH, C("3D View", "G", -1, -1, -1))  # «any» modifikator
    assert not keys.overlaps(SATH, C("3D View", "G", 1, 1, value="RELEASE"))
    assert keys.overlaps(SATH, C("3D View", "G", 1, 1, value="CLICK"))


def test_conflicts_scope_allowed_and_own_duplicates():
    other = [
        C("Object Mode", "G", 1, 1, idname="collection.objects_add_active"),  # ALLOWED
        C("Node Editor", "G", 1, 1, idname="node.select_grouped"),  # 3D ko'rinishda emas
        C("Window", "N", 1, idname="wm.call_menu", owner="addon", menu="X"),  # boshqa chord
    ]
    ours = [SATH, SATH._replace(keymap="Object Mode")]  # bir xil menyu ikki keymapda — to'qnashuv emas
    assert keys.conflicts(ours, other) == []
    bad = keys.conflicts(ours, other, allowed={})
    assert len(bad) == 2 and all("collection.objects_add_active" in b for b in bad)
    clash = C("Mesh", "G", 1, 1, idname="mesh.yangi")
    assert len(keys.conflicts([SATH], [clash])) == 1  # rejim keymapi 3D View dan oldin ishlaydi
    twin = C("3D View", "G", 1, 1, idname="sath.boshqa", owner="sath:twin")
    assert any("sath.boshqa" in b for b in keys.conflicts([SATH, twin], []))  # Sath ichida


def test_scope_for_non_3d_keymaps_is_own_plus_global():
    assert keys.scope("Outliner") == frozenset({"Outliner", "Window", "Screen"})
    assert "Object Mode" in keys.scope("3D View")


def test_chord_from_blender_default_event_and_kmi():
    c = keys.chord_from_event(
        "Object Mode", "wm.call_menu", {"type": "G", "value": "PRESS", "ctrl": True, "shift": True},
        {"properties": [("name", "VIEW3D_MT_x")]},
    )
    assert (c.ctrl, c.shift, c.alt, c.menu) == (1, 1, 0, "VIEW3D_MT_x")
    ev = {"type": "TIMER1", "value": "ANY", "any": True}
    anyc = keys.chord_from_event("3D View", "view3d.smoothview", ev, None)
    assert (anyc.ctrl, anyc.shift, anyc.alt, anyc.oskey) == (-1, -1, -1, -1)
    kmi = SimpleNamespace(type="G", value="PRESS", ctrl=1, shift=1, alt=0, oskey=0, any=False,
                          idname="wm.call_menu", properties=SimpleNamespace(name="SATH_MT_main"))  # fmt: skip
    assert keys.chord(kmi, "3D View", "sath:core") == SATH
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_keys.py`
Expected: FAIL (`ImportError: cannot import name 'keys'`).

- [ ] **Step 2: `desktop/blender/sath/core/keys.py`**

```python
"""Sath klaviatura yorliqlari (spec §5). Yadro (ui.py: Ctrl+Shift+G → «Sath» menyusi) va modullar
(api.ui.keymap) shu modul orqali qo'shadi — ITEMS ro'yxati bo'yicha headless `keymap` sinovi Blender standart
keymapi va Bonsai yorliqlari bilan to'qnashuvni tekshiradi. conflicts() va boshqalar — bpy siz (pytest)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NamedTuple


class Chord(NamedTuple):
    keymap: str
    type: str
    value: str
    ctrl: int  # 0 | 1 | -1 (ixtiyoriy — Blender KM_ANY)
    shift: int
    alt: int
    oskey: int
    idname: str
    owner: str  # "sath:<egasi>" | "blender" | "addon"
    menu: str = ""  # wm.call_menu / call_panel nomi


# 3D ko'rinishda bir vaqtda ishlaydigan keymaplar. Rejim keymaplari («Object Mode», «Mesh» …) «3D View» dan
# OLDIN ishlov beradi — shu yerdagi bir xil chord Sath yorlig'ini yopadi (yoki aksincha).
VIEW3D_KEYMAPS = frozenset({
    "Window", "Screen", "Frames", "User Interface", "3D View Generic", "3D View", "Object Mode",
    "Object Non-modal", "Mesh", "Curve", "Curves", "Armature", "Pose", "Metaball", "Lattice", "Font",
    "Point Cloud", "Particle", "Sculpt", "Weight Paint", "Vertex Paint", "Image Paint", "Grease Pencil",
    "Grease Pencil Edit Mode",
})  # fmt: skip
GLOBAL_KEYMAPS = frozenset({"Window", "Screen"})
# Ataylab ustun qo'yilgan: (keymap, boshqa amal) → sabab. Addon elementi o'sha keymap boshiga qo'shiladi.
ALLOWED = {
    ("Object Mode", "collection.objects_add_active"): (
        "Ctrl+Shift+G — Sath menyusi (spec §5: saqlanadi); «faol obyektni kolleksiyaga qo'shish» "
        "Object → Collection menyusida qoladi"
    ),
}
_VALUES = frozenset({"PRESS", "CLICK", "ANY"})  # bir bosishda birga ishlaydigan qiymatlar
_CALLS = frozenset({"wm.call_menu", "wm.call_menu_pie", "wm.call_panel"})
ITEMS: list[tuple[str, object, object]] = []  # (egasi, keymap, keymap_item) — faol Sath yorliqlari


def add(owner: str, idname: str, key: str, *, km_name: str = "3D View", space_type: str = "VIEW_3D",
        ctrl: bool = False, shift: bool = False, alt: bool = False,
        **properties) -> tuple[object | None, Callable[[], None]]:  # fmt: skip
    """Addon keyconfig ga yorliq; qaytaradi (kmi, off). Keyconfig yo'q bo'lsa — (None, hech narsa)."""
    import bpy

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return None, lambda: None
    km = kc.keymaps.new(name=km_name, space_type=space_type)
    kmi = km.keymap_items.new(idname, key, "PRESS", ctrl=ctrl, shift=shift, alt=alt)
    for k, v in properties.items():
        setattr(kmi.properties, k, v)
    entry = (owner, km, kmi)
    ITEMS.append(entry)

    def off() -> None:
        for i, e in enumerate(ITEMS):
            if e is entry:
                del ITEMS[i]
                km.keymap_items.remove(kmi)
                return

    return kmi, off


def chord(kmi, keymap: str, owner: str) -> Chord:
    any_ = bool(getattr(kmi, "any", False))

    def m(v) -> int:
        return -1 if any_ else int(v)

    menu = getattr(kmi.properties, "name", "") if kmi.idname in _CALLS else ""
    return Chord(keymap, kmi.type, kmi.value, m(kmi.ctrl), m(kmi.shift), m(kmi.alt), m(kmi.oskey),
                 kmi.idname, owner, menu)  # fmt: skip


def chord_from_event(keymap: str, idname: str, event: dict, props: dict | None,
                     owner: str = "blender") -> Chord:  # fmt: skip
    """blender_default.generate_keymaps() elementi (idname, event, props) → Chord."""
    any_ = bool(event.get("any"))

    def m(k: str) -> int:
        v = event.get(k)
        return -1 if any_ or v == -1 else int(bool(v))

    menu = ""
    if props and idname in _CALLS:
        menu = dict(props.get("properties", ())).get("name", "")
    return Chord(keymap, event["type"], event.get("value", "PRESS"), m("ctrl"), m("shift"), m("alt"),
                 m("oskey"), idname, owner, menu)  # fmt: skip


def _mod(a: int, b: int) -> bool:
    return a == b or a == -1 or b == -1


def overlaps(a: Chord, b: Chord) -> bool:
    return (
        a.type == b.type and a.value in _VALUES and b.value in _VALUES
        and _mod(a.ctrl, b.ctrl) and _mod(a.shift, b.shift) and _mod(a.alt, b.alt) and _mod(a.oskey, b.oskey)
    )  # fmt: skip


def scope(keymap: str) -> frozenset[str]:
    return VIEW3D_KEYMAPS if keymap in VIEW3D_KEYMAPS else GLOBAL_KEYMAPS | {keymap}


def text(c: Chord) -> str:
    mods = [n for n, v in (("Ctrl", c.ctrl), ("Shift", c.shift), ("Alt", c.alt), ("OS", c.oskey)) if v == 1]
    return "+".join([*mods, c.type])


def _label(c: Chord) -> str:
    return f"{c.owner} «{c.keymap}» {text(c)} {c.idname}" + (f" ({c.menu})" if c.menu else "")


def conflicts(ours: Iterable[Chord], others: Iterable[Chord], allowed: dict | None = None) -> list[str]:
    """Sath yorliqlari to'qnashuvlari (bo'sh — yaxshi): boshqalar bilan (Sath yorlig'i keymapining ta'sir
    doirasida) va Sath ichida (turli amal — bir chord). allowed — ataylab ustun qo'yilganlar."""
    allowed = ALLOWED if allowed is None else allowed
    ours, others = list(ours), list(others)
    out = []
    for s in ours:
        sc = scope(s.keymap)
        for o in others:
            if o.keymap in sc and overlaps(s, o) and (o.keymap, o.idname) not in allowed:
                out.append(f"{_label(s)}  <->  {_label(o)}")
    for i, a in enumerate(ours):
        for b in ours[i + 1 :]:
            if b.keymap in scope(a.keymap) and overlaps(a, b) and (a.idname, a.menu) != (b.idname, b.menu):
                out.append(f"{_label(a)}  <->  {_label(b)}")
    return out
```

- [ ] **Step 3: `ui.py`** — importni `from .core import host, keys, perms` qiling; `_keymaps: list = []` va `_register_keymap` ni almashtiring:

```python
_keymap_offs: list = []


def _register_keymap():
    """Ctrl+Shift+G → «Sath» menyusi: «3D View» va «Object Mode» da. Rejim keymapi 3D View dan oldin ishlaydi,
    u yerdagi standart collection.objects_add_active ni ataylab yopamiz (core/keys.ALLOWED)."""
    for km_name, space in (("3D View", "VIEW_3D"), ("Object Mode", "EMPTY")):
        _kmi, off = keys.add("core", "wm.call_menu", "G", km_name=km_name, space_type=space,
                             ctrl=True, shift=True, name="SATH_MT_main")  # fmt: skip
        _keymap_offs.append(off)
```

`unregister` dagi 3 qatorni (`for km, kmi in _keymaps:` … `_keymaps.clear()`) almashtiring:

```python
    for off in reversed(_keymap_offs):
        off()
    _keymap_offs.clear()
```

- [ ] **Step 4: `api.py`** — `from .core import keys as _keys` importi; `ui.keymap` tanasini almashtiring (imzo o'zgarmaydi):

```python
        _main_thread()
        _host.REG.owner(mod_id)
        kmi, off = _keys.add(mod_id, idname, key, km_name=km_name, space_type=space_type,
                             ctrl=ctrl, shift=shift, alt=alt, **properties)  # fmt: skip
        if kmi is not None:
            _host.REG.add_cleanup(mod_id, off)
        return kmi
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_keys.py` → `4 passed`

- [ ] **Step 5: Headless test** — `desktop/tests/sath_tests/keymap.py`:

```python
"""P4 keymap (headless, --bonsai): Sath yorliqlari (Ctrl+Shift+G, modullar api.ui.keymap) Blender standart
keymapi (blender_default.py dan generatsiya — fon rejimida standart keymaplar bo'sh) va Bonsai/addon
yorliqlari bilan to'qnashmaydi (ataylab ustun qo'yilganlar — core/keys.ALLOWED); addon o'chirilganda
yorliqlar qaytadi, qayta yoqilganda takrorlanmaydi."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy


def _blender_default() -> list:
    path = Path(bpy.utils.system_resource("SCRIPTS")) / "presets" / "keyconfig" / "keymap_data"
    spec = importlib.util.spec_from_file_location("sath_kc_blender_default", path / "blender_default.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate_keymaps(mod.Params())


def _menu_items(kc) -> list:
    return [
        k for km in kc.keymaps for k in km.keymap_items
        if k.idname == "wm.call_menu" and getattr(k.properties, "name", "") == "SATH_MT_main"
    ]  # fmt: skip


def run(ctx):
    from sath.core import keys

    assert "bl_ext.user_default.bonsai" in bpy.context.preferences.addons, "Bonsai yoqilmagan (--bonsai)"
    kc = bpy.context.window_manager.keyconfigs.addon
    ours = [keys.chord(kmi, km.name, f"sath:{owner}") for owner, km, kmi in keys.ITEMS]
    menu = [c for c in ours if c.menu == "SATH_MT_main"]
    assert {c.keymap for c in menu} == {"3D View", "Object Mode"}, ours
    assert all((c.type, c.ctrl, c.shift, c.alt) == ("G", 1, 1, 0) for c in menu)  # spec §5: Ctrl+Shift+G
    mine = {kmi.as_pointer() for _o, _km, kmi in keys.ITEMS}
    addon = [
        keys.chord(k, km.name, "addon") for km in kc.keymaps for k in km.keymap_items
        if k.active and k.as_pointer() not in mine
    ]  # fmt: skip
    default = [
        keys.chord_from_event(name, idn, ev, props)
        for name, _args, data in _blender_default() for idn, ev, props in data["items"]
        if not (props and props.get("active") is False)
    ]  # fmt: skip
    assert len(default) > 1000, len(default)  # standart keymap haqiqatan o'qildi (sinov bo'sh emas)
    bad = keys.conflicts(ours, default + addon)
    assert not bad, "to'qnashuvlar:\n" + "\n".join(bad)
    stale = [k for k in keys.ALLOWED if not any(
        (c.keymap, c.idname) == k and any(keys.overlaps(s, c) for s in ours) for c in default + addon)]
    assert not stale, f"keys.ALLOWED eskirgan: {stale}"
    for (km_name, idn), why in keys.ALLOWED.items():
        print(f"keymap: ataylab ustun — «{km_name}» {idn}: {why}", flush=True)

    addon_pkg = ctx["addon"]
    addon_pkg.unregister()
    try:
        assert keys.ITEMS == [], keys.ITEMS
        assert not _menu_items(kc), "addon o'chirilgandan keyin Sath yorlig'i qoldi"
    finally:
        addon_pkg.register()
    assert len(_menu_items(kc)) == 2  # qayta yoqilganda takrorlanmaydi
```

`run_blender_tests.ps1` — `$tests` ga `, @("keymap", "--bonsai")`.

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test keymap --bonsai`
Expected: `keymap: ataylab ustun — «Object Mode» collection.objects_add_active: …` va `[OK] keymap`. Agar `to'qnashuvlar:` chiqsa — yangi to'qnashuvni ALLOWED ga **qo'shmang**, hisobot bering (qaror foydalanuvchi bilan).

- [ ] **Step 6: Regressiya va lint**

Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test smoke` → `[OK] smoke`
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test modules --bonsai` → `[OK] modules`
Run: `.venv\Scripts\ruff.exe check desktop` → toza; `git ls-files --eol desktop/blender/sath/ui.py desktop/blender/sath/api.py` → `i/lf w/lf`

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/sath/core/keys.py desktop/blender/sath/ui.py desktop/blender/sath/api.py desktop/tests/test_sath_keys.py desktop/tests/sath_tests/keymap.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(UI): keymap — core/keys.py (Sath yorliqlari ro'yxati, to'qnashuv qoidalari), Ctrl+Shift+G Object Mode da ham; headless to'qnashuv testi (Blender standart + Bonsai)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Oynali tekshiruv — `run_gui_workspaces.py` + `blender_gui_workspaces.py`

**Model:** sonnet — GUI taymer zanjiri, ikki rejim (repo/bundle), natijani o'qish.

**Files:**
- Create: `desktop/tests/run_gui_workspaces.py` (haydovchi, Blender tashqarisida), `desktop/tests/blender_gui_workspaces.py` (Blender ichida)

**Interfaces:**
- Consumes: template `workspaces` moduli (`sys.modules` dagi `*.workspaces`, `ensure`/`finish` bilan), `<pkg>.core.panels.in_workspace`, `<pkg>.core.host.record`; `keyconfigs.user` (birlashtirilgan keymap).
- Produces: `python desktop/tests/run_gui_workspaces.py [--blender <exe>] [--bundle <stage>]` → `[GUI-OK]` exit 0 / `[GUI-FAIL]` exit 1; `SATH_SCREENSHOT=<png>` — BIM bosqichida oyna skrinshoti. Task 7 `--bundle` bilan ishlatadi.

- [ ] **Step 1: `desktop/tests/blender_gui_workspaces.py`**

```python
"""GUI: Sath ish joylari (run_gui_workspaces.py ishga tushiradi). Taymerlar zanjiri:
(1) ochilganda BIM faol, N-panel, egasi filtri, bim paneli ko'rinadi, Ctrl+Shift+G «Object Mode» da birinchi
→ SCADA ga; (2) SCADA da bim paneli yashirin, scada ko'rinadi, ISA kulrang fon → Simulation ga;
(3) Graph editor Timeline va 3D orasida, belgi o'chgan, chizish xatosiz → [GUI-OK].
Repo rejimi: addon repo dan (blender_headless.load_addon); bundle (SATH_GUI_BUNDLE=1): o'rnatilgan extension."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BUNDLE = os.environ.get("SATH_GUI_BUNDLE") == "1"
PKG = "bl_ext.user_default.sath" if BUNDLE else "sath"
if not BUNDLE:
    sys.path.insert(0, str(HERE))
    import blender_headless  # noqa: E402

    blender_headless.load_addon()


def _win():
    return bpy.context.window_manager.windows[0]


def _W():
    return next(m for k, m in sys.modules.items() if k.endswith(".workspaces") and hasattr(m, "finish"))


def _tagged(tag):
    return next(w for w in bpy.data.workspaces if w.get("sath_ws") == tag)


def _visible(mod_id, ws) -> bool:
    panels, host = sys.modules[f"{PKG}.core.panels"], sys.modules[f"{PKG}.core.host"]
    return panels.in_workspace(host.record(mod_id).manifest, ws)


def _draw(win, shot: str | None = None) -> None:
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
        if shot:
            bpy.ops.screen.screenshot(filepath=shot)
            print("[GUI-SHOT]", shot, flush=True)


def bim():
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "BIM", f"ochilganda faol: {ws.name}"  # spec P4: BIM ish joyida ochiladi
    W = _W()
    assert sorted(W.tagged(bpy.data)) == sorted(W.ORDER)
    names = {w.name for w in bpy.data.workspaces}
    assert not names & set(W.REMOVE), sorted(names & set(W.REMOVE))
    v3d = [a for a in win.screen.areas if a.type == "VIEW_3D"]
    assert v3d and all(a.spaces.active.show_region_ui for a in v3d)
    assert ws.use_filter_by_owner
    assert _visible("bim", ws) and not _visible("scada", ws)
    km = bpy.context.window_manager.keyconfigs.user.keymaps.get("Object Mode")
    first = next((k for k in km.keymap_items if k.active and k.type == "G" and k.value == "PRESS"
                  and k.ctrl == 1 and k.shift == 1 and k.alt == 0), None) if km else None  # fmt: skip
    assert first is not None and first.idname == "wm.call_menu", first and first.idname
    assert first.properties.name == "SATH_MT_main"  # addon elementi standartdan oldin (core/keys.ALLOWED)
    _draw(win, os.environ.get("SATH_SCREENSHOT"))
    win.workspace = _tagged("SCADA")


def scada():
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "SCADA", ws.name
    assert _visible("scada", ws) and not _visible("bim", ws)
    sh = next(a for a in win.screen.areas if a.type == "VIEW_3D").spaces.active.shading
    assert sh.background_type == "VIEWPORT" and sh.color_type == "OBJECT"
    _draw(win)
    win.workspace = _tagged("Simulation")


def simulation():
    win = _win()
    ws = win.workspace
    assert ws.get("sath_ws") == "Simulation", ws.name
    assert not ws.get(_W().TODO), "Graph editor yakunlanmadi (msgbus finish ishlamadi)"
    areas = win.screen.areas
    g = [a for a in areas if a.type == "GRAPH_EDITOR"]
    v = [a for a in areas if a.type == "VIEW_3D"]
    t = [a for a in areas if a.ui_type == "TIMELINE"]
    assert len(g) == 1 and len(v) == 1 and t, [(a.type, a.ui_type) for a in areas]
    assert t[0].y < g[0].y < v[0].y, "pastdan yuqoriga: Timeline, Graph, 3D"
    _draw(win)


STEPS = [bim, scada, simulation]
_i = 0


def _tick():
    global _i
    try:
        STEPS[_i]()
        print(f"GUI-WS {STEPS[_i].__name__}: OK", flush=True)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("[GUI-FAIL]", flush=True)
        bpy.ops.wm.quit_blender()
        return None
    _i += 1
    if _i == len(STEPS):
        print("[GUI-OK]", flush=True)
        bpy.ops.wm.quit_blender()
        return None
    return 0.7  # Window.workspace almashinuvi keyingi siklda qo'llanadi


bpy.app.timers.register(_tick, first_interval=3.0, persistent=True)  # sath_boot read_homefile dan omon qolsin
```

- [ ] **Step 2: `desktop/tests/run_gui_workspaces.py`**

```python
"""Oynali sinov (CI da emas): Sath app template ish joylari — blender_gui_workspaces.py ni GUI Blender da
ishga tushiradi. Repo rejimi: template vaqtinchalik BLENDER_USER_SCRIPTS/startup/bl_app_templates_user ga
nusxalanadi, `--app-template Sath`, addon repo dan. Bundle rejimi: --bundle <stage> (argumentsiz ishga
tushiriladi — sath_boot.py template ga o'tkazadi, extension lar bundle dan).

  python desktop/tests/run_gui_workspaces.py [--blender <exe>] [--bundle desktop/build/_work/sath-bundle/Sath]
  $env:SATH_SCREENSHOT="$PWD\\ws_bim.png"  # ixtiyoriy: BIM bosqichida oyna skrinshoti
Natija: [GUI-OK] — exit 0, aks holda 1."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "desktop" / "tests" / "blender_gui_workspaces.py"
TEMPLATE = ROOT / "desktop" / "blender" / "template" / "Sath"
DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--bundle", type=Path, default=None, help="bundle stage (blender.exe + portable/)")
    ap.add_argument("--timeout", type=int, default=240)
    a = ap.parse_args()
    env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="sath-gui-ws-") as tmp:
        if a.bundle:
            env["SATH_GUI_BUNDLE"] = "1"
            cmd = [str(a.bundle / "blender.exe"), "--python", str(CHECK)]
        else:
            scripts = Path(tmp) / "scripts"
            dst = scripts / "startup" / "bl_app_templates_user" / "Sath"
            shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns("__pycache__", "startup.blend"))
            env["BLENDER_USER_SCRIPTS"] = str(scripts)
            cmd = [str(a.blender), "--app-template", "Sath", "--python", str(CHECK)]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=a.timeout)  # fmt: skip
    out = r.stdout + r.stderr
    keep = ("[GUI", "GUI-WS", "Traceback", "  File", "AssertionError", "Error:", "[sath]")
    for ln in out.splitlines():
        if ln.startswith(keep):
            print(ln)
    return 0 if "[GUI-OK]" in out else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Repo rejimida ishga tushiring** (oynali Windows sessiyasida)

Run: `$env:SATH_SCREENSHOT="$env:TEMP\sath_ws_bim.png"; .venv\Scripts\python.exe desktop/tests/run_gui_workspaces.py`
Expected: `[sath] ish joylari: {'created': ['BIM', 'Compare', 'Simulation', 'SCADA'], …}`, `GUI-WS bim: OK`, `GUI-WS scada: OK`, `GUI-WS simulation: OK`, `[GUI-OK]`, exit 0.
Skrinshotni Read vositasi bilan oching: yuqorida «BIM, Compare, Simulation, SCADA, Layout, Modeling, Animation» tablari, 3D o'ng tomonida N-panel. Agar `first.idname` tekshiruvi yiqilsa (addon elementi standartdan keyin) — Task 4 qarori noto'g'ri: to'xtang va hisobot bering.

- [ ] **Step 4: Lint va EOL**

Run: `.venv\Scripts\ruff.exe check desktop/tests/run_gui_workspaces.py desktop/tests/blender_gui_workspaces.py` → toza; `git ls-files --eol` (yangi) → LF.

- [ ] **Step 5: Commit**

```bash
git add desktop/tests/run_gui_workspaces.py desktop/tests/blender_gui_workspaces.py
git commit -m "test(UI): oynali ish joylari sinovi — ochilganda BIM, SCADA/Simulation ga o'tish, Graph editor msgbus bilan, Ctrl+Shift+G Object Mode da birinchi (repo va bundle rejimi)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Byudjetlar — `core/budget.py`, register perf logi, numpy dangasa, headless `budgets`

**Model:** sonnet — o'lchov va dangasa import (umumiy fayl + sync), CRLF fayllar, subprocess asosidagi headless test.

**Files:**
- Create: `desktop/blender/sath/core/budget.py`
- Modify: `desktop/blender/sath/__init__.py` (**CRLF**, to'liq almashtiriladi)
- Modify: `common/sath_common/ges_kinds.py` (`from . import geom`, `build_parts`, `build`) → `python desktop/build/sync_blender.py` → `desktop/blender/sath/shared/ges_kinds.py`
- Modify: `desktop/blender/sath/ges_objects.py` (**CRLF**: `:16-18` importlar, `set_mesh`)
- Modify: `desktop/tests/perf_blender.py` (`--budget` rejimi)
- Create: `desktop/tests/test_sath_budget.py`, `desktop/tests/sath_tests/budgets.py`
- Modify: `desktop/tests/run_blender_tests.ps1` (`@("budgets", "")`)

**Interfaces:**
- Produces: `budget.REGISTER_MS = 150.0`, `COLD_START_RATIO = 1.2`, `IDLE_RSS_DELTA_MB = 50.0`, `HEAVY_MODULES = ("numpy", "ifcopenshell", "ezdxf", "assimp_py")`; `budget.heavy_loaded(names) -> list[str]`; `budget.register_line(import_ms, core: dict, modules: dict) -> str` (ASCII: `[sath] register 42.0 ms (byudjet < 150): import 9.1, ui_tasks 0.3, … [modullar: review 2.0, …]`); `budget.check(*, register_ms, cold_ratio, rss_delta_mb, heavy) -> list[str]`. `sath.IMPORT_MS`, `sath.REGISTER_MS: dict[str, float]`. `perf_blender.py -- --budget [--bonsai]` → `BUDGET {"register_ms": …, "heavy": [...]}`. Task 8 ishlatadi.

- [ ] **Step 1: Yiqiluvchi sof test** — `desktop/tests/test_sath_budget.py`:

```python
"""core/budget.py — spec §5 byudjetlari (P4) va dangasa og'ir importlar."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))

from sath.core import budget  # noqa: E402


def test_register_line_lists_core_parts_and_modules():
    line = budget.register_line(10.0, {"ui_tasks": 0.5, "host": 20.0}, {"review": 3.0, "bim": 7.3})
    assert line == (
        "[sath] register 30.5 ms (byudjet < 150): import 10.0, ui_tasks 0.5, host 20.0"
        " [modullar: review 3.0, bim 7.3]"
    )
    assert line.isascii()  # Windows konsoli/pipe kodirovkasidan qat'i nazar
    assert "BYUDJET OSHDI" in budget.register_line(100.0, {"host": 60.0}, {})


def test_heavy_loaded_uses_top_level_names():
    names = ["numpy.core", "numpy", "ezdxf.math", "json", "sath.shared.geom", "assimp_py"]
    assert budget.heavy_loaded(names) == ["assimp_py", "ezdxf", "numpy"]


def test_check_reports_each_violation():
    assert budget.check(register_ms=40.0, cold_ratio=1.05, rss_delta_mb=12.0, heavy=[]) == []
    bad = budget.check(register_ms=150.0, cold_ratio=1.3, rss_delta_mb=60.0, heavy=["numpy"])
    assert len(bad) == 4
    assert len(budget.check(register_ms=None, cold_ratio=None, rss_delta_mb=None, heavy=[])) == 3


def test_ges_kinds_imports_without_numpy():
    """Blender register da ges_objects → ges_kinds import qilinadi: geom (numpy) birinchi qurishgacha yuklanmaydi."""
    code = (
        "import sys; sys.modules['numpy'] = None; sys.path.insert(0, 'common');"
        "from sath_common import ges_kinds;"
        "assert ges_kinds.KINDS and ges_kinds.geometric_params('GES_Dam');"
        "assert 'sath_common.geom' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)
```

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_sath_budget.py`
Expected: FAIL (`ImportError: cannot import name 'budget'`).

- [ ] **Step 2: `desktop/blender/sath/core/budget.py`**

```python
"""Spec §5 unumdorlik byudjetlari — yagona joy: addon register logi (sath/__init__.py), headless `budgets`
sinovi, desktop/tests/perf_baseline.py --check. bpy siz (pytest)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

REGISTER_MS = 150.0  # Sath import + register jami (modullar bilan)
COLD_START_RATIO = 1.2  # sovuq start: Blender+Bonsai+Sath / Blender+Bonsai
IDLE_RSS_DELTA_MB = 50.0  # bo'sh sahnada Sath RSS ortishi (Bonsai ustiga)
HEAVY_MODULES = ("numpy", "ifcopenshell", "ezdxf", "assimp_py")  # faqat funksiya ichida import qilinadi


def heavy_loaded(names: Iterable[str]) -> list[str]:
    """Yangi yuklangan modul nomlaridan og'irlari (yuqori paket nomi bo'yicha)."""
    return sorted({n.split(".", 1)[0] for n in names} & set(HEAVY_MODULES))


def register_line(import_ms: float, core: Mapping[str, float], modules: Mapping[str, float]) -> str:
    """Bitta log qatori (ASCII): jami, har yadro qismi, modullar (Record.ms: import + register)."""
    total = import_ms + sum(core.values())
    head = f"[sath] register {total:.1f} ms (byudjet < {REGISTER_MS:.0f})"
    if total >= REGISTER_MS:
        head += " - BYUDJET OSHDI"
    parts = [f"import {import_ms:.1f}", *(f"{k} {v:.1f}" for k, v in core.items())]
    line = head + ": " + ", ".join(parts)
    if modules:
        line += " [modullar: " + ", ".join(f"{k} {v:.1f}" for k, v in modules.items()) + "]"
    return line


def check(*, register_ms: float | None, cold_ratio: float | None, rss_delta_mb: float | None,
          heavy: Iterable[str]) -> list[str]:  # fmt: skip
    """O'lchovlar → buzilgan byudjetlar (bo'sh — hammasi bajarildi). None — o'lchanmagan (buzilgan)."""
    bad = []
    if register_ms is None or register_ms >= REGISTER_MS:
        bad.append(f"Sath register {register_ms} ms (byudjet < {REGISTER_MS:.0f})")
    if cold_ratio is None or cold_ratio > COLD_START_RATIO:
        bad.append(f"sovuq start nisbati {cold_ratio} (byudjet <= {COLD_START_RATIO})")
    if rss_delta_mb is None or rss_delta_mb > IDLE_RSS_DELTA_MB:
        bad.append(f"RSS ortishi {rss_delta_mb} MB (byudjet <= {IDLE_RSS_DELTA_MB:.0f})")
    heavy = list(heavy)
    if heavy:
        bad.append(f"register da og'ir importlar: {', '.join(heavy)}")
    return bad
```

- [ ] **Step 3: `ges_kinds` — `geom` dangasa** (`common/sath_common/ges_kinds.py`, LF). Import qatorlarini (`import json` … `from . import geom`) almashtiring:

```python
import importlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field


class _LazyGeom:
    """`geom` (numpy) birinchi geometriya chaqiruvida import qilinadi: Blender register (ges_objects →
    ges_kinds) numpy siz o'tadi (spec §5 byudjeti). Sxema, psetlar va miqdorlar numpy siz ishlaydi."""

    def __getattr__(self, name: str):
        mod = importlib.import_module(".geom", __package__)
        globals()["geom"] = mod
        return getattr(mod, name)


geom = _LazyGeom()
```

`build_parts` va `build` ni almashtiring (sukut `geom.TOL` endi import paytida o'qilmaydi):

```python
def build_parts(kind: str, params: dict | None = None, tol: float | None = None) -> list:
    """Har biri yopiq qobiq bo'lgan qismlar ([geom.Mesh]); tegib turgan qismlar birlashtirilmaydi (boolean yo'q).
    tol=None — geom.TOL (chord tolerance, 5 mm)."""
    return spec(kind).parts(validate(kind, params), geom.TOL if tol is None else tol)


def build(kind: str, params: dict | None = None, tol: float | None = None) -> geom.Mesh:
    """Bitta mesh (V float64 metr, F int64 uchburchak) — Blender ga `foreach_set` bilan uzatiladi."""
    return geom.merge(*build_parts(kind, params, tol))
```

Run: `.venv\Scripts\python.exe desktop/build/sync_blender.py` → `nusxalandi: … ges_kinds.py …`
Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests/test_ges_kinds.py desktop/tests/test_geom.py` → PASS (paritet o'zgarmagan)

- [ ] **Step 4: `ges_objects.py` (CRLF)** — `import numpy as np` qatorini olib tashlang; `from dataclasses import dataclass, field` qatoridan keyin:

```python
from typing import TYPE_CHECKING
```

`from .shared import ges_kinds` qatoridan keyin:

```python

if TYPE_CHECKING:
    import numpy as np
```

`set_mesh` docstring idan keyingi birinchi qator sifatida:

```python
    import numpy as np  # dangasa: register da numpy yuklanmaydi (spec §5)
```

Run: `git ls-files --eol desktop/blender/sath/ges_objects.py` → `i/crlf w/crlf`; `git diff --stat` — ~8 qator.

- [ ] **Step 5: `sath/__init__.py` (CRLF)** — butun matnni almashtiring (CRLF saqlansin):

```python
"""Sath Blender addoni: yadro (server, versiyalar, rolga sezgir UI, fon vazifalari) + modullar (sath/modules/:
review, sim, scada, twin, io, bim; Sozlamalarda yoqiladi/o'chiriladi). IFC — Bonsai. register() har yadro
qismi va modul vaqtini bitta qatorda logga yozadi (spec §5 byudjeti: core/budget.py)."""

from __future__ import annotations

import time

try:
    import bpy  # noqa: F401
except ImportError:  # pytest (Blender siz): faqat sof modullar import qilinadi
    bpy = None

_T0 = time.perf_counter()
MODULES: list = []
if bpy is not None:
    from . import ops_server, prefs, props, ui
    from .core import host, ui_tasks

    # Yadro: fon vazifalari, sozlamalar, Scene.ges, server/login/commit, yadro panellari va menyu; qolgani — modules/
    MODULES = [ui_tasks, prefs, props, ops_server, ui, host]

IMPORT_MS = (time.perf_counter() - _T0) * 1000.0  # yadro fayllari importi; modullar importi — host.scan da
REGISTER_MS: dict[str, float] = {}  # oxirgi register(): yadro qismlari (ms)


def register():
    from .core import budget

    REGISTER_MS.clear()
    for m in MODULES:
        t = time.perf_counter()
        m.register()
        REGISTER_MS[m.__name__.rpartition(".")[2]] = (time.perf_counter() - t) * 1000.0
    reg = host.REG
    mods = {rid: rec.ms for rid, rec in reg.records.items() if rec.state == "enabled"} if reg is not None else {}
    print(budget.register_line(IMPORT_MS, REGISTER_MS, mods), flush=True)


def unregister():
    for m in reversed(MODULES):
        m.unregister()
```

Run: `git ls-files --eol desktop/blender/sath/__init__.py` → `i/crlf w/crlf` (Edit/Write CRLF ni saqlamasa: `python -c "p='desktop/blender/sath/__init__.py'; s=open(p,encoding='utf-8').read().replace('\r\n','\n'); open(p,'w',encoding='utf-8',newline='\r\n').write(s)"`).

- [ ] **Step 6: `perf_blender.py` — `--budget` rejimi.** `main()` da `n = int(opt("--n", "2000"))` qatoridan keyin:

```python
    if "--budget" in argv:  # spec §5: register vaqti va register da yangi yuklangan og'ir modullar
        if "--bonsai" in argv:
            enable_bonsai()
        before = set(sys.modules)
        ms = register_sath()
        from sath.core import budget

        heavy = budget.heavy_loaded(set(sys.modules) - before)
        print("BUDGET " + json.dumps({"register_ms": ms, "heavy": heavy}), flush=True)
        return
```

- [ ] **Step 7: Headless test** — `desktop/tests/sath_tests/budgets.py`:

```python
"""P4 byudjetlari (headless, spec §5): Sath import + register < 150 ms (Bonsai siz va bilan, 3 urinishdan eng
yaxshisi), register da og'ir modullar (numpy, ifcopenshell, ezdxf, assimp_py) yuklanmaydi, perf logi (yadro
qismlari va modullar) chiqadi. Har o'lchov alohida toza Blender jarayonida (perf_blender.py --budget)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import bpy

PERF = Path(__file__).resolve().parents[1] / "perf_blender.py"


def _run(bonsai: bool) -> tuple[dict, str]:
    cmd = [bpy.app.binary_path, "-b", "--factory-startup", "--python", str(PERF), "--", "--budget"]
    if bonsai:
        cmd.append("--bonsai")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = r.stdout.splitlines()
    line = next((ln for ln in lines if ln.startswith("BUDGET ")), None)
    assert line is not None, r.stdout[-3000:] + r.stderr[-2000:]
    log = next((ln for ln in lines if ln.startswith("[sath] register")), "")
    return json.loads(line[len("BUDGET ") :]), log


def run(ctx):
    from sath.core import budget

    for bonsai in (False, True):
        runs = [_run(bonsai) for _ in range(3)]
        times = [r["register_ms"] for r, _log in runs]
        label = "Bonsai bilan" if bonsai else "Bonsai siz"
        assert min(times) < budget.REGISTER_MS, f"register ({label}): {times} ms"
        heavy = sorted({h for r, _log in runs for h in r["heavy"]})
        assert heavy == [], f"register da og'ir importlar ({label}): {heavy} — funksiya ichiga ko'chiring"
        for _r, log in runs:
            assert "(byudjet < 150)" in log and "[modullar: " in log and "bim " in log, log
        print(f"budgets ({label}): register {times} ms | {runs[0][1]}", flush=True)
```

`run_blender_tests.ps1` — `$tests` ga `, @("budgets", "")`.

- [ ] **Step 8: Tekshiring**

Run: `.venv\Scripts\python.exe -m pytest -q desktop/tests` → PASS
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test budgets`
Expected: ikki `budgets (…): register [...] ms | [sath] register … [modullar: …]` qatori, `[OK] budgets`. Agar `og'ir importlar` chiqsa — qaysi Sath modul import qilayotganini `python -X importtime` uslubida emas, `sys.modules` farqi va logdagi modul vaqtlari bo'yicha toping va importni funksiya ichiga ko'chiring; **byudjet chegarasini o'zgartirmang**. 150 ms oshsa — logdagi eng katta qismni (odatda `host` → modul) tahlil qilib, hisobot bering.
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test objects --bonsai` → `[OK] objects` (numpy dangasa, mesh qurish ishlaydi)
Run: `& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test kinds_mesh` → `[OK] kinds_mesh`
Run: `.venv\Scripts\python.exe desktop/build/sync_blender.py --check` → sinxron; `.venv\Scripts\ruff.exe check desktop common` → toza

- [ ] **Step 9: Commit**

```bash
git add desktop/blender/sath/core/budget.py desktop/blender/sath/__init__.py common/sath_common/ges_kinds.py desktop/blender/sath/shared/ges_kinds.py desktop/blender/sath/ges_objects.py desktop/tests/perf_blender.py desktop/tests/test_sath_budget.py desktop/tests/sath_tests/budgets.py desktop/tests/run_blender_tests.ps1
git commit -m "feat(PERF): byudjetlar — core/budget.py, register perf logi (yadro qismlari va modullar), numpy dangasa (ges_kinds geom, ges_objects), headless budgets

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Bundle — tema, ish joylari bilan startup.blend, stage tekshiruvi, «BIM da ochiladi»

**Model:** sonnet — bundle yig'ish (bir necha daqiqa), fon va oynali tekshiruv, natijani o'qish.

**Files:**
- Modify: `desktop/blender/template/setup_bundle.py` (LF, to'liq almashtiriladi)
- Modify: `desktop/build/build_blender_bundle.py` (**CRLF**: `install_template`, yangi `stage_mb`/`check_stage`, `main`, `write_readme`)
- Create: `desktop/tests/bundle_check.py`

**Interfaces:**
- Consumes: `template/Sath/theme_sath.xml` (Task 1), template ilgagi (Task 3), `run_gui_workspaces.py --bundle` (Task 5), `sath.core.tokens` (bundle_check).
- Produces: stage da `5.2/scripts/startup/bl_app_templates_system/Sath/{__init__.py, workspaces.py, theme_sath.xml, startup.blend}`; portable userpref da Sath temasi (`themes[0].filepath == ""`), `show_developer_ui=False`; `build_blender_bundle.check_stage()` (freecad/ yo'q, template fayllari bor, hajm logda); `python desktop/tests/bundle_check.py [--stage]` → `[BUNDLE-OK]`.

- [ ] **Step 1: `setup_bundle.py`** (to'liq, LF):

```python
"""Sath bundle ichida ishlaydi (stage/blender.exe -b --app-template Sath --python setup_bundle.py -- <template>):
app template `Sath` sukut, Sath temasi (theme_sath.xml — Blender Dark + Sath farqlari), prefs, portable
userpref.blend va template startup.blend (Sath ish joylari bilan — template ilgagi workspaces.ensure quradi).
Extension lar oldindan `--command extension install-file` bilan o'rnatilgan bo'ladi."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

TEMPLATE_DIR = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None

p = bpy.context.preferences
p.app_template = "Sath"
p.view.show_splash = True
p.filepaths.use_relative_paths = True
for name in ("bl_ext.user_default.bonsai", "bl_ext.user_default.sath"):
    if name not in p.addons:
        bpy.ops.preferences.addon_enable(module=name)

# startup.blend: bo'sh sahna (kub siz), metr, kamera/yorug'lik + Sath ish joylari. Scripting fayl ichida qolsin
# (developer UI yoqilsa kerak) — ilgak uni developer UI o'chiq bo'lsa olib tashlaydi, shuning uchun qurishda
# vaqtincha yoqiladi; har ishga tushishda ilgak qayta ishlaydi va Scripting ni olib tashlaydi.
p.view.show_developer_ui = True
bpy.ops.wm.read_homefile(app_template="Sath", use_factory_startup=True)
p.view.show_developer_ui = False
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
for sc in bpy.data.scenes:
    sc.name = "Sath"
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "METERS"
tags = sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws"))
print("WORKSPACES:", tags, flush=True)
if TEMPLATE_DIR is not None:
    out = TEMPLATE_DIR / "startup.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True)
    print("STARTUP:", out, flush=True)
    theme = TEMPLATE_DIR / "theme_sath.xml"
    bpy.ops.script.execute_preset(filepath=str(theme), menu_idname="USERPREF_MT_interface_theme_presets")
    p.themes[0].filepath = ""  # build mashinasi yo'li userpref da qolmasin
    print("THEME:", theme.name, flush=True)
bpy.ops.wm.save_userpref()
print("USERPREF:", bpy.utils.user_resource("CONFIG"), "app_template=", p.app_template, flush=True)
```

- [ ] **Step 2: `build_blender_bundle.py` (CRLF)** — `install_template` dagi `shutil.copytree(TEMPLATE / "Sath", dst, dirs_exist_ok=True)` ni:

```python
    shutil.copytree(TEMPLATE / "Sath", dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
```

`copy_libredwg` dan oldin:

```python
def stage_mb() -> int:
    return sum(f.stat().st_size for f in STAGE.rglob("*") if f.is_file()) // 2**20


def check_stage() -> None:
    """P4: FreeCAD siz (K1), Sath template ish joylari va temasi bilan; hajm logda."""
    if (STAGE / "freecad").exists():
        raise SystemExit("stage da freecad/ bor — FreeCAD bundle dan chiqqan bo'lishi kerak (P2)")
    tpl = blender_ver_dir() / "scripts" / "startup" / "bl_app_templates_system" / "Sath"
    need = ("__init__.py", "workspaces.py", "theme_sath.xml", "startup.blend")
    missing = [n for n in need if not (tpl / n).exists()]
    if missing:
        raise SystemExit(f"Sath template da yo'q: {missing}")
    print(f"stage: {stage_mb()} MB (FreeCAD siz)", flush=True)
```

`main` da `write_build_info(ver)` dan keyin: `check_stage()`.
`write_readme` matnidagi `3D Viewport → N panel → «Sath» yorlig'i.` jumlasidan keyin (shu satr ichida):

```
Ish joylari: BIM (asosiy), Compare, Simulation, SCADA; tiklash — Sath menyusi → «Ish joylarini tiklash».
```

Run: `git ls-files --eol desktop/build/build_blender_bundle.py desktop/blender/template/setup_bundle.py` → `i/crlf w/crlf` va `i/lf w/lf`.

- [ ] **Step 3: `desktop/tests/bundle_check.py`**

```python
"""Yig'ilgan Sath bundle (stage) tekshiruvi — fon rejimida, bundle ning o'z Blender i va portable prefs i
bilan: Sath template ish joylari (Blender ish joylari va Scripting yo'q), Sath temasi, Bonsai va sath
extension lari, «Standard» view transform, FreeCAD yo'q, hajm. Oynali qism («BIM ish joyida ochiladi») —
`python desktop/tests/run_gui_workspaces.py --bundle <stage>`.

  python desktop/tests/bundle_check.py [--stage desktop/build/_work/sath-bundle/Sath]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
from sath.core import registry, tokens  # noqa: E402

STAGE = ROOT / "desktop" / "build" / "_work" / "sath-bundle" / "Sath"
GONE = {"Sculpting", "UV Editing", "Texture Paint", "Shading", "Rendering", "Compositing", "Geometry Nodes",
        "Scripting"}  # fmt: skip
PROBE = """
import bpy, json
p = bpy.context.preferences
t = p.themes[0]
print("BUNDLE " + json.dumps({
    "addons": sorted(k for k in p.addons.keys() if k.rpartition(".")[2] in ("sath", "bonsai")),
    "tags": sorted(w["sath_ws"] for w in bpy.data.workspaces if w.get("sath_ws")),
    "names": sorted(w.name for w in bpy.data.workspaces),
    "object_active": [round(c * 255) for c in t.view_3d.object_active],
    "theme_filepath": t.filepath,
    "dev_ui": p.view.show_developer_ui,
    "view_transform": bpy.context.scene.view_settings.view_transform,
}), flush=True)
"""


def stage_mb(stage: Path) -> int:
    return sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) // 2**20


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, default=STAGE)
    a = ap.parse_args()
    cmd = [str(a.stage / "blender.exe"), "-b", "--app-template", "Sath", "--python-expr", PROBE]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("BUNDLE ")), None)
    if line is None:
        print(r.stdout[-3000:], r.stderr[-2000:])
        print("[BUNDLE-FAIL] tekshiruv skripti natija bermadi")
        return 1
    got = json.loads(line[len("BUNDLE ") :])
    want_active = [round(c * 255) for c in tokens.parse(tokens.PAL["highlight"])[:3]]
    problems = []
    if got["addons"] != ["bl_ext.user_default.bonsai", "bl_ext.user_default.sath"]:
        problems.append(f"addonlar: {got['addons']}")
    if got["tags"] != sorted(registry.WORKSPACES):
        problems.append(f"Sath ish joylari: {got['tags']}")
    if set(got["names"]) & GONE:
        problems.append(f"olib tashlanmagan: {sorted(set(got['names']) & GONE)}")
    if got["object_active"] != want_active:
        problems.append(f"tema object_active {got['object_active']} != {want_active}")
    if got["theme_filepath"]:
        problems.append(f"tema yo'li userpref da qoldi: {got['theme_filepath']}")
    if got["dev_ui"]:
        problems.append("developer UI yoqiq")
    if got["view_transform"] != "Standard":
        problems.append(f"view transform: {got['view_transform']}")
    if (a.stage / "freecad").exists():
        problems.append("freecad/ bor")
    print(f"stage: {stage_mb(a.stage)} MB; ish joylari: {got['names']}")
    for p in problems:
        print("  -", p)
    print("[BUNDLE-OK]" if not problems else "[BUNDLE-FAIL]")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Bundle ni yig'ing** (Blender 5.2.2, Bonsai 0.9.0 zip va libredwg `~\Tools` da)

Run: `.venv\Scripts\python.exe desktop/build/build_blender_bundle.py --no-zip`
Expected (logda): `WORKSPACES: ['BIM', 'Compare', 'SCADA', 'Simulation']`, `STARTUP: …startup.blend`, `THEME: theme_sath.xml`, `USERPREF: … app_template= Sath`, `stage: <N> MB (FreeCAD siz)`.

- [ ] **Step 5: Fon tekshiruvi**

Run: `.venv\Scripts\python.exe desktop/tests/bundle_check.py`
Expected: `stage: <N> MB; ish joylari: ['Animation', 'BIM', 'Compare', 'Layout', 'Modeling', 'SCADA', 'Simulation']`, `[BUNDLE-OK]`.

- [ ] **Step 6: Oynali tekshiruv — «BIM ish joyida ochiladi»**

Run: `$env:SATH_SCREENSHOT="$env:TEMP\sath_bundle_bim.png"; .venv\Scripts\python.exe desktop/tests/run_gui_workspaces.py --bundle desktop/build/_work/sath-bundle/Sath`
Expected: `GUI-WS bim: OK`, `GUI-WS scada: OK`, `GUI-WS simulation: OK`, `[GUI-OK]`.
Skrinshotni Read vositasi bilan oching va tasdiqlang: BIM tab faol; 3D N-panelida «Sath» yorlig'i va Sath panellari (Server, Model, GES obyektlari) **ko'rinadi** — `use_filter_by_owner` ularni yashirmagan; Properties da Bonsai yorliqlari bor. Panellar ko'rinmasa — egasi nomlari mos emas: `bpy.context.window.workspace.owner_ids` va `bpy.context.preferences.addons.keys()` ni hisobotga yozing va to'xtang.

- [ ] **Step 7: Lint va commit**

Run: `.venv\Scripts\ruff.exe check desktop` → toza

```bash
git add desktop/blender/template/setup_bundle.py desktop/build/build_blender_bundle.py desktop/tests/bundle_check.py
git commit -m "build(BUNDLE): Sath temasi va ish joylari bilan startup.blend, stage tekshiruvi (FreeCAD siz, template fayllari), bundle_check — BIM ish joyida ochiladi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: O'lchov — `perf_baseline.py` byudjet jadvali, P0 bilan taqqoslash, `docs/benchmark-desktop.md`

**Model:** sonnet — o'lchov skriptini kengaytirish, uzoq ishga tushirish, natijani halol talqin qilish.

**Files:**
- Modify: `desktop/tests/perf_blender.py` (`template_workspaces`, `--ws`, `--cold` ga ish joylari)
- Modify: `desktop/tests/perf_baseline.py` (to'liq almashtiriladi, LF)
- Modify: `docs/benchmark-desktop.md` (skript yozadi)

**Interfaces:**
- Consumes: `budget.*` (Task 6), template `workspaces.ensure` (Task 3), stage (Task 7).
- Produces: `perf_blender.py -- --ws` → `WS {"ensure_ms": …}`; `perf_baseline.py [--blender] [--n 2000] [--bundle <stage>] [--check]` → doc (O'lchovlar: P0 | hozir; Byudjetlar: chegara | hozir | holat; xulosa), `--check` da byudjet buzilsa exit 1.

- [ ] **Step 1: `perf_blender.py`** — `register_sath` dan keyin:

```python
TEMPLATE_WS = Path(__file__).resolve().parents[2] / "desktop" / "blender" / "template" / "Sath" / "workspaces.py"


def template_workspaces():
    """App template ish joylari moduli (Blender uni template sifatida yuklaydi; o'lchovda — fayldan)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("sath_template_workspaces", TEMPLATE_WS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

`main()` dagi `--cold` blokini almashtiring va undan oldin `--ws` qo'shing:

```python
    if "--ws" in argv:  # Sath ish joylari (app template ilgagi ishi) — factory startup ustida
        ws = template_workspaces()
        t = time.perf_counter()
        rep = ws.ensure(bpy.context)
        ms = round((time.perf_counter() - t) * 1000, 2)
        assert rep["created"] == list(ws.ORDER), rep
        print("WS " + json.dumps({"ensure_ms": ms}), flush=True)
        return
    if "--cold" in argv:  # sovuq start: Bonsai + Sath + ish joylari (bundle startidagi ish), keyin chiqish
        enable_bonsai()
        register_sath()
        template_workspaces().ensure(bpy.context)
        return
```

- [ ] **Step 2: `perf_baseline.py`** (to'liq, LF):

```python
"""Desktop unumdorligi (P0 bazaviy, P4 byudjetlar): sovuq start (vanilla / +Bonsai / +Sath + ish joylari),
register vaqti va og'ir importlar, RSS, ish joylari qurish, katta IFC ochish, bundle hajmi. Har o'lchov 3
marta, mediana. Natija docs/benchmark-desktop.md ga (P0 ustuni bilan); --check — spec §5 byudjeti buzilsa
exit 1. Chegaralar — desktop/blender/sath/core/budget.py.

  python desktop/tests/perf_baseline.py [--blender <exe>] [--n 2000] [--bundle <stage>] [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "blender"))
from sath.core import budget  # noqa: E402

DEFAULT_BLENDER = Path(os.environ.get("GES_BLENDER", Path.home() / "Tools" / "blender-5.2" / "blender.exe"))
REPEAT = 3
BLENDER = ["-b", "--factory-startup"]  # barcha qatorlar bir xil boshlang'ich rejimda
SCRIPT = str(ROOT / "desktop" / "tests" / "perf_blender.py")
BONSAI = "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.bonsai')"
# P0 bazaviy o'lchov (2026-10-08, shu mashina; Sath P0 holatida) — taqqoslash uchun
P0 = {
    "cold_blender_s": 1.03, "cold_bonsai_s": 4.63, "cold_sath_s": 4.62, "register_ms": 31.4,
    "rss_blender_mb": 160.71, "rss_bonsai_mb": 350.68, "rss_sath_mb": 351.93, "ifc_open_s": 3.1,
    "rss_ifc_mb": 598.32,
}  # fmt: skip
BUNDLE_P0_MB = 2392  # Sath-0.3.0 bundle (ochilgan; FreeCAD 935 MB bilan) — P2 gacha


def wall(cmd: list[str]) -> float:
    t = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    return time.perf_counter() - t


def tagged(exe: Path, args: list[str], tag: str) -> dict:
    r = subprocess.run([str(exe), *BLENDER, "--python", SCRIPT, "--", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", check=True)  # fmt: skip
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith(tag + " "))
    return json.loads(line[len(tag) + 1 :])


def median(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def blender_label(exe: Path) -> str:
    """Blender versiyasi + exe yo'li (uy papkasi `~` bilan — lokal foydalanuvchi yo'li commit bo'lmasin)."""
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True).stdout.splitlines()
    ver = out[0].strip() if out else "?"
    try:
        shown = "~/" + exe.resolve().relative_to(Path.home()).as_posix()
    except ValueError:
        shown = exe.name
    return f"{ver} (`{shown}`)"


def ok(cond: bool) -> str:
    return "bajarildi" if cond else "**OSHDI**"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--bundle", type=Path, default=None, help="bundle stage papkasi (hajm, FreeCAD yo'qligi)")
    ap.add_argument("--check", action="store_true", help="byudjet buzilsa exit 1")
    a = ap.parse_args()
    exe = a.blender
    quit_ = "; bpy.ops.wm.quit_blender()"
    vanilla = [wall([str(exe), *BLENDER, "--python-expr", "import bpy" + quit_]) for _ in range(REPEAT)]
    bonsai = [wall([str(exe), *BLENDER, "--python-expr", BONSAI + quit_]) for _ in range(REPEAT)]
    sath = [wall([str(exe), *BLENDER, "--python", SCRIPT, "--", "--cold"]) for _ in range(REPEAT)]
    with tempfile.TemporaryDirectory(prefix="sath-perf-") as tmp:
        ifc = Path(tmp) / f"perf_{a.n}.ifc"
        subprocess.run([str(exe), *BLENDER, "--python", SCRIPT, "--", "--n", str(a.n), "--gen", str(ifc)],
                       check=True, capture_output=True)  # fmt: skip
        runs = [tagged(exe, ["--n", str(a.n), "--ifc", str(ifc)], "PERF") for _ in range(REPEAT)]
    heavy = tagged(exe, ["--budget"], "BUDGET")["heavy"]  # Bonsai siz (u numpy ni oldindan yuklaydi)
    ws_ms = median([tagged(exe, ["--ws"], "WS")["ensure_ms"] for _ in range(REPEAT)])
    keys = ["addon_register_ms", "rss_blender_mb", "rss_bonsai_mb", "rss_sath_mb", "ifc_open_s", "rss_ifc_mb",
            "ifc_size_mb"]  # fmt: skip
    med = {k: median([r.get(k) for r in runs]) for k in keys}
    mv, mb, ms = median(vanilla), median(bonsai), median(sath)
    ratio = round(ms / mb, 2)
    rss_delta = round(med["rss_sath_mb"] - med["rss_bonsai_mb"], 1)
    reg = med["addon_register_ms"]
    rows = [
        ("Sovuq start, Blender", f"{P0['cold_blender_s']} s", f"{mv} s"),
        ("Sovuq start, + Bonsai", f"{P0['cold_bonsai_s']} s", f"{mb} s"),
        ("Sovuq start, + Bonsai + Sath (+ ish joylari)", f"{P0['cold_sath_s']} s", f"{ms} s"),
        ("Sath import + register (Bonsai yoqilgan)", f"{P0['register_ms']} ms", f"{reg} ms"),
        ("Idle RSS: Blender / + Bonsai / + Sath",
         f"{P0['rss_blender_mb']} / {P0['rss_bonsai_mb']} / {P0['rss_sath_mb']} MB",
         f"{med['rss_blender_mb']} / {med['rss_bonsai_mb']} / {med['rss_sath_mb']} MB"),
        (f"Sintetik IFC ({a.n} element, {med['ifc_size_mb']} MB) ochish", f"{P0['ifc_open_s']} s",
         f"{med['ifc_open_s']} s"),
        ("RSS IFC ochilgandan keyin", f"{P0['rss_ifc_mb']} MB", f"{med['rss_ifc_mb']} MB"),
        ("Sath ish joylari qurish (ensure, 4 ta)", "—", f"{ws_ms} ms"),
    ]  # fmt: skip
    bad = budget.check(register_ms=reg, cold_ratio=ratio, rss_delta_mb=rss_delta, heavy=heavy)
    budgets = [
        ("Sath import + register", f"< {budget.REGISTER_MS:.0f} ms", f"{reg} ms", ok(reg < budget.REGISTER_MS)),
        ("Og'ir importlar register da (" + ", ".join(budget.HEAVY_MODULES) + ")", "yo'q",
         ", ".join(heavy) or "yo'q", ok(not heavy)),
        ("Sovuq start nisbati (+Sath / +Bonsai)", f"<= {budget.COLD_START_RATIO}x", f"{ratio}x",
         ok(ratio <= budget.COLD_START_RATIO)),
        ("Sath RSS ortishi (Bonsai ustiga)", f"<= {budget.IDLE_RSS_DELTA_MB:.0f} MB", f"{rss_delta} MB",
         ok(rss_delta <= budget.IDLE_RSS_DELTA_MB)),
    ]  # fmt: skip
    if a.bundle:
        size = sum(f.stat().st_size for f in a.bundle.rglob("*") if f.is_file()) // 2**20
        no_fc = not (a.bundle / "freecad").exists()
        rows.append(("Bundle hajmi (ochilgan stage)", f"{BUNDLE_P0_MB} MB (FreeCAD 935 MB bilan)",
                     f"{size} MB (−{BUNDLE_P0_MB - size} MB)"))  # fmt: skip
        budgets.append(("Bundle FreeCAD siz (~0.9 GB kichik)", "freecad/ yo'q", "yo'q" if no_fc else "bor",
                        ok(no_fc)))  # fmt: skip
        if not no_fc:
            bad.append("bundle da freecad/ bor")
    md = [
        "# Desktop (Blender) unumdorligi — o'lchov va byudjetlar",
        "",
        f"Sana: {date.today().isoformat()} · Mashina: {platform.processor() or platform.machine()} · "
        f"OS: {platform.system()} {platform.release()} · Blender: {blender_label(exe)}",
        "",
        f"Usul: `python desktop/tests/perf_baseline.py --n {a.n}" + (" --bundle <stage>" if a.bundle else "")
        + f" --check` — har o'lchov {REPEAT} marta, mediana. P0 ustuni — 2026-10-08 bazaviy o'lchov "
        "(Sath P0 holatida). Byudjetlar — spec §5 (`desktop/blender/sath/core/budget.py`).",
        "",
        "Rejim: barcha qatorlar `blender -b --factory-startup` (bir xil toza profil; Bonsai extension "
        "`bl_ext.user_default.bonsai` o'zi yoqiladi). Sath repo dan ro'yxatga olinadi; «+ Sath» sovuq starti "
        "app template ish joylarini ham quradi. Og'ir importlar Bonsai siz o'lchanadi (Bonsai numpy va "
        "ifcopenshell ni o'zi yuklaydi). O'lchovlar ketma-ket, issiq OS keshi bilan (sovuq-disk start emas). "
        "Har ishga tushishda Sath logi: `[sath] register … ms (byudjet < 150): import …, host … [modullar: …]`.",
        "",
        "| O'lchov | P0 | Hozir |",
        "|---|---|---|",
        *[f"| {k} | {p} | {v} |" for k, p, v in rows],
        "",
        "## Byudjetlar (spec §5)",
        "",
        "| Byudjet | Chegara | Hozir | Holat |",
        "|---|---|---|---|",
        *[f"| {k} | {c} | {v} | {s} |" for k, c, v, s in budgets],
        "",
        "Xulosa: " + ("barcha byudjetlar bajarildi." if not bad else "buzilgan — " + "; ".join(bad) + "."),
        "",
    ]
    out = ROOT / "docs" / "benchmark-desktop.md"
    out.write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(out.read_text(encoding="utf-8"))
    return 1 if a.check and bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Lint**

Run: `.venv\Scripts\ruff.exe check desktop/tests/perf_baseline.py desktop/tests/perf_blender.py` → toza

- [ ] **Step 4: O'lchang** (boshqa og'ir jarayonlarsiz; ~5–8 daqiqa)

Run: `.venv\Scripts\python.exe desktop/tests/perf_baseline.py --n 2000 --bundle desktop/build/_work/sath-bundle/Sath --check`
Expected: jadval chop etiladi, `Xulosa: barcha byudjetlar bajarildi.`, exit 0. Byudjet buzilsa — raqamlarni **o'zgartirmang**, chegara/usulni yumshatmang: logdagi `[sath] register` qismlari va `heavy` ro'yxati bilan sababni toping (ko'pincha modul `register()` idagi import) va tuzating yoki hisobot bering. Shovqin shubhasi bo'lsa — bir marta qayta ishga tushiring va ikkala natijani hisobotga yozing.

- [ ] **Step 5: Hujjatni tekshiring**

`docs/benchmark-desktop.md`: ikki jadval (P0 | Hozir; Byudjetlar 5 qator — register, og'ir importlar, sovuq start, RSS, bundle), xulosa qatori; `git ls-files --eol docs/benchmark-desktop.md` → `i/lf w/lf`.

- [ ] **Step 6: Commit**

```bash
git add desktop/tests/perf_blender.py desktop/tests/perf_baseline.py docs/benchmark-desktop.md
git commit -m "feat(PERF): perf_baseline — spec §5 byudjetlari jadvali (P0 bilan taqqoslash, ish joylari, bundle hajmi, --check); P4 o'lchovi docs ga

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Hujjat va yakuniy tekshiruv

**Model:** haiku — matn va buyruqlarni ishga tushirish.

**Files:**
- Modify: `desktop/blender/README.md` (**CRLF**)

- [ ] **Step 1: «Tayyor bundle» bo'limi** — `(splash, bo'sh metr sahna, N-panel ochiq)` ni `(splash, bo'sh metr sahna, N-panel ochiq, **ish joylari** BIM/Compare/Simulation/SCADA, Sath temasi)` ga; `Bundle hajmi ≈1568 MB (`freecad/` siz).` ni `docs/benchmark-desktop.md` dagi hozirgi qiymat bilan `Bundle hajmi ≈<N> MB (`freecad/` siz; 0.3.0 da 2392 MB edi).` ga almashtiring.

- [ ] **Step 2: «Ishlatish»** — `- **Rollar:** …` bandidan oldin (va shu bo'limdagi takrorlangan `tugma ustida sababi («Ruxsat yo'q: cr.approve»). Haqiqiy tekshiruv serverda.` qatorining **ikkinchi** nusxasini o'chiring):

```markdown
- **Ish joylari (bundle):** Sath BIM ish joyida ochiladi. BIM — Outliner, Properties (Bonsai), 3D + N-panel
  (GES obyektlari, Import, Taqriz, Simulyatsiya); Compare — ikki 3D ko'rinish (taqqoslash — 3-quyi-loyiha);
  Simulation — Timeline + Graph editor (simulyatsiya va egizak natijalari); SCADA — ISA-101 kulrang fon,
  alarm/sog'liq ranglari (Monitoring, Raqamli egizak). Panel ish joyiga modul manifestidagi `workspaces` bo'yicha
  chiqadi; Layout/Modeling/Animation da hammasi. Sath ish joylarida faqat Sath va Bonsai interfeysi. Blender ning
  Sculpting/UV/Texture/Shading/Rendering/Compositing/Geometry Nodes ish joylari yo'q, Scripting — faqat
  Preferences → Interface → Developer Extras bilan. Eski faylda: Sath menyusi → «Ish joylarini tiklash»
  (`sath.reset_workspaces`, «Qaytadan qurish» — teglilarni yangidan).
- **Ranglar va tema:** 3D diff (yashil/sariq) va alarm (ustuvorlik bo'yicha; normal — kulrang) ranglari web
  bilan bir xil — manba `web/src/ui/tokens.ts`, `python desktop/build/gen_tokens.py` → `sath/core/tokens.py`
  va `template/Sath/theme_sath.xml` (Blender Dark + tanlov, viewport foni, gizmo o'qlari); CI `--check`.
- **Yorliq:** `Ctrl+Shift+G` — «Sath» menyusi (3D View va Object Mode; Object Mode dagi standart «faol obyektni
  kolleksiyaga qo'shish» Object → Collection menyusida qoladi).
```

- [ ] **Step 3: «Tuzilma»** — `core/` qatoriga `tokens.py` (web tokenlari, generatsiya), `keys.py` (yorliqlar va to'qnashuv qoidalari), `budget.py` (spec §5 byudjetlari) qo'shing; yangi qator:

```markdown
- `template/` — Sath app template: `Sath/__init__.py` (ilgaklar, `sath.reset_workspaces`), `Sath/workspaces.py`
  (ish joylari, `ensure`/`finish`), `Sath/theme_sath.xml` (generatsiya), `setup_bundle.py` (tema, startup.blend)
```

- [ ] **Step 4: «Testlar»** — pytest ro'yxatiga `tokens, workspaces, keys, budget`; headless soni `25` va yangi `workspaces` (template ish joylari, tema), `keymap` (Blender standart + Bonsai bilan to'qnashuv), `budgets` (register < 150 ms, og'ir importlar yo'q, perf logi); qo'shimcha qator:

```markdown
  Oynali (lokal, CI da emas): `python desktop/tests/run_gui_workspaces.py [--bundle <stage>]` — ochilganda BIM,
  SCADA/Simulation, Graph editor; bundle: `python desktop/tests/bundle_check.py`.
- Unumdorlik: `python desktop/tests/perf_baseline.py --bundle <stage> --check` → `docs/benchmark-desktop.md`
  (P0 bilan taqqoslash, spec §5 byudjetlari; har ishga tushishda `[sath] register … ms` logi).
```

(eski `- Unumdorlik: …` qatorini shu bilan almashtiring.)

- [ ] **Step 5: «Sinalgan»** qatorini haqiqiy natija bilan yangilang (oldingisi «Avval sinalgan» ga emas — o'chiriladi, chunki 2026-10-08 sanali):

```markdown
Sinalgan: <sana>, Blender 5.2.2, Bonsai 0.9.0, FreeCAD siz — headless 25/25, FAIL 0, SKIP 0 (`SATH_REQUIRE_NO_SKIP=1`); GUI ish joylari (repo va bundle) [GUI-OK]; bundle_check [BUNDLE-OK], stage <N> MB; byudjetlar: register <x> ms, sovuq start <r>x, RSS +<d> MB, og'ir importlar yo'q (`docs/benchmark-desktop.md`).
```

- [ ] **Step 6: Yakuniy tekshiruv** (pastdagi «Yakuniy tekshiruv» bo'limi) — hammasi yashil bo'lgach Step 5 dagi raqamlarni qo'ying; `git ls-files --eol desktop/blender/README.md` → `i/crlf w/crlf`; `git diff --stat` — faqat o'zgargan qatorlar.

- [ ] **Step 7: Commit**

```bash
git add desktop/blender/README.md
git commit -m "docs(UI): addon README — ish joylari, tokenlar va tema, Ctrl+Shift+G, P4 testlari va byudjetlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Yakuniy tekshiruv

```powershell
.venv\Scripts\python.exe desktop/build/sync_blender.py --check
.venv\Scripts\python.exe desktop/build/gen_tokens.py --check                  # web tokenlari ↔ desktop
.venv\Scripts\python.exe -m pytest -q desktop/tests                           # tokens, workspaces, keys, budget, pure, ges_kinds …
.venv\Scripts\ruff.exe check server sim desktop common
$env:GES_BLENDER="$HOME\Tools\blender-5.2\blender.exe"; $env:SATH_REQUIRE_NO_SKIP="1"; .\desktop\tests\run_blender_tests.ps1   # 25 ta, FAIL 0, SKIP 0
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test workspaces
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test keymap --bonsai
& $env:GES_BLENDER -b --python desktop/tests/blender_headless.py -- --test budgets
.venv\Scripts\python.exe desktop/tests/run_gui_workspaces.py                  # oynali, repo: [GUI-OK]
.venv\Scripts\python.exe desktop/build/build_blender_bundle.py --no-zip        # stage: <N> MB (FreeCAD siz)
.venv\Scripts\python.exe desktop/tests/bundle_check.py                        # [BUNDLE-OK]
.venv\Scripts\python.exe desktop/tests/run_gui_workspaces.py --bundle desktop/build/_work/sath-bundle/Sath   # BIM da ochiladi: [GUI-OK]
.venv\Scripts\python.exe desktop/tests/perf_baseline.py --n 2000 --bundle desktop/build/_work/sath-bundle/Sath --check   # exit 0
```

Qo'lda (GUI, bundle `Sath.exe`): BIM ish joyida ochiladi; tablar BIM, Compare, Simulation, SCADA, Layout, Modeling, Animation; SCADA ga o'tganda N-panelda «GES obyektlari» yo'q; Simulation ga birinchi o'tganda pastda Graph editor; Ctrl+Shift+G (obyekt tanlangan holda ham) «Sath» menyusini ochadi; Edit → Preferences → Themes — Sath temasi (faol obyekt to'q sariq #f5a623).

## O'z-o'zini tekshirish (spec bo'yicha)

**Qamrov:**
- §5 `template/Sath/__init__.py` + yangi `workspaces.py`, `load_factory_startup_post` da idempotent → Task 3 (`ensure`, ilgak, headless `_check` + `rep == {…}`).
- BIM (Outliner, Properties, N-panel), Compare (ikki VIEW_3D), Simulation (Timeline, Graph), SCADA (Object-colour shading, ISA-101 kulrang asos) → Task 3 builderlar, Task 5 GUI (Graph — msgbus).
- `ws["sath_ws"]` ↔ manifest `workspaces` → Task 3 `registry.WORKSPACE_TAG/WORKSPACES`, `panels.in_workspace`, sof test (barcha manifest qiymatlari = 4 teg).
- Sculpting/UV/Texture/Shading/Rendering/Compositing/GeoNodes o'chiriladi, Scripting faqat developer UI da → Task 3 `REMOVE/DEV_ONLY`, headless `dev=False/True`, Task 7 setup_bundle (startup.blend da Scripting saqlanadi).
- `use_filter_by_owner=True`, `owner_ids` = sath, bonsai → Task 3 `owner_ids`, Task 7 skrinshot.
- `sath.reset_workspaces` → Task 3 operator (+ `rebuild`), menyu bandi; xavf «mavjud foydalanuvchilarda faqat reset bilan» → README (Task 9).
- Tema: Blender Dark asosida `template/Sath/theme_sath.xml`, `setup_bundle.py` da qo'llanadi → Task 1 (generatsiya), Task 7 (execute_preset, bundle_check).
- `core/tokens.py` `tokens.ts` dan generatsiya, sync + CI `--check`, 3D diff/alarm ranglari web bilan bir xil → Task 1, Task 2.
- Keymap: Ctrl+Shift+G saqlanadi, modullar `api.ui.keymap()` orqali, headless konflikt testi → Task 4 (+ Task 5 GUI ustuvorlik).
- Byudjetlar: register < 150 ms (har modul `perf_counter` bilan log) → Task 6 (`register_line`, `budgets`); og'ir importlar funksiya ichida (ifcopenshell, ezdxf, assimp allaqachon; numpy — Task 6) → `budgets`/`heavy`; sovuq start ≤ 1.2×, RSS ≤ +50 MB → Task 8 `--check`.
- «Bosqichlar» P4: «bundle ~0.9 GB kichik» → Task 7 `check_stage` + Task 8 bundle qatori (0.3.0: 2392 MB, FreeCAD 935 MB); «BIM workspace da ochiladi» → Task 7 Step 6 (`run_gui_workspaces.py --bundle`); «byudjetlar log da va bajarilgan» → Task 6 log + Task 8 doc va xulosa.
- «Tekshirish» bo'limidagi `build_blender_bundle.py --no-zip` (workspace lar, perf log, FreeCAD siz GES obyektlari) → Task 7 Step 4–6 (GES obyektlari P2 da tekshirilgan, bundle_check addonlar yoqilganini tasdiqlaydi).

**Placeholder tekshiruvi:** Task 9 dagi `<sana>`, `<N>`, `<x>`, `<r>`, `<d>` — o'lchov natijalari (Task 7/8 dan) bilan to'ldiriladi, ataylab. Qolgan barcha kod to'liq; README matnidagi almashtirishlar aniq jumlalar bilan berilgan.

**Tiplar va nomlar izchilligi:** `registry.WORKSPACE_TAG/WORKSPACES` ↔ template `TAG/ORDER` (sof test) ↔ `bundle_check` (`registry.WORKSPACES`); `workspaces.ensure → {"created","removed","kept"}` ↔ operator hisobi va headless `rep ==`; `workspaces.TODO` ↔ `_simulation`/`finish` ↔ headless va GUI; `panels.in_workspace(manifest, ws)` ↔ `visible`, headless, GUI; `tokens.rgba/pal_rgba/parse/PAL/THEMES` ↔ flows, workspaces testi, bundle_check, `THEME_KEYS`; `keys.add → (kmi, off)` ↔ `ui._keymap_offs`, `api.ui.keymap`; `keys.Chord` maydonlari ↔ `chord/chord_from_event/conflicts` va testlar; `budget.check(*, register_ms, cold_ratio, rss_delta_mb, heavy)` ↔ perf_baseline va test; `perf_blender` teglari `BUDGET/WS/PERF` ↔ `budgets.py` va `perf_baseline.tagged`.

## Keyingi rejalar (shu spec bo'yicha)

- Poydevor yakunlandi — 2-quyi-loyiha «Jonli egizak (SCADA) moduli» uchun alohida spec (SCADA ish joyi va `ALARM_PRIORITIES` ranglari tayyor: ISA-101 shakllari, 1 Hz miltillash, alarm ro'yxati → kamera).
- 3-quyi-loyiha Compare ish joyini to'ldiradi (ikki 3D sinxron kamera, farq ro'yxati, slayder) — ish joyi va `review` moduli tegi tayyor.
- Ochiq kuzatuv: GUI testlarini CI ga olib chiqish (Windows runner da oynali Blender barqarorligi tekshirilgach); `use_filter_by_owner` bilan uchinchi tomon Sath modullari (owner = `sath` paketi ichida — filtrdan o'tadi).
