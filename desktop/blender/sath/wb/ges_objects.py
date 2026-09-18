"""GES parametrik obyektlari (FeaturePython): To'g'on, Bosimli quvur (to'g'ri/egri), Turbina agregati, Generator,
Chiqarish quvuri, Suv tashlagich, Mashina zali, Boshqaruv xonasi, Transformator, Suv qabul qilgich, Daryo oqimi
kanali (web qoralama turlari bilan bir xil Pset_GES_* — ikkala mijozda yaratilgan element bir xil ko'rinadi va
simulyatsiyalar bir xil o'qiydi).

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
    "GES_Generator": "turbine",
    "GES_DraftTube": "penstock",
    "GES_ControlRoom": "powerhouse",
    "GES_Tailrace": "spillway",
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


def penstock_path(length: float, inclination_deg: float, bend_radius: float, outlet_length: float) -> dict:
    """Egri quvur o'qi (birlik — chaqiruvchi birligi): kirish p0=(0,0,0) → qiya qism (u1) → yoy (R) → gorizontal +Y.
    Qaytaradi: p0, p1 (yoy boshi), pm (yoy o'rtasi), p2 (yoy oxiri), p3 (chiqish), u1, alpha (rad), l1.
    Blender tomonidagi physics.penstock_path bilan bir xil formulalar."""
    import math

    a = math.radians(inclination_deg)
    arc = bend_radius * a
    l1 = max(length * 0.1, length - outlet_length - arc)
    u1 = FreeCAD.Vector(0, math.cos(a), -math.sin(a))
    n1 = FreeCAD.Vector(0, math.sin(a), math.cos(a))  # u1 ga perpendikulyar, yuqoriga-oldinga
    p0 = FreeCAD.Vector(0, 0, 0)
    p1 = p0 + u1 * l1
    c = p1 + n1 * bend_radius
    p2 = c + FreeCAD.Vector(0, 0, -bend_radius)
    nm = (n1 + FreeCAD.Vector(0, 0, 1)).normalize()
    pm = c - nm * bend_radius
    p3 = p2 + FreeCAD.Vector(0, outlet_length, 0)
    return {"p0": p0, "p1": p1, "pm": pm, "p2": p2, "p3": p3, "u1": u1, "alpha": a, "l1": l1}


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
        # Egri variant: 0/0 — Z bo'ylab to'g'ri silindr (eski xatti-harakat); aks holda kirish (0,0,0) dan
        # gorizontaldan Inclination° pastga qiya qism, BendRadius yoy, +Y bo'ylab gorizontal chiqish qismi.
        obj.addProperty(
            "App::PropertyFloat", "Inclination", "GES", "Qiyalik, ° (gorizontaldan pastga; 0 — to'g'ri)"
        ).Inclination = 0.0
        obj.addProperty("App::PropertyLength", "BendRadius", "GES", "Tirsak radiusi").BendRadius = 8 * MM
        obj.addProperty(
            "App::PropertyLength", "OutletLength", "GES", "Gorizontal chiqish qismi uzunligi"
        ).OutletLength = 6 * MM

    def build_shape(self, obj):
        r, t, L = obj.Diameter.Value / 2, obj.WallThickness.Value, obj.Length.Value
        alpha = float(getattr(obj, "Inclination", 0.0) or 0.0)
        if alpha <= 0:
            outer = Part.makeCylinder(r + t, L)
            inner = Part.makeCylinder(r, L)
            return outer.cut(inner)
        pts = penstock_path(L, alpha, obj.BendRadius.Value, obj.OutletLength.Value)
        try:
            path = Part.Wire(
                [
                    Part.LineSegment(pts["p0"], pts["p1"]).toShape(),
                    Part.Arc(pts["p1"], pts["pm"], pts["p2"]).toShape(),
                    Part.LineSegment(pts["p2"], pts["p3"]).toShape(),
                ]
            )
            u1 = pts["u1"]
            outer = path.makePipeShell([Part.Wire(Part.makeCircle(r + t, pts["p0"], u1))], True, True)
            inner = path.makePipeShell([Part.Wire(Part.makeCircle(r, pts["p0"], u1))], True, True)
            return outer.cut(inner)
        except Exception:  # noqa: BLE001 — geometriya xatosi: to'g'ri quvurga qaytamiz
            outer = Part.makeCylinder(r + t, L)
            inner = Part.makeCylinder(r, L)
            return outer.cut(inner)

    def sim_properties(self, obj):
        return {
            "Diametr_m": ("IfcReal", obj.Diameter.Value / MM),
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "Gadirbudirlik_mm": ("IfcReal", obj.Roughness),
            "Material": ("IfcLabel", obj.Material),
            "Qiyalik_deg": ("IfcReal", float(getattr(obj, "Inclination", 0.0) or 0.0)),
            "TirsakRadiusi_m": ("IfcReal", obj.BendRadius.Value / MM),
            "ChiqishUzunligi_m": ("IfcReal", obj.OutletLength.Value / MM),
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
    """Mashina zali — karkas bino (quti yoki kesim: devorlari bo'sh, +X yon devori olib tashlangan — egizakda agregatlar
    ko'rinadi), agregatlar soni va pol belgisi; web «powerhouse» bilan bir xil."""

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
        obj.addProperty("App::PropertyEnumeration", "View", "GES", "Ko'rinish").View = [
            "Yopiq",
            "Kesim",
        ]

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
        if getattr(obj, "View", "Yopiq") != "Kesim":
            return body.fuse(roof)
        # kesim: ichi bo'sh (devor 0.6 m), +X yon devori va tomning yarmi olib tashlangan
        wall = 0.6 * MM
        inner = Part.makeBox(L - wall, W - 2 * wall, H + t, FreeCAD.Vector(-L / 2 + wall, -W / 2 + wall, wall))
        shell = body.fuse(roof).cut(inner)
        cut = Part.makeBox(L / 2 + 1, W + 2, H + t + 2, FreeCAD.Vector(0, -W / 2 - 1, wall))
        return shell.cut(cut)

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


class Generator(_GesBase):
    """Sinxron gidrogenerator — stator (qovurg'ali silindr), qo'zg'atgich qopqog'i, val; turbina ustiga o'rnatiladi.
    Aylanish tezligi n = 120·f/p (sinxron), FIK — temir (doimiy) + mis (∝P²) yo'qotishlar (IEEE Std 115)."""

    ifc_type = "Electric Generator"
    pset = "Pset_GES_Generator"

    def add_properties(self, obj):
        obj.addProperty(
            "App::PropertyFloat", "RatedPower", "GES", "Nominal to'liq quvvat, MVA"
        ).RatedPower = 30.0
        obj.addProperty("App::PropertyFloat", "Voltage", "GES", "Stator kuchlanishi, kV").Voltage = 10.5
        obj.addProperty(
            "App::PropertyFloat", "EfficiencyMax", "GES", "Nominal FIK, 0..1"
        ).EfficiencyMax = 0.985
        obj.addProperty(
            "App::PropertyFloat", "IronLossFrac", "GES", "Temir (doimiy) yo'qotish ulushi, 0..1"
        ).IronLossFrac = 0.4
        obj.addProperty("App::PropertyInteger", "Poles", "GES", "Qutblar soni").Poles = 24
        obj.addProperty("App::PropertyFloat", "Frequency", "GES", "Chastota, Hz").Frequency = 50.0
        obj.addProperty(
            "App::PropertyLength", "StatorDiameter", "GES", "Stator diametri"
        ).StatorDiameter = 6 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 3.5 * MM

    def build_shape(self, obj):
        d, h = obj.StatorDiameter.Value, obj.Height.Value
        stator = Part.makeCylinder(d / 2, h * 0.7)
        shape = stator
        # sovitish qovurg'alari (rotor aylanishi ko'rinishi uchun ham) — 12 ta radial plastina
        for i in range(12):
            rib = Part.makeBox(d * 0.08, d * 0.05, h * 0.7, FreeCAD.Vector(d / 2 - d * 0.02, -d * 0.025, 0))
            rib.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), i * 30)
            shape = shape.fuse(rib)
        cap = Part.makeCone(d * 0.35, d * 0.2, h * 0.2, FreeCAD.Vector(0, 0, h * 0.7))
        exciter = Part.makeCylinder(d * 0.15, h * 0.1, FreeCAD.Vector(0, 0, h * 0.9))
        shaft = Part.makeCylinder(d * 0.06, h * 0.15, FreeCAD.Vector(0, 0, -h * 0.15))
        return shape.fuse(cap).fuse(exciter).fuse(shaft)

    def sim_properties(self, obj):
        rpm = 120.0 * obj.Frequency / max(2, obj.Poles)
        return {
            "Quvvat_MVA": ("IfcReal", obj.RatedPower),
            "Kuchlanish_kV": ("IfcReal", obj.Voltage),
            "FIK": ("IfcReal", obj.EfficiencyMax),
            "TemirUlushi": ("IfcReal", obj.IronLossFrac),
            "Qutblar": ("IfcInteger", obj.Poles),
            "Chastota_Hz": ("IfcReal", obj.Frequency),
            "Aylanish_rpm": ("IfcReal", round(rpm, 2)),
        }


class DraftTube(_GesBase):
    """Chiqarish (so'rish) quvuri — turbina ostidan vertikal konus, tirsak, +Y bo'ylab kengayuvchi diffuzor.
    So'rish balandligi H_s (ish g'ildiragi o'qi − quyi byef) Thoma kavitatsiya koeffitsientini belgilaydi."""

    ifc_type = "Flow Segment"
    pset = "Pset_GES_DraftTube"

    def add_properties(self, obj):
        obj.addProperty(
            "App::PropertyLength", "InletDiameter", "GES", "Kirish diametri (ish g'ildiragi ostida)"
        ).InletDiameter = 3 * MM
        obj.addProperty("App::PropertyLength", "ConeHeight", "GES", "Konus balandligi").ConeHeight = 5 * MM
        obj.addProperty("App::PropertyLength", "OutletWidth", "GES", "Chiqish kengligi").OutletWidth = 8 * MM
        obj.addProperty(
            "App::PropertyLength", "OutletHeight", "GES", "Chiqish balandligi"
        ).OutletHeight = 4 * MM
        obj.addProperty(
            "App::PropertyLength", "DiffuserLength", "GES", "Diffuzor uzunligi (+Y)"
        ).DiffuserLength = 12 * MM
        obj.addProperty(
            "App::PropertyFloat", "SuctionHead", "GES", "So'rish balandligi H_s, m (ish g'ildiragi − quyi byef)"
        ).SuctionHead = 2.0

    def build_shape(self, obj):
        d, hc = obj.InletDiameter.Value, obj.ConeHeight.Value
        bw, bh, L = obj.OutletWidth.Value, obj.OutletHeight.Value, obj.DiffuserLength.Value
        # konus: yuqorida d/2, pastda d·0.75 (kengayuvchi), pastga qarab
        R = d * 0.75
        cone = Part.makeCone(R, d / 2, hc, FreeCAD.Vector(0, 0, -hc))
        # tirsak: konus tagidagi doira X o'qi atrofida (markaz (0, R, −hc)) 90° aylantiriladi → +Y ga buriladi
        disc = Part.Face(Part.Wire(Part.makeCircle(R, FreeCAD.Vector(0, 0, -hc), FreeCAD.Vector(0, 0, 1))))
        elbow = disc.revolve(FreeCAD.Vector(0, R, -hc), FreeCAD.Vector(1, 0, 0), 90)
        if elbow.BoundBox.ZMax > -hc + 1.0:  # noto'g'ri tomonga aylangan bo'lsa
            elbow = disc.revolve(FreeCAD.Vector(0, R, -hc), FreeCAD.Vector(1, 0, 0), -90)
        # diffuzor: kengayuvchi loft (kirish kvadrat ≈ 2R, chiqish bw×bh), tirsak oxiridan +Y
        y0 = R
        z0 = -hc - R
        s_in = 2 * R

        def rect(y, w, h):
            return Part.makePolygon(
                [
                    FreeCAD.Vector(-w / 2, y, z0 - h / 2),
                    FreeCAD.Vector(w / 2, y, z0 - h / 2),
                    FreeCAD.Vector(w / 2, y, z0 + h / 2),
                    FreeCAD.Vector(-w / 2, y, z0 + h / 2),
                    FreeCAD.Vector(-w / 2, y, z0 - h / 2),
                ]
            )

        diffuser = Part.makeLoft([rect(y0, s_in, s_in), rect(y0 + L, bw, bh)], True)
        # qismlar bir tekislikda tutashadi — bunday bool amallar OCC da buziladi/osiladi; kompaund yetarli
        return Part.makeCompound([cone, elbow, diffuser])

    def sim_properties(self, obj):
        return {
            "KirishDiametr_m": ("IfcReal", obj.InletDiameter.Value / MM),
            "KonusBalandligi_m": ("IfcReal", obj.ConeHeight.Value / MM),
            "ChiqishKenglik_m": ("IfcReal", obj.OutletWidth.Value / MM),
            "ChiqishBalandlik_m": ("IfcReal", obj.OutletHeight.Value / MM),
            "DiffuzorUzunligi_m": ("IfcReal", obj.DiffuserLength.Value / MM),
            "SorishBalandligi_m": ("IfcReal", obj.SuctionHead),
        }


class ControlRoom(_GesBase):
    """Boshqaruv (dispetcher) xonasi — SCADA; oynali quti (old tomon −Y)."""

    ifc_type = "Building Element Proxy"
    pset = "Pset_GES_ControlRoom"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Length", "GES", "Uzunligi (X)").Length = 12 * MM
        obj.addProperty("App::PropertyLength", "Width", "GES", "Kengligi (Y)").Width = 8 * MM
        obj.addProperty("App::PropertyLength", "Height", "GES", "Balandligi").Height = 4 * MM
        obj.addProperty(
            "App::PropertyFloat", "FloorElevation", "GES", "Pol belgisi, m (abs)"
        ).FloorElevation = 0.0
        obj.addProperty("App::PropertyInteger", "Operators", "GES", "Dispetcherlar soni").Operators = 2
        obj.addProperty(
            "App::PropertyInteger", "ScadaChannels", "GES", "SCADA kanallari soni"
        ).ScadaChannels = 256

    def build_shape(self, obj):
        L, W, H = obj.Length.Value, obj.Width.Value, obj.Height.Value
        room = Part.makeBox(L, W, H, FreeCAD.Vector(-L / 2, -W / 2, 0))
        # old tomonda (−Y) uzun oyna — mashina zaliga qaraydi
        win = Part.makeBox(L * 0.8, W * 0.1, H * 0.45, FreeCAD.Vector(-L * 0.4, -W / 2 - 1, H * 0.35))
        return room.cut(win)

    def sim_properties(self, obj):
        return {
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "Kenglik_m": ("IfcReal", obj.Width.Value / MM),
            "Balandlik_m": ("IfcReal", obj.Height.Value / MM),
            "PolBelgisi_m": ("IfcReal", obj.FloorElevation),
            "Dispetcherlar": ("IfcInteger", obj.Operators),
            "SCADA_Kanallar": ("IfcInteger", obj.ScadaChannels),
        }


class Tailrace(_GesBase):
    """Daryo oqimi (quyi byef kanali) — U-kesimli ochiq kanal, +Y yo'nalishda; Manning bo'yicha normal chuqurlik
    quyi byef sathini beradi: Q = (1/n)·A·R^(2/3)·√S."""

    ifc_type = "Civil Element"
    pset = "Pset_GES_Tailrace"

    def add_properties(self, obj):
        obj.addProperty("App::PropertyLength", "Width", "GES", "Kanal kengligi (X)").Width = 20 * MM
        obj.addProperty("App::PropertyLength", "Length", "GES", "Uzunligi (Y)").Length = 40 * MM
        obj.addProperty("App::PropertyLength", "Depth", "GES", "Devor balandligi").Depth = 6 * MM
        obj.addProperty(
            "App::PropertyLength", "WallThickness", "GES", "Devor/tag qalinligi"
        ).WallThickness = 0.8 * MM
        obj.addProperty("App::PropertyFloat", "BedSlope", "GES", "Tag nishabi S").BedSlope = 0.001
        obj.addProperty("App::PropertyFloat", "Manning", "GES", "Manning g'adir-budirligi n").Manning = 0.03
        obj.addProperty(
            "App::PropertyFloat", "BedElevation", "GES", "Tag belgisi, m (abs)"
        ).BedElevation = 0.0
        # Quyi byef reyting egri chizig'i: TW(Q) = TW_hisobiy + [y_n(Q) − y_n(Q_hisobiy)]  (Manning normal chuqurlik)
        obj.addProperty(
            "App::PropertyFloat", "DesignTailwater", "GES", "Hisobiy quyi byef sathi, m (abs)"
        ).DesignTailwater = 0.0
        obj.addProperty(
            "App::PropertyFloat", "DesignFlow", "GES", "Hisobiy sarf (barcha agregatlar), m3/s"
        ).DesignFlow = 100.0

    def build_shape(self, obj):
        W, L, D, t = obj.Width.Value, obj.Length.Value, obj.Depth.Value, obj.WallThickness.Value
        outer = Part.makeBox(W + 2 * t, L, D + t, FreeCAD.Vector(-W / 2 - t, 0, -t))
        inner = Part.makeBox(W, L + 2, D + 1, FreeCAD.Vector(-W / 2, -1, 0))
        return outer.cut(inner)

    def sim_properties(self, obj):
        return {
            "Kenglik_m": ("IfcReal", obj.Width.Value / MM),
            "Uzunlik_m": ("IfcReal", obj.Length.Value / MM),
            "Chuqurlik_m": ("IfcReal", obj.Depth.Value / MM),
            "Nishab": ("IfcReal", obj.BedSlope),
            "Manning_n": ("IfcReal", obj.Manning),
            "TagBelgisi_m": ("IfcReal", obj.BedElevation),
            "HisobiyQuyiByef_m": ("IfcReal", obj.DesignTailwater),
            "HisobiySarf_m3s": ("IfcReal", obj.DesignFlow),
        }


COLORS = {
    "Dam": (0.72, 0.70, 0.66),  # beton
    "Penstock": (0.45, 0.52, 0.60),  # po'lat
    "TurbineUnit": (0.22, 0.65, 0.72),  # teal
    "Spillway": (0.80, 0.80, 0.78),
    "Powerhouse": (0.69, 0.63, 0.53),
    "Transformer": (0.73, 0.53, 0.15),
    "Intake": (0.49, 0.61, 0.71),
    "Generator": (0.16, 0.45, 0.78),  # ko'k (rasmdagi kabi)
    "DraftTube": (0.20, 0.40, 0.70),
    "ControlRoom": (0.82, 0.82, 0.86),
    "Tailrace": (0.62, 0.62, 0.60),
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
    "GES_Generator": ("Generator", Generator),
    "GES_DraftTube": ("Chiqarish quvuri", DraftTube),
    "GES_ControlRoom": ("Boshqaruv xonasi", ControlRoom),
    "GES_Tailrace": ("Daryo oqimi kanali", Tailrace),
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
