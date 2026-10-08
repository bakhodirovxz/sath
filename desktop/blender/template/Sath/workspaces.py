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
    order = [have[t].name for t in ORDER if t in have] + [n for n in KEEP if n in data.workspaces]
    if not bpy.app.background:  # oynasiz tab tartibi yo'q (reorder_to_front faol ish joyini ko'chiradi)
        _reorder_chain(order, have["BIM"].name if activate and "BIM" in have else None)
    if activate and "BIM" in have:
        # oyna qayta olinadi: startup ilgagida context.window None bo'lishi mumkin, yuqoridagi win eskirgan bo'lsa
        cwm = bpy.context.window_manager
        target = bpy.context.window or (cwm.windows[0] if cwm is not None and cwm.windows else win)
        target.workspace = have["BIM"]
    return report


CHAIN_DONE = [False]  # GUI sinovi: tab tartibi zanjiri tugadimi
_CHAIN_STEP_S = 0.05
_chain_gen = [0]  # avlod: yangi zanjir, fayl yuklash (load_pre) yoki unregister eskisini to'xtatadi


def cancel_chain() -> None:
    _chain_gen[0] += 1


def _reorder_chain(names, final) -> None:
    """Tab tartibi: workspace.reorder_to_front oynada FAOL ish joyini ko'chiradi (temp_override(workspace=)
    e'tiborga olinmaydi), Window.workspace esa keyingi siklda qo'llanadi — shuning uchun taymer zanjiri:
    teskari tartibda har ish joyini faol qilib, keyingi taktda oldinga suramiz; oxirida `final` (yoki avvalgisi)."""
    import bpy

    CHAIN_DONE[0] = False
    _chain_gen[0] += 1
    gen = _chain_gen[0]
    wm = bpy.context.window_manager
    if wm is None or not wm.windows:
        return
    before = wm.windows[0].workspace.name if wm.windows[0].workspace is not None else None
    queue = list(names)  # pop() oxiridan oladi — teskari tartib
    state = {"want": None, "tries": 0}

    def step():
        if gen != _chain_gen[0]:
            return None  # bekor qilindi / almashtirildi
        cwm = bpy.context.window_manager
        if cwm is None or not cwm.windows:
            return None
        win = cwm.windows[0]
        if state["want"] is None:
            if not queue:
                end = bpy.data.workspaces.get(final or before or "")
                if end is not None:
                    win.workspace = end
                CHAIN_DONE[0] = True
                return None
            state["want"], state["tries"] = queue.pop(), 0
            ws = bpy.data.workspaces.get(state["want"])
            if ws is None:
                state["want"] = None
                return _CHAIN_STEP_S
            win.workspace = ws
            return _CHAIN_STEP_S
        if win.workspace is None or win.workspace.name != state["want"]:
            state["tries"] += 1  # almashish hali qo'llanmagan yoki boshqa taymer (BIM faollash) aralashdi
            if state["tries"] > 20:
                state["want"] = None
                return _CHAIN_STEP_S
            ws = bpy.data.workspaces.get(state["want"])
            if ws is not None:
                win.workspace = ws
            return _CHAIN_STEP_S
        with bpy.context.temp_override(window=win):
            bpy.ops.workspace.reorder_to_front()
        state["want"] = None
        return _CHAIN_STEP_S

    bpy.app.timers.register(step, first_interval=_CHAIN_STEP_S, persistent=False)


def finish(win) -> bool:
    """Oynada ko'rinayotgan ish joyining kechiktirilgan qadamini bajaradi (msgbus: Window.workspace).
    True — o'zgardi. Area turi faqat ko'rinayotgan ekranda almashadi, shuning uchun aynan shu yerda."""
    ws = win.workspace
    if ws is None or not ws.get(TODO):
        return False
    screen = win.screen
    if screen is None or screen.as_pointer() not in {s.as_pointer() for s in ws.screens}:
        return False  # oyna hali boshqa ekranni ko'rsatmoqda (almashish keyingi siklda) — unga tegilmaydi
    if ws.get(TAG) == "Simulation":
        v = _areas(screen, "VIEW_3D")
        if len(v) >= 2:
            min(v, key=lambda a: a.y).ui_type = "FCURVES"  # pastki (split dagi yangi) area → Graph editor
        if not _areas(screen, "GRAPH_EDITOR"):
            if len(v) >= 2:
                return False  # hali qo'llanmadi — keyingi o'tishda yana urinadi
            # ikkita 3D yo'q (foydalanuvchi o'zgartirgan) va Graph ham yo'q — qayta urinishning foydasi yo'q
    del ws[TODO]
    return True
