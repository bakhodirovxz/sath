# Desktop (Blender) unumdorligi — bazaviy o'lchov

Sana: 2026-10-08 · Mashina: Intel64 Family 6 Model 165 Stepping 3, GenuineIntel · OS: Windows 10 · Blender: Blender 5.2.2 LTS (`~/Tools/blender-5.2/blender.exe`)

Usul: `python desktop/tests/perf_baseline.py --n 2000` — har o'lchov 3 marta, mediana. Spec §5 byudjetlari va C++ (`sath_core`) qarorlari shu raqamlarga tayanadi.

Rejim: barcha qatorlar `blender -b --factory-startup` (bir xil toza profil; Bonsai extension `bl_ext.user_default.bonsai` o'zi yoqiladi va tekshiriladi). Sath repo dan ro'yxatga olinadi. Eslatma: o'lchovlar ketma-ket, issiq OS keshi bilan (sovuq-disk start emas).

| O'lchov | Qiymat |
|---|---|
| Sovuq start, Blender | 1.03 s |
| Sovuq start, + Bonsai | 4.63 s |
| Sovuq start, + Bonsai + Sath | 4.62 s |
| Sovuq start nisbati (+Sath / +Bonsai), byudjet <= 1.2 | 1.0x |
| Sath import + register (Bonsai yoqilgan), byudjet < 150 ms | 31.4 ms |
| Idle RSS: Blender / + Bonsai / + Sath | 160.71 / 350.68 / 351.93 MB |
| Sath RSS ortishi (Bonsai ustiga), byudjet <= 50 MB | 1.2 MB |
| Sintetik IFC (2000 element, 1.61 MB) ochish | 3.1 s |
| RSS IFC ochilgandan keyin (alohida jarayonda yaratilgan IFC) | 598.32 MB |
