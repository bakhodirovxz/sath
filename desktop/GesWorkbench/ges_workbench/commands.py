"""FreeCAD buyruqlari (toolbar/menyu). Har biri FreeCADGui.addCommand bilan ro'yxatga olinadi."""

from __future__ import annotations

import tempfile
from pathlib import Path

import FreeCAD
import FreeCADGui

from . import dialogs, ifc_io, session
from .server_client import ServerError

ICON_DIR = Path(__file__).resolve().parents[1] / "resources"
CACHE = Path(tempfile.gettempdir()) / "sath"


def _guard(fn):
    """Server xatolarini dialog qilib ko'rsatadi."""

    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ServerError as e:
            dialogs.error(e.message)
        except RuntimeError as e:
            dialogs.error(str(e))

    return wrapper


def _addon_version() -> str:
    import re

    text = (Path(__file__).resolve().parents[1] / "package.xml").read_text(encoding="utf-8")
    m = re.search(r"<version>([^<]+)</version>", text)
    return m.group(1) if m else "0.0.0"


def _check_update() -> None:
    """Serverda yangiroq desktop paketi bo'lsa — xabar (yuklab olish havolasi bilan)."""
    try:
        latest = session.client().desktop_latest()
    except ServerError:
        return
    if not latest:
        return
    cur = tuple(int(x) for x in _addon_version().split("."))
    new = tuple(int(x) for x in latest["version"].split("."))
    if new > cur:
        url = session.client().base_url + latest["url"]
        how = (
            "Yuklab olib, installer ni ishga tushiring (eski versiya ustiga o'rnatiladi)."
            if latest.get("kind") == "installer"
            else "Zip ni ochib, Sath.bat ni ishga tushiring."
        )
        dialogs.info(
            f"Yangi Sath versiyasi bor: {latest['version']} (sizda {_addon_version()}).\n"
            f"Yuklab oling: {url}\n{how}"
        )


def _check_notifications() -> None:
    """Kirishda o'qilmagan bildirishnomalar bo'lsa — qisqa xabar (dialog: GES → Bildirishnomalar)."""
    try:
        n = session.client().notifications(unread=True, limit=5)
    except ServerError:
        return
    if n:
        FreeCAD.Console.PrintWarning(
            f"Sath: {len(n)} ta o'qilmagan bildirishnoma — {n[0]['title']}\n"
        )


def _res(text: str, tip: str, icon: str = "ges") -> dict:
    return {"Pixmap": str(ICON_DIR / f"{icon}.svg"), "MenuText": text, "ToolTip": tip}


class GesConnect:
    def GetResources(self):
        return _res("Serverga ulanish", "Sath serveriga kirish", "connect")

    def Activated(self):
        d = dialogs.LoginDialog()
        if d.exec_():
            FreeCAD.Console.PrintMessage(f"Sath: {d.user['username']} sifatida kirildi\n")
            _check_update()
            _check_notifications()

    def IsActive(self):
        return True


class GesOpen:
    def GetResources(self):
        return _res("Modelni ochish", "Serverdagi versiyani yuklab, ochish", "open")

    @_guard
    def Activated(self):
        d = dialogs.ModelBrowser()
        if not d.exec_():
            return
        project, model, version = d.selected
        dest = CACHE / f"m{model['id']}_v{version['number']}.ifc"
        session.client().download_version(version["id"], dest)
        doc = ifc_io.open_ifc(dest)
        ifc_io.tag_document(doc, model["id"], version["id"], model["name"])
        doc.Label = f"{project['name']} — {model['name']} v{version['number']}"
        FreeCAD.Console.PrintMessage(f"Sath: {doc.Label} ochildi\n")

    def IsActive(self):
        return session.is_logged_in()


class GesCommit:
    def GetResources(self):
        return _res(
            "Commit (yangi versiya)",
            "Joriy hujjatni IFC qilib serverga yangi versiya sifatida yuklash",
            "commit",
        )

    @_guard
    def Activated(self):
        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc)
        if model_id is None:
            # Hujjat serverdagi modelga bog'lanmagan — model tanlatamiz
            d = dialogs.ModelBrowser("Qaysi modelga yuklash?", need_version=False)
            if not d.exec_():
                return
            _project, model, _v = d.selected
            model_id = model["id"]
            ifc_io.tag_document(doc, model_id, None, model["name"])
        c = session.client()
        versions = c.versions(model_id)
        parent_id = ifc_io.doc_version_id(doc)
        parent = next((v for v in versions if v["id"] == parent_id), None)
        dlg = dialogs.CommitDialog(doc.Meta.get("ges_model_name", ""), parent)
        if not dlg.exec_():
            return
        path = CACHE / f"commit_m{model_id}.ifc"
        ifc_io.save_ifc(doc, path)
        message = dlg.message.toPlainText().strip()
        v = c.upload_version(model_id, path, message, parent_id)
        ifc_io.tag_document(doc, model_id, v["id"], doc.Meta.get("ges_model_name", ""))
        msg = f"v{v['number']} yuklandi"
        if dlg.submit.isChecked():
            c.create_change_request(model_id, v["id"], message[:200] or f"v{v['number']}")
            msg += " va tasdiqqa yuborildi"
        dialogs.info(msg)

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesSubmit:
    def GetResources(self):
        return _res("Tasdiqqa yuborish", "Joriy versiya uchun tasdiqlash so'rovi ochish", "submit")

    @_guard
    def Activated(self):
        doc = FreeCAD.ActiveDocument
        model_id, version_id = ifc_io.doc_model_id(doc), ifc_io.doc_version_id(doc)
        if not model_id or not version_id:
            dialogs.error("Avval commit qiling — hujjat serverdagi versiyaga bog'lanmagan")
            return
        from PySide import QtWidgets

        title, ok = QtWidgets.QInputDialog.getText(
            FreeCADGui.getMainWindow(), "Tasdiqqa yuborish", "Sarlavha:"
        )
        if ok and title.strip():
            cr = session.client().create_change_request(model_id, version_id, title.strip())
            dialogs.info(f"So'rov #{cr['id']} ochildi. Tasdiqlovchi webda ko'rib chiqadi.")

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesIssues:
    def GetResources(self):
        return _res("Issue lar", "Model bo'yicha muammolar, 3D ko'rinishga o'tish", "issues")

    @_guard
    def Activated(self):
        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc)
        if not model_id:
            dialogs.error("Hujjat serverdagi modelga bog'lanmagan (GES → Modelni ochish)")
            return
        dialogs.IssuesDialog(
            model_id, doc.Meta.get("ges_model_name", ""), ifc_io.doc_version_id(doc)
        ).exec_()

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


def _model_role(model_id: int) -> str | None:
    """Foydalanuvchining shu model loyihasidagi roli (viewer/engineer/approver)."""
    c = session.client()
    project = c.project(c.model(model_id)["project_id"])
    return project.get("my_role")


class GesReview:
    def GetResources(self):
        return _res("Tasdiqlash so'rovlari", "CR ro'yxati, qarorlar (tasdiqlovchi uchun)", "submit")

    @_guard
    def Activated(self):
        from . import review_dialogs

        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc) if doc else None
        if not model_id:
            d = dialogs.ModelBrowser("Qaysi model?", need_version=False)
            if not d.exec_():
                return
            model_id = d.selected[1]["id"]
            name = d.selected[1]["name"]
        else:
            name = doc.Meta.get("ges_model_name", "")
        review_dialogs.ReviewDialog(model_id, name, _model_role(model_id)).exec_()

    def IsActive(self):
        return session.is_logged_in()


class GesSim:
    def GetResources(self):
        return _res(
            "Simulyatsiya",
            "Suv ombori / turbina rejimi (serverda hisob), natija va 3D suv sathi",
            "turbine",
        )

    @_guard
    def Activated(self):
        from . import review_dialogs

        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc) if doc else None
        if not model_id:
            dialogs.error("Avval serverdagi modelni oching (GES → Modelni ochish)")
            return
        review_dialogs.SimDialog(
            model_id, doc.Meta.get("ges_model_name", ""), ifc_io.doc_version_id(doc)
        ).exec_()

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesVersions:
    def GetResources(self):
        return _res(
            "Versiyalar va farq",
            "Model versiyalari tarixi: ochish, ota bilan farq (3D da yashil/sariq), webda ochish",
            "commit",
        )

    @_guard
    def Activated(self):
        from . import web_parity

        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc) if doc else None
        if not model_id:
            dialogs.error("Avval serverdagi modelni oching (GES → Modelni ochish)")
            return
        web_parity.VersionsDialog(
            model_id, doc.Meta.get("ges_model_name", ""), ifc_io.doc_version_id(doc)
        ).exec_()

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesSimCatalog:
    def GetResources(self):
        return _res(
            "Simulyatsiya katalogi",
            "Barcha simulyatsiyalar (toshqin, zilzila, barqarorlik, gidrozarba…), xavfsizlik tekshiruvi",
            "turbine",
        )

    @_guard
    def Activated(self):
        from . import web_parity

        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc) if doc else None
        if not model_id:
            dialogs.error("Avval serverdagi modelni oching (GES → Modelni ochish)")
            return
        web_parity.SimCatalogDialog(
            model_id, doc.Meta.get("ges_model_name", ""), ifc_io.doc_version_id(doc)
        ).exec_()

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesMonitor:
    def GetResources(self):
        return _res(
            "Monitoring (SCADA)",
            "Jonli o'lchovlar: obyektlar alarm rangi, suv sathi, sensor → 3D",
            "issues",
        )

    @_guard
    def Activated(self):
        from . import web_parity

        doc = FreeCAD.ActiveDocument
        model_id = ifc_io.doc_model_id(doc) if doc else None
        if not model_id:
            dialogs.error("Avval serverdagi modelni oching (GES → Modelni ochish)")
            return
        project_id = session.client().model(model_id)["project_id"]
        dlg = web_parity.MonitoringDialog(project_id, model_id)
        dlg.setModal(False)
        dlg.show()
        web_parity.MONITOR = dlg  # oyna yopilguncha yashasin (GC dan saqlash)

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesOpenWeb:
    def GetResources(self):
        return _res(
            "Webda ochish",
            "Joriy model (tanlangan element bilan) brauzerda: 3D vizual, tasdiqlash, monitoring",
            "open",
        )

    @_guard
    def Activated(self):
        from . import web_parity

        web_parity.open_in_web()

    def IsActive(self):
        return session.is_logged_in() and FreeCAD.ActiveDocument is not None


class GesNotify:
    def GetResources(self):
        return _res("Bildirishnomalar", "Tasdiqlash, issue, alarm xabarlari", "issues")

    @_guard
    def Activated(self):
        from . import review_dialogs

        review_dialogs.NotificationsDialog().exec_()

    def IsActive(self):
        return session.is_logged_in()


class GesPreset:
    def GetResources(self):
        return _res(
            "AutoCAD uslubi sozlamalari",
            "Qora tema, sichqoncha odatlari, birliklar — Sath standarti",
            "preset",
        )

    def Activated(self):
        from . import preset

        preset.apply()
        dialogs.info("Sozlamalar qo'llandi. To'liq kuchga kirishi uchun FreeCAD ni qayta oching.")

    def IsActive(self):
        return True


class GesDxfMode:
    """DWG/DXF ochish rejimi: tahrirlash (har element alohida Draft obyekti, matn/o'lcham tahrirlanadi) yoki
    ko'rish (qatlam+rang bo'yicha bitta shakl — juda katta chizmalar uchun tez)."""

    def GetResources(self):
        return _res(
            "DWG/DXF ochish rejimi",
            "Tahrirlash (AutoCAD kabi elementlar) ↔ Ko'rish (tez, birlashtirilgan)",
            "preset",
        )

    def Activated(self):
        import FreeCAD

        g = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Ges")
        cur = g.GetString("DxfMode", "edit")
        new = "view" if cur == "edit" else "edit"
        g.SetString("DxfMode", new)
        dialogs.info(
            "DWG/DXF endi «{}» rejimida ochiladi.".format(
                "ko'rish — tez, qatlam+rang bo'yicha birlashtirilgan"
                if new == "view"
                else "tahrirlash — har element alohida, matn va o'lchamlar tahrirlanadi"
            )
        )

    def IsActive(self):
        return True


COMMANDS = {
    "GES_Connect": GesConnect,
    "GES_Open": GesOpen,
    "GES_Commit": GesCommit,
    "GES_Submit": GesSubmit,
    "GES_Issues": GesIssues,
    "GES_Review": GesReview,
    "GES_Sim": GesSim,
    "GES_Notify": GesNotify,
    "GES_Versions": GesVersions,
    "GES_SimCatalog": GesSimCatalog,
    "GES_Monitor": GesMonitor,
    "GES_OpenWeb": GesOpenWeb,
    "GES_Preset": GesPreset,
    "GES_DxfMode": GesDxfMode,
}


def register() -> None:
    for name, cls in COMMANDS.items():
        FreeCADGui.addCommand(name, cls())
