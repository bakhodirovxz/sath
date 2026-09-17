"""CFD (OpenFOAM) — case generatsiya, ishga tushirish, natijalarni o'qish.

Ikki shablon:
- penstock  — bosimli quvur ichidagi oqim, o'q-simmetrik (wedge), simpleFoam + k-epsilon.
- spillway  — suv tashlagich ustidan erkin sirtli oqim, 2D, interFoam (VOF).

OpenFOAM (v2406, opencfd) lokal yoki Docker orqali ishlaydi: runner.py.
"""

from .case import PenstockCase, SpillwayCase, build_case
from .runner import run_case

__all__ = ["PenstockCase", "SpillwayCase", "build_case", "run_case"]
