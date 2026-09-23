# Legacy: FreeCAD workbench (GesWorkbench)

Holat: **legacy** (audit CODE-02). Asosiy desktop — Blender 5.2 extension `desktop/blender/sath`;
FreeCAD u yerda faqat geometriya dvigateli (`sath/wb/ges_objects.py` nusxasi orqali).

- Bu papkada faqat xatolar tuzatiladi, yangi funksiya qo'shilmaydi.
- GUI qismi (`InitGui.py`, `ges_workbench/commands.py`, `dialogs.py`, `review_dialogs.py`) — legacy.
- `ges_workbench/ges_objects.py` — Blender addoni ham ishlatadi (manba shu yerda, `desktop/build/sync_blender.py`
  → `sath/wb/`).
- `assimp_load.py`, `dxf_prepare.py`, `server_client.py`, `ifc_classes.py`, `cad_common.py` —
  `common/sath_common` dan nusxa (CODE-01), bu yerda tahrirlamang.
- FreeCAD forki (Sath-FreeCAD), `desktop/build/sync_fork.py`, `desktop/build/build_portable.py`, NSIS — legacy
  tarqatish quvuri; paket nomi `Sath-FreeCAD-<ver>-Windows-x86_64` (Blender — `Sath-Blender-…`, CODE-03). Arxivlash / olib tashlash —
  roadmap K1, alohida qaror.
- Papka ko'chirilmagan: `sync_fork.py`, `desktop/tests/fc_headless.py`, `fc_gui.py`, `fc_cad.py` shu yo'lga tayanadi.
