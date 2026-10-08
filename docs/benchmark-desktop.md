# Desktop (Blender) unumdorligi — bazaviy o'lchov

Sana: 2026-10-08 · Mashina: Intel64 Family 6 Model 165 Stepping 3, GenuineIntel · OS: Windows 10 · Blender: Blender 5.2.2 LTS (`~/Tools/blender-5.2/blender.exe`)

Usul: `python desktop/tests/perf_baseline.py --n 2000` — har o'lchov 3 marta, mediana. Spec §5 byudjetlari va C++ (`sath_core`) qarorlari shu raqamlarga tayanadi.

| O'lchov | Qiymat |
|---|---|
| Sovuq start, vanilla (-b, factory) | 1.05 s |
| Sovuq start, + Bonsai | 4.89 s |
| Sath import + register | 30.5 ms |
| RSS: start / Sath bilan | 357.94 / 358.82 MB |
| Sintetik IFC (2000 element, 1.61 MB) ochish | 2.9 s |
| RSS IFC ochilgandan keyin | 606.55 MB |
