"""ISO 19650 (G4): axborot konteynerlari uchun yaroqlilik (suitability) va reviziya kodlari, holat bilan
moslik, konteyner nomlash qoidasi.

Yaroqlilik kodlari (BS EN ISO 19650-2 UK milliy ilovasi, jadval NA.2 / PAS 1192-2 lineage):
  S0 — WIP (ishlanmoqda);  S1 koordinatsiya, S2 axborot, S3 ko'rib chiqish/izoh, S4 bosqich tasdig'i,
  S5 ishlab chiqarish/qurilish, S6 PIM avtorizatsiyasi, S7 AIM avtorizatsiyasi — Shared (umumiy);
  A1…An — avtorizatsiya qilingan va qabul qilingan (bosqich n), B1…Bn — qisman imzolangan (izohlar bilan),
  CR — qurilgandek (as constructed), PR — ekspluatatsiya uchun (published/archived).
Reviziya: P01, P02… (dastlabki — WIP/Shared), C01, C02… (shartnomaviy — Published).
Holat ↔ kod mosligi tekshiriladi; noto'g'ri juftlik rad etiladi (roadmap G4 qabul mezoni).
"""

from __future__ import annotations

import re

from ..orm import VersionState

SUITABILITY_RE = re.compile(r"^(S[0-7]|A[1-9][0-9]?|B[1-9][0-9]?|CR|PR)$")
REVISION_RE = re.compile(r"^(P|C)(\d{2,3})$")

SUITABILITY_LABEL = {
    "S0": "WIP — ishlanmoqda",
    "S1": "koordinatsiya uchun",
    "S2": "axborot uchun",
    "S3": "ko'rib chiqish va izoh uchun",
    "S4": "bosqich tasdig'i uchun",
    "S5": "ishlab chiqarish/qurilish uchun",
    "S6": "PIM avtorizatsiyasi uchun",
    "S7": "AIM avtorizatsiyasi uchun",
    "A": "avtorizatsiya qilingan va qabul qilingan",
    "B": "qisman imzolangan (izohlar bilan)",
    "CR": "qurilgandek (as constructed)",
    "PR": "ekspluatatsiya (AIM)",
}

# Holat → ruxsat etilgan kod oilalari
_ALLOWED = {
    VersionState.wip: ("S0",),
    VersionState.shared: ("S1", "S2", "S3", "S4", "S5", "S6", "S7"),
    VersionState.published: ("A", "B", "CR", "PR"),
    VersionState.archived: ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "A", "B", "CR", "PR"),
}
DEFAULT = {VersionState.wip: "S0", VersionState.shared: "S3", VersionState.published: "A1", VersionState.archived: None}


def family(code: str) -> str:
    if code.startswith("A"):
        return "A"
    if code.startswith("B"):
        return "B"
    return code


def label(code: str | None) -> str:
    if not code:
        return ""
    return SUITABILITY_LABEL.get(family(code), "")


def check_suitability(code: str, state: VersionState) -> None:
    """Kod formati va holat bilan mosligi; xato — ValueError (matn foydalanuvchiga)."""
    c = code.strip().upper()
    if not SUITABILITY_RE.match(c):
        raise ValueError(f"Yaroqlilik kodi noto'g'ri: {code} (S0–S7, A1–An, B1–Bn, CR, PR)")
    if family(c) not in _ALLOWED[state]:
        raise ValueError(
            f"{c} kodi «{state.value}» holatiga mos emas: wip → S0; shared → S1–S7; published → A/B/CR/PR"
        )


def check_revision(code: str, state: VersionState) -> None:
    c = code.strip().upper()
    m = REVISION_RE.match(c)
    if not m:
        raise ValueError(f"Reviziya kodi noto'g'ri: {code} (P01… dastlabki, C01… shartnomaviy)")
    if state == VersionState.published and m.group(1) != "C":
        raise ValueError("Published versiya shartnomaviy reviziya (C01…) bo'lishi kerak")
    if state in (VersionState.wip, VersionState.shared) and m.group(1) != "P":
        raise ValueError("WIP/Shared versiya dastlabki reviziya (P01…) bo'lishi kerak")


def next_revision(existing: list[str | None], series: str) -> str:
    """Modeldagi mavjud kodlardan keyingisi: series P yoki C."""
    n = 0
    for c in existing:
        if not c:
            continue
        m = REVISION_RE.match(c.upper())
        if m and m.group(1) == series:
            n = max(n, int(m.group(2)))
    return f"{series}{n + 1:02d}"


def normalize(code: str | None) -> str | None:
    return code.strip().upper() if code and code.strip() else None


# --------------------------------------------------------------------------- konteyner nomlash


def naming_regex(template: str) -> re.Pattern:
    """Shablon `{project}-{originator}-{volume}-{level}-{type}-{role}-{number}` → regex (har maydon [A-Z0-9]+,
    ajratuvchi shablondagidek; kengaytma ixtiyoriy). Bo'sh shablon → hamma nom mos."""
    if not template.strip():
        return re.compile(r".*")
    parts = re.split(r"(\{[a-z_]+\})", template.strip())
    out = "^"
    for part in parts:
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            out += r"[A-Za-z0-9]+"
        else:
            out += re.escape(part)
    out += r"(\.[A-Za-z0-9]+)?$"
    return re.compile(out)


def check_name(file_name: str, template: str) -> str | None:
    """Nom shablonga mos bo'lmasa — ogohlantirish matni, aks holda None."""
    if not template.strip():
        return None
    if naming_regex(template).match(file_name):
        return None
    return f"Konteyner nomi «{file_name}» loyiha qoidasiga mos emas: {template}"
