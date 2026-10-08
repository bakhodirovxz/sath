# Desktop (Blender) unumdorligi — o'lchov va byudjetlar

Sana: 2026-10-09 · Mashina: Intel64 Family 6 Model 165 Stepping 3, GenuineIntel · OS: Windows 10 · Blender: Blender 5.2.2 LTS (`~/Tools/blender-5.2/blender.exe`)

Usul: `python desktop/tests/perf_baseline.py --n 2000 --bundle <stage> --check` — har o'lchov 3 marta, mediana. P0 ustuni — 2026-10-08 bazaviy o'lchov (Sath P0 holatida). Byudjetlar — spec §5 (`desktop/blender/sath/core/budget.py`).

Rejim: barcha qatorlar `blender -b --factory-startup` (bir xil toza profil; Bonsai extension `bl_ext.user_default.bonsai` o'zi yoqiladi). Sath repo dan ro'yxatga olinadi; «+ Sath» sovuq starti app template ish joylarini ham quradi. Og'ir importlar Bonsai siz o'lchanadi (Bonsai numpy va ifcopenshell ni o'zi yuklaydi). O'lchovlar ketma-ket, issiq OS keshi bilan (sovuq-disk start emas). Har ishga tushishda Sath logi: `[sath] register … ms (byudjet < 150): import …, host … [modullar: …]`.

Eslatma (issiq va sovuq register): byudjet `< 150 ms` **issiq** register ga tegishli (`__pycache__` bor, oddiy qayta ishga tushish). `__pycache__` tozalangan birinchi ishga tushishda (extension o'rnatilgandan keyin) register ~260–310 ms (2026-10-09 o'lchovi: 265 / 276 / 307 ms; import ~115–155, host ~140) — bu bir martalik .pyc kompilyatsiyasi, byudjet unga qo'llanmaydi. Bundle da .pyc oldindan kompilyatsiya qilingan (checked-hash, `compileall -f`): zip/installer fayl vaqtini o'zgartirsa ham birinchi ishga tushishda qayta kompilyatsiya yo'q (`bundle_check` tekshiradi); bundle (GUI, yangi stage) birinchi ishga tushishda register ~69 ms, keyingisida ~43 ms (2026-10-09, `run_gui_workspaces.py --bundle`).

| O'lchov | P0 | Hozir |
|---|---|---|
| Sovuq start, Blender | 1.03 s | 0.93 s |
| Sovuq start, + Bonsai | 4.63 s | 4.5 s |
| Sovuq start, + Bonsai + Sath (+ ish joylari) | 4.62 s | 4.64 s |
| Sath import + register (Bonsai yoqilgan) | 31.4 ms | 62.0 ms |
| Idle RSS: Blender / + Bonsai / + Sath | 160.71 / 350.68 / 351.93 MB | 160.75 / 351.16 / 353.36 MB |
| Sintetik IFC (2000 element, 1.61 MB) ochish | 3.1 s | 2.86 s |
| RSS IFC ochilgandan keyin | 598.32 MB | 599.28 MB |
| Sath ish joylari qurish (ensure, 4 ta) | — | 1.11 ms |
| Bundle hajmi (ochilgan stage) | 2392 MB (FreeCAD 935 MB bilan) | 1637 MB (sof o'zgarish P0 ga nisbatan −755 MB) |

## Byudjetlar (spec §5)

| Byudjet | Chegara | Hozir | Holat |
|---|---|---|---|
| Sath import + register | < 150 ms | 62.0 ms | bajarildi |
| Og'ir importlar register da (numpy, ifcopenshell, ezdxf, assimp_py) | yo'q | yo'q | bajarildi |
| Sovuq start nisbati (+Sath / +Bonsai) | <= 1.2x | 1.03x | bajarildi |
| Sath RSS ortishi (Bonsai ustiga) | <= 50 MB | 2.2 MB | bajarildi |
| Bundle FreeCAD siz (−935 MB) | freecad/ yo'q | yo'q | bajarildi |
| Bundle hajmi | <= 1700 MB | 1637 MB | bajarildi |

## Bundle hajmi (ochilgan stage)

FreeCAD olib tashlanishi **935 MB** tejadi; P0 (2392 MB) ga nisbatan sof o'zgarish **−755 MB** (1637 MB). Qolgan o'sish (taxminiy: P0 uchun toifalar bo'yicha o'lchov yo'q) Bonsai 0.9.0 va oldindan kompilyatsiya qilingan `.pyc` fayllar bilan bog'liq (ular «FreeCAD tejami» taqqosiga kirmaydi).

| Toifa | MB |
|---|---|
| Blender | 915 |
| Bonsai | 571 |
| Sath | 4 |
| libredwg | 35 |
| .pyc | 112 |
| **Jami** | **1637** |

Xulosa: barcha byudjetlar bajarildi.
