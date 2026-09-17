"""Tayyor GES raqamli egizagi (preset) — haqiqiy inshoot ma'lumotlaridan parametrik 3D model + maydon pasporti.

Preset ma'lumotlari ochiq manbalardan (Wikipedia, orexca, cawater-info); geometriya parametrik (vodiy relyefi,
tosh-tuproq/beton to'g'on kesimi, suv qabul minorasi, bosimli tunnellar, mashina zali, agregatlar,
transformatorlar, suv tashlagich). Har element IFC klass va Pset_GES_* bilan — simulyatsiyalar (to'g'on
barqarorligi, yoriq, toshqin, gidrozarba, zilzila, dispetcherlik) modeldan avtomatik to'ldiriladi.

Koordinatalar: X — to'g'on gerbi bo'ylab (vodiy kesimi), Y — daryo bo'ylab (+Y yuqori byef / suv ombori),
Z — mutlaq balandlik (m, dengiz sathidan; model 0 belgisi = 0).
"""

from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------- presetlar
PRESETS: dict[str, dict] = {
    "chorvoq": {
        "title": "Chorvoq GES (O'zbekiston, Chirchiq daryosi)",
        "description": "Tosh-tuproq to'g'on 168 m, gerb 770 m, suv ombori 2006 mln m³ (NPU 890 m), 4×150 MW, "
        "2 ta 9 m bosimli tunnel (770 va 852 m), suv tashlagich 2400 m³/s. 1970 y.",
        "sources": [
            "https://en.wikipedia.org/wiki/Lake_Charvak",
            "https://www.orexca.com/uzbekistan/charvak/charvak-power-station.htm",
            "https://www.cawater-info.net/bk/1-1-1-1-3-uz.htm",
        ],
        "photo": {
            "file": "charvak_dam.jpg",
            "credit": "Ymblanter, Wikimedia Commons, CC BY-SA 4.0 — quyi yuza (bermalar bilan)",
        },
        "location": "Toshkent viloyati, Bo'stonliq tumani, 41.64° N 70.03° E",
        "dam": {
            "type": "rockfill",
            "height_m": 168.0,
            "crest_elevation_m": 896.0,
            "base_elevation_m": 728.0,
            "crest_width_m": 12.0,
            "length_m": 770.0,
            "upstream_slope": 2.2,  # gor./vert.
            "downstream_slope": 1.9,
            "berms": 4,
        },
        "reservoir": {
            "normal_level_m": 890.0,
            "max_level_m": 892.0,
            "dead_level_m": 830.0,
            "capacity_mcm": 2006.0,
            "dead_mcm": 426.0,
            "area_km2": 40.1,
            "curve_elev": [728, 780, 830, 860, 890, 892],
            "curve_vol": [0, 40, 426, 950, 2006, 2090],
        },
        "hydrology": {
            "inflow_mean_m3s": 208.0,
            "flood_01_m3s": 1800.0,
            "flood_001_m3s": 2400.0,
            "basin_km2": 10900.0,
            "basin_length_km": 160.0,
            "basin_slope": 0.03,
            "land_cover": "bare_rock",
            "soil_group": "C",
            "design_rain_mm": 90.0,
            "glacial_lake_mcm": 5.0,
        },
        "units": {
            "count": 4,
            "rated_mw": 150.0,
            "type": "Francis",
            "head_m": 148.0,
            "flow_m3s": 125.0,
        },
        "penstocks": {
            "count": 2,
            "diameter_m": 9.0,
            "lengths_m": [770.0, 852.0],
            "material": "concrete",
        },
        "spillway": {"crest_m": 890.0, "width_m": 45.0, "gates": 3, "capacity_m3s": 2400.0},
        "tailwater_m": 742.0,
        "powerhouse": {"floor_m": 736.0, "length_m": 130.0, "width_m": 45.0, "height_m": 38.0},
        "seismic": {"intensity": "9", "ground": "A", "soil": "rock"},
    },
    "maket": {
        "title": "Namunaviy GES maketi (ichki ko'rinish sxemasi bo'yicha)",
        "description": "O'quv sxemasi: 1 suv ombori, 2 suv qabul qilish inshooti, 3 bosh quvur (penstock), 4 turbina, "
        "5 generator, 6 chiqarish quvuri (draft tube), 7 transformatorlar, 8 boshqaruv xonasi, 9 daryo oqimi (tailrace). "
        "Beton og'irlik to'g'on 45 m, gerb 160 m, 1×Francis 20 MW, napor 40 m.",
        "sources": ["Sxema: «Gidroelektrostansiya (ichki ko'rinishi)» infografikasi"],
        "photo": None,
        "layout": "compact",
        "location": "shartli (o'quv maketi)",
        "dam": {
            "type": "concrete",
            "height_m": 45.0,
            "crest_elevation_m": 245.0,
            "base_elevation_m": 200.0,
            "crest_width_m": 8.0,
            "length_m": 160.0,
            "upstream_slope": 0.05,
            "downstream_slope": 0.75,
            "berms": 0,
        },
        "reservoir": {
            "normal_level_m": 240.0,
            "max_level_m": 243.0,
            "dead_level_m": 218.0,
            "capacity_mcm": 12.0,
            "dead_mcm": 2.0,
            "area_km2": 0.9,
            "curve_elev": [200, 210, 218, 230, 240, 243, 245],
            "curve_vol": [0, 0.4, 2.0, 5.5, 12.0, 14.6, 16.5],
        },
        "hydrology": {
            "inflow_mean_m3s": 45.0,
            "flood_01_m3s": 600.0,
            "flood_001_m3s": 850.0,
            "basin_km2": 1800.0,
            "basin_length_km": 70.0,
            "basin_slope": 0.02,
            "land_cover": "forest",
            "soil_group": "B",
            "design_rain_mm": 80.0,
            "glacial_lake_mcm": 0.0,
        },
        "units": {
            "count": 1,
            "rated_mw": 20.0,
            "type": "Francis",
            "head_m": 40.0,
            "flow_m3s": 58.0,
        },
        "penstocks": {"count": 1, "diameter_m": 4.0, "lengths_m": [95.0], "material": "steel"},
        "spillway": {"crest_m": 240.0, "width_m": 30.0, "gates": 2, "capacity_m3s": 850.0},
        "tailwater_m": 203.0,
        "powerhouse": {"floor_m": 200.0, "length_m": 42.0, "width_m": 34.0, "height_m": 30.0},
        "seismic": {"intensity": "8", "ground": "B", "soil": "rock"},
    },
    "hoover": {
        "title": "Hoover Dam (AQSh, Kolorado daryosi)",
        "description": "Beton arkali-og'irlik to'g'on 221 m, gerb 379 m, Mid ko'li 35 km³, 17 agregat ≈ 2080 MW. 1936 y.",
        "sources": ["https://en.wikipedia.org/wiki/Hoover_Dam"],
        "photo": None,
        "location": "Nevada/Arizona, 36.016° N 114.737° W",
        "dam": {
            "type": "concrete",
            "height_m": 221.0,
            "crest_elevation_m": 376.0,
            "base_elevation_m": 155.0,
            "crest_width_m": 14.0,
            "length_m": 379.0,
            "upstream_slope": 0.0,
            "downstream_slope": 0.76,
            "berms": 0,
        },
        "reservoir": {
            "normal_level_m": 372.0,
            "max_level_m": 374.0,
            "dead_level_m": 290.0,
            "capacity_mcm": 35200.0,
            "dead_mcm": 3000.0,
            "area_km2": 640.0,
            "curve_elev": [155, 250, 290, 330, 372, 374],
            "curve_vol": [0, 500, 3000, 12000, 35200, 36500],
        },
        "hydrology": {
            "inflow_mean_m3s": 400.0,
            "flood_01_m3s": 8000.0,
            "flood_001_m3s": 11300.0,
            "basin_km2": 435000.0,
            "basin_length_km": 1000.0,
            "basin_slope": 0.004,
            "land_cover": "bare_rock",
            "soil_group": "C",
            "design_rain_mm": 60.0,
            "glacial_lake_mcm": 0.0,
        },
        "units": {
            "count": 17,
            "rated_mw": 122.0,
            "type": "Francis",
            "head_m": 180.0,
            "flow_m3s": 80.0,
        },
        "penstocks": {
            "count": 4,
            "diameter_m": 9.1,
            "lengths_m": [400.0, 400.0, 400.0, 400.0],
            "material": "steel",
        },
        "spillway": {"crest_m": 372.0, "width_m": 2 * 120.0, "gates": 8, "capacity_m3s": 11300.0},
        "tailwater_m": 195.0,
        "powerhouse": {"floor_m": 190.0, "length_m": 200.0, "width_m": 30.0, "height_m": 40.0},
        "seismic": {"intensity": "7", "ground": "A", "soil": "rock"},
    },
}


# ---------------------------------------------------------------- mesh yordamchilari
def _mesh_obj(name, kind, ifc_class, verts, faces, color, psets=None) -> dict:
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=int)
    ctr = v.mean(axis=0)
    return {
        "kind": kind,
        "name": name,
        "ifc_class": ifc_class,
        "color": color,
        "transform": {"x": float(ctr[0]), "y": float(ctr[1]), "z": float(ctr[2]), "rz": 0.0},
        "psets": psets or {},
        "mesh": {"vertices": (v - ctr).round(4).tolist(), "faces": f.tolist()},
    }


def _box(cx, cy, cz, sx, sy, sz):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [
        [cx - hx, cy - hy, cz - hz],
        [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz],
        [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz],
        [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz],
        [cx - hx, cy + hy, cz + hz],
    ]
    f = [
        [0, 2, 1], [0, 3, 2],  # tub
        [4, 5, 6], [4, 6, 7],  # tepa
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ]  # fmt: skip
    return v, f


def _extrude_section_x(section_yz: list[tuple[float, float]], x0: float, x1: float):
    """(y,z) yopiq qavariq ko'pburchak → X bo'ylab prizma (yelpig'ich qopqoqlar + yon yuzalar)."""
    n = len(section_yz)
    v = [[x0, y, z] for y, z in section_yz] + [[x1, y, z] for y, z in section_yz]
    f = []
    for k in range(1, n - 1):  # qopqoqlar
        f.append([0, k + 1, k])
        f.append([n, n + k, n + k + 1])
    for k in range(n):  # yon
        a, b = k, (k + 1) % n
        f.append([a, b, n + b])
        f.append([a, n + b, n + a])
    return v, f


def _cylinder(p0, p1, r, seg=20):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    if L < 1e-9:
        raise ValueError("cylinder")
    d /= L
    a = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    w = np.cross(d, u)
    v, f = [], []
    for i in range(seg):
        t = 2 * math.pi * i / seg
        off = r * (math.cos(t) * u + math.sin(t) * w)
        v.append((p0 + off).tolist())
        v.append((p1 + off).tolist())
    for i in range(seg):
        a0, b0 = 2 * i, 2 * i + 1
        a1, b1 = 2 * ((i + 1) % seg), 2 * ((i + 1) % seg) + 1
        f.append([a0, a1, b1])
        f.append([a0, b1, b0])
    c0, c1 = len(v), len(v) + 1
    v.append(p0.tolist())
    v.append(p1.tolist())
    for i in range(seg):
        a0, a1 = 2 * i, 2 * ((i + 1) % seg)
        f.append([c0, a1, a0])
        f.append([c1, a0 + 1, a1 + 1])
    return v, f


def _terrain(preset: dict, grid: int = 90):
    """Vodiy relyefi: V shaklli kesim (to'g'on gerbi qirg'oqqa tegadi), daryo nishabi, yuqori byef havzasi."""
    d = preset["dam"]
    L = d["length_m"]
    base, crest = d["base_elevation_m"], d["crest_elevation_m"]
    half = L / 2
    xs = np.linspace(-1.4 * half, 1.4 * half, grid)
    ys = np.linspace(-6 * d["height_m"], 12 * d["height_m"], int(grid * 1.5))
    X, Y = np.meshgrid(xs, ys)
    # kesim: |x| = half da gerb + 25 m; kanyon tubida kengligi ~L/6 tekis
    flat = half / 6
    ax = np.maximum(np.abs(X) - flat, 0) / max(half - flat, 1)
    Z = base + (crest + 25 - base) * np.power(ax, 1.5)
    # daryo nishabi: quyi byef pastga (0.5 %), yuqori byef ombor tubi sekin ko'tariladi (0.3 %)
    Z = Z + np.where(Y < 0, Y * 0.005, Y * 0.003)
    # daryo o'zani: vodiy markazida parabolik kanal (kengligi 90 m, chuqurligi 8 m) — oqim kanalda yuradi,
    # toshqinda qirg'oqdan chiqib yoyiladi (Manning o'zani parametrlari bilan mos)
    chw, chd = 90.0, 8.0
    Z = Z - chd * np.clip(1 - (X / (chw / 2)) ** 2, 0, 1)
    # yon soylar / notekislik
    Z = Z + 6 * np.sin(X / 90) * np.cos(Y / 140)
    V = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    ny, nx = X.shape
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F.append([a, a + 1, a + nx])
            F.append([a + 1, a + nx + 1, a + nx])
    return V, np.asarray(F)


def _bent_pipe(points: list[list[float]], r: float, seg: int = 20) -> tuple[list, list]:
    """Bir nechta silindr bo'lagidan egri quvur (nuqtalar ketma-ketligi; bo'g'inlarda sfera o'rniga ustma-ust)."""
    V: list = []
    F: list = []
    for a, b in zip(points, points[1:], strict=False):
        v, f = _cylinder(a, b, r, seg)
        off = len(V)
        V.extend(v)
        F.extend([[i + off, j + off, k + off] for i, j, k in f])
    return V, F


def _build_compact(p: dict) -> list[dict]:
    """Sxema bo'yicha ixcham GES: to'g'on (yuqori byef ombori bilan), unga tutashgan suv qabul inshooti, egri bosh
    quvur qiyalik bo'ylab mashina zaliga (tog' bag'riga kiritilgan), vertikal Francis turbina + generator, egri
    chiqarish quvuri quyi byefga, daryo oqimi kanali, transformatorlar maydonchasi, boshqaruv xonasi, ko'prik kran,
    suv tashlagich (darvozali). Elementlar sxemadagi 1–9 raqamlari bilan nomlangan."""
    d, r, u, pen, sp, ph = (
        p["dam"],
        p["reservoir"],
        p["units"],
        p["penstocks"],
        p["spillway"],
        p["powerhouse"],
    )
    H, L, bw = d["height_m"], d["length_m"], d["crest_width_m"]
    base, crest = d["base_elevation_m"], d["crest_elevation_m"]
    mu, md = d["upstream_slope"], d["downstream_slope"]
    tw = p["tailwater_m"]
    out: list[dict] = []
    V, F = _terrain(p, grid=80)
    out.append(_mesh_obj("Relyef (vodiy)", "site", "IfcGeographicElement", V, F, (0.42, 0.5, 0.33),
                         {"Pset_GES_Site": {"Manba": "parametrik vodiy", "Preset": p["title"]}}))  # fmt: skip
    # 1) suv ombori — belgi obyekt (yuqori byef, NPU sathida yupqa plita; jonli suv relyefga moslashadi)
    rv, rf = _box(0, 6 * H, r["normal_level_m"] - 0.3, L * 1.2, 8 * H, 0.4)
    out.append(_mesh_obj("1 Suv ombori (reservuar)", "reservoir", "IfcGeographicElement", rv, rf, (0.3, 0.55, 0.8, 0.25),
                         {"Pset_GES_Reservoir": {"NPU_m": r["normal_level_m"], "FPU_m": r["max_level_m"],
                                                 "Hajm_mln_m3": r["capacity_mcm"]}}))  # fmt: skip
    # to'g'on — beton og'irlik, gerb X bo'ylab
    sec = [(-bw / 2 - md * H, base), (bw / 2 + mu * H, base), (bw / 2, crest), (-bw / 2, crest)]
    v, f = _extrude_section_x(sec, -L / 2 - 30, L / 2 + 30)
    out.append(_mesh_obj("To'g'on (beton og'irlik)", "dam", "IfcWall", v, f, (0.72, 0.72, 0.7),
                         {"Pset_GES_Dam": {"Turi": "concrete", "Balandlik_m": H, "Uzunlik_m": L, "GerbBelgisi_m": crest,
                                           "GerbKengligi_m": bw, "TagKengligi_m": round(bw + (mu + md) * H, 1),
                                           "TagBelgisi_m": base, "YuqoriQiyalik": mu, "QuyiQiyalik": md,
                                           "NPU_m": r["normal_level_m"], "BetonKlassi": "B25"}}))  # fmt: skip
    # 2) suv qabul qilish inshooti — to'g'on yuqori yuzasiga tutashgan minora (panjara, zatvor)
    ix = -L * 0.15
    iz0 = r["dead_level_m"] - 6
    iv, if_ = _box(ix, bw / 2 + 8, (iz0 + crest + 3) / 2, 16, 16, crest + 3 - iz0)
    out.append(_mesh_obj("2 Suv qabul qilish inshooti (intake)", "intake", "IfcBuildingElementProxy", iv, if_,
                         (0.66, 0.66, 0.64), {"Pset_GES_Intake": {"OstonaBelgisi_m": iz0, "HisobiySarf_m3s": u["flow_m3s"],
                                                                 "Teshiklar": 2, "PanjaraOraligi_mm": 100, "Panjara": "ha"}}))  # fmt: skip
    # mashina zali — to'g'on quyi etagida, tog' bag'riga kiritilgan (pol = tag belgisi)
    toe_y = -bw / 2 - md * H
    py = toe_y - 30 - ph["width_m"] / 2
    pz = ph["floor_m"] + ph["height_m"] / 2
    pv, pf = _box(ix, py, pz, ph["length_m"], ph["width_m"], ph["height_m"])
    # bino — yarim shaffof (sxemadagi kesim ko'rinishi: turbina/generator ichkarida ko'rinadi)
    out.append(_mesh_obj("Mashina zali", "powerhouse", "IfcBuildingElementProxy", pv, pf, (0.8, 0.78, 0.72, 0.35),
                         {"Pset_GES_Powerhouse": {"PolBelgisi_m": ph["floor_m"], "Agregatlar": u["count"],
                                                  "BetonKlassi": "B25"}}))  # fmt: skip
    # 3) bosh quvur — intake dan to'g'on tanasi orqali, so'ng qiyalik bo'ylab egilib turbinaga (sxemadagi ko'k quvur)
    rr = pen["diameter_m"] / 2
    tz = ph["floor_m"] + 3.5  # turbina o'qi balandligi
    pts = [
        [ix, bw / 2 + 8, iz0 + 8],
        [ix, -bw / 2 - md * (crest - iz0 - 8) - 6, iz0 + 6],
        [ix, toe_y - 12, tz + 6],
        [ix, py + ph["width_m"] / 2 - 6, tz],
        [ix, py + 4.5, tz],
    ]
    cv, cf = _bent_pipe(pts, rr, 22)
    out.append(_mesh_obj("3 Bosh quvur (penstock)", "penstock", "IfcPipeSegment", cv, cf, (0.16, 0.42, 0.78),
                         {"Pset_GES_Penstock": {"Diametr_m": pen["diameter_m"], "Uzunlik_m": pen["lengths_m"][0],
                                                "Gadirbudirlik_mm": 0.1, "Material": "steel",
                                                "DevorQalinligi_mm": 20}}))  # fmt: skip
    # 4) turbina — vertikal Francis: spiral kamera (past silindr) + ish g'ildiragi
    tv, tf = _cylinder([ix, py, ph["floor_m"] - 2], [ix, py, ph["floor_m"] + 7], 5.0, 28)
    out.append(_mesh_obj("4 Turbina", "turbine", "IfcFlowMovingDevice", tv, tf, (0.2, 0.45, 0.75),
                         {"Pset_GES_Turbine": {"Turi": u["type"], "Quvvat_MW": u["rated_mw"], "Napor_m": u["head_m"],
                                               "Sarf_m3s": u["flow_m3s"], "FIK": 0.92}}))  # fmt: skip
    # val
    sv, sf = _cylinder([ix, py, ph["floor_m"] + 7], [ix, py, ph["floor_m"] + 13], 0.9, 16)
    out.append(_mesh_obj("Val", "shaft", "IfcShaft", sv, sf, (0.75, 0.75, 0.78)))
    # 5) generator — yuqorida (statorli silindr)
    gv, gf = _cylinder([ix, py, ph["floor_m"] + 13], [ix, py, ph["floor_m"] + 21], 4.5, 28)
    out.append(_mesh_obj("5 Generator", "generator", "IfcElectricGenerator", gv, gf, (0.18, 0.35, 0.7),
                         {"Pset_GES_Generator": {"Quvvat_MW": u["rated_mw"], "Kuchlanish_kV": 10.5}}))  # fmt: skip
    # 6) chiqarish quvuri — turbina tagidan pastga va quyi byef tomon egilib (draft tube)
    dv, df = _bent_pipe([[ix, py, ph["floor_m"] - 2], [ix, py, ph["floor_m"] - 9], [ix, py - 14, ph["floor_m"] - 11],
                         [ix, py - ph["width_m"] / 2 - 10, tw - 4]], rr * 1.2, 20)  # fmt: skip
    out.append(_mesh_obj("6 Chiqarish quvuri (draft tube)", "drafttube", "IfcPipeSegment", dv, df, (0.2, 0.5, 0.8),
                         {"Pset_GES_DraftTube": {"Diametr_m": round(pen["diameter_m"] * 1.2, 1),
                                                 "ChiqishBelgisi_m": tw - 4}}))  # fmt: skip
    # 9) daryo oqimi — quyi byef kanali (tailrace): tub plitasi + ikki devor
    ty0 = py - ph["width_m"] / 2 - 10
    kv, kf = _box(ix, ty0 - 60, tw - 6, 30, 120, 1.0)
    out.append(_mesh_obj("9 Daryo oqimi (tailrace) — kanal tubi", "tailrace", "IfcSlab", kv, kf, (0.55, 0.55, 0.5),
                         {"Pset_GES_Tailrace": {"TubBelgisi_m": tw - 6, "SuvSathi_m": tw, "Kenglik_m": 30}}))  # fmt: skip
    for sgn in (-1, 1):
        wv, wf = _box(ix + sgn * 15.5, ty0 - 60, tw - 2.5, 1.0, 120, 6)
        out.append(
            _mesh_obj(
                f"Kanal devori {'chap' if sgn < 0 else 'o' + chr(39) + 'ng'}",
                "wall",
                "IfcWall",
                wv,
                wf,
                (0.6, 0.6, 0.58),
            )
        )
    # 7) transformatorlar va yuqori kuchlanish uskunalari — mashina zali yonidagi maydoncha
    tx0 = ix + ph["length_m"] / 2 + 14
    for i in range(3):
        tv2, tf2 = _box(tx0 + i * 9, py + 6, ph["floor_m"] + 3.5, 5, 4, 5)
        out.append(_mesh_obj(f"7 Transformator {i + 1}", "transformer", "IfcTransformer", tv2, tf2, (0.55, 0.55, 0.6),
                             {"Pset_GES_Transformer": {"Quvvat_MVA": round(u["rated_mw"] / 0.9 / 3 * 3, 0) if i == 0 else 8.0,
                                                       "KuchlanishYuqori_kV": 110, "KuchlanishPast_kV": 10.5,
                                                       "Sovitish": "ONAF"}}))  # fmt: skip
    ov, of_ = _box(tx0 + 9, py - 8, ph["floor_m"] + 1.5, 34, 20, 1.0)
    out.append(
        _mesh_obj(
            "7 Taqsimlash qurilmasi (110 kV)",
            "switchyard",
            "IfcBuildingElementProxy",
            ov,
            of_,
            (0.6, 0.6, 0.6),
        )
    )
    # 8) boshqaruv xonasi — mashina zali yuqori qavatida (quyi byef tomon oynali xona)
    bv, bf = _box(
        ix + ph["length_m"] / 2 - 8,
        py - ph["width_m"] / 2 + 5,
        ph["floor_m"] + ph["height_m"] - 7,
        12,
        8,
        5,
    )
    out.append(_mesh_obj("8 Boshqaruv xonasi (dispecher)", "controlroom", "IfcBuildingElementProxy", bv, bf, (0.85, 0.85, 0.9),
                         {"Pset_GES_ControlRoom": {"Qavat": 2, "SCADA": "ha"}}))  # fmt: skip
    # ko'prik kran — zal tepasida
    crv, crf = _box(ix, py, ph["floor_m"] + ph["height_m"] - 3, ph["length_m"] - 4, 3, 2)
    out.append(_mesh_obj("Ko'prik kran", "crane", "IfcTransportElement", crv, crf, (0.9, 0.75, 0.1),
                         {"Pset_GES_Crane": {"YukKotarish_t": 120}}))  # fmt: skip
    # suv tashlagich — to'g'onning o'ng qismida darvozali ostona (NPU da) va nov quyi byefgacha
    sx = L * 0.3
    zc = sp["crest_m"]
    chute = [
        [sx - sp["width_m"] / 2, bw / 2 + 2, zc], [sx + sp["width_m"] / 2, bw / 2 + 2, zc],
        [sx + sp["width_m"] / 2, toe_y - 25, tw + 1], [sx - sp["width_m"] / 2, toe_y - 25, tw + 1],
    ]  # fmt: skip
    cv2 = chute + [[x, y, z - 3] for x, y, z in chute]
    cf2 = [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ]
    out.append(_mesh_obj("Suv tashlagich", "spillway", "IfcBuildingElementProxy", cv2, cf2, (0.68, 0.68, 0.7),
                         {"Pset_GES_Spillway": {"OstonaBelgisi_m": zc, "Kenglik_m": sp["width_m"], "SarfKoeff": 0.49,
                                                "Darvozalar": sp["gates"], "Sarf_m3s": sp["capacity_m3s"]}}))  # fmt: skip
    for g in range(sp["gates"]):
        gw = sp["width_m"] / sp["gates"]
        gx = sx - sp["width_m"] / 2 + gw * (g + 0.5)
        gv2, gf2 = _box(gx, bw / 2 + 2, zc + 2.5, gw - 1, 1.5, crest - zc)
        out.append(
            _mesh_obj(
                f"Darvoza {g + 1}", "gate", "IfcBuildingElementProxy", gv2, gf2, (0.75, 0.3, 0.2)
            )
        )
    return out


def build_objects(preset_id: str) -> list[dict]:
    p = PRESETS[preset_id]
    if p.get("layout") == "compact":
        return _build_compact(p)
    d, r, u, pen, sp, ph = (
        p["dam"],
        p["reservoir"],
        p["units"],
        p["penstocks"],
        p["spillway"],
        p["powerhouse"],
    )
    H, L, bw = d["height_m"], d["length_m"], d["crest_width_m"]
    base, crest = d["base_elevation_m"], d["crest_elevation_m"]
    mu, md = d["upstream_slope"], d["downstream_slope"]
    out: list[dict] = []

    # 1) relyef
    V, F = _terrain(p)
    out.append(
        _mesh_obj("Relyef (vodiy)", "site", "IfcGeographicElement", V, F, (0.42, 0.5, 0.33),
                  {"Pset_GES_Site": {"Manba": "parametrik vodiy", "Preset": p["title"]}})
    )  # fmt: skip

    # 2) to'g'on — trapetsiya kesimi (y: +yuqori byef), X bo'ylab gerb uzunligi + qirg'oqqa 40 m
    sec = [(-bw / 2 - md * H, base), (bw / 2 + mu * H, base), (bw / 2, crest), (-bw / 2, crest)]
    v, f = _extrude_section_x(sec, -L / 2 - 40, L / 2 + 40)
    base_w = bw + (mu + md) * H
    out.append(
        _mesh_obj("To'g'on", "dam", "IfcWall", v, f,
                  (0.55, 0.52, 0.47) if d["type"] in ("rockfill", "earth") else (0.72, 0.72, 0.7),
                  {"Pset_GES_Dam": {
                      "Turi": d["type"], "Balandlik_m": H, "Uzunlik_m": L, "GerbBelgisi_m": crest,
                      "GerbKengligi_m": bw, "TagKengligi_m": round(base_w, 1), "TagBelgisi_m": base,
                      "YuqoriQiyalik": mu, "QuyiQiyalik": md, "NPU_m": r["normal_level_m"]}})
    )  # fmt: skip
    # bermalar (quyi yuzada) — tosh-tuproq to'g'on
    for k in range(1, int(d.get("berms", 0)) + 1):
        z = base + H * k / (d["berms"] + 1)
        y = -bw / 2 - md * (crest - z)
        bv, bf = _box(0, y - 3, z + 1.0, L + 60, 6, 2)
        out.append(_mesh_obj(f"Berma {k}", "slab", "IfcSlab", bv, bf, (0.62, 0.6, 0.55)))

    # 3) suv qabul minorasi (yuqori byef, o'lik sath ustida)
    intake_z0 = r["dead_level_m"] - 25
    iy = bw / 2 + mu * (crest - intake_z0) + 20
    tv, tf = _box(-L * 0.18, iy, (intake_z0 + crest + 4) / 2, 34, 34, crest + 4 - intake_z0)
    out.append(
        _mesh_obj("Suv qabul minorasi", "intake", "IfcBuildingElementProxy", tv, tf, (0.7, 0.7, 0.68),
                  {"Pset_GES_Intake": {"OstonaBelgisi_m": intake_z0, "Panjara": "ha"}})
    )  # fmt: skip

    # 4) mashina zali (quyi byef) + agregatlar + transformatorlar
    py = -bw / 2 - md * H - 120 - ph["width_m"] / 2
    pz = ph["floor_m"] + ph["height_m"] / 2
    pv, pf = _box(-L * 0.18, py, pz, ph["length_m"], ph["width_m"], ph["height_m"])
    out.append(
        _mesh_obj("Mashina zali", "powerhouse", "IfcBuildingElementProxy", pv, pf, (0.8, 0.78, 0.72),
                  {"Pset_GES_Powerhouse": {"PolBelgisi_m": ph["floor_m"], "Agregatlar": u["count"]}})
    )  # fmt: skip
    n = u["count"]
    pitch = ph["length_m"] / (n + 1)
    for i in range(n):
        x = -L * 0.18 - ph["length_m"] / 2 + pitch * (i + 1)
        cv, cf = _cylinder([x, py, ph["floor_m"]], [x, py, ph["floor_m"] + 9], 4.5)
        out.append(
            _mesh_obj(f"Agregat {i + 1}", "turbine", "IfcFlowMovingDevice", cv, cf, (0.2, 0.45, 0.75),
                      {"Pset_GES_Turbine": {"Turi": u["type"], "Quvvat_MW": u["rated_mw"], "Napor_m": u["head_m"],
                                            "Sarf_m3s": u["flow_m3s"], "FIK": 0.93}})
        )  # fmt: skip
        gv, gf = _box(x, py, ph["floor_m"] + 13, 7, 7, 8)
        out.append(
            _mesh_obj(f"Generator {i + 1}", "generator", "IfcElectricGenerator", gv, gf, (0.55, 0.2, 0.2),
                      {"Pset_GES_Generator": {"Quvvat_MW": u["rated_mw"]}})
        )  # fmt: skip
        tv2, tf2 = _box(x, py - ph["width_m"] / 2 - 18, ph["floor_m"] + 4, 8, 6, 8)
        out.append(
            _mesh_obj(f"Transformator {i + 1}", "transformer", "IfcTransformer", tv2, tf2, (0.5, 0.5, 0.55),
                      {"Pset_GES_Transformer": {"Quvvat_MVA": round(u["rated_mw"] / 0.9, 0), "Kuchlanish_kV": 220}})
        )  # fmt: skip

    # 5) bosimli tunnellar/quvurlar: minoradan mashina zaligacha
    for k in range(pen["count"]):
        x = -L * 0.18 - 20 + 40 * k
        p0 = [x, iy - 17, intake_z0 + 10]
        p1 = [x, py + ph["width_m"] / 2, ph["floor_m"] + 6]
        cv, cf = _cylinder(p0, p1, pen["diameter_m"] / 2, seg=24)
        Lk = pen["lengths_m"][min(k, len(pen["lengths_m"]) - 1)]
        out.append(
            _mesh_obj(f"Bosimli tunnel {k + 1}", "penstock", "IfcPipeSegment", cv, cf, (0.35, 0.35, 0.4),
                      {"Pset_GES_Penstock": {"Diametr_m": pen["diameter_m"], "Uzunlik_m": Lk,
                                             "Gadirbudirlik_mm": 0.6 if pen["material"] == "concrete" else 0.1,
                                             "Material": pen["material"]}})
        )  # fmt: skip

    # 6) suv tashlagich — o'ng qirg'oqda ochiq nov (ostona NPU da), quyi byefgacha
    sx = L / 2 + 30
    zc = sp["crest_m"]
    tw = p["tailwater_m"]
    chute = [
        [sx - sp["width_m"] / 2, bw / 2 + 30, zc], [sx + sp["width_m"] / 2, bw / 2 + 30, zc],
        [sx + sp["width_m"] / 2, -bw / 2 - md * H - 60, tw + 2], [sx - sp["width_m"] / 2, -bw / 2 - md * H - 60, tw + 2],
    ]  # fmt: skip
    cv = chute + [[x, y, z - 4] for x, y, z in chute]
    cf = [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ]
    out.append(
        _mesh_obj("Suv tashlagich", "spillway", "IfcBuildingElementProxy", cv, cf, (0.68, 0.68, 0.7),
                  {"Pset_GES_Spillway": {"OstonaBelgisi_m": zc, "Kenglik_m": sp["width_m"], "SarfKoeff": 0.49,
                                         "Darvozalar": sp["gates"], "Sarf_m3s": sp["capacity_m3s"]}})
    )  # fmt: skip
    # darvozalar
    for g in range(sp["gates"]):
        gw = sp["width_m"] / sp["gates"]
        gx = sx - sp["width_m"] / 2 + gw * (g + 0.5)
        gv, gf = _box(gx, bw / 2 + 30, zc + 5, gw - 1, 2, 10)
        out.append(
            _mesh_obj(
                f"Darvoza {g + 1}", "gate", "IfcBuildingElementProxy", gv, gf, (0.75, 0.3, 0.2)
            )
        )

    # 7) taqsimlash qurilmasi (OPU) — quyi byef, o'ng qirg'oq
    ov, of = _box(L * 0.25, py - 60, ph["floor_m"] + 8 + 1, 90, 60, 2)
    out.append(
        _mesh_obj(
            "Taqsimlash qurilmasi (OPU)",
            "switchyard",
            "IfcBuildingElementProxy",
            ov,
            of,
            (0.6, 0.6, 0.6),
        )
    )
    return out


def site_values(preset_id: str) -> dict:
    """Maydon pasporti (ges_sim.site SITE_FIELDS kalitlari)."""
    p = PRESETS[preset_id]
    d, r, h, u, pen, sp, ph, s = (
        p["dam"], p["reservoir"], p["hydrology"], p["units"], p["penstocks"], p["spillway"], p["powerhouse"], p["seismic"],
    )  # fmt: skip
    return {
        "intensity": s["intensity"],
        "ground": s["ground"],
        "soil": s["soil"],
        "k_m_s": 1e-7 if s["soil"] == "rock" else 1e-5,
        "friction": 0.75 if d["type"] == "concrete" else 0.7,
        "cohesion_kpa": 300 if s["soil"] == "rock" else 100,
        "capacity_mcm": r["capacity_mcm"],
        "dead_mcm": r["dead_mcm"],
        "normal_level_m": r["normal_level_m"],
        "max_level_m": r["max_level_m"],
        "dead_level_m": r["dead_level_m"],
        "area_km2": r["area_km2"],
        "curve_elev": r["curve_elev"],
        "curve_vol": r["curve_vol"],
        **h,
        "dam_type": d["type"],
        "dam_height_m": d["height_m"],
        "crest_elevation_m": d["crest_elevation_m"],
        "base_elevation_m": d["base_elevation_m"],
        "crest_width_m": d["crest_width_m"],
        "dam_length_m": d["length_m"],
        "upstream_slope": d["upstream_slope"],
        "downstream_slope": d["downstream_slope"],
        "spill_crest_m": sp["crest_m"],
        "spill_width_m": sp["width_m"],
        "outlet_area_m2": 0.0,
        "outlet_sill_m": d["base_elevation_m"]
        + 10.0,  # tubi suv chiqargich (bo'lsa) — tag ustidan 10 m
        "penstock_length_m": max(pen["lengths_m"]),
        "penstock_diameter_m": pen["diameter_m"],
        "penstock_material": pen["material"],
        "penstock_roughness_mm": 0.6 if pen["material"] == "concrete" else 0.1,
        "design_flow_m3s": u["count"] * u["flow_m3s"],
        "units_count": u["count"],
        "tailwater_m": p["tailwater_m"],
        "tailwater_flood_m": p["tailwater_m"] + 6,
        "ch_width_m": 30.0 if p.get("layout") == "compact" else 90.0,
        "ch_bank_depth_m": 5.0 if p.get("layout") == "compact" else 8.0,
        "powerhouse_floor_m": ph["floor_m"],
        "powerhouse_height_m": ph["height_m"],
        "model_zero_m": 0.0,
        "slope_deg": 32.0,
        "slide_depth_m": max(5.0, (r["normal_level_m"] - d["base_elevation_m"]) * 0.75),
        # ko'chki ssenariysi ombor hajmiga mutanosib (katta ombor — 2 mln m³ sukut; kichik maket — 50 ming m³)
        "slide_volume_m3": 2_000_000.0 if r["capacity_mcm"] > 200 else 50_000.0,
        "slide_distance_m": 1500.0 if r["capacity_mcm"] > 200 else 300.0,
    }
