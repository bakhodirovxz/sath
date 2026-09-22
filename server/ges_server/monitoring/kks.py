"""Uskuna kodlash (H1): KKS (VGB-B 105/106, Kraftwerk-Kennzeichensystem) va RDS-PP (VGB-S-823-32 / IEC 81346)
kod grammatikasi, daraja aniqlash (ISO 14224 taksonomiyasi), ierarxiya yordamchilari.

KKS tuzilmasi (0–3 darajalar):
  0 — butun stansiya:  G (ixtiyoriy, 1 belgi) — masalan «1»
  1 — funksiya kaliti:  [n] AAA nn   — blok raqami (ixtiyoriy), tizim (3 harf, masalan MKA — generator,
                        MAA — turbina, LAB — bosim quvuri suvi, HAD — suv olish), raqam 2 xona
  2 — uskuna birligi:   AA nnn      — masalan AH001 (agregat), AP001 (nasos), AT001 (zatvor)
  3 — komponent:        AA nn       — masalan MA01 (dvigatel), CT01 (harorat datchigi)
Namuna: «1MKA10 AH001 MA01». Ajratuvchi bo'sh joy ixtiyoriy.

RDS-PP (IEC 81346-10): belgilar — «=» funksiya, «-» mahsulot, «++»/«+» joylashuv, «#» tur; masalan
«=G001 MKA10 AH001» yoki «=1MKA10.AH001». Bu yerda funksiya («=») qismi KKS grammatikasi bilan tekshiriladi.

ISO 14224 taksonomiya darajalari (Sath): plant → system → equipment → component → part.
"""

from __future__ import annotations

import re

KKS_RE = re.compile(r"^(?P<unit>\d)?(?P<system>[A-Z]{3})(?P<sysno>\d{2})(?:\s?(?P<eq>[A-Z]{2})(?P<eqno>\d{3})(?:\s?(?P<comp>[A-Z]{2})(?P<compno>\d{2}))?)?$")
RDS_RE = re.compile(r"^=(?P<func>[A-Z0-9.\s]+?)(?:\s*-(?P<prod>[A-Z0-9.]+))?(?:\s*\+\+?(?P<loc>[A-Z0-9.]+))?$")

LEVELS = ("plant", "system", "equipment", "component", "part")
LEVEL_LABEL = {"plant": "stansiya", "system": "tizim", "equipment": "uskuna", "component": "komponent", "part": "qism"}

# KKS tizim kalitlari (VGB-B 105, GES uchun tegishli qismi) — nomi (ma'lumot uchun; ro'yxatdan tashqari kod ham qabul)
SYSTEM_KEYS = {
    "MAA": "Gidroturbina",
    "MAB": "Turbina yo'naltiruvchi apparati / regulyator",
    "MAV": "Turbina moylash tizimi",
    "MKA": "Generator",
    "MKC": "Generator qo'zg'atish",
    "MKF": "Generator sovutish",
    "MKY": "Generator himoyasi",
    "BAT": "Blok transformatori",
    "BAC": "Generator kommutatori",
    "LAB": "Bosimli quvur (turbina suv yo'li)",
    "HAD": "Suv qabul qilish inshooti",
    "HAA": "To'g'on / suv ombori",
    "HAB": "Suv tashlagich",
    "PAB": "Texnik suv ta'minoti",
    "SGA": "Ko'tarish mexanizmlari (kran)",
    "CJA": "Stansiya boshqaruv tizimi",
    "CFA": "O'lchov (sath, sarf)",
    "GKA": "Yordamchi elektr ta'minoti",
}


def normalize(code: str) -> str:
    return re.sub(r"\s+", " ", (code or "").strip().upper())


def parse(code: str) -> dict:
    """KKS yoki RDS-PP kodini tahlil qiladi → {"scheme", "level", "unit", "system", "sysno", "eq", "eqno",
    "comp", "compno", "system_name", "normalized"}; noto'g'ri — ValueError."""
    c = normalize(code)
    if not c:
        raise ValueError("Kod bo'sh")
    scheme = "KKS"
    func = c
    if c.startswith("="):
        scheme = "RDS-PP"
        m = RDS_RE.match(c)
        if not m:
            raise ValueError(f"RDS-PP kodi noto'g'ri: {code} (masalan =1MKA10 AH001)")
        func = m.group("func").replace(".", " ").strip()
        if func.startswith("G") and re.match(r"^G\d{3}\b", func):
            func = func[4:].strip()  # =G001 (stansiya) prefiksi
    m = KKS_RE.match(func.replace(".", " "))
    if not m:
        raise ValueError(
            f"KKS kodi noto'g'ri: {code} — shakl: [n]AAAnn [AAnnn [AAnn]] (masalan 1MKA10 AH001 MA01); "
            "tizim 3 harf + 2 raqam, uskuna 2 harf + 3 raqam, komponent 2 harf + 2 raqam"
        )
    g = m.groupdict()
    level = "system"
    if g["eq"]:
        level = "equipment"
    if g["comp"]:
        level = "component"
    return {
        "scheme": scheme,
        "level": level,
        "unit": g["unit"],
        "system": g["system"],
        "sysno": g["sysno"],
        "eq": g["eq"],
        "eqno": g["eqno"],
        "comp": g["comp"],
        "compno": g["compno"],
        "system_name": SYSTEM_KEYS.get(g["system"]),
        "normalized": (("=" if scheme == "RDS-PP" else "") + " ".join(p for p in [(g["unit"] or "") + g["system"] + g["sysno"], (g["eq"] or "") + (g["eqno"] or ""), (g["comp"] or "") + (g["compno"] or "")] if p)),
    }


def validate(code: str | None) -> str | None:
    """Bo'sh — None; aks holda normallashtirilgan kod (ValueError noto'g'ri bo'lsa)."""
    if code is None or not str(code).strip():
        return None
    return parse(code)["normalized"]


def parent_code(code: str) -> str | None:
    """Kodning ota kodi (komponent → uskuna → tizim → None)."""
    p = parse(code)
    prefix = "=" if p["scheme"] == "RDS-PP" else ""
    head = (p["unit"] or "") + p["system"] + p["sysno"]
    if p["level"] == "component":
        return prefix + head + " " + p["eq"] + p["eqno"]
    if p["level"] == "equipment":
        return prefix + head
    return None


def check_level(level: str | None) -> str | None:
    if level is None or level == "":
        return None
    if level not in LEVELS:
        raise ValueError(f"Taksonomiya darajasi: {', '.join(LEVELS)} (ISO 14224)")
    return level


def level_for(code: str | None, given: str | None) -> str | None:
    """Berilgan daraja yoki koddan aniqlangan daraja."""
    if given:
        return check_level(given)
    if code:
        return parse(code)["level"]
    return None
