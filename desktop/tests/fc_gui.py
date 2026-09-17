# FreeCAD GUI da ishga tushiriladi (ishlayotgan server kerak):
#   "C:\Program Files\FreeCAD 1.1\bin\freecad.exe" desktop\tests\fc_gui.py
# Muhit: GES_URL (default http://localhost:8000), GES_USER/GES_PASS (admin/admin123).
# Natija: %TEMP%\sath\fc_gui.log va fc_gui.png. Tekshiradi: workbench, buyruqlar, dialoglar,
# serverga kirish, modelni ochish, GES obyekt, commit, issue + ko'rinish.
import os
import tempfile
import traceback

OUT = os.path.join(tempfile.gettempdir(), "sath")
os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, "fc_gui.log"), "w", encoding="utf-8")


def P(*a):
    log.write(" ".join(str(x) for x in a) + "\n")
    log.flush()


try:
    import FreeCAD
    import FreeCADGui
    from PySide import QtCore, QtWidgets

    P("FreeCAD", ".".join(FreeCAD.Version()[:3]))
    assert "GesWorkbench" in FreeCADGui.listWorkbenches(), "workbench ro'yxatda yo'q"
    FreeCADGui.activateWorkbench("GesWorkbench")
    cmds = sorted(c for c in FreeCADGui.listCommands() if c.startswith("GES_"))
    P("buyruqlar:", cmds)
    assert len(cmds) == 21, cmds

    from ges_workbench import commands, dialogs, ges_objects, ifc_io, session, viewpoint

    url = os.environ.get("GES_URL", "http://localhost:8000")
    d = dialogs.LoginDialog()
    d.server.setText(url)
    d.username.setText(os.environ.get("GES_USER", "admin"))
    d.password.setText(os.environ.get("GES_PASS", "admin123"))
    d.try_login()
    assert d.result() == QtWidgets.QDialog.Accepted, d.status.text()
    P("login:", d.user["username"])

    mb = dialogs.ModelBrowser()
    assert mb.projects.count() > 0, "loyiha yo'q"
    mb.projects.setCurrentRow(0)
    assert mb.models.count() > 0, "model yo'q"
    mb.models.setCurrentRow(0)
    assert mb.versions.topLevelItemCount() > 0, "versiya yo'q"
    mb.finish()
    project, model, version = mb.selected
    P("tanlandi:", project["name"], "/", model["name"], "v", version["number"])

    c = session.client()
    dest = commands.CACHE / f"m{model['id']}_v{version['number']}.ifc"
    c.download_version(version["id"], dest)
    doc = ifc_io.open_ifc(dest)
    ifc_io.tag_document(doc, model["id"], version["id"], model["name"])
    P("ochildi:", len(doc.Objects), "obyekt")
    assert len(doc.Objects) > 0

    t = ges_objects.make("GES_Turbine", "Sinov turbinasi")
    t.Placement.Base = FreeCAD.Vector(25000, 5000, 0)
    doc.recompute()
    FreeCADGui.SendMsgToActiveView("ViewFit")
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.updateGui()
    FreeCADGui.ActiveDocument.ActiveView.saveImage(
        os.path.join(OUT, "fc_gui.png"), 1400, 900, "Current"
    )

    vp = viewpoint.capture()
    assert vp["camera"]["space"] == "ifc"
    out = commands.CACHE / "commit_test.ifc"
    ifc_io.save_ifc(doc, out)
    newv = c.upload_version(model["id"], out, "fc_gui.py sinov commit", version["id"])
    P(f"commit: v{newv['number']}", newv["meta"]["element_count"], "element")
    iss = c.create_issue(model["id"], "fc_gui.py sinov issue", version_id=newv["id"], viewpoint=vp)
    viewpoint.apply(c.issue(iss["id"])["viewpoint"])
    idlg = dialogs.IssuesDialog(model["id"], model["name"], newv["id"])
    assert idlg.list.topLevelItemCount() > 0
    P("issue:", iss["id"], "dialogda:", idlg.list.topLevelItemCount())

    # Taqriz dialogi: CR ro'yxati, rol bo'yicha tugmalar
    from ges_workbench import review_dialogs

    cr = c.create_change_request(model["id"], newv["id"], "fc_gui.py sinov CR")
    rd = review_dialogs.ReviewDialog(model["id"], model["name"], commands._model_role(model["id"]))
    assert rd.list.topLevelItemCount() >= 1
    rd.list.setCurrentItem(rd.list.topLevelItem(0))
    P("review:", cr["id"], "rol:", rd.role, "ma'qullash faol:", rd.b_approve.isEnabled())
    review_dialogs.error = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(a[0]))  # modal emas
    review_dialogs.info = lambda *a, **k: None
    rd.comment.setText("fc_gui: izoh")
    rd.decide("comment")  # muallif o'z CR ini ma'qullay olmaydi — izoh qoldiradi
    assert len(c.change_request(cr["id"])["reviews"]) == 1
    P("review izoh: ok")

    # Simulyatsiya dialogi: modeldan parametrlar, serverda hisob, natija, 3D suv sathi
    sd = review_dialogs.SimDialog(model["id"], model["name"], newv["id"])
    sd.from_model()
    sd.days.setValue(30)
    sd.run()
    import time as _t

    for _ in range(60):
        j = c.sim_job(sd.job["id"])
        if j["status"] in ("done", "failed"):
            break
        _t.sleep(1)
    assert j["status"] == "done", j.get("error")
    sd.timer.stop()
    sd.show_result(c.sim_result(j["id"]))
    assert sd.summary.topLevelItemCount() >= 5 and sd.chart.pixmap() is not None
    sd.show_water()
    assert doc.getObject("GES_SuvSathi") is not None
    P("sim:", j["id"], "energiya", sd.result["summary"]["energy_mwh"], "suv sathi obyekt: ok")

    nd = review_dialogs.NotificationsDialog()
    P("bildirishnomalar:", nd.list.topLevelItemCount())

    # --- Web bilan tenglik: versiyalar/farq, simulyatsiya katalogi + xavfsizlik, monitoring, webda ochish
    from ges_workbench import web_parity

    web_parity.error = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(a[0]))
    web_parity.info = lambda *a, **k: None
    vd = web_parity.VersionsDialog(model["id"], model["name"], newv["id"])
    assert vd.tree.topLevelItemCount() >= 2
    vd.tree.setCurrentItem(vd.tree.topLevelItem(0))  # eng yangi (newv, ota bor)
    vd.show_diff()
    assert "Farq" in vd.detail.toPlainText() and web_parity.DIFF_STATE.saved, (
        vd.detail.toPlainText()
    )
    vd.clear_diff()
    assert not web_parity.DIFF_STATE.saved
    P("versiyalar/diff: ok", vd.tree.topLevelItemCount(), "versiya")

    sc = web_parity.SimCatalogDialog(model["id"], model["name"], newv["id"])
    assert sc.list.count() >= 10, sc.list.count()
    idx = next(
        i
        for i in range(sc.list.count())
        if sc.list.item(i).data(QtCore.Qt.UserRole) == "dam_stability"
    )
    sc.list.setCurrentRow(idx)
    assert "height_m" in sc.widgets
    sc.prefill("model")
    sc.run()
    for _ in range(60):
        j = c.sim_job(sc.job["id"])
        if j["status"] in ("done", "failed"):
            break
        _t.sleep(1)
    sc.timer.stop()
    assert j["status"] == "done", j.get("error")
    sc.show_result(c.sim_result(j["id"]))
    assert sc.out.topLevelItemCount() >= 3
    P("sim katalogi: dam_stability ok, ko'rsatkichlar", sc.out.topLevelItemCount())
    try:
        res = c.safety_check(model["id"], newv["id"])
        P("xavfsizlik:", res["score"], res["counts"])
        web_parity.SafetyDialog(res)
    except Exception as e:  # noqa: BLE001 — pasport bo'lmasa 400 (Namuna loyihasi)
        P("xavfsizlik o'tkazib yuborildi:", e)

    md = web_parity.MonitoringDialog(project["id"], model["id"])
    md.refresh()
    md.timer.stop()
    P("monitoring:", md.tree.topLevelItemCount(), "sensor")
    md.close()
    P("NATIJA: OK")
except Exception:
    P(traceback.format_exc())
    P("NATIJA: XATO")
finally:
    log.close()
    from PySide import QtCore, QtWidgets

    QtCore.QTimer.singleShot(1000, QtWidgets.QApplication.instance().quit)
