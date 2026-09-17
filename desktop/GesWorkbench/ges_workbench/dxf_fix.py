"""DXF/DWG ochilganda AutoCAD dagidek ko'rinsin: ranglar, matn va o'lchamlar.

FreeCAD 1.1 ning yangi (C++) DXF importeri ikki kamchilik bilan keladi:
  * «Use colors from the DXF file» yoqilganda Draft qatlamining «OverrideLineColorChildren» belgisi ham
    yoqiladi va qatlamga qo'shilgan har element qatlam rangiga bo'yaladi — elementning o'z rangi
    (masalan qizil «yangi qurilish» chiziqlari) yo'qoladi. O'chirilsa esa hamma element bitta default rang.
  * matn va o'lchamlar («dxftext») sukut bo'yicha o'chiq.
Bu modul import vaqtida qatlamning rang-yuklash funksiyasini vaqtincha o'chirib (chiziq qalinligi, uslub,
ko'rinish qoladi), importdan keyin qatlam «override» belgilarini o'chiradi — natijada har element o'z rangida
(BYLAYER lar qatlam rangida) qoladi. Sozlamalar bir marta (marker bilan) qo'yiladi — foydalanuvchi keyin
o'zgartirsa, qayta yozilmaydi.
"""

from __future__ import annotations

import FreeCAD

DRAFT = "User parameter:BaseApp/Preferences/Mod/Draft"
GES = "User parameter:BaseApp/Preferences/Mod/Ges"

# (nom, qiymat) — FreeCAD Draft DXF import sozlamalari
PREFS_BOOL = {
    "dxftext": False,  # matn/o'lchamlar dxf_prepare da chiziqlarga aylanadi (ezdxf bo'lmasa install() yoqadi)
    "dxfGetOriginalColors": True,  # ranglar
    "dxfUseDraftVisGroups": True,  # qatlamlar
    "dxfImportPoints": False,  # nuqtalar chizmani ifloslaydi
    "dxflayout": False,  # faqat model fazosi (varaq maketlari emas)
    "dxfShowDialog": False,  # AutoCAD kabi darhol ochilsin (rejim: alohida shakllar)
    # Rejim: har element alohida Part shakl — tez, elementning o'z rangi saqlanadi (Draft rejimida
    # ranglar Draft default bo'lib qoladi). importDXF.readPreferences() shu bool lardan DxfImportMode ni yasaydi.
    "dxfImportAsDraft": False,
    "dxfImportAsPrimitives": False,
    "dxfImportAsFused": True,  # qatlam+rang bo'yicha bitta obyekt — 20 000+ chiziqli chizma ham tez
    "dxfImportAsShapes": False,
}


def apply_prefs(force: bool = False) -> bool:
    g = FreeCAD.ParamGet(GES)
    if g.GetBool("DxfPrefsApplied", False) and not force:
        return False
    d = FreeCAD.ParamGet(DRAFT)
    for k, v in PREFS_BOOL.items():
        d.SetBool(k, v)
    d.SetInt("DxfImportMode", 2)  # 2 = har element alohida shakl (tez, qatlam/rang saqlanadi)
    g.SetBool("DxfPrefsApplied", True)
    return True


def unlock_layers(doc) -> int:
    """Draft qatlamlarining «bolalar rangini yuklash» belgilarini o'chiradi (elementlar o'z rangida qoladi)."""
    n = 0
    for obj in doc.Objects:
        proxy = getattr(obj, "Proxy", None)
        if getattr(proxy, "Type", None) != "Layer":
            continue
        vobj = getattr(obj, "ViewObject", None)
        if vobj is None:
            continue
        for prop in ("OverrideLineColorChildren", "OverrideShapeAppearanceChildren"):
            if hasattr(vobj, prop) and getattr(vobj, prop):
                setattr(vobj, prop, False)
        n += 1
    return n


def _drawing_bbox(doc):
    """Model fazosidagi (blok ta'rifiga kirmagan) shakllarning umumiy chegarasi."""
    bb = FreeCAD.BoundBox()
    for obj in doc.Objects:
        if not obj.TypeId.startswith("Part::") or obj.Label.startswith("BLOCK_"):
            continue
        if any(q.Label.startswith(("BLOCK_", "_")) for q in obj.InList):
            continue
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and shape.BoundBox.isValid():
            bb.add(shape.BoundBox)
    return bb if bb.isValid() else None


def remove_stray_annotations(doc) -> int:
    """FreeCAD 1.1 importeri blok ichidagi matn/o'lchamlarni blokka qo'sha olmaydi («Attempted to add a
    DocumentObject ('Text') to a block definition») — lekin ularni hujjatda blokning lokal koordinatalarida
    (odatda 0,0 atrofida) qoldiradi. Natijada chizma «Fit» qilinganda nuqtaga aylanadi. Chizma chegarasidan
    (50 % kengaytirilgan) tashqaridagi annotatsiyalar olib tashlanadi."""
    bb = _drawing_bbox(doc)
    if bb is None:
        return 0
    big = FreeCAD.BoundBox(bb)
    big.enlarge(max(bb.DiagonalLength * 0.5, 1.0))
    stray = []
    for obj in doc.Objects:
        t = getattr(getattr(obj, "Proxy", None), "Type", "")
        if t == "Text":
            pts = [obj.Placement.Base]
        elif t in ("LinearDimension", "AngularDimension"):
            pts = [obj.Start, obj.End] if hasattr(obj, "Start") else [obj.Placement.Base]
        else:
            continue
        if any(not big.isInside(q) for q in pts):
            stray.append(obj.Name)
    for name in stray:
        try:
            doc.removeObject(name)
        except Exception:  # noqa: BLE001
            pass
    return len(stray)


def postprocess(doc) -> tuple[int, int]:
    n_layers = unlock_layers(doc)
    n_stray = remove_stray_annotations(doc)
    if n_stray:
        doc.recompute()
    return n_layers, n_stray


def install() -> bool:
    """importDXF._import_dxf_file ni o'rab qo'yadi (DWG ham shu orqali ochiladi)."""
    try:
        import importDXF
    except Exception:  # noqa: BLE001 — Draft yo'q (konsol rejimi)
        return False
    if getattr(importDXF, "_ges_patched", False):
        return True
    orig = importDXF._import_dxf_file

    def wrapped(filename, doc_name=None):
        # 0) Tahrirlanadigan rejim (sukut): har element — Draft/Part obyekti, matn va o'lchamlar tahrirlanadi
        if FreeCAD.ParamGet(GES).GetString("DxfMode", "edit") == "edit":
            try:
                import time

                from ges_workbench import dxf_edit, dxf_prepare

                if dxf_prepare.ensure_ezdxf():
                    doc = None
                    if doc_name:
                        doc = (
                            FreeCAD.getDocument(doc_name)
                            if doc_name in FreeCAD.listDocuments()
                            else None
                        )
                        if doc is None:
                            doc = FreeCAD.newDocument(doc_name)
                    t0 = time.time()
                    doc, _stats = dxf_edit.import_file(filename, doc)
                    return doc, None, t0, time.time()
            except Exception as e:  # noqa: BLE001 — bo'lmasa ko'rish rejimi (pastda)
                FreeCAD.Console.PrintWarning(
                    f"Sath: tahrirlanadigan DXF import o'tmadi ({e}) — ko'rish rejimi\n"
                )
        # 1) ezdxf bilan tekislash (bloklar, o'lchamlar, matn, shtrix → chiziqlar)
        try:
            from ges_workbench import dxf_prepare

            if dxf_prepare.ensure_ezdxf():
                prepared, stats = dxf_prepare.prepare(filename)
                FreeCAD.Console.PrintMessage(f"Sath: DXF tekislandi {stats}\n")
                filename = prepared
            else:
                FreeCAD.ParamGet(DRAFT).SetBool("dxftext", True)  # hech bo'lmasa FreeCAD matnlari
        except Exception as e:  # noqa: BLE001 — tekislash o'tmasa asl fayl
            FreeCAD.Console.PrintWarning(
                f"Sath: DXF tekislash o'tmadi ({e}) — asl fayl ochiladi\n"
            )
        # 2) qatlam rang-yuklashini vaqtincha o'chirib import
        try:
            from draftviewproviders import view_layer

            cls = view_layer.ViewProviderLayer
            orig_cvp = cls.change_view_properties

            def cvp(self, vobj, prop, old_prop=None, targets=None):
                if prop in ("LineColor", "ShapeAppearance"):
                    return None  # element o'z rangini saqlaydi
                return orig_cvp(self, vobj, prop, old_prop, targets)

            cls.change_view_properties = cvp
        except Exception:  # noqa: BLE001
            cls = None
            orig_cvp = None
        try:
            res = orig(filename, doc_name)
        finally:
            if cls is not None:
                cls.change_view_properties = orig_cvp
        doc = res[0] if isinstance(res, tuple) and res else None
        if doc is not None:
            try:
                n, stray = postprocess(doc)
                FreeCAD.Console.PrintMessage(
                    f"Sath: {n} qatlam — elementlar o'z rangida; blok ichidagi {stray} ta noto'g'ri "
                    "joylashgan matn/o'lcham olib tashlandi (FreeCAD cheklovi)" + chr(10)
                )
            except Exception as e:  # noqa: BLE001
                FreeCAD.Console.PrintWarning(f"Sath: qatlam ranglari: {e}\n")
        return res

    importDXF._import_dxf_file = wrapped
    importDXF._ges_patched = True
    return True
