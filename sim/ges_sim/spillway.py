"""Suv tashlagich o'tkazuvchanligi — amaliy profilli (Kriger–Ofitserov) ostona, zatvor ostidan oqim.

Erkin oqim (SNiP 2.06.05-84*, Kiselev/Chugaev):  Q = ε·σ_s·m·b·√(2g)·H₀^1.5
  m — sarf koeffitsienti (Kriger–Ofitserov profili ≈ 0.49), b — ostonaning sof kengligi (bykalarsiz),
  H₀ = H + v₀²/(2g) — kelish tezligi napori bilan (v₀ = Q/A_kelish, 2 iteratsiya),
  ε — yon siqilish (Kiselev): ε = 1 − 0.2·[ξ_q + (n − 1)·ξ_b]·H₀/(n·b_oraliq), n — oraliqlar soni,
      ξ_q — qirg'oq ustuni (0.7 yumaloq, 1.0 to'g'ri burchak), ξ_b — byka (0.25 uchli, 0.45 yumaloq, 0.8 to'g'ri),
  σ_s — bostirish koeffitsienti, h_s/H₀ bo'yicha (amaliy profil, Chugaev jadvali): 0→1.0 … 1.0→0.
Zatvor ostidan (a < 0.75·H, Chugaev):  Q = μ·ε·b·a·√(2g·(H₀ − ε_c·a)),  μ ≈ 0.65, ε_c ≈ 0.62
  (vertikal siqilish, Jukovskiy); a ≥ 0.75·H — erkin oqim.
Bu modul `reservoir.py` (balans) va `flood.py` (marshrutlash) uchun yagona manba.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .penstock import G

# h_s/H₀ → σ_s (amaliy profil, Chugaev "Gidravlika" 2-jadval, taxminan)
_SUBMERGENCE = [
    (0.0, 1.0),
    (0.2, 0.99),
    (0.4, 0.97),
    (0.5, 0.93),
    (0.6, 0.86),
    (0.7, 0.76),
    (0.8, 0.62),
    (0.9, 0.40),
    (1.0, 0.0),
]
PIER_XI = {"pointed": 0.25, "rounded": 0.45, "square": 0.8}
ABUTMENT_XI = {"rounded": 0.7, "square": 1.0}


def submergence_factor(h_s: float, h0: float) -> float:
    """σ_s(h_s/H₀); h_s = quyi byef sathi − ostona (≤ 0 → 1.0)."""
    if h_s <= 0 or h0 <= 0:
        return 1.0
    r = min(h_s / h0, 1.0)
    for (x0, y0), (x1, y1) in zip(_SUBMERGENCE, _SUBMERGENCE[1:], strict=False):
        if x0 <= r <= x1:
            return y0 + (y1 - y0) * (r - x0) / (x1 - x0)
    return 0.0


def side_contraction(h0: float, bays: int, bay_width: float, xi_pier: float, xi_abut: float) -> float:
    """ε — yon siqilish (Kiselev); 0.6 dan kam bo'lmaydi (formula amal doirasi H₀/b ≤ 1)."""
    if bays <= 0 or bay_width <= 0:
        return 1.0
    eps = 1 - 0.2 * (xi_abut + (bays - 1) * xi_pier) * h0 / (bays * bay_width)
    return max(min(eps, 1.0), 0.6)


@dataclass(frozen=True)
class Spillway:
    crest_m: float
    width_m: float  # ostonaning sof (jami) kengligi, m
    m: float = 0.49  # sarf koeffitsienti
    bays: int = 1  # oraliqlar soni (bykalar + 1)
    pier: str = "rounded"  # byka boshi: pointed | rounded | square
    abutment: str = "rounded"  # qirg'oq ustuni: rounded | square
    approach_area_m2: float = 0.0  # kelish o'zani kesimi; 0 — tezlik napori hisobga olinmaydi
    gate_opening: float = 1.0  # 0..1 — zatvor ochiqligi (gate_height_m ga yoki H ga nisbatan)
    gate_height_m: float = 0.0  # zatvor to'liq balandligi; 0 — ochiqlik H ga nisbatan ulush
    mu_gate: float = 0.65  # zatvor ostidan oqim koeffitsienti
    eps_c: float = 0.62  # vertikal siqilish

    def discharge(self, elev: float, tailwater_m: float | None = None) -> float:
        return self.discharge_detail(elev, tailwater_m)["q"]

    def discharge_detail(self, elev: float, tailwater_m: float | None = None) -> dict:
        h = elev - self.crest_m
        if h <= 0 or self.gate_opening <= 0 or self.width_m <= 0:
            return {"q": 0.0, "h0": max(h, 0.0), "eps": 1.0, "sigma": 1.0, "regime": "yopiq"}
        bay_w = self.width_m / max(self.bays, 1)
        xi_p, xi_a = PIER_XI.get(self.pier, 0.45), ABUTMENT_XI.get(self.abutment, 0.7)
        h_s = (tailwater_m - self.crest_m) if tailwater_m is not None else 0.0
        a = self.gate_opening * (self.gate_height_m if self.gate_height_m > 0 else h)
        orifice = a < 0.75 * h
        q, h0 = 0.0, h
        for _ in range(3):  # kelish tezligi napori: H₀ = H + v₀²/2g, Q ga bog'liq → iteratsiya
            v0 = q / self.approach_area_m2 if self.approach_area_m2 > 0 else 0.0
            h0 = h + v0 * v0 / (2 * G)
            eps = side_contraction(h0, self.bays, bay_w, xi_p, xi_a)
            if orifice:
                head = max(h0 - self.eps_c * a, 0.0)
                q = self.mu_gate * eps * self.width_m * a * math.sqrt(2 * G * head)
                sigma = 1.0
                if h_s > 0:
                    # zatvor ostidan bostirilgan oqim: napor farqi bilan (soddalashtirilgan)
                    q = self.mu_gate * eps * self.width_m * a * math.sqrt(2 * G * max(h0 - h_s, 0.0))
            else:
                sigma = submergence_factor(h_s, h0)
                q = eps * sigma * self.m * self.width_m * math.sqrt(2 * G) * h0**1.5
        return {
            "q": q,
            "h0": h0,
            "eps": eps,
            "sigma": sigma,
            "regime": "zatvor ostidan" if orifice else ("bostirilgan" if h_s > 0 else "erkin"),
        }
