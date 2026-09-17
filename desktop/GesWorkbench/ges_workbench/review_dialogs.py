"""Taqriz (tasdiqlash so'rovlari), simulyatsiya va bildirishnomalar dialoglari."""

from __future__ import annotations

import os
import tempfile

from PySide import QtCore, QtGui, QtWidgets

from . import session
from .dialogs import _mw, error, info
from .server_client import ServerError

STATUS_UZ = {
    "open": "Ochiq",
    "changes_requested": "O'zgartirish so'ralgan",
    "approved": "Ma'qullangan",
    "rejected": "Rad etilgan",
    "merged": "Tasdiqlangan",
}


class ReviewDialog(QtWidgets.QDialog):
    """Modelning tasdiqlash so'rovlari: ro'yxat, tafsilot, qaror (tasdiqlovchi) — webdagi oqim bilan bir xil."""

    def __init__(self, model_id: int, model_name: str, role: str | None):
        super().__init__(_mw())
        self.model_id, self.role = model_id, role
        self.setWindowTitle(f"Tasdiqlash so'rovlari — {model_name}")
        self.resize(820, 480)
        lay = QtWidgets.QHBoxLayout(self)
        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderLabels(["#", "Sarlavha", "Versiya", "Holat", "Muallif"])
        self.list.setRootIsDecorated(False)
        self.list.currentItemChanged.connect(self.show_cr)
        lay.addWidget(self.list, 3)
        right = QtWidgets.QVBoxLayout()
        self.detail = QtWidgets.QTextBrowser()
        right.addWidget(self.detail, 1)
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("Izoh (qaror bilan yuboriladi)")
        right.addWidget(self.comment)
        row = QtWidgets.QHBoxLayout()
        self.b_approve = QtWidgets.QPushButton("Ma'qullash")
        self.b_changes = QtWidgets.QPushButton("O'zgartirish so'rash")
        self.b_merge = QtWidgets.QPushButton("Tasdiqlash (merge)")
        self.b_reject = QtWidgets.QPushButton("Rad etish")
        self.b_approve.clicked.connect(lambda: self.decide("approve"))
        self.b_changes.clicked.connect(lambda: self.decide("request_changes"))
        self.b_merge.clicked.connect(self.merge)
        self.b_reject.clicked.connect(self.reject_cr)
        for b in (self.b_approve, self.b_changes, self.b_merge, self.b_reject):
            row.addWidget(b)
        right.addLayout(row)
        b_comment = QtWidgets.QPushButton("Faqat izoh qoldirish")
        b_comment.clicked.connect(lambda: self.decide("comment"))
        right.addWidget(b_comment)
        lay.addLayout(right, 2)
        self.reload()

    def reload(self):
        self.list.clear()
        for cr in session.client().change_requests(self.model_id):
            it = QtWidgets.QTreeWidgetItem(
                [
                    str(cr["id"]),
                    cr["title"],
                    f"v{cr['version_number']}"
                    if cr.get("version_number")
                    else str(cr["version_id"]),
                    STATUS_UZ.get(cr["status"], cr["status"]),
                    cr.get("author_username", ""),
                ]
            )
            it.setData(0, QtCore.Qt.UserRole, cr)
            self.list.addTopLevelItem(it)
        self.update_buttons()

    def current(self):
        it = self.list.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it else None

    def update_buttons(self):
        cr = self.current()
        approver = self.role == "approver"
        open_ = bool(cr) and cr["status"] in ("open", "changes_requested", "approved")
        self.b_approve.setEnabled(approver and open_ and cr["status"] != "approved")
        self.b_changes.setEnabled(approver and open_)
        self.b_merge.setEnabled(approver and bool(cr) and cr["status"] == "approved")
        self.b_reject.setEnabled(bool(cr) and cr["status"] not in ("merged", "rejected"))

    def show_cr(self, cur, _prev=None):
        cr = self.current()
        self.update_buttons()
        if not cr:
            return self.detail.clear()
        full = session.client().change_request(cr["id"])
        html = (
            f"<b>#{full['id']} {full['title']}</b><br><i>{full.get('author_username', '')} · "
            f"{STATUS_UZ.get(full['status'], full['status'])}</i><p>{full.get('description', '')}</p>"
        )
        for r in full.get("reviews", []):
            html += (
                f"<div style='border-left:2px solid #888;padding-left:6px;margin:4px 0'>"
                f"<i>{r.get('reviewer_username', '')} — {r['decision']}</i><br>{r.get('comment', '')}</div>"
            )
        self.detail.setHtml(html)

    def _do(self, fn):
        cr = self.current()
        if not cr:
            return
        try:
            fn(cr)
        except ServerError as e:
            error(e.message)
            return
        self.comment.clear()
        self.reload()

    def decide(self, decision: str):
        self._do(
            lambda cr: session.client().review_change_request(
                cr["id"], decision, self.comment.text().strip()
            )
        )

    def merge(self):
        self._do(lambda cr: session.client().merge_change_request(cr["id"]))

    def reject_cr(self):
        if (
            QtWidgets.QMessageBox.question(self, "Rad etish", "So'rovni rad etasizmi?")
            == QtWidgets.QMessageBox.Yes
        ):
            self._do(lambda cr: session.client().reject_change_request(cr["id"]))


class SimDialog(QtWidgets.QDialog):
    """Suv ombori/turbina simulyatsiyasi: parametrlar modeldan (Pset_GES_*), hisob serverda,
    natija — jadval + grafik (matplotlib) + 3D da suv sathi tekisligi."""

    def __init__(self, model_id: int, model_name: str, version_id: int | None):
        super().__init__(_mw())
        self.model_id, self.version_id = model_id, version_id
        self.job = None
        self.setWindowTitle(f"Simulyatsiya — {model_name}")
        self.resize(860, 560)
        lay = QtWidgets.QVBoxLayout(self)
        c = session.client()
        self.params = c.sim_example()
        top = QtWidgets.QFormLayout()
        self.mode = QtWidgets.QComboBox()
        for m, lb in (
            ("max_power", "Maksimal quvvat"),
            ("target_level", "Sath ushlab turish"),
            ("target_power", "Berilgan quvvat"),
            ("target_flow", "Berilgan sarf"),
            ("rule_curve", "Dispetcher grafigi"),
        ):
            self.mode.addItem(lb, m)
        self.inflow = QtWidgets.QDoubleSpinBox()
        self.inflow.setRange(0, 100000)
        self.inflow.setValue(self.params["inflow_m3s"].get("constant", 100))
        self.days = QtWidgets.QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(self.params["inflow_m3s"].get("steps", 365))
        self.level0 = QtWidgets.QDoubleSpinBox()
        self.level0.setRange(0, 10000)
        self.level0.setValue(self.params["reservoir"]["initial_level_m"])
        self.target = QtWidgets.QDoubleSpinBox()
        self.target.setRange(0, 100000)
        self.target.setValue(self.params["reservoir"]["normal_level_m"])
        top.addRow("Rejim", self.mode)
        top.addRow("Kiruvchi sarf, m³/s (doimiy)", self.inflow)
        top.addRow("Davr, kun", self.days)
        top.addRow("Boshlang'ich sath, m", self.level0)
        top.addRow("Maqsad (sath m / quvvat MW / sarf m³/s)", self.target)
        lay.addLayout(top)
        row = QtWidgets.QHBoxLayout()
        self.b_model = QtWidgets.QPushButton("Modeldan olish (Pset_GES)")
        self.b_model.clicked.connect(self.from_model)
        self.b_model.setEnabled(version_id is not None)
        self.b_run = QtWidgets.QPushButton("Hisoblash")
        self.b_run.clicked.connect(self.run)
        self.units_label = QtWidgets.QLabel(self._units_text())
        row.addWidget(self.b_model)
        row.addWidget(self.b_run)
        row.addWidget(self.units_label, 1)
        lay.addLayout(row)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        body = QtWidgets.QHBoxLayout()
        self.summary = QtWidgets.QTreeWidget()
        self.summary.setHeaderLabels(["Ko'rsatkich", "Qiymat"])
        self.summary.setRootIsDecorated(False)
        body.addWidget(self.summary, 2)
        self.chart = QtWidgets.QLabel("Natija grafigi shu yerda")
        self.chart.setAlignment(QtCore.Qt.AlignCenter)
        self.chart.setMinimumWidth(420)
        body.addWidget(self.chart, 3)
        lay.addLayout(body, 1)
        bottom = QtWidgets.QHBoxLayout()
        self.b_water = QtWidgets.QPushButton("3D: suv sathi tekisligi (yakuniy sath)")
        self.b_water.clicked.connect(self.show_water)
        self.b_water.setEnabled(False)
        bottom.addWidget(self.b_water)
        bottom.addStretch(1)
        lay.addLayout(bottom)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)

    def _units_text(self) -> str:
        u = self.params.get("units", [])
        return f"Agregatlar: {len(u)} ta, {sum(x['rated_power_mw'] for x in u):.0f} MW"

    def from_model(self):
        try:
            g = session.client().ges_params(self.version_id)
        except ServerError as e:
            return error(e.message)
        if g.get("units"):
            self.params["units"] = [
                {
                    k: u[k]
                    for k in (
                        "name",
                        "type",
                        "rated_power_mw",
                        "rated_head_m",
                        "rated_flow_m3s",
                        "max_efficiency",
                    )
                }
                for u in g["units"]
            ]
        if g.get("penstocks"):
            p = g["penstocks"][0]
            self.params["penstock"].update(
                {
                    "length_m": p["length_m"],
                    "diameter_m": p["diameter_m"],
                    "roughness_mm": p["roughness_mm"],
                }
            )
        if g.get("spillways"):
            s = g["spillways"][0]
            self.params["reservoir"]["spillway"].update(
                {"crest_m": s["crest_m"], "width_m": s["width_m"], "coefficient": s["coefficient"]}
            )
        self.units_label.setText(self._units_text() + " (modeldan)")

    def run(self):
        p = self.params
        p["inflow_m3s"] = {"constant": self.inflow.value(), "steps": self.days.value()}
        p["reservoir"]["initial_level_m"] = self.level0.value()
        mode = self.mode.currentData()
        op = {"mode": mode}
        if mode == "target_level":
            op["target_level_m"] = self.target.value()
        elif mode == "target_power":
            op["target_power_mw"] = self.target.value()
        elif mode == "target_flow":
            op["target_flow_m3s"] = self.target.value()
        p["operation"] = op
        try:
            self.job = session.client().create_sim(
                self.model_id, f"FreeCAD: {self.mode.currentText()}", self.version_id, p
            )
        except ServerError as e:
            return error(e.message)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.b_run.setEnabled(False)
        self.timer.start(1000)

    def poll(self):
        try:
            j = session.client().sim_job(self.job["id"])
        except ServerError as e:
            self.timer.stop()
            return error(e.message)
        self.progress.setValue(int(j.get("progress", 0) * 100))
        if j["status"] in ("done", "failed"):
            self.timer.stop()
            self.progress.setVisible(False)
            self.b_run.setEnabled(True)
            if j["status"] == "failed":
                return error(j.get("error") or "Simulyatsiya xato")
            self.show_result(session.client().sim_result(j["id"]))

    def show_result(self, r: dict):
        self.result = r
        self.summary.clear()
        labels = {
            "energy_mwh": ("Energiya, MWh", 0),
            "mean_power_mw": ("O'rtacha quvvat, MW", 2),
            "max_power_mw": ("Maks. quvvat, MW", 2),
            "installed_mw": ("O'rnatilgan quvvat, MW", 0),
            "capacity_factor": ("Quvvat koeffitsienti", 3),
            "min_level_m": ("Min. sath, m", 2),
            "max_level_m": ("Maks. sath, m", 2),
            "final_level_m": ("Yakuniy sath, m", 2),
            "spill_volume_mcm": ("Tashlangan hajm, mln m³", 2),
            "turbined_volume_mcm": ("Turbinalangan hajm, mln m³", 2),
            "curtailed_steps": ("Cheklangan qadamlar", 0),
        }
        for k, (lb, d) in labels.items():
            if k in r["summary"]:
                v = r["summary"][k]
                self.summary.addTopLevelItem(
                    QtWidgets.QTreeWidgetItem(
                        [lb, f"{v:.{d}f}" if isinstance(v, int | float) else str(v)]
                    )
                )
        self.b_water.setEnabled(True)
        try:
            self.chart.setPixmap(QtGui.QPixmap(self._plot(r)))
        except Exception as e:  # noqa: BLE001 — grafiksiz ham natija ko'rinsin
            self.chart.setText(f"Grafik chizilmadi: {e}")

    def _plot(self, r: dict) -> str:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        s = r["series"]
        t = list(range(len(s["level"])))
        fig, ax1 = plt.subplots(figsize=(6.2, 4.2), dpi=90)
        fig.patch.set_facecolor("#26282c")
        ax1.set_facecolor("#1e1f22")
        ax1.plot(t, s["level"], color="#4da3ff", label="Sath, m")
        ax1.set_ylabel("Sath, m", color="#d6d8dc")
        ax2 = ax1.twinx()
        ax2.plot(t, s["power_mw"], color="#e0a93a", label="Quvvat, MW")
        ax2.set_ylabel("Quvvat, MW", color="#d6d8dc")
        for ax in (ax1, ax2):
            ax.tick_params(colors="#8b9098")
            for sp in ax.spines.values():
                sp.set_color("#3a3d44")
        ax1.set_xlabel("Qadam", color="#8b9098")
        fig.legend(
            loc="upper center",
            ncol=2,
            facecolor="#26282c",
            labelcolor="#d6d8dc",
            edgecolor="#3a3d44",
        )
        fig.tight_layout()
        out = os.path.join(tempfile.gettempdir(), "sath", "sim_plot.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fig.savefig(out, facecolor=fig.get_facecolor())
        plt.close(fig)
        return out

    def show_water(self):
        """Faol hujjatda suv sathi tekisligi (yakuniy sath, IFC z metr → mm)."""
        import FreeCAD

        doc = FreeCAD.ActiveDocument
        if doc is None:
            return error("Faol hujjat yo'q")
        level = float(self.result["summary"].get("final_level_m", 0))
        place_water_plane(doc, level)
        info(f"Suv sathi tekisligi: {level:.2f} m (obyekt: GES_SuvSathi)")


def place_water_plane(doc, level_m: float, size_m: float | None = None) -> None:
    """GES_SuvSathi nomli yarim shaffof tekislik — model bbox ini qoplaydi, z = level."""
    import FreeCAD
    import Part

    shapes = [
        o.Shape
        for o in doc.Objects
        if hasattr(o, "Shape") and not o.Shape.isNull() and o.Name != "GES_SuvSathi"
    ]
    if not shapes:
        return
    bb = shapes[0].BoundBox
    for s in shapes[1:]:
        bb.add(s.BoundBox)
    size = (size_m * 1000) if size_m else max(bb.XLength, bb.YLength) * 1.2
    obj = doc.getObject("GES_SuvSathi") or doc.addObject("Part::Feature", "GES_SuvSathi")
    obj.Label = "Suv sathi"
    plane = Part.makePlane(
        size, size, FreeCAD.Vector(bb.Center.x - size / 2, bb.Center.y - size / 2, level_m * 1000)
    )
    obj.Shape = plane
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = (0.22, 0.72, 0.79)
        obj.ViewObject.Transparency = 60
    doc.recompute()


class NotificationsDialog(QtWidgets.QDialog):
    """Ilova ichi bildirishnomalar (tasdiqlash, issue, alarm) — serverdagi qo'ng'iroq bilan bir xil."""

    def __init__(self):
        super().__init__(_mw())
        self.setWindowTitle("Bildirishnomalar")
        self.resize(640, 400)
        lay = QtWidgets.QVBoxLayout(self)
        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderLabels(["Tur", "Sarlavha", "Vaqt"])
        self.list.setRootIsDecorated(False)
        lay.addWidget(self.list, 1)
        self.body = QtWidgets.QLabel("")
        self.body.setWordWrap(True)
        lay.addWidget(self.body)
        row = QtWidgets.QHBoxLayout()
        b_all = QtWidgets.QPushButton("Hammasini o'qilgan qilish")
        b_all.clicked.connect(self.read_all)
        row.addStretch(1)
        row.addWidget(b_all)
        lay.addLayout(row)
        self.list.currentItemChanged.connect(self.show)
        self.reload()

    def reload(self):
        self.list.clear()
        for n in session.client().notifications(unread=False, limit=50):
            it = QtWidgets.QTreeWidgetItem(
                [n["kind"], n["title"], n["created_at"][:16].replace("T", " ")]
            )
            it.setData(0, QtCore.Qt.UserRole, n)
            if not n.get("read_at"):
                f = it.font(1)
                f.setBold(True)
                it.setFont(1, f)
            self.list.addTopLevelItem(it)

    def show(self, cur, _prev=None):
        it = self.list.currentItem()
        if not it:
            return
        n = it.data(0, QtCore.Qt.UserRole)
        self.body.setText(n.get("body") or "")
        if not n.get("read_at"):
            session.client().mark_notifications_read([n["id"]])
            n["read_at"] = "x"
            f = it.font(1)
            f.setBold(False)
            it.setFont(1, f)

    def read_all(self):
        session.client().mark_notifications_read(None)
        self.reload()
