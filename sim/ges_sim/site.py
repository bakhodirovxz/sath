"""Maydon pasporti (site profile): GES joylashgan yer va inshootlar sharoitlari — bir marta kiritiladi,
barcha simulyatsiyalarga avtomatik uzatiladi (formadagi «Maydondan» tugmasi / avtomatik to'ldirish).

Bo'limlar: seysmiklik va grunt, asos (tuproq), suv ombori, to'g'on, suv tashlagich, bosimli quvur,
quyi byef va daryo o'zani, inshootlarning suv sathidan balandligi, yonbag'irlar (ko'chki xavfi), loyqa.
"""

from __future__ import annotations

from . import materials
from .schema import Field
from .seepage import SOILS
from .seismic import GROUND

SITE_FIELDS: list[Field] = [
    # Seysmiklik va grunt
    Field(
        "intensity",
        "Seysmiklik (MSK-64)",
        "ball",
        type="select",
        default="8",
        options=(("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"), ("10", "10")),
        group="Seysmiklik va grunt",
        hint="KMK 2.01.03 xaritasi bo'yicha",
    ),
    Field(
        "ground",
        "Grunt turi (EC8)",
        type="select",
        default="B",
        options=tuple((k, v[0]) for k, v in GROUND.items()),
        group="Seysmiklik va grunt",
    ),
    Field(
        "soil",
        "Asos tuprog'i",
        type="select",
        default="gravel",
        options=tuple((k, v[0]) for k, v in SOILS.items()) + (("rock", "Qoya"),),
        group="Seysmiklik va grunt",
    ),
    Field(
        "k_m_s",
        "Filtratsiya koeffitsienti k",
        "m/s",
        default=1e-5,
        min=1e-12,
        group="Seysmiklik va grunt",
        hint="qum 1e-4…1e-3; alevrit 1e-6; gil 1e-9; qoya 1e-7…1e-8",
    ),
    Field(
        "friction",
        "Ishqalanish tgφ (asos–to'g'on)",
        "",
        default=0.7,
        min=0.2,
        max=1.2,
        step=0.05,
        group="Seysmiklik va grunt",
    ),
    Field("cohesion_kpa", "Ilashish c", "kPa", default=200, min=0, group="Seysmiklik va grunt"),
    Field(
        "allow_stress_mpa",
        "Ruxsat etilgan asos kuchlanishi",
        "MPa",
        default=4.0,
        min=0.1,
        step=0.1,
        group="Seysmiklik va grunt",
    ),
    Field(
        "groundwater_m",
        "Grunt suvlari sathi (mutlaq)",
        "m",
        default=0,
        group="Seysmiklik va grunt",
        hint="0 — noma'lum",
    ),
    # Suv ombori
    Field(
        "capacity_mcm", "To'liq sig'im (NPU)", "mln m³", default=480, min=0.1, group="Suv ombori"
    ),
    Field("dead_mcm", "O'lik hajm", "mln m³", default=60, min=0, group="Suv ombori"),
    Field("normal_level_m", "NPU (normal sath)", "m", default=905, group="Suv ombori"),
    Field("max_level_m", "FPU (majburiy sath)", "m", default=912, group="Suv ombori"),
    Field("dead_level_m", "O'lik sath", "m", default=870, group="Suv ombori"),
    Field("area_km2", "Ko'zgu yuzasi (NPU da)", "km²", default=40, min=0.01, group="Suv ombori"),
    Field(
        "seepage_m3s", "Filtratsion yo'qotish (sizish)", "m³/s", default=0, min=0, group="Suv ombori",
        hint="To'g'on va asos orqali doimiy yo'qotish; «Filtratsiya» simulyatsiyasi baholaydi",
    ),
    # Iqlim — bug'lanish (Hargreaves–Samani), muz qoplami (climate.py)
    Field("latitude_deg", "Geografik kenglik", "°", default=41.6, min=-90, max=90, group="Iqlim"),
    Field("t_mean_annual_c", "Yillik o'rtacha harorat", "°C", default=13, min=-30, max=40, group="Iqlim"),
    Field(
        "t_amplitude_c", "Yillik tebranish amplitudasi", "°C", default=14, min=0, max=40, group="Iqlim",
        hint="(iyul o'rtacha − yanvar o'rtacha) / 2",
    ),
    Field("diurnal_range_c", "Sutkalik T_max − T_min", "°C", default=12, min=0, max=30, group="Iqlim"),
    Field(
        "curve_elev",
        "Sath–hajm: sathlar",
        "m",
        type="series",
        default=[850, 870, 890, 905, 915],
        group="Suv ombori",
    ),
    Field(
        "curve_vol",
        "Sath–hajm: hajmlar",
        "mln m³",
        type="series",
        default=[0, 60, 220, 480, 700],
        group="Suv ombori",
    ),
    Field(
        "inflow_mean_m3s",
        "O'rtacha ko'p yillik sarf",
        "m³/s",
        default=120,
        min=0,
        group="Suv ombori",
    ),
    Field(
        "flood_01_m3s", "Loyihaviy toshqin (0.1 %)", "m³/s", default=2500, min=0, group="Suv ombori"
    ),
    Field(
        "flood_001_m3s",
        "Tekshiruv toshqini (0.01 %)",
        "m³/s",
        default=4000,
        min=0,
        group="Suv ombori",
    ),
    Field(
        "concentration_kg_m3",
        "O'rtacha loyqalik",
        "kg/m³",
        default=1.2,
        min=0,
        step=0.1,
        group="Suv ombori",
    ),
    Field("basin_km2", "Havza maydoni", "km²", default=10000, min=1, group="Suv ombori"),
    Field(
        "basin_length_km",
        "Havza uzunligi (eng uzoq oqim yo'li)",
        "km",
        default=150,
        min=0.5,
        group="Suv ombori",
    ),
    Field(
        "basin_slope",
        "Havza o'rtacha nishabi",
        "m/m",
        default=0.02,
        min=0.0005,
        max=1,
        step=0.005,
        group="Suv ombori",
    ),
    Field(
        "land_cover",
        "Havza yer qoplami",
        type="select",
        default="pasture",
        options=(
            ("forest", "O'rmon"),
            ("pasture", "Yaylov / buta"),
            ("crop", "Ekin"),
            ("bare_rock", "Yalang'och qoya / tog'"),
            ("urban", "Shahar"),
            ("glacier_snow", "Muzlik / qor"),
        ),
        group="Suv ombori",
    ),
    Field(
        "soil_group",
        "Havza gidrologik grunt guruhi",
        type="select",
        default="C",
        options=(("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")),
        group="Suv ombori",
    ),
    Field(
        "design_rain_mm",
        "Loyihaviy jala (24 soat, 1 %)",
        "mm",
        default=120,
        min=1,
        group="Suv ombori",
    ),
    Field(
        "glacial_lake_mcm",
        "Yuqoridagi muzlik ko'llari hajmi (0 — yo'q)",
        "mln m³",
        default=0,
        min=0,
        group="Suv ombori",
    ),
    # To'g'on
    Field(
        "dam_type",
        "To'g'on turi",
        type="select",
        default="concrete",
        options=(
            ("concrete", "Beton og'irlik"),
            ("earth", "Tuproq"),
            ("rockfill", "Tosh-tuproq"),
            ("arch", "Arkali"),
        ),
        group="To'g'on",
    ),
    Field("dam_height_m", "Balandlik (tagdan gerbgacha)", "m", default=80, min=1, group="To'g'on"),
    Field("crest_elevation_m", "Gerb belgisi", "m", default=912, group="To'g'on"),
    Field("base_elevation_m", "Tag belgisi", "m", default=832, group="To'g'on"),
    Field("crest_width_m", "Gerb kengligi", "m", default=8, min=0.5, group="To'g'on"),
    Field("dam_length_m", "Gerb uzunligi", "m", default=300, min=1, group="To'g'on"),
    Field(
        "upstream_slope",
        "Yuqori yuza qiyaligi (gor./vert.)",
        "",
        default=0.05,
        min=0,
        max=3,
        step=0.05,
        group="To'g'on",
    ),
    Field(
        "downstream_slope",
        "Quyi yuza qiyaligi (gor./vert.)",
        "",
        default=0.75,
        min=0,
        max=3,
        step=0.05,
        group="To'g'on",
    ),
    Field(
        "concrete_kn_m3",
        "Material solishtirma og'irligi",
        "kN/m³",
        default=24,
        min=15,
        max=28,
        step=0.5,
        group="To'g'on",
    ),
    Field(
        "drain_eff",
        "Drenaj samaradorligi E",
        "",
        default=0.5,
        min=0,
        max=0.9,
        step=0.05,
        group="To'g'on",
    ),
    Field("cutoff_m", "Shpunt/sement parda chuqurligi", "m", default=12, min=0, group="To'g'on"),
    Field(
        "concrete_class",
        "Beton klassi (massiv)",
        type="select",
        default="B20",
        options=materials.concrete_options(),
        group="To'g'on",
    ),
    Field(
        "face_class",
        "Beton klassi (yuza zonasi)",
        type="select",
        default="B25",
        options=materials.concrete_options(),
        group="To'g'on",
    ),
    Field(
        "cement_kg_m3",
        "Sement miqdori (massiv)",
        "kg/m³",
        default=220,
        min=80,
        max=500,
        group="To'g'on",
    ),
    Field(
        "dam_e_mpa",
        "Beton elastiklik moduli",
        "MPa",
        default=25000,
        min=1000,
        group="To'g'on",
        advanced=True,
    ),
    # Suv tashlagich
    Field("spill_crest_m", "Ostona belgisi", "m", default=905, group="Suv tashlagich"),
    Field("spill_width_m", "Kenglik (jami)", "m", default=40, min=0, group="Suv tashlagich"),
    Field(
        "spill_coeff",
        "Sarf koeffitsienti",
        "",
        default=0.49,
        min=0.3,
        max=0.6,
        step=0.01,
        group="Suv tashlagich",
    ),
    Field(
        "outlet_area_m2",
        "Tubi suv chiqargich yuzasi",
        "m²",
        default=0,
        min=0,
        group="Suv tashlagich",
    ),
    Field("outlet_sill_m", "Tubi suv chiqargich belgisi", "m", default=860, group="Suv tashlagich"),
    # Bosimli quvur
    Field("penstock_length_m", "Uzunlik", "m", default=300, min=1, group="Bosimli quvur"),
    Field(
        "penstock_diameter_m", "Diametr", "m", default=3.0, min=0.1, step=0.1, group="Bosimli quvur"
    ),
    Field("penstock_wall_mm", "Devor qalinligi", "mm", default=20, min=1, group="Bosimli quvur"),
    Field(
        "penstock_material",
        "Material",
        type="select",
        default="steel",
        options=(
            ("steel", "Po'lat S355/09G2S"),
            ("st3", "Po'lat St3 (S235)"),
            ("17g1s", "Po'lat 17G1S"),
            ("10hsnd", "Po'lat 10HSND"),
            ("s460", "Po'lat S460"),
            ("ductile_iron", "Cho'yan"),
            ("concrete", "Temir-beton"),
            ("grp", "GRP"),
        ),
        group="Bosimli quvur",
    ),
    Field(
        "penstock_roughness_mm",
        "G'adir-budirlik",
        "mm",
        default=0.1,
        min=0.001,
        group="Bosimli quvur",
    ),
    Field(
        "design_flow_m3s",
        "Loyihaviy sarf (jami)",
        "m³/s",
        default=150,
        min=0,
        group="Bosimli quvur",
    ),
    Field(
        "units_count", "Agregatlar soni", "", type="int", default=2, min=1, group="Bosimli quvur"
    ),
    Field(
        "surge_tank_diameter_m",
        "Tenglashtiruvchi minora diametri (0 — yo'q)",
        "m",
        default=0,
        min=0,
        group="Bosimli quvur",
    ),
    # Quyi byef, daryo o'zani
    Field("tailwater_m", "Quyi byef sathi (normal)", "m", default=840, group="Quyi byef"),
    Field("tailwater_flood_m", "Quyi byef sathi (toshqinda)", "m", default=845, group="Quyi byef"),
    Field("ch_width_m", "O'zan tubi kengligi", "m", default=80, min=1, group="Quyi byef"),
    Field(
        "ch_side_slope", "Qirg'oq qiyaligi (gor./vert.)", "", default=3.0, min=0, group="Quyi byef"
    ),
    Field(
        "ch_slope", "O'zan nishabi", "", default=0.002, min=0.00001, step=0.0005, group="Quyi byef"
    ),
    Field(
        "ch_manning",
        "Manning n",
        "",
        default=0.035,
        min=0.01,
        max=0.2,
        step=0.005,
        group="Quyi byef",
    ),
    Field(
        "ch_bank_depth_m",
        "Qirg'oq balandligi (toshqin boshlanadi)",
        "m",
        default=5,
        min=0.1,
        group="Quyi byef",
    ),
    Field(
        "settlement_km",
        "Eng yaqin aholi punkti masofasi",
        "km",
        default=20,
        min=0,
        group="Quyi byef",
    ),
    # Inshootlarning suv sathidan balandligi
    Field(
        "powerhouse_floor_m",
        "Mashina zali poli belgisi",
        "m",
        default=846,
        group="Inshootlar",
        hint="Quyi byefdan qancha baland — toshqin xavfi",
    ),
    Field(
        "powerhouse_height_m", "Mashina zali balandligi", "m", default=30, min=1, group="Inshootlar"
    ),
    Field(
        "powerhouse_mass_t", "Mashina zali massasi", "t", default=20000, min=1, group="Inshootlar"
    ),
    Field(
        "switchyard_m", "Taqsimlash qurilmasi (OPU) belgisi", "m", default=850, group="Inshootlar"
    ),
    Field("control_room_m", "Boshqaruv binosi belgisi", "m", default=852, group="Inshootlar"),
    Field(
        "model_zero_m",
        "3D model 0 belgisi (IFC z=0 mutlaq balandligi)",
        "m",
        default=0,
        group="Inshootlar",
        hint="Suv sathini 3D da to'g'ri joylash uchun",
    ),
    # Yonbag'irlar (ko'chki xavfi)
    Field(
        "slope_deg",
        "Ombor yonbag'iri qiyaligi",
        "°",
        default=35,
        min=5,
        max=85,
        group="Yonbag'irlar",
    ),
    Field(
        "slide_volume_m3",
        "Ehtimoliy ko'chki hajmi",
        "m³",
        default=500000,
        min=0,
        group="Yonbag'irlar",
        hint="Geologik xulosa bo'yicha",
    ),
    Field(
        "slide_drop_m",
        "Ko'chki og'irlik markazining sath ustidagi balandligi",
        "m",
        default=120,
        min=0,
        group="Yonbag'irlar",
    ),
    Field(
        "slide_distance_m",
        "Ko'chki joyidan to'g'ongacha",
        "m",
        default=1500,
        min=1,
        group="Yonbag'irlar",
    ),
    Field(
        "slide_depth_m",
        "Suv chuqurligi ko'chki joyida (NPU da)",
        "m",
        default=60,
        min=1,
        group="Yonbag'irlar",
    ),
    Field(
        "slide_density_kg_m3",
        "Yonbag'ir grunti zichligi",
        "kg/m³",
        default=2200,
        min=1000,
        max=3000,
        group="Yonbag'irlar",
    ),
    Field(
        "slide_friction_deg",
        "Dinamik ishqalanish burchagi",
        "°",
        default=20,
        min=5,
        max=45,
        group="Yonbag'irlar",
    ),
]

# Simulyatsiya turi → {forma maydoni: pasport maydoni yoki funksiya}
MAPPING: dict[str, dict[str, str]] = {
    "seismic": {
        "intensity": "intensity",
        "ground": "ground",
        "dam_height_m": "dam_height_m",
        "dam_e_mpa": "dam_e_mpa",
        "water_depth_m": "=normal_level_m-base_elevation_m",
        "dam_base_m": "=dam_height_m*(upstream_slope+downstream_slope)+crest_width_m",
        "ph_height_m": "powerhouse_height_m",
        "ph_mass_t": "powerhouse_mass_t",
    },
    "dam_stability": {
        "height_m": "dam_height_m",
        "crest_width_m": "crest_width_m",
        "upstream_slope": "upstream_slope",
        "downstream_slope": "downstream_slope",
        "concrete_kn_m3": "concrete_kn_m3",
        "base_elev_m": "base_elevation_m",
        "headwater_m": "normal_level_m",
        "tailwater_m": "tailwater_m",
        "drain_eff": "drain_eff",
        "friction": "friction",
        "cohesion_kpa": "cohesion_kpa",
        "allow_stress_mpa": "allow_stress_mpa",
    },
    "seepage": {
        "dam_type": "=dam_type_seepage",
        "head_m": "=normal_level_m-tailwater_m",
        "k_m_s": "k_m_s",
        "soil": "=soil_seepage",
        "base_width_m": "=dam_height_m*(upstream_slope+downstream_slope)+crest_width_m",
        "cutoff_m": "cutoff_m",
        "dam_length_m": "dam_length_m",
        "h1_m": "=normal_level_m-base_elevation_m",
        "h2_m": "=tailwater_m-base_elevation_m",
        "seep_length_m": "=dam_height_m*(upstream_slope+downstream_slope)+crest_width_m",
    },
    "flood": {
        "peak_m3s": "flood_01_m3s",
        "base_m3s": "inflow_mean_m3s",
        "curve_elev": "curve_elev",
        "curve_vol": "curve_vol",
        "initial_level_m": "normal_level_m",
        "crest_m": "crest_elevation_m",
        "crest_length_m": "dam_length_m",
        "spill_crest_m": "spill_crest_m",
        "spill_width_m": "spill_width_m",
        "spill_coeff": "spill_coeff",
        "outlet_area_m2": "outlet_area_m2",
        "outlet_sill_m": "outlet_sill_m",
        "turbine_m3s": "design_flow_m3s",
        "breach_bottom_m": "=base_elevation_m+dam_height_m*0.25",
        "reach_length_km": "settlement_km",
        "ch_width_m": "ch_width_m",
        "ch_side_slope": "ch_side_slope",
        "ch_slope": "ch_slope",
        "ch_manning": "ch_manning",
        "ch_bank_depth_m": "ch_bank_depth_m",
    },
    "landslide": {
        "volume_m3": "slide_volume_m3",
        "density_kg_m3": "slide_density_kg_m3",
        "drop_m": "slide_drop_m",
        "slope_deg": "slope_deg",
        "friction_deg": "slide_friction_deg",
        "depth_m": "slide_depth_m",
        "distance_m": "slide_distance_m",
        "freeboard_m": "=crest_elevation_m-normal_level_m",
        "dam_face_deg": "=dam_face_deg",
        "water_level_m": "normal_level_m",
    },
    "water_hammer": {
        "length_m": "penstock_length_m",
        "diameter_m": "penstock_diameter_m",
        "wall_mm": "penstock_wall_mm",
        "material": "penstock_material",
        "roughness_mm": "penstock_roughness_mm",
        "head_m": "=normal_level_m-tailwater_m",
        "flow_m3s": "=design_flow_m3s/units_count",
    },
    "surge_tank": {
        "tunnel_length_m": "penstock_length_m",
        "tunnel_diameter_m": "penstock_diameter_m",
        "roughness_mm": "penstock_roughness_mm",
        "tank_diameter_m": "surge_tank_diameter_m",
        "head_m": "=normal_level_m-tailwater_m",
        "flow_m3s": "design_flow_m3s",
    },
    "cracking": {
        "dam_type": "=dam_type_seepage",
        "height_m": "dam_height_m",
        "crest_width_m": "crest_width_m",
        "upstream_slope": "upstream_slope",
        "downstream_slope": "downstream_slope",
        "concrete_class": "concrete_class",
        "face_class": "face_class",
        "base_elev_m": "base_elevation_m",
        "headwater_m": "normal_level_m",
        "tailwater_m": "tailwater_m",
        "drain_eff": "drain_eff",
        "cement_kg_m3": "cement_kg_m3",
    },
    "dam_type": {
        "foundation": "=foundation_advisor",
        "height_m": "dam_height_m",
        "crest_length_m": "dam_length_m",
        "intensity": "intensity",
        "flood_m3s": "flood_01_m3s",
    },
    "rainfall": {
        "basin_km2": "basin_km2",
        "basin_length_km": "basin_length_km",
        "basin_slope": "basin_slope",
        "land_cover": "land_cover",
        "soil_group": "soil_group",
        "rain_mm": "design_rain_mm",
        "base_m3s": "inflow_mean_m3s",
        "curve_elev": "curve_elev",
        "curve_vol": "curve_vol",
        "initial_level_m": "normal_level_m",
        "crest_m": "crest_elevation_m",
        "crest_length_m": "dam_length_m",
        "spill_crest_m": "spill_crest_m",
        "spill_width_m": "spill_width_m",
        "turbine_m3s": "design_flow_m3s",
        "lake_mcm": "glacial_lake_mcm",
        "glof": "=glof_flag",
        "breach_bottom_m": "=base_elevation_m+dam_height_m*0.25",
    },
    "sediment": {
        "capacity_mcm": "capacity_mcm",
        "dead_mcm": "dead_mcm",
        "inflow_m3s": "inflow_mean_m3s",
        "concentration_kg_m3": "concentration_kg_m3",
        "basin_km2": "basin_km2",
    },
}


def defaults() -> dict:
    return {f.key: f.default for f in SITE_FIELDS}


def _derived(site: dict, expr: str):
    """ "=a-b", "=a*(b+c)+d" ko'rinishidagi oddiy ifodalar yoki maxsus kalitlar."""
    if expr == "dam_type_seepage":
        return "earth" if site.get("dam_type") in ("earth", "rockfill") else "concrete"
    if expr == "glof_flag":
        return float(site.get("glacial_lake_mcm") or 0) > 0
    if expr == "foundation_advisor":
        return {
            "rock": "rock_hard",
            "gravel": "gravel",
            "coarse_sand": "gravel",
            "medium_sand": "sand",
            "fine_sand": "sand",
            "clay": "clay",
        }.get(site.get("soil"), "rock_weathered")
    if expr == "soil_seepage":
        return site.get("soil")  # qoya → seepage.SOILS["rock"] (Lane shartli, sementatsiya bilan)
    if expr == "dam_face_deg":
        m = float(site.get("upstream_slope") or 0)
        import math

        return 90.0 if m <= 0 else max(min(math.degrees(math.atan(1 / m)), 90.0), 10.0)
    from .custom import compile_expr, evaluate

    env = {k: v for k, v in site.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    return evaluate(compile_expr(expr), env)


def apply(kind: str, site: dict | None) -> dict:
    """Pasportdan simulyatsiya formasi uchun qiymatlar (faqat mavjud maydonlar)."""
    if not site:
        return {}
    mp = MAPPING.get(kind, {})
    out = {}
    for fkey, skey in mp.items():
        try:
            if skey.startswith("="):
                v = _derived(site, skey[1:])
            else:
                v = site.get(skey)
            if v is None or v == "":
                continue
            out[fkey] = v
        except Exception:  # noqa: BLE001 — bitta maydon xatosi qolganlarini to'xtatmasin
            continue
    # Ombor hajmi bo'yicha "suv chuqurligi/ko'chki" uchun yordamchi: hech narsa qilmaymiz
    return out


def climate_from_site(site: dict | None) -> dict | None:
    """Pasportdan iqlim (hydro senariysi uchun ClimateSpec maydonlari) — kenglik bo'lmasa None."""
    if not site or site.get("latitude_deg") in (None, ""):
        return None
    out = {}
    for k in ("latitude_deg", "t_mean_annual_c", "t_amplitude_c", "diurnal_range_c"):
        v = site.get(k)
        if v not in (None, ""):
            out[k] = float(v)
    return out or None


def risk_summary(site: dict) -> list[dict]:
    """Pasportdan tezkor xavf ko'rsatkichlari (formulasiz, geometrik): inshootlar sathdan qancha baland va h.k."""
    out = []
    tw, twf = site.get("tailwater_m"), site.get("tailwater_flood_m")
    for key, label in (
        ("powerhouse_floor_m", "Mashina zali poli"),
        ("switchyard_m", "OPU"),
        ("control_room_m", "Boshqaruv binosi"),
    ):
        v = site.get(key)
        if v is None or twf is None:
            continue
        margin = float(v) - float(twf)
        out.append(
            {
                "name": f"{label} — toshqin sathidan balandlik",
                "value": round(margin, 2),
                "unit": "m",
                "ok": margin > 0.5,
                "note": f"normal quyi byefdan {float(v) - float(tw or twf):.1f} m",
            }
        )
    if site.get("crest_elevation_m") is not None and site.get("max_level_m") is not None:
        fb = float(site["crest_elevation_m"]) - float(site["max_level_m"])
        out.append(
            {
                "name": "Gerb zaxirasi FPU dan",
                "value": round(fb, 2),
                "unit": "m",
                "ok": fb >= 1.5,
                "note": "SNiP: to'lqin + 1.5 m tavsiya",
            }
        )
    if site.get("intensity"):
        b = int(site["intensity"])
        out.append(
            {
                "name": "Seysmiklik",
                "value": b,
                "unit": "ball",
                "ok": b <= 8,
                "note": "9 ball — maxsus seysmik hisob talab qilinadi",
            }
        )
    return out
