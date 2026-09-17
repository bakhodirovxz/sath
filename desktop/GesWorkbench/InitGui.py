# Sath workbench — FreeCAD GUI da yuklanadi.
# Eslatma: FreeCAD InitGui.py ni __file__ siz va alohida nomlar fazosida bajaradi — modul darajasidagi
# nomlar class tanasida ko'rinmasligi mumkin. Shuning uchun hamma narsa class ichida import qilinadi;
# addon papkasi `ges_workbench` paketidan (Mod papkalari sys.path da) aniqlanadi.
import FreeCADGui


class GesWorkbench(FreeCADGui.Workbench):
    MenuText = "Sath"
    ToolTip = "Sath: server, versiyalar, tasdiqlash, GES obyektlari"
    Icon = __import__("os").path.join(
        __import__("os").path.dirname(
            __import__("os").path.dirname(
                __import__("os").path.abspath(__import__("ges_workbench").__file__)
            )
        ),
        "resources",
        "ges.svg",
    )

    def Initialize(self):
        from ges_workbench import commands, ges_objects

        commands.register()
        ges_objects.register()
        try:  # DXF/DWG: ranglar, matn, o'lchamlar AutoCAD kabi (dxf_fix hujjatiga qarang)
            from ges_workbench import dxf_fix

            dxf_fix.apply_prefs()
            dxf_fix.install()
        except Exception as e:  # noqa: BLE001
            __import__("FreeCAD").Console.PrintWarning(f"Sath: DXF sozlash o'tmadi: {e}\n")
        server_cmds = [
            "GES_Connect",
            "GES_Open",
            "GES_Commit",
            "GES_Submit",
            "GES_Review",
            "GES_Issues",
            "GES_Sim",
            "GES_SimCatalog",
            "GES_Versions",
            "GES_Monitor",
            "GES_OpenWeb",
            "GES_Notify",
        ]
        obj_cmds = ges_objects.COMMAND_NAMES
        self.appendToolbar("Sath server", server_cmds)
        self.appendToolbar("GES obyektlari", obj_cmds)
        self.appendMenu(
            "Sath",
            server_cmds + ["Separator"] + obj_cmds + ["Separator", "GES_Preset", "GES_DxfMode"],
        )

    def Activated(self):
        import FreeCAD
        from ges_workbench import converters, preset

        if converters.ensure_dwg_converter() is None:
            FreeCAD.Console.PrintWarning(
                "Sath: DWG konverter topilmadi — LibreDWG (dwg2dxf.exe) ni ~/Tools/libredwg ga yoki "
                "ODA File Converter ni o'rnating; dastur qayta ochilganda o'zi topadi\n"
            )

        if not preset.applied():
            preset.apply()
            FreeCAD.Console.PrintMessage(
                "Sath: AutoCAD uslubi sozlamalari qo'llandi (qayta ochganda to'liq kuchga kiradi)\n"
            )

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(GesWorkbench())
