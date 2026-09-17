"""AutoCAD ga o'rgangan muhandislar uchun FreeCAD sozlamalari (bir marta qo'llanadi)."""

import FreeCAD

P = "User parameter:BaseApp/Preferences/"

# Ishchilarga ko'rinadigan workbench lar — qolganlari yashiriladi
WORKBENCHES = [
    "BIMWorkbench",
    "GesWorkbench",
    "DraftWorkbench",
    "PartWorkbench",
    "PartDesignWorkbench",
    "SketcherWorkbench",
    "TechDrawWorkbench",
    "SpreadsheetWorkbench",
    "FemWorkbench",
]


def apply_pack(name: str = "FreeCAD Dark") -> bool:
    """FreeCAD ning o'z "preference pack" ini (data/Gui/PreferencePacks/<nom>/<nom>.cfg) qo'llaydi —
    tema, ranglar, uslub. Python API yo'q, shuning uchun XML ni o'zimiz o'qib parametrlarga yozamiz."""
    import os
    from xml.etree import ElementTree as ET  # FreeCAD ning o'z fayli — ishonchli manba

    path = os.path.join(FreeCAD.getResourceDir(), "Gui", "PreferencePacks", name, name + ".cfg")
    if not os.path.exists(path):
        return False
    setters = {
        "FCText": lambda g, n, v: g.SetString(n, v or ""),
        "FCInt": lambda g, n, v: g.SetInt(n, int(v)),
        "FCUInt": lambda g, n, v: g.SetUnsigned(n, int(v)),
        "FCBool": lambda g, n, v: g.SetBool(n, v in ("1", "true", "True")),
        "FCFloat": lambda g, n, v: g.SetFloat(n, float(v)),
    }

    def walk(el, parts):
        for child in el:
            if child.tag == "FCParamGroup":
                walk(child, parts + [child.get("Name")])
            elif child.tag in setters:
                # Root/BaseApp/Preferences/... → User parameter:BaseApp/Preferences/...
                if len(parts) >= 2 and parts[0] == "Root":
                    grp = FreeCAD.ParamGet("User parameter:" + "/".join(parts[1:]))
                    value = child.get("Value") if child.tag != "FCText" else (child.text or "")
                    try:
                        setters[child.tag](grp, child.get("Name"), value)
                    except (TypeError, ValueError):
                        pass

    walk(ET.parse(path).getroot(), [])
    return True


def apply() -> None:
    # Qora tema — FreeCAD ning o'z "FreeCAD Dark" paketi (1.0/1.1)
    if not apply_pack("FreeCAD Dark"):
        main = FreeCAD.ParamGet(P + "MainWindow")
        main.SetString("Theme", "FreeCAD Dark")
    # Navigatsiya: CAD uslubi — o'rta tugma pan, g'ildirak zoom (kursorga), turntable orbit
    view = FreeCAD.ParamGet(P + "View")
    view.SetString("NavigationStyle", "Gui::CADNavigationStyle")
    view.SetBool("ZoomAtCursor", True)
    view.SetBool("InvertZoom", False)
    view.SetInt("OrbitStyle", 1)
    view.SetString("NewDocumentCameraOrientation", "Isometric")
    # Fon rangi — grafit, gradientsiz
    view.SetBool("Gradient", False)
    view.SetUnsigned("BackgroundColor", 0x1E1F22FF)
    # Birliklar: Building Euro (mm, m2, m3) — qurilish standarti
    # Birliklar: MeterDecimal — gidrotexnika uchun metr (1.1 da 5 = ImperialBuilding!)
    schemas = list(FreeCAD.Units.listSchemas()) if hasattr(FreeCAD, "Units") else []
    FreeCAD.ParamGet(P + "Units").SetInt(
        "UserSchema", schemas.index("MeterDecimal") if "MeterDecimal" in schemas else 0
    )
    # Boshlang'ich workbench — Sath (server, obyektlar); chizish uchun BIM ga o'tiladi
    FreeCAD.ParamGet(P + "General").SetString("AutoloadModule", "GesWorkbench")
    # Draft: ish tekisligi ko'rsatkichi (AutoCAD UCS ga o'xshash)
    FreeCAD.ParamGet(P + "Mod/Draft").SetBool("showPlaneTracker", True)
    FreeCAD.ParamGet(P + "Workbenches").SetString("Enabled", ",".join(WORKBENCHES))
    # Toolbarlar ko'rinsin (skript bilan ishga tushirilgan sessiyalar ularni yashirib qoldirishi mumkin)
    tb = FreeCAD.ParamGet("User parameter:BaseApp/MainWindow/Toolbars")  # Preferences ostida emas
    for name in (
        "File",
        "Edit",
        "View",
        "Workbench",
        "Structure",
        "Sath server",
        "GES obyektlari",
    ):
        tb.SetBool(name, True)
    FreeCAD.ParamGet(P + "Mod/Sath").SetBool("preset_applied", True)


def applied() -> bool:
    return FreeCAD.ParamGet(P + "Mod/Sath").GetBool("preset_applied", False)
