"""Web bilan tenglik — desktopda ham: versiyalar tarixi va farq (diff rangi), simulyatsiya katalogi
(barcha turlar, forma pasport/modeldan to'ladi, natija + grafik + 3D suv), xavfsizlik tekshiruvi (12 ssenariy),
monitoring (SCADA jonli qiymatlar — obyektlar alarm rangi, yorliqlar), webda ochish (chuqur havola).

Server API lari web bilan bir xil (GesClient); dialoglar PySide (FreeCAD ichidagi Qt)."""

from __future__ import annotations

import os
import tempfile
import webbrowser

import FreeCAD
from PySide import QtCore, QtGui, QtWidgets

from . import ifc_io, session
from .dialogs import error, info
from .server_client import ServerError

DIFF_COLORS = {"added": (0.25, 0.7, 0.35), "changed": (0.9, 0.7, 0.2), "deleted": (0.85, 0.3, 0.3)}
ALARM_COLORS = {
    "ok": (0.23, 0.66, 0.39),
    "low": (0.88, 0.4, 0.42),
    "high": (0.88, 0.4, 0.42),
    "stale": (0.42, 0.43, 0.46),
}


# ------------------------------------------------------------------ yordamchilar
def _guid_map(doc) -> dict[str, object]:
    """IFC GUID → FreeCAD obyekt (NativeIFC yoki legacy)."""
    from .viewpoint import _ifc_guid

    out = {}
    for o in doc.Objects:
        g = _ifc_guid(o)
        if g:
            out[g] = o
    return out


class _ColorState:
    """Obyektlar rangini vaqtincha almashtirish (diff / alarm) va qaytarish."""

    def __init__(self):
        self.saved: dict[str, tuple] = {}

    def paint(self, doc, colors: dict[str, tuple]) -> int:
        gm = _guid_map(doc)
        n = 0
        for guid, rgb in colors.items():
            o = gm.get(guid)
            vo = getattr(o, "ViewObject", None) if o else None
            if vo is None or not hasattr(vo, "ShapeColor"):
                continue
            if o.Name not in self.saved:
                self.saved[o.Name] = tuple(vo.ShapeColor)
            vo.ShapeColor = rgb
            n += 1
        return n

    def restore(self, doc) -> None:
        for name, rgb in self.saved.items():
            o = doc.getObject(name)
            if o is not None and getattr(o, "ViewObject", None) is not None:
                o.ViewObject.ShapeColor = rgb
        self.saved.clear()


DIFF_STATE = _ColorState()
ALARM_STATE = _ColorState()
MONITOR: object | None = None  # ochiq monitoring oynasi


def _web_url(path: str) -> str:
    """Ishlab chiqarishda server web ni o'zi tarqatadi (bir xil manzil); dev muhitda (health.web = False)
    Vite 5173 portiga yo'naltiriladi."""
    base = session.saved_server().rstrip("/")
    try:
        if not session.client().health().get("web", True) and base.endswith(":8000"):
            base = base[: -len(":8000")] + ":5173"
    except ServerError:
        pass
    return f"{base}{path}"


# ------------------------------------------------------------------ Versiyalar va farq
class VersionsDialog(QtWidgets.QDialog):
    """Model versiyalari (git kabi tarix): ochish, ota bilan farq — 3D da rang (yashil qo'shilgan, sariq
    o'zgargan; o'chirilganlar ro'yxatda), webda ochish."""

    def __init__(self, model_id: int, model_name: str, current_version_id: int | None):
        super().__init__()
        self.model_id, self.current_version_id = model_id, current_version_id
        self.setWindowTitle(f"Versiyalar — {model_name}")
        self.resize(760, 480)
        self.client = session.client()
        lay = QtWidgets.QVBoxLayout(self)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["v", "Holat", "Muallif", "Sana", "Izoh", "Elementlar"])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree, 2)
        self.detail = QtWidgets.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(130)
        lay.addWidget(self.detail)
        row = QtWidgets.QHBoxLayout()
        self.b_open = QtWidgets.QPushButton("Ochish")
        self.b_diff = QtWidgets.QPushButton("Ota bilan farq (3D rang)")
        self.b_clear = QtWidgets.QPushButton("Rangni tozalash")
        self.b_web = QtWidgets.QPushButton("Webda ochish")
        for b in (self.b_open, self.b_diff, self.b_clear, self.b_web):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.b_open.clicked.connect(self.open_version)
        self.b_diff.clicked.connect(self.show_diff)
        self.b_clear.clicked.connect(self.clear_diff)
        self.b_web.clicked.connect(self.open_web)
        self.tree.currentItemChanged.connect(lambda *_: self.update_buttons())
        self.reload()

    def reload(self):
        self.tree.clear()
        self.versions = self.client.versions(self.model_id)
        for v in sorted(self.versions, key=lambda x: -x["number"]):
            it = QtWidgets.QTreeWidgetItem([
                f"v{v['number']}", v.get("state", ""), v.get("author_username", ""),
                str(v.get("created_at", ""))[:16].replace("T", " "), v.get("message", ""),
                str((v.get("meta") or {}).get("element_count", "")),
            ])  # fmt: skip
            it.setData(0, QtCore.Qt.UserRole, v["id"])
            if v["id"] == self.current_version_id:
                it.setText(0, f"v{v['number']} ●")
            self.tree.addTopLevelItem(it)
        for i in range(6):
            self.tree.resizeColumnToContents(i)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def current(self) -> dict | None:
        it = self.tree.currentItem()
        if not it:
            return None
        vid = it.data(0, QtCore.Qt.UserRole)
        return next((v for v in self.versions if v["id"] == vid), None)

    def update_buttons(self):
        v = self.current()
        self.b_open.setEnabled(v is not None and v["id"] != self.current_version_id)
        self.b_diff.setEnabled(v is not None and bool(v.get("parent_id")))
        if v:
            self.detail.setPlainText(v.get("message", ""))

    def open_version(self):
        from . import commands

        v = self.current()
        if not v:
            return
        try:
            dest = commands.CACHE / f"m{self.model_id}_v{v['number']}.ifc"
            self.client.download_version(v["id"], dest)
            doc = ifc_io.open_ifc(dest)
            ifc_io.tag_document(doc, self.model_id, v["id"], self.windowTitle().split("— ", 1)[-1])
            self.current_version_id = v["id"]
            self.reload()
            info(f"v{v['number']} ochildi ({len(doc.Objects)} obyekt)")
        except ServerError as e:
            error(str(e))

    def show_diff(self):
        v = self.current()
        if not v:
            return
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return error("Faol hujjat yo'q")
        note = (
            ""
            if ifc_io.doc_version_id(doc) == v["id"]
            else "(diqqat: hujjatda boshqa versiya ochiq — rang faqat mos GUID larga) "
        )
        try:
            d = self.client.diff(v["id"])
        except ServerError as e:
            return error(str(e))
        DIFF_STATE.restore(doc)
        colors = {}
        for kind in ("added", "changed"):
            for e in d.get(kind, []):
                colors[e["guid"]] = DIFF_COLORS[kind]
        n = DIFF_STATE.paint(doc, colors)
        s = d.get("summary", {})
        deleted = ", ".join((e.get("name") or e["guid"]) for e in d.get("deleted", [])[:20])
        self.detail.setPlainText(
            f"{note}Farq (ota bilan): +{s.get('added', 0)} qo'shilgan (yashil), ~{s.get('changed', 0)} o'zgargan (sariq), "
            f"−{s.get('deleted', 0)} o'chirilgan{': ' + deleted if deleted else ''}\n3D da {n} obyekt bo'yaldi."
        )
        doc.recompute()

    def clear_diff(self):
        doc = FreeCAD.ActiveDocument
        if doc:
            DIFF_STATE.restore(doc)
            doc.recompute()

    def open_web(self):
        v = self.current()
        webbrowser.open(_web_url(f"/models/{self.model_id}" + (f"?v={v['id']}" if v else "")))


# ------------------------------------------------------------------ Simulyatsiya katalogi
class SimCatalogDialog(QtWidgets.QDialog):
    """Barcha simulyatsiya turlari (server katalogi): forma maydonlari avtomatik, pasport/modeldan to'ladi,
    hisob serverda, natija: xulosa, ko'rsatkichlar, grafik (matplotlib), 3D suv sathi; xavfsizlik tekshiruvi."""

    def __init__(self, model_id: int, model_name: str, version_id: int | None):
        super().__init__()
        self.model_id, self.version_id = model_id, version_id
        self.setWindowTitle(f"Simulyatsiya katalogi — {model_name}")
        self.resize(980, 640)
        self.client = session.client()
        self.catalog = self.client.sim_catalog()
        self.kinds = [k for k in self.catalog["kinds"] if not k.get("custom_ui")]
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self.fields: list[dict] = []
        self.job: dict | None = None
        self.result: dict | None = None

        root = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        root.addLayout(left, 1)
        self.list = QtWidgets.QListWidget()
        groups = self.catalog.get("groups", {})
        for k in self.kinds:
            it = QtWidgets.QListWidgetItem(f"{k['title']}\n   {groups.get(k['group'], k['group'])}")
            it.setData(QtCore.Qt.UserRole, k["id"])
            it.setToolTip(k.get("description", ""))
            self.list.addItem(it)
        left.addWidget(self.list, 1)
        self.b_safety = QtWidgets.QPushButton("Xavfsizlik tekshiruvi (12 ssenariy)")
        self.b_safety.setToolTip(
            "Toshqinlar, N−1 darvoza, zilzila, barqarorlik, filtratsiya, yoriq, gidrozarba, ko'chki — bir bosishda"
        )
        self.b_safety.clicked.connect(self.safety_check)
        left.addWidget(self.b_safety)

        right = QtWidgets.QVBoxLayout()
        root.addLayout(right, 2)
        self.title = QtWidgets.QLabel("Turini tanlang")
        self.title.setStyleSheet("font-weight:bold;font-size:14px")
        self.title.setWordWrap(True)
        right.addWidget(self.title)
        self.desc = QtWidgets.QLabel("")
        self.desc.setWordWrap(True)
        right.addWidget(self.desc)
        self.form_area = QtWidgets.QScrollArea()
        self.form_area.setWidgetResizable(True)
        right.addWidget(self.form_area, 2)
        row = QtWidgets.QHBoxLayout()
        self.b_site = QtWidgets.QPushButton("Pasportdan")
        self.b_model = QtWidgets.QPushButton("Modeldan")
        self.b_run = QtWidgets.QPushButton("Hisoblash")
        self.b_run.setDefault(True)
        for b in (self.b_site, self.b_model, self.b_run):
            row.addWidget(b)
        row.addStretch(1)
        self.status = QtWidgets.QLabel("")
        row.addWidget(self.status)
        right.addLayout(row)
        self.out = QtWidgets.QTreeWidget()
        self.out.setHeaderLabels(["Ko'rsatkich", "Qiymat"])
        self.out.setRootIsDecorated(False)
        self.out.setMaximumHeight(170)
        right.addWidget(self.out)
        self.chart = QtWidgets.QLabel("")
        self.chart.setMinimumHeight(180)
        right.addWidget(self.chart, 1)
        row2 = QtWidgets.QHBoxLayout()
        self.b_water = QtWidgets.QPushButton("3D: suv sathi")
        self.b_water.setEnabled(False)
        self.b_web = QtWidgets.QPushButton("Webda ochish (3D vizual, hisobot)")
        row2.addWidget(self.b_water)
        row2.addWidget(self.b_web)
        row2.addStretch(1)
        right.addLayout(row2)

        self.list.currentItemChanged.connect(lambda *_: self.pick())
        self.b_site.clicked.connect(lambda: self.prefill("site"))
        self.b_model.clicked.connect(lambda: self.prefill("model"))
        self.b_run.clicked.connect(self.run)
        self.b_water.clicked.connect(self.show_water)
        self.b_web.clicked.connect(self.open_web)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        if self.list.count():
            self.list.setCurrentRow(0)

    # --- forma ---
    def kind(self) -> dict | None:
        it = self.list.currentItem()
        return (
            next((k for k in self.kinds if k["id"] == it.data(QtCore.Qt.UserRole)), None)
            if it
            else None
        )

    def pick(self):
        k = self.kind()
        if not k:
            return
        self.title.setText(k["title"])
        self.desc.setText(k.get("description", ""))
        self.fields = k["fields"]
        self.widgets = {}
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        groups: dict[str, QtWidgets.QFormLayout] = {}
        for f in self.fields:
            g = ("Qo'shimcha: " if f.get("advanced") else "") + (f.get("group") or "Parametrlar")
            if g not in groups:
                box = QtWidgets.QGroupBox(g)
                fl = QtWidgets.QFormLayout(box)
                groups[g] = fl
                lay.addWidget(box)
            fl = groups[g]
            t = f["type"]
            if t in ("number", "int"):
                e = QtWidgets.QLineEdit(
                    str(f.get("default", "") if f.get("default") is not None else "")
                )
                e.setValidator(QtGui.QDoubleValidator())
            elif t == "bool":
                e = QtWidgets.QCheckBox()
                e.setChecked(bool(f.get("default")))
            elif t == "select":
                e = QtWidgets.QComboBox()
                for val, lb in f.get("options", []):
                    e.addItem(lb, val)
                idx = e.findData(str(f.get("default")))
                if idx >= 0:
                    e.setCurrentIndex(idx)
            elif t == "series":
                d = f.get("default")
                e = QtWidgets.QLineEdit(
                    ", ".join(str(x) for x in d) if isinstance(d, list) else str(d or "")
                )
                e.setPlaceholderText("qiymatlar vergul bilan")
            else:
                e = QtWidgets.QLineEdit(str(f.get("default") or ""))
            e.setToolTip(f.get("hint", ""))
            label = f["label"] + (f", {f['unit']}" if f.get("unit") else "")
            fl.addRow(label, e)
            self.widgets[f["key"]] = e
        lay.addStretch(1)
        self.form_area.setWidget(w)
        self.out.clear()
        self.chart.clear()
        self.result = None
        self.b_water.setEnabled(False)
        self.prefill("site", quiet=True)

    def set_values(self, vals: dict) -> int:
        n = 0
        for key, v in vals.items():
            e = self.widgets.get(key)
            if e is None:
                continue
            if isinstance(e, QtWidgets.QCheckBox):
                e.setChecked(bool(v))
            elif isinstance(e, QtWidgets.QComboBox):
                i = e.findData(str(v))
                if i >= 0:
                    e.setCurrentIndex(i)
            else:
                e.setText(", ".join(str(x) for x in v) if isinstance(v, list) else str(v))
            n += 1
        return n

    def values(self) -> dict:
        out = {}
        for f in self.fields:
            e = self.widgets[f["key"]]
            if isinstance(e, QtWidgets.QCheckBox):
                out[f["key"]] = e.isChecked()
            elif isinstance(e, QtWidgets.QComboBox):
                out[f["key"]] = e.currentData()
            else:
                txt = e.text().strip()
                if f["type"] == "series":
                    out[f["key"]] = [
                        float(x) for x in txt.replace(";", ",").split(",") if x.strip()
                    ]
                elif f["type"] in ("number", "int"):
                    if txt:
                        out[f["key"]] = float(txt.replace(",", "."))
                else:
                    out[f["key"]] = txt
        return out

    def prefill(self, src: str, quiet: bool = False):
        k = self.kind()
        if not k:
            return
        try:
            pf = self.client.sim_prefill(self.model_id, k["id"], self.version_id)
        except ServerError as e:
            return error(str(e))
        vals = pf.get(src) or {}
        n = self.set_values(vals)
        if not quiet:
            self.status.setText(f"{n} maydon {'pasportdan' if src == 'site' else 'modeldan'}")
            if not vals and src == "site":
                info(
                    "Maydon pasporti to'ldirilmagan — webda loyiha sahifasida «Maydon pasporti» ni kiriting"
                )

    # --- hisob ---
    def run(self):
        k = self.kind()
        if not k:
            return
        try:
            self.job = self.client.create_sim(
                self.model_id, k["title"], self.version_id, self.values(), kind=k["id"]
            )
        except (ServerError, ValueError) as e:
            return error(str(e))
        self.status.setText("Hisoblanmoqda…")
        self.b_run.setEnabled(False)
        self.timer.start(600)

    def poll(self):
        try:
            j = self.client.sim_job(self.job["id"])
        except ServerError as e:
            self.timer.stop()
            self.b_run.setEnabled(True)
            return error(str(e))
        if j["status"] == "done":
            self.timer.stop()
            self.b_run.setEnabled(True)
            self.show_result(self.client.sim_result(j["id"]))
        elif j["status"] == "failed":
            self.timer.stop()
            self.b_run.setEnabled(True)
            self.status.setText("Xato")
            error(j.get("error") or "Hisob xatosi")

    def show_result(self, r: dict):
        self.result = r
        k = self.kind() or {}
        s = r.get("summary", {})
        self.out.clear()
        top = QtWidgets.QTreeWidgetItem(["Xulosa", str(s.get("verdict", ""))])
        top.setForeground(
            1, QtGui.QBrush(QtGui.QColor("#e0656a" if s.get("ok") is False else "#3aa864"))
        )
        self.out.addTopLevelItem(top)
        for o in k.get("outputs", []):
            v = s.get(o["key"])
            if v is None:
                continue
            txt = f"{v:,.2f}" if isinstance(v, float) else str(v)
            self.out.addTopLevelItem(
                QtWidgets.QTreeWidgetItem([o["label"], f"{txt} {o.get('unit', '')}".strip()])
            )
        self.status.setText("Tayyor")
        water_key = (k.get("viz") or {}).get("water_level")
        self.water_level = None
        if water_key:
            ser = r.get("series", {}).get(water_key)
            if isinstance(ser, list) and ser:
                self.water_level = float(max(ser))
            elif isinstance(s.get(water_key), int | float):
                self.water_level = float(s[water_key])
        self.b_water.setEnabled(self.water_level is not None)
        try:
            self.chart.setPixmap(QtGui.QPixmap(self._plot(r)))
        except Exception as e:  # noqa: BLE001
            self.chart.setText(f"Grafik chizilmadi: {e}")

    def _plot(self, r: dict) -> str:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        s = r.get("series", {})
        xkey = next((k for k in ("t", "x", "level", "year", "cutoff_m", "kh", "y") if k in s), None)
        x = s.get(xkey) if xkey else None
        ys = [
            k
            for k, v in s.items()
            if k != xkey
            and isinstance(v, list)
            and v
            and all(isinstance(q, int | float) for q in v)
        ][:4]
        if not ys:
            raise ValueError("qator yo'q")
        fig, axes = plt.subplots(
            len(ys), 1, figsize=(6.4, 1.7 * len(ys) + 0.6), dpi=90, sharex=True
        )
        if len(ys) == 1:
            axes = [axes]
        fig.patch.set_facecolor("#26282c")
        colors = ["#3d8ee6", "#b98626", "#3aa864", "#b46dcc"]
        for ax, k, c in zip(axes, ys, colors, strict=False):
            ax.set_facecolor("#1e1f22")
            xs = (
                x
                if isinstance(x, list)
                and len(x) == len(s[k])
                and all(isinstance(q, int | float) for q in x)
                else list(range(len(s[k])))
            )
            ax.plot(xs, s[k], color=c)
            ax.set_ylabel(k, color="#d6d8dc", fontsize=8)
            ax.tick_params(colors="#8b9098", labelsize=7)
            for sp in ax.spines.values():
                sp.set_color("#3a3d44")
        axes[-1].set_xlabel(xkey or "qadam", color="#8b9098", fontsize=8)
        fig.tight_layout()
        out = os.path.join(tempfile.gettempdir(), "sath", "sim_catalog_plot.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fig.savefig(out, facecolor=fig.get_facecolor())
        plt.close(fig)
        return out

    def show_water(self):
        from .review_dialogs import place_water_plane

        doc = FreeCAD.ActiveDocument
        if doc is None or self.water_level is None:
            return
        place_water_plane(doc, self.water_level)
        info(f"Suv sathi tekisligi: {self.water_level:.2f} m (GES_SuvSathi)")

    def open_web(self):
        k = self.kind()
        webbrowser.open(
            _web_url(
                f"/models/{self.model_id}?tab=sim"
                + (f"&v={self.version_id}" if self.version_id else "")
            )
        )
        if k:
            self.status.setText(f"Webda: Simulyatsiya → {k['title']}")

    # --- xavfsizlik ---
    def safety_check(self):
        self.status.setText("Xavfsizlik tekshiruvi…")
        QtWidgets.QApplication.processEvents()
        try:
            res = self.client.safety_check(self.model_id, self.version_id)
        except ServerError as e:
            self.status.setText("")
            return error(str(e))
        self.status.setText("")
        SafetyDialog(res).exec_()


class SafetyDialog(QtWidgets.QDialog):
    def __init__(self, res: dict):
        super().__init__()
        self.setWindowTitle(f"Xavfsizlik tekshiruvi — {res['score']}/100")
        self.resize(820, 460)
        lay = QtWidgets.QVBoxLayout(self)
        c = res["counts"]
        head = QtWidgets.QLabel(
            f"<b>{res['score']} / 100</b> — {res['verdict']} · {c['ok']} ok · {c['warn']} ogohlantirish · {c['fail']} bajarilmadi · {c['skip']} hisoblanmadi"
        )
        lay.addWidget(head)
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderLabels(["Ssenariy", "Holat", "Xulosa", "Ko'rsatkichlar"])
        tree.setRootIsDecorated(False)
        colors = {"ok": "#3aa864", "warn": "#b98626", "fail": "#e0656a", "skip": "#8b9098"}
        labels = {
            "ok": "bajarildi",
            "warn": "ogohlantirish",
            "fail": "bajarilmadi",
            "skip": "hisoblanmadi",
        }
        for r in res["rows"]:
            it = QtWidgets.QTreeWidgetItem([
                r["title"], labels.get(r["status"], r["status"]), r.get("message", ""),
                " · ".join(f"{k} = {v:.2f}" if isinstance(v, float) else f"{k} = {v}" for k, v in (r.get("metrics") or {}).items()),
            ])  # fmt: skip
            it.setForeground(1, QtGui.QBrush(QtGui.QColor(colors.get(r["status"], "#fff"))))
            it.setToolTip(0, r.get("why", ""))
            tree.addTopLevelItem(it)
        for i in range(4):
            tree.resizeColumnToContents(i)
        lay.addWidget(tree)
        note = QtWidgets.QLabel(
            "Mezonlar: zaxira ≥ 1 m (loyihaviy), gerbdan oshmaslik, K ≥ 1.5 / 1.3 / 1.1, suffoziya ≥ 1.5, quvur ≥ 1.5. Har hisob webda «Oldingi hisoblar» da (3D vizual, hisobot)."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        b = QtWidgets.QPushButton("Yopish")
        b.clicked.connect(self.accept)
        lay.addWidget(b, alignment=QtCore.Qt.AlignRight)


# ------------------------------------------------------------------ Monitoring (SCADA)
class MonitoringDialog(QtWidgets.QDialog):
    """SCADA jonli qiymatlar (REST polling): sensorlar jadvali, bog'langan obyektlar alarm rangi
    (yashil/qizil/kulrang), tanlangan obyekt → sensor; suv sathi sensori → 3D tekislik."""

    def __init__(self, project_id: int, model_id: int):
        super().__init__()
        self.project_id, self.model_id = project_id, model_id
        self.setWindowTitle("Monitoring (SCADA) — jonli")
        self.resize(760, 440)
        self.client = session.client()
        lay = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("…")
        row.addWidget(self.status)
        row.addStretch(1)
        self.cb_color = QtWidgets.QCheckBox("3D alarm rangi")
        self.cb_color.setChecked(True)
        self.cb_water = QtWidgets.QCheckBox("suv sathi sensoridan 3D tekislik")
        self.cb_water.setChecked(True)
        row.addWidget(self.cb_color)
        row.addWidget(self.cb_water)
        lay.addLayout(row)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Sensor", "Kalit", "Qiymat", "Holat", "Vaqt", "3D"])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree)
        row2 = QtWidgets.QHBoxLayout()
        self.b_show = QtWidgets.QPushButton("3D da ko'rsatish")
        self.b_web = QtWidgets.QPushButton("Webda (HMI, vaqt mashinasi, boshqaruv)")
        row2.addWidget(self.b_show)
        row2.addWidget(self.b_web)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.b_show.clicked.connect(self.show_in_3d)
        self.b_web.clicked.connect(
            lambda: webbrowser.open(_web_url(f"/models/{self.model_id}?tab=mon"))
        )
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.sensors: list[dict] = []
        self.refresh()

    def refresh(self):
        try:
            self.sensors = self.client.sensors(self.project_id, self.model_id)
        except ServerError as e:
            self.status.setText(f"Xato: {e}")
            return
        alarms = [s for s in self.sensors if s.get("enabled") and s.get("alarm") != "ok"]
        self.status.setText(f"{len(self.sensors)} sensor · {len(alarms)} alarm · yangilanish 5 s")
        sel = (
            self.tree.currentItem().data(0, QtCore.Qt.UserRole) if self.tree.currentItem() else None
        )
        self.tree.clear()
        labels = {"ok": "normal", "low": "past", "high": "yuqori", "stale": "uzilgan"}
        for s in self.sensors:
            v = s.get("last_value")
            it = QtWidgets.QTreeWidgetItem([
                s["name"], s["key"], f"{v:.2f} {s.get('unit', '')}" if isinstance(v, int | float) else "—",
                labels.get(s.get("alarm"), str(s.get("alarm"))), str(s.get("last_ts") or "")[:16].replace("T", " "),
                "bog'langan" if s.get("element_guid") else "",
            ])  # fmt: skip
            it.setData(0, QtCore.Qt.UserRole, s["id"])
            c = ALARM_COLORS.get(s.get("alarm"), (1, 1, 1))
            it.setForeground(3, QtGui.QBrush(QtGui.QColor.fromRgbF(*c)))
            self.tree.addTopLevelItem(it)
            if s["id"] == sel:
                self.tree.setCurrentItem(it)
        for i in range(6):
            self.tree.resizeColumnToContents(i)
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return
        if self.cb_color.isChecked():
            colors = {
                s["element_guid"]: ALARM_COLORS.get(s.get("alarm"), (1, 1, 1))
                for s in self.sensors
                if s.get("element_guid") and s.get("enabled")
            }
            ALARM_STATE.paint(doc, colors)
        else:
            ALARM_STATE.restore(doc)
        if self.cb_water.isChecked():
            lvl = next(
                (
                    s
                    for s in self.sensors
                    if s.get("kind") == "level"
                    and isinstance(s.get("last_value"), int | float)
                    and s.get("alarm") != "stale"
                ),
                None,
            )
            if lvl:
                from .review_dialogs import place_water_plane

                place_water_plane(doc, float(lvl["last_value"]))
        doc.recompute()

    def show_in_3d(self):
        import FreeCADGui

        it = self.tree.currentItem()
        if not it or FreeCAD.ActiveDocument is None:
            return
        s = next((x for x in self.sensors if x["id"] == it.data(0, QtCore.Qt.UserRole)), None)
        if not s or not s.get("element_guid"):
            return info("Bu sensor elementga bog'lanmagan (webda «Tanlanganga bog'lash»)")
        o = _guid_map(FreeCAD.ActiveDocument).get(s["element_guid"])
        if o is None:
            return info("Element hujjatda topilmadi (NativeIFC obyektlarini kengaytiring)")
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(o)
        FreeCADGui.SendMsgToActiveView("ViewSelection")

    def closeEvent(self, ev):
        self.timer.stop()
        doc = FreeCAD.ActiveDocument
        if doc:
            ALARM_STATE.restore(doc)
            doc.recompute()
        super().closeEvent(ev)


# ------------------------------------------------------------------ Webda ochish
def open_in_web() -> None:
    """Joriy model (va tanlangan element) web da: /models/{id}?v=&sel=<GUID>."""
    import FreeCADGui

    from .viewpoint import _ifc_guid

    doc = FreeCAD.ActiveDocument
    mid = ifc_io.doc_model_id(doc) if doc else None
    if not mid:
        return error("Avval serverdagi modelni oching")
    vid = ifc_io.doc_version_id(doc)
    sel = [g for g in (_ifc_guid(o) for o in FreeCADGui.Selection.getSelection()) if g]
    q = f"?v={vid}" if vid else "?"
    if sel:
        q += f"&sel={sel[0]}"
    webbrowser.open(_web_url(f"/models/{mid}{q}"))
