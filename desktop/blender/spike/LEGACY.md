# Legacy: Blender + FreeCAD spike (2026-09)

Holat: **legacy / o'lik kod** (audit CODE-02). Bir martalik tajriba — FreeCAD ni Blender jarayoniga yuklash,
DWG → DXF → Blender, Bonsai bilan birga ishlash. Natijalar: `docs/spike-blender-freecad.md`; ishlaydigan kod —
`desktop/blender/sath` (`fc_engine.py`, `ops_import.py`).

- Ishlatilmaydi, testlarga kirmaydi, ruff dan chiqarilgan (`ruff.toml` `extend-exclude`).
- Yo'llar muhit o'zgaruvchilaridan (`GES_FC_HOME`, `GES_WB_DIR`, `GES_TEST_IFC`, `GES_TEST_DWG`) yoki repo ga
  nisbatan olinadi; loglar (`spike-*.log`) repoga qo'shilmaydi.
- Tarix uchun qoldirilgan; keyinchalik o'chirilishi mumkin.
