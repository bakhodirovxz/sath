# FreeCAD konsol rejimida ham yuklanadi (GUI siz).
#  * DWG konverterni (dwg2dxf / ODA) avtomatik sozlaydi — bo'lmasa FreeCAD «No suitable external DWG converter» deydi
#  * assimp (Mod/Ges/vendor) o'qiydigan formatlarni (FBX, LWO, X, …) Fayl → Ochish ga qo'shadi
try:
    from ges_workbench import converters as _ges_conv

    _ges_conv.ensure_dwg_converter()
except Exception as _e:  # noqa: BLE001 — sozlama ixtiyoriy, dasturni to'xtatmasin
    import FreeCAD as _App

    _App.Console.PrintWarning(f"Sath: DWG konverter tekshiruvi o'tmadi: {_e}\n")
try:
    from ges_workbench import mesh_open as _ges_mesh

    _ges_mesh.register()
except Exception as _e:  # noqa: BLE001
    import FreeCAD as _App

    _App.Console.PrintWarning(f"Sath: mesh formatlar ro'yxati o'tmadi: {_e}\n")
