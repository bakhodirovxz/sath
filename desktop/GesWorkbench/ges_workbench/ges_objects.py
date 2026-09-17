"""GES parametrik obyektlari (FeaturePython): To'g'on, Bosimli quvur, Turbina agregati, Suv tashlagich,
Mashina zali, Transformator, Suv qabul qilgich (web qoralama turlari bilan bir xil Pset_GES_* — ikkala mijozda
yaratilgan element bir xil ko'rinadi va simulyatsiyalar bir xil o'qiydi).

Har obyekt:
- geometriyasini o'z parametrlaridan hisoblaydi (Part shakl),
- IfcType va IfcProperties (Pset_GES_*) ga ega — IFC eksportda class va xususiyatlar saqlanadi,
- xususiyatlar 4-bosqichdagi simulyatsiya (ges_sim) uchun kirish ma'lumot bo'ladi.
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD
import Part

RES = Path(__file__).resolve().parents[1] / "resources"
ICON = str(RES / "ges.svg")
ICONS = {
    "GES_Dam": "dam",
    "GES_Penstock": "penstock",
    "GES_Turbine": "turbine",
    "GES_Spillway": "spillway",
    "GES_Powerhouse": "powerhouse",
    "GES_Transformer": "transformer",
    "GES_Intake": "intake",
}
CONCRETE = ["B10", "B15", "B20", "B25", "B30", "B35", "B40", "B45", "B50", "B60"]
MM = 1000.0  # FreeCAD ichki birligi mm; parametrlar metrda


def _pset(obj, pset: str, props: dict[str, tuple[str, object]]) -> None:
    """Arch/BIM eksporteri tushunadigan formatda: IfcProperties[name] = "Pset;;IfcType;;value"."""
    data = dict(obj.IfcProperties) if hasattr(obj, "IfcProperties") else {}
    for name, (ifc_type, value) in props.items():
        data[name] = f"{pset};;{ifc_type};;{value}"
    obj.IfcProperties = data


class _GesBase:
    ifc_type = "Building Element Proxy"
    pset = "Pset_GES_Object"

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty(
            "App::PropertyString", "IfcType", "IFC", "IFC klassi"
        ).IfcType = self.ifc_type
        obj.addProperty("App::PropertyMap", "IfcProperties", "IFC", "IFC xususiyatlar to'plamlari")
        self.add_properties(obj)

    def add_properties(self, obj):
        raise NotImplementedError

    def sim_properties(self, obj) -> dict[str, tuple[str, object]]:
        return {}

    def execute(self, obj):
        obj.Shape = self.build_shape(obj)
        _pset(obj, self.pset, self.sim_properties(obj))

    def build_shape(self, obj):
        raise NotImplementedError

    def onChanged(self, obj, prop):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class Dam(_GesBase):
    ifc_type = "Wall"
    pset = "Pset_GES_Dam"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Length", "GES", "Gerbi uzunligi").Length = 60 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 20 * MM
        obj.addProperty("App::PropertyLength", "CrestWidth", "GES", "Gerbi kengligi").CrestWidth = (
            6 * MM
        )
        obj.addProperty("App::PropertyLength", "BaseWidth", "GES", "Asos kengligi").BaseWidth = (
            16 * MM
        )
        obj.addProperty("App::PropertyEnumeration", "DamType", "GES", "Turi").DamType = [
            "Gravitatsion",
            "Arkali",
            "Tuproq",
            "Tosh-tuproq",
        ]
        obj.addProperty(
            "App::PropertyFloat", "CrestElevation", "GES", "Gerbi belgisi, m (abs)"
        ).CrestElevation = 0.0
        obj.addProperty(
            "App::PropertyFloat", "BaseElevation", "GES", "Tag belgisi, m (abs)"
        ).BaseElevation = 0.0
        obj.addProperty(
            "App::PropertyEnumeration", "ConcreteClass", "GES", "Beton klassi (KMK 2.03.01)"
        ).ConcreteClass = ["B15", "B20", "B25", "B30", "B35", "B40"]
        obj.ConcreteClass = "B20"

    def build_shape(self, obj):
        L, H, cw, bw = obj.Length.Value, obj.Height.Value, obj.CrestWidth.Value, obj.BaseWidth.Value
        # Trapetsiya kesim (oqim yo'nalishi Y): asos keng, gerb tor; uzunlik X bo'ylab
        profile = Part.makePolygon(
            [
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, bw, 0),
                FreeCAD.Vector(0, bw - (bw - cw) / 2, H),
                FreeCAD.Vector(0, (bw - cw) / 2, H),
                FreeCAD.Vector(0, 0, 0),
            ]
        )
        return Part.Face(profile).extrude(FreeCAD.Vector(L, 0, 0))

    def sim_properties(self, obj):
        return {
            "Turi": ("IfcLabel", obj.DamType),
            "Balandlik_m": ("IfcReal", obj.Height.Value / MM),
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "GerbBelgisi_m": ("IfcReal", obj.CrestElevation),
            "GerbKengligi_m": ("IfcReal", obj.CrestWidth.Value / MM),
            "TagKengligi_m": ("IfcReal", obj.BaseWidth.Value / MM),
            "TagBelgisi_m": ("IfcReal", getattr(obj, "BaseElevation", 0.0)),
            "BetonKlassi": ("IfcLabel", getattr(obj, "ConcreteClass", "B20")),
        }


class Penstock(_GesBase):
    ifc_type = "Pipe Segment"
    pset = "Pset_GES_Penstock"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Length", "GES", "Uzunligi").Length = 20 * MM
        obj.addProperty("App::PropertyLength", "Diameter", "GES", "Ichki diametri").Diameter = (
            2.4 * MM
        )
        obj.addProperty(
            "App::PropertyLength", "WallThickness", "GES", "Devor qalinligi"
        ).WallThickness = 0.02 * MM
        obj.addProperty(
            "App::PropertyFloat", "Roughness", "GES", "G'adir-budirlik, mm (Darcy-Weisbach)"
        ).Roughness = 0.1
        obj.addProperty("App::PropertyEnumeration", "Material", "GES", "Material").Material = [
            "Po'lat",
            "Temir-beton",
            "GRP",
        ]

    def build_shape(self, obj):
        r, t, L = obj.Diameter.Value / 2, obj.WallThickness.Value, obj.Length.Value
        outer = Part.makeCylinder(r + t, L)
        inner = Part.makeCylinder(r, L)
        return outer.cut(inner)

    def sim_properties(self, obj):
        return {
            "Diametr_m": ("IfcReal", obj.Diameter.Value / MM),
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "Gadirbudirlik_mm": ("IfcReal", obj.Roughness),
            "Material": ("IfcLabel", obj.Material),
        }


class TurbineUnit(_GesBase):
    ifc_type = "Flow Moving Device"
    pset = "Pset_GES_Turbine"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyEnumeration", "TurbineType", "GES", "Turi").TurbineType = [
            "Francis",
            "Kaplan",
            "Pelton",
            "Bulb",
        ]
        obj.addProperty(
            "App::PropertyFloat", "RatedPower", "GES", "Nominal quvvat, MW"
        ).RatedPower = 25.0
        obj.addProperty(
            "App::PropertyFloat", "RatedHead", "GES", "Hisobiy napor, m"
        ).RatedHead = 45.0
        obj.addProperty(
            "App::PropertyFloat", "RatedFlow", "GES", "Hisobiy sarf, m3/s"
        ).RatedFlow = 62.0
        obj.addProperty(
            "App::PropertyFloat", "Efficiency", "GES", "Maksimal FIK, 0..1"
        ).Efficiency = 0.92
        obj.addProperty(
            "App::PropertyLength", "RunnerDiameter", "GES", "Ish g'ildiragi diametri"
        ).RunnerDiameter = 3 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Agregat balandligi").Height = (
            4 * MM
        )

    def build_shape(self, obj):
        d, h = obj.RunnerDiameter.Value, obj.Height.Value
        spiral = Part.makeTorus(d * 0.7, d * 0.2)
        shaft = Part.makeCylinder(d * 0.12, h)
        casing = Part.makeCylinder(d * 0.5, h * 0.4, FreeCAD.Vector(0, 0, h * 0.6))
        return spiral.fuse(shaft).fuse(casing)

    def sim_properties(self, obj):
        return {
            "Turi": ("IfcLabel", obj.TurbineType),
            "Quvvat_MW": ("IfcReal", obj.RatedPower),
            "Napor_m": ("IfcReal", obj.RatedHead),
            "Sarf_m3s": ("IfcReal", obj.RatedFlow),
            "FIK": ("IfcReal", obj.Efficiency),
        }


class Spillway(_GesBase):
    ifc_type = "Slab"
    pset = "Pset_GES_Spillway"

    def add_properties(self, obj):
        obj.addProperty(
            "App::PropertyLength", "Width", "GES", "Kengligi (oqimga ko'ndalang)"
        ).Width = 12 * MM
        obj.addProperty(
            "App::PropertyLength", "Length", "GES", "Uzunligi (oqim bo'ylab)"
        ).Length = 10 * MM
        obj.addProperty("App::PropertyLength", "Thickness", "GES", "Qalinligi").Thickness = 1 * MM
        obj.addProperty(
            "App::PropertyFloat", "CrestElevation", "GES", "Ostona belgisi, m"
        ).CrestElevation = 0.0
        obj.addProperty(
            "App::PropertyFloat",
            "DischargeCoefficient",
            "GES",
            "Sarf koeffitsienti m (Q = m·b·√(2g)·H^1.5)",
        ).DischargeCoefficient = 0.49
        obj.addProperty("App::PropertyInteger", "Gates", "GES", "Darvozalar soni").Gates = 2

    def build_shape(self, obj):
        return Part.makeBox(obj.Width.Value, obj.Length.Value, obj.Thickness.Value)

    def sim_properties(self, obj):
        return {
            "Kenglik_m": ("IfcReal", obj.Width.Value / MM),
            "OstonaBelgisi_m": ("IfcReal", obj.CrestElevation),
            "SarfKoeff": ("IfcReal", obj.DischargeCoefficient),
            "Darvozalar": ("IfcInteger", obj.Gates),
        }


class Powerhouse(_GesBase):
    """Mashina zali — karkas bino (quti), agregatlar soni va pol belgisi; web «powerhouse» bilan bir xil."""

    ifc_type = "Building Element Proxy"
    pset = "Pset_GES_Powerhouse"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Length", "GES", "Uzunligi (X)").Length = 40 * MM
        obj.addProperty("App::PropertyLength", "Width", "GES", "Kengligi (Y)").Width = 20 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 18 * MM
        obj.addProperty("App::PropertyInteger", "Units", "GES", "Agregatlar soni").Units = 2
        obj.addProperty(
            "App::PropertyFloat", "FloorElevation", "GES", "Pol belgisi, m (abs)"
        ).FloorElevation = 0.0
        obj.addProperty(
            "App::PropertyEnumeration", "ConcreteClass", "GES", "Beton klassi (karkas)"
        ).ConcreteClass = CONCRETE
        obj.ConcreteClass = "B25"

    def build_shape(self, obj):
        L, W, H = obj.Length.Value, obj.Width.Value, obj.Height.Value
        body = Part.makeBox(L, W, H, FreeCAD.Vector(-L / 2, -W / 2, 0))
        # tom — yengil qiya (gable) ko'rinish uchun uchburchak prizma
        t = H * 0.18
        roof = Part.Face(
            Part.makePolygon(
                [
                    FreeCAD.Vector(-L / 2, -W / 2, H),
                    FreeCAD.Vector(-L / 2, W / 2, H),
                    FreeCAD.Vector(-L / 2, 0, H + t),
                    FreeCAD.Vector(-L / 2, -W / 2, H),
                ]
            )
        ).extrude(FreeCAD.Vector(L, 0, 0))
        return body.fuse(roof)

    def sim_properties(self, obj):
        return {
            "Agregatlar": ("IfcInteger", obj.Units),
            "PolBelgisi_m": ("IfcReal", obj.FloorElevation),
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "Kenglik_m": ("IfcReal", obj.Width.Value / MM),
            "Balandlik_m": ("IfcReal", obj.Height.Value / MM),
            "BetonKlassi": ("IfcLabel", obj.ConcreteClass),
        }


class Transformer(_GesBase):
    """Kuch transformatori — bak + radiatorlar; quvvat/kuchlanish (IEC 60076-7 simulyatsiyasi uchun)."""

    ifc_type = "Transformer"
    pset = "Pset_GES_Transformer"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Length", "GES", "Uzunligi").Length = 6 * MM
        obj.addProperty("App::PropertyLength", "Width", "GES", "Kengligi").Width = 4 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 5 * MM
        obj.addProperty(
            "App::PropertyFloat", "RatedPower", "GES", "Nominal quvvat, MVA"
        ).RatedPower = 40.0
        obj.addProperty(
            "App::PropertyFloat", "VoltageHV", "GES", "Yuqori kuchlanish, kV"
        ).VoltageHV = 110.0
        obj.addProperty(
            "App::PropertyFloat", "VoltageLV", "GES", "Past kuchlanish, kV"
        ).VoltageLV = 10.5
        obj.addProperty(
            "App::PropertyEnumeration", "Cooling", "GES", "Sovitish turi (IEC 60076)"
        ).Cooling = ["ONAN", "ONAF", "OFAF", "ODAF"]
        obj.Cooling = "ONAF"

    def build_shape(self, obj):
        L, W, H = obj.Length.Value, obj.Width.Value, obj.Height.Value
        tank = Part.makeBox(L * 0.7, W, H * 0.8, FreeCAD.Vector(-L * 0.35, -W / 2, 0))
        shape = tank
        # radiatorlar (ikki yonda plastinalar)
        n = 5
        for i in range(n):
            x = -L * 0.3 + i * (L * 0.6 / (n - 1))
            for side in (-1, 1):
                rad = Part.makeBox(
                    L * 0.04,
                    L * 0.15,
                    H * 0.6,
                    FreeCAD.Vector(x, side * W / 2 + (0 if side > 0 else -L * 0.15), H * 0.1),
                )
                shape = shape.fuse(rad)
        # izolyatorlar (3 ta)
        for i in range(3):
            ins = Part.makeCylinder(
                W * 0.05, H * 0.2, FreeCAD.Vector(-L * 0.2 + i * L * 0.2, 0, H * 0.8)
            )
            shape = shape.fuse(ins)
        return shape

    def sim_properties(self, obj):
        return {
            "Quvvat_MVA": ("IfcReal", obj.RatedPower),
            "KuchlanishYuqori_kV": ("IfcReal", obj.VoltageHV),
            "KuchlanishPast_kV": ("IfcReal", obj.VoltageLV),
            "Sovitish": ("IfcLabel", obj.Cooling),
        }


class Intake(_GesBase):
    """Suv qabul qilgich (minora) — panjara/to'siq bilan; ostona belgisi va hisobiy sarf."""

    ifc_type = "Building Element Proxy"
    pset = "Pset_GES_Intake"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Width", "GES", "Kengligi (X)").Width = 8 * MM
        obj.addProperty("App::PropertyLength", "Depth", "GES", "Chuqurligi (Y)").Depth = 8 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 15 * MM
        obj.addProperty(
            "App::PropertyFloat", "SillElevation", "GES", "Ostona belgisi, m (abs)"
        ).SillElevation = 0.0
        obj.addProperty(
            "App::PropertyFloat", "DesignFlow", "GES", "Hisobiy sarf, m3/s"
        ).DesignFlow = 120.0
        obj.addProperty("App::PropertyInteger", "Openings", "GES", "Teshiklar soni").Openings = 2
        obj.addProperty(
            "App::PropertyFloat", "ScreenBarSpacing", "GES", "Panjara oralig'i, mm"
        ).ScreenBarSpacing = 100.0

    def build_shape(self, obj):
        W, D, H = obj.Width.Value, obj.Depth.Value, obj.Height.Value
        tower = Part.makeBox(W, D, H, FreeCAD.Vector(-W / 2, -D / 2, 0))
        # oqim tomon (−Y) teshiklar
        n = max(1, obj.Openings)
        ow = W * 0.7 / n
        for i in range(n):
            x = -W * 0.35 + i * (W * 0.7 / n) + ow * 0.1
            hole = Part.makeBox(ow * 0.8, D * 0.3, H * 0.35, FreeCAD.Vector(x, -D / 2 - 1, H * 0.1))
            tower = tower.cut(hole)
        return tower

    def sim_properties(self, obj):
        return {
            "OstonaBelgisi_m": ("IfcReal", obj.SillElevation),
            "HisobiySarf_m3s": ("IfcReal", obj.DesignFlow),
            "Teshiklar": ("IfcInteger", obj.Openings),
            "PanjaraOraligi_mm": ("IfcReal", obj.ScreenBarSpacing),
            "Balandlik_m": ("IfcReal", obj.Height.Value / MM),
        }


COLORS = {
    "Dam": (0.72, 0.70, 0.66),  # beton
    "Penstock": (0.45, 0.52, 0.60),  # po'lat
    "TurbineUnit": (0.22, 0.65, 0.72),  # teal
    "Spillway": (0.80, 0.80, 0.78),
    "Powerhouse": (0.69, 0.63, 0.53),
    "Transformer": (0.73, 0.53, 0.15),
    "Intake": (0.49, 0.61, 0.71),
}


class _ViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self
        kind = type(vobj.Object.Proxy).__name__
        if kind in COLORS:
            vobj.ShapeColor = COLORS[kind]

    def getIcon(self):
        return ICON

    def attach(self, vobj):
        self.Object = vobj.Object

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


OBJECTS = {
    "GES_Dam": ("To'g'on", Dam),
    "GES_Penstock": ("Bosimli quvur", Penstock),
    "GES_Turbine": ("Turbina agregati", TurbineUnit),
    "GES_Spillway": ("Suv tashlagich", Spillway),
    "GES_Powerhouse": ("Mashina zali", Powerhouse),
    "GES_Transformer": ("Transformator", Transformer),
    "GES_Intake": ("Suv qabul qilgich", Intake),
}
COMMAND_NAMES = list(OBJECTS)


def make(kind: str, name: str | None = None):
    """Python API: ges_objects.make("GES_Dam", "To'g'on 1")."""
    label, cls = OBJECTS[kind]
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("GES")
    obj = doc.addObject("Part::FeaturePython", (name or label).replace(" ", "_"))
    obj.Label = name or label  # Label IFC Name bo'lib chiqadi (bo'shliq va apostrof bilan)
    cls(obj)
    if FreeCAD.GuiUp:
        _ViewProvider(obj.ViewObject)
    doc.recompute()
    return obj


class _MakeCommand:
    def __init__(self, kind: str):
        self.kind = kind

    def GetResources(self):
        label = OBJECTS[self.kind][0]
        return {
            "Pixmap": str(RES / f"{ICONS.get(self.kind, 'ges')}.svg"),
            "MenuText": label,
            "ToolTip": f"{label} qo'shish (parametrlari xususiyatlar panelida)",
        }

    def Activated(self):
        make(self.kind)

    def IsActive(self):
        return True


def register() -> None:
    import FreeCADGui

    for kind in OBJECTS:
        FreeCADGui.addCommand(kind, _MakeCommand(kind))
