"""Materiallar katalogi: gidrotexnik beton klasslari, po'lat markalari (quvurlar), gruntlar va tosh.

Beton — KMK 2.03.01 / SP 63.13330 (SNiP 2.03.01-84*): B — siqilishga klass; R_b, R_bt — hisobiy
qarshiliklar (MPa), R_bn/R_btn — normativ, E_b — elastiklik moduli (tabiiy qotish), γ — solishtirma og'irlik.
Gidrotexnik beton (SP 41.13330 / SNiP 2.06.08): suv o'tkazmaslik W, sovuqqa chidamlilik F, zonalar bo'yicha
tavsiyalar. Issiqlik: adiabatik qizish sement miqdoriga proporsional (~0.12 °C na kg/m³ CEM I).
Po'lat — GOST 19281 / 27772: σ_T (oquvchanlik), σ_B (mustahkamlik), ruxsat etilgan = σ_T/1.5 (statik),
σ_T/1.25 (o'tkinchi — gidravlik zarba).
"""

from __future__ import annotations

CONCRETE: dict[str, dict] = {
    # klass: nom, Rb, Rbt, Rbn, Rbtn, E (MPa), gamma kN/m³, zona/tavsiya
    "B10": {
        "name": "B10 (RCC/ichki massiv)",
        "Rb": 6.0,
        "Rbt": 0.56,
        "Rbn": 7.5,
        "Rbtn": 0.85,
        "E": 19000,
        "gamma": 23.5,
        "use": "Katta massiv ichki zonasi, RCC (g'altakli beton); yuzaga yaroqsiz",
    },
    "B15": {
        "name": "B15",
        "Rb": 8.5,
        "Rbt": 0.75,
        "Rbn": 11.0,
        "Rbtn": 1.10,
        "E": 24000,
        "gamma": 24.0,
        "use": "To'g'on ichki massivi (past issiqlik), poydevor",
    },
    "B20": {
        "name": "B20",
        "Rb": 11.5,
        "Rbt": 0.90,
        "Rbn": 15.0,
        "Rbtn": 1.35,
        "E": 27500,
        "gamma": 24.0,
        "use": "Massiv beton, yuqori/quyi yuza (W6–W8, F150–F200)",
    },
    "B25": {
        "name": "B25",
        "Rb": 14.5,
        "Rbt": 1.05,
        "Rbn": 18.5,
        "Rbtn": 1.55,
        "E": 30000,
        "gamma": 24.0,
        "use": "Yuza zonasi, mashina zali konstruksiyalari (W8, F200–F300)",
    },
    "B30": {
        "name": "B30",
        "Rb": 17.0,
        "Rbt": 1.15,
        "Rbn": 22.0,
        "Rbtn": 1.75,
        "E": 32500,
        "gamma": 24.5,
        "use": "Suv tashlagich, quvur qobig'i, temir-beton (W8–W12, F300)",
    },
    "B35": {
        "name": "B35",
        "Rb": 19.5,
        "Rbt": 1.30,
        "Rbn": 25.5,
        "Rbtn": 1.95,
        "E": 34500,
        "gamma": 24.5,
        "use": "Yemirilishga chidamli yuzalar (chute, byef), yuqori bosim",
    },
    "B40": {
        "name": "B40",
        "Rb": 22.0,
        "Rbt": 1.40,
        "Rbn": 29.0,
        "Rbtn": 2.10,
        "E": 36000,
        "gamma": 24.5,
        "use": "Kavitatsiya/abraziv zonalar, oldindan zo'riqtirilgan elementlar",
    },
    "B45": {
        "name": "B45",
        "Rb": 25.0,
        "Rbt": 1.50,
        "Rbn": 32.0,
        "Rbtn": 2.25,
        "E": 37000,
        "gamma": 25.0,
        "use": "Yuqori yuklamali konstruksiyalar",
    },
    "B50": {
        "name": "B50",
        "Rb": 27.5,
        "Rbt": 1.60,
        "Rbn": 36.0,
        "Rbtn": 2.45,
        "E": 38000,
        "gamma": 25.0,
        "use": "Maxsus (arkali to'g'on, nozik elementlar)",
    },
    "B60": {
        "name": "B60",
        "Rb": 33.0,
        "Rbt": 1.80,
        "Rbn": 43.0,
        "Rbtn": 2.75,
        "E": 39500,
        "gamma": 25.0,
        "use": "Yuqori mustahkamlik — massiv uchun tavsiya etilmaydi (issiqlik)",
    },
}

# Sement turi → adiabatik qizish koeffitsienti, °C na (kg sement / m³), va sharh
CEMENT: dict[str, dict] = {
    "cem1": {
        "name": "CEM I (portland)",
        "q": 0.12,
        "note": "eng yuqori issiqlik — massivda sovutish/qatlamlash kerak",
    },
    "cem2": {"name": "CEM II (pussolan/shlak 20–35 %)", "q": 0.095, "note": "o'rtacha issiqlik"},
    "cem3": {
        "name": "CEM III (shlakli 36–65 %)",
        "q": 0.08,
        "note": "past issiqlik — massiv beton uchun",
    },
    "lowheat": {"name": "Past issiqlikli (LH) / RCC", "q": 0.065, "note": "to'g'on ichki zonasi"},
}

STEEL: dict[str, dict] = {
    # marka: σ_T, σ_B (MPa), E, izoh
    "st3": {
        "name": "St3sp (S235)",
        "yield": 245,
        "ult": 370,
        "E": 2.06e5,
        "note": "past bosimli quvurlar, arzon",
    },
    "s355": {
        "name": "S355 / 09G2S",
        "yield": 345,
        "ult": 490,
        "E": 2.06e5,
        "note": "bosimli quvurlar standarti, payvandlanadi",
    },
    "17g1s": {
        "name": "17G1S",
        "yield": 365,
        "ult": 510,
        "E": 2.06e5,
        "note": "yirik diametrli quvur (GOST 19281)",
    },
    "10hsnd": {
        "name": "10HSND",
        "yield": 390,
        "ult": 530,
        "E": 2.06e5,
        "note": "sovuqqa chidamli, yuqori bosim",
    },
    "s460": {
        "name": "S460 (yuqori mustahkam)",
        "yield": 460,
        "ult": 560,
        "E": 2.06e5,
        "note": "juda yuqori napor; payvandlash nazorati talab etiladi",
    },
}

SOIL_MATERIALS: dict[str, dict] = {
    "clay_core": {
        "name": "Gil (yadro)",
        "gamma": 19.0,
        "phi": 22,
        "c": 30,
        "k": 1e-8,
        "note": "suv o'tkazmas yadro; qurishda yoriladi, gidravlik yorilish xavfi",
    },
    "sandy_gravel": {
        "name": "Qumli shag'al (prizma)",
        "gamma": 20.5,
        "phi": 38,
        "c": 0,
        "k": 1e-4,
        "note": "drenajlovchi prizma, zilzilada suyuqlanish (bo'sh holda)",
    },
    "rockfill": {
        "name": "Tosh to'kma",
        "gamma": 21.5,
        "phi": 43,
        "c": 0,
        "k": 1e-2,
        "note": "eng mustahkam, cho'kish 0.2–0.5 % balandlikdan",
    },
    "loess": {
        "name": "Lyoss (cho'kuvchan)",
        "gamma": 16.5,
        "phi": 24,
        "c": 15,
        "k": 1e-6,
        "note": "namlanganda cho'kadi — to'g'on asosi uchun xavfli",
    },
    "rock_hard": {
        "name": "Mustahkam qoya (granit, gneys)",
        "gamma": 26.0,
        "phi": 45,
        "c": 500,
        "k": 1e-7,
        "note": "beton to'g'onlar uchun ideal asos",
    },
    "rock_weathered": {
        "name": "Nurgan qoya / ohaktosh",
        "gamma": 24.0,
        "phi": 35,
        "c": 150,
        "k": 1e-5,
        "note": "karst/yoriqlar — sement parda kerak",
    },
}

ALPHA_CONCRETE = 1.0e-5  # chiziqli kengayish, 1/°C


def concrete(cls: str) -> dict:
    return CONCRETE.get(cls, CONCRETE["B20"])


def steel(grade: str) -> dict:
    return STEEL.get(grade, STEEL["s355"])


def concrete_options() -> tuple[tuple[str, str], ...]:
    return tuple((k, v["name"]) for k, v in CONCRETE.items())


def steel_options() -> tuple[tuple[str, str], ...]:
    return tuple((k, v["name"]) for k, v in STEEL.items())


def catalog() -> dict:
    """Web uchun to'liq katalog (tanlash ro'yxatlari + tavsiyalar)."""
    return {
        "concrete": [{"id": k, **v} for k, v in CONCRETE.items()],
        "cement": [{"id": k, **v} for k, v in CEMENT.items()],
        "steel": [{"id": k, **v} for k, v in STEEL.items()],
        "soil": [{"id": k, **v} for k, v in SOIL_MATERIALS.items()],
        "zones": [
            {
                "zone": "To'g'on ichki massivi",
                "concrete": "B10–B15, past issiqlikli sement, yirik to'ldiruvchi (120–150 mm)",
                "why": "issiqlik yorilishini kamaytirish, hajm katta",
            },
            {
                "zone": "Yuqori byef yuzasi (2–4 m qatlam)",
                "concrete": "B20–B25, W8–W12, F200–F300",
                "why": "suv bosimi, muzlash-erish, sizish",
            },
            {
                "zone": "Quyi byef yuzasi",
                "concrete": "B20, W4–W6, F200",
                "why": "atmosfera ta'siri",
            },
            {
                "zone": "Suv tashlagich ostonasi va chute",
                "concrete": "B30–B40, F300, abraziv chidamli",
                "why": "yuqori tezlik (kavitatsiya, yemirilish)",
            },
            {
                "zone": "Tag (asos bilan tutashuv)",
                "concrete": "B20–B25, W8",
                "why": "sizish, tovon kuchlanishlari",
            },
            {
                "zone": "Mashina zali karkasi",
                "concrete": "B25–B30 temir-beton",
                "why": "dinamik yuklar (agregat), aniq o'lchamlar",
            },
            {
                "zone": "Bosimli quvur (po'lat)",
                "concrete": "S355/17G1S; qobiq B30",
                "why": "gidravlik zarba, halqa kuchlanish",
            },
        ],
    }
