"""To'g'on turini tanlash maslahatchisi: maydon sharoitlari → turlar reytingi, qachon yaxshi/yomon, moyil joylar.

Qoidalar ICOLD Bulletin / USBR "Design of Small Dams" (1987) / SNiP 2.06.05, 2.06.06 tavsiyalariga
asoslangan: asos turi, dara shakli (L/H), balandlik, seysmiklik, mahalliy materiallar, suv tashlagich,
qurilish muddati, iqlim. Har tur uchun ball (0–100) va sabablar; yakuniy — reyting.
"""

from __future__ import annotations

from .schema import Field, Meta

META = Meta(
    id="dam_type",
    title="Qaysi to'g'on turi mos? (maslahatchi)",
    description="Asos, dara shakli, balandlik, seysmiklik, materiallar, toshqin va muddat bo'yicha beton og'irlik, "
    "arkali, kontrfors, RCC, tuproq va tosh to'kma to'g'onlarni solishtiradi: qachon yaxshi, qachon yomon, "
    "yorilishga moyil joylar.",
    group="mustahkamlik",
    icon="compass",
    formulas=[
        "Ballar: asos 30 · dara 20 · balandlik 15 · seysmiklik 15 · materiallar 10 · toshqin 5 · muddat 5"
    ],
    outputs=[
        {"key": "best", "label": "Eng mos tur", "unit": ""},
        {"key": "best_score", "label": "Ball", "unit": "/100"},
    ],
)

FIELDS = [
    Field(
        "foundation",
        "Asos",
        type="select",
        default="rock_hard",
        options=(
            ("rock_hard", "Mustahkam qoya"),
            ("rock_weathered", "Nurgan/yoriq qoya, ohaktosh"),
            ("gravel", "Shag'al-qum (zich)"),
            ("sand", "Qum (bo'sh)"),
            ("clay", "Gil / lyoss"),
        ),
        group="Maydon",
    ),
    Field(
        "height_m",
        "To'g'on balandligi",
        "m",
        default=80,
        min=5,
        group="Maydon",
        model="dam.height_m",
    ),
    Field(
        "crest_length_m",
        "Gerb uzunligi (dara kengligi)",
        "m",
        default=300,
        min=10,
        group="Maydon",
        model="dam.length_m",
    ),
    Field(
        "intensity",
        "Seysmiklik",
        "ball",
        type="select",
        default="8",
        options=(("6", "≤6"), ("7", "7"), ("8", "8"), ("9", "9"), ("10", "10")),
        group="Maydon",
    ),
    Field("rock_nearby", "Yaqinda tosh karyeri", type="bool", default=True, group="Materiallar"),
    Field(
        "clay_nearby", "Yaqinda gil (yadro uchun)", type="bool", default=True, group="Materiallar"
    ),
    Field(
        "aggregate_nearby",
        "Beton to'ldiruvchisi (shag'al/qum)",
        type="bool",
        default=True,
        group="Materiallar",
    ),
    Field("flood_m3s", "Loyihaviy toshqin", "m³/s", default=2500, min=0, group="Gidrologiya"),
    Field(
        "overflow_needed",
        "Suv tashlagich to'g'on ustidan kerak",
        type="bool",
        default=True,
        group="Gidrologiya",
        hint="tor dara — alohida suv tashlagich joyi yo'q",
    ),
    Field("fast_build", "Qisqa muddat ustuvor", type="bool", default=False, group="Boshqa"),
    Field("cold_climate", "Qattiq sovuq iqlim (F300+)", type="bool", default=False, group="Boshqa"),
]

TYPES = {
    "gravity": {
        "name": "Beton og'irlik to'g'on",
        "good": [
            "mustahkam qoya asos",
            "toshqinni gerb orqali o'tkazish",
            "zilzila (massiv, past markaz)",
            "har qanday balandlik",
        ],
        "bad": [
            "yumshoq/qumli asos (sirpanish, cho'kish)",
            "yirik beton hajmi — issiqlik yoriqlari, narx",
            "filtratsion bosim katta (drenaj kerak)",
        ],
        "cracks": [
            "yuqori tovon (cho'zilish)",
            "asosga yaqin bloklar (issiqlik)",
            "galereyalar atrofi",
            "gerb osti (zilzila)",
        ],
    },
    "arch": {
        "name": "Arkali to'g'on",
        "good": [
            "tor dara (L/H < 3–4)",
            "mustahkam qoya abutmentlar",
            "kam beton (60–80 % tejash)",
            "zilzila (elastik)",
        ],
        "bad": [
            "keng dara (L/H > 5)",
            "zaif/nurgan abutment (asos tayanchi)",
            "yumshoq asos",
            "murakkab qurilish",
        ],
        "cracks": [
            "abutment tutashuvi",
            "toj konsoli tagi (yuqori yuza)",
            "bir tomonlama harorat gradienti (quyi yuza)",
        ],
    },
    "buttress": {
        "name": "Kontrfors to'g'on",
        "good": [
            "o'rtacha qoya asos",
            "filtratsion bosim kam",
            "beton tejash (og'irlikdan 30–50 %)",
        ],
        "bad": [
            "yuqori seysmiklik (ingichka elementlar)",
            "ko'p opalubka, temir-beton",
            "yumshoq asos",
        ],
        "cracks": [
            "kontrfors–plita tutashuvi",
            "kontrfors tagi (cho'zilish)",
            "yupqa plitalarda muzlash",
        ],
    },
    "rcc": {
        "name": "RCC (g'altakli beton) to'g'on",
        "good": [
            "mustahkam/o'rtacha qoya",
            "tez qurilish (4–6 m/hafta)",
            "past narx, kam sement (kam issiqlik)",
            "toshqin gerb orqali",
        ],
        "bad": [
            "yumshoq asos",
            "qatlamlar orasi sizish (W past)",
            "qattiq sovuqda yuza himoyasi kerak",
        ],
        "cracks": [
            "qatlam choklari (gorizontal sizish)",
            "yuqori tovon",
            "ko'ndalang harorat choklari yetarli bo'lmasa",
        ],
    },
    "earth": {
        "name": "Tuproq (yadroli) to'g'on",
        "good": [
            "har qanday asos (gil, qum, shag'al)",
            "keng dara",
            "mahalliy tuproq, arzon",
            "asos cho'kishiga moslashadi",
        ],
        "bad": [
            "gerbdan oshib o'tishga chidamsiz (halokat)",
            "alohida suv tashlagich kerak",
            "yuqori seysmiklikda yotiq qiyaliklar",
            "gidravlik yorilish, suffoziya",
        ],
        "cracks": [
            "gerb — abutmentlar yonida (ko'ndalang)",
            "yadro yuqori qismi (gidravlik yorilish)",
            "yadro–prizma chegarasi",
            "quvurlar atrofi",
        ],
    },
    "rockfill": {
        "name": "Tosh to'kma (CFRD / gil yadroli)",
        "good": [
            "tosh karyeri yaqin",
            "qoya/shag'al asos",
            "zilzilaga chidamli (yuqori)",
            "katta balandliklar (200 m+)",
        ],
        "bad": [
            "gerbdan oshib o'tish",
            "yumshoq gil asos (cho'kish)",
            "CFRD: yuza plitasi cho'kishga sezgir",
        ],
        "cracks": [
            "CFRD perimetral chok (plita–plinth)",
            "yuza plitasi markazi (siqilish)",
            "gerb (cho'kish)",
            "yadro–filtr chegarasi",
        ],
    },
}


def run(p: dict) -> dict:
    H, L = p["height_m"], p["crest_length_m"]
    ratio = L / H
    ball = int(p["intensity"])

    def add(t: str, pts: float, why: str, lst: dict):
        s, r = lst.get(t, (0.0, []))
        lst[t] = (s + pts, r + [f"{'+' if pts >= 0 else '−'}{abs(pts):.0f}: {why}"])

    sc: dict[str, tuple[float, list[str]]] = {}
    f = p["foundation"]
    # Asos (30)
    fnd = {
        "rock_hard": {
            "gravity": 30,
            "arch": 30,
            "buttress": 28,
            "rcc": 30,
            "earth": 20,
            "rockfill": 26,
        },
        "rock_weathered": {
            "gravity": 20,
            "arch": 12,
            "buttress": 16,
            "rcc": 20,
            "earth": 24,
            "rockfill": 26,
        },
        "gravel": {
            "gravity": 6 if H < 30 else 0,
            "arch": 0,
            "buttress": 2,
            "rcc": 4 if H < 30 else 0,
            "earth": 28,
            "rockfill": 28,
        },
        "sand": {
            "gravity": 2 if H < 20 else 0,
            "arch": 0,
            "buttress": 0,
            "rcc": 0,
            "earth": 26,
            "rockfill": 20,
        },
        "clay": {"gravity": 0, "arch": 0, "buttress": 0, "rcc": 0, "earth": 26, "rockfill": 12},
    }[f]
    for t, v in fnd.items():
        add(t, v, f"asos: {dict(FIELDS[0].options)[f]}", sc)
    # Dara shakli (20)
    for t in TYPES:
        if t == "arch":
            v = 20 if ratio < 3 else 14 if ratio < 4 else 6 if ratio < 5 else 0
            add(t, v, f"L/H = {ratio:.1f} ({'tor' if ratio < 4 else 'keng'} dara)", sc)
        elif t in ("earth", "rockfill"):
            add(t, 20 if ratio > 5 else 14 if ratio > 3 else 8, f"L/H = {ratio:.1f}", sc)
        else:
            add(t, 16 if ratio > 2 else 12, f"L/H = {ratio:.1f}", sc)
    # Balandlik (15)
    for t in TYPES:
        if t == "earth":
            v = 15 if H < 50 else 10 if H < 100 else 5
        elif t == "buttress":
            v = 12 if H < 60 else 6
        elif t == "rockfill":
            v = 15 if H >= 40 else 12
        elif t == "arch":
            v = 15 if H >= 60 else 10
        else:
            v = 14
        add(t, v, f"balandlik {H:.0f} m", sc)
    # Seysmiklik (15)
    seis = (
        {"gravity": 13, "arch": 12, "buttress": 6, "rcc": 12, "earth": 8, "rockfill": 14}
        if ball >= 8
        else {t: 13 for t in TYPES}
    )
    if ball >= 9:
        seis = {k: max(v - 3, 0) for k, v in seis.items()}
        seis["rockfill"] = 15
    for t, v in seis.items():
        add(t, v, f"seysmiklik {ball} ball", sc)
    # Materiallar (10)
    for t in TYPES:
        if t in ("gravity", "arch", "buttress", "rcc"):
            v = 10 if p["aggregate_nearby"] else 3
        elif t == "earth":
            v = 10 if p["clay_nearby"] else 2
        else:
            v = 10 if p["rock_nearby"] else 2
        add(t, v, "mahalliy materiallar", sc)
    # Toshqin / suv tashlagich (5)
    for t in TYPES:
        if p["overflow_needed"] or p["flood_m3s"] > 5000:
            v = 5 if t in ("gravity", "rcc", "buttress") else 3 if t == "arch" else 0
            add(t, v, "suv tashlagich to'g'on ustidan / katta toshqin", sc)
        else:
            add(t, 4, "toshqin alohida suv tashlagich orqali", sc)
    # Muddat / iqlim (5)
    for t in TYPES:
        v = 5 if (t in ("rcc", "rockfill", "earth") and p["fast_build"]) else 3
        if p["cold_climate"] and t in ("rcc", "buttress"):
            v -= 2
        add(t, v, "muddat/iqlim", sc)

    # Cheklovchi mezonlar: asos yaroqsiz (0–5 ball) → jami ≤ 40; arkali keng darada → ≤ 50
    for t, v in fnd.items():
        if v <= 5:
            s, r = sc[t]
            sc[t] = (min(s, 40.0), r + ["chegara: asos bu tur uchun yaroqsiz — jami ≤ 40"])
    if ratio >= 5:
        s, r = sc["arch"]
        sc["arch"] = (min(s, 50.0), r + ["chegara: keng dara (L/H ≥ 5) — arka ishlamaydi"])
    ranking = sorted(((t, s, r) for t, (s, r) in sc.items()), key=lambda x: -x[1])
    rows = [
        {
            "type": t,
            "name": TYPES[t]["name"],
            "score": round(s, 0),
            "reasons": r,
            "good": TYPES[t]["good"],
            "bad": TYPES[t]["bad"],
            "cracks": TYPES[t]["cracks"],
            "verdict": "mos" if s >= 75 else "shartli" if s >= 55 else "tavsiya etilmaydi",
        }
        for t, s, r in ranking
    ]
    best = rows[0]
    return {
        "series": {"type": [r["name"] for r in rows], "score": [r["score"] for r in rows]},
        "ranking": rows,
        "summary": {
            "best": best["name"],
            "best_score": best["score"],
            "second": rows[1]["name"],
            "ratio_LH": round(ratio, 2),
            "verdict": f"{best['name']} — {best['score']:.0f} ball ({best['verdict']}); keyingi: {rows[1]['name']} ({rows[1]['score']:.0f})",
            "ok": best["score"] >= 55,
        },
    }
