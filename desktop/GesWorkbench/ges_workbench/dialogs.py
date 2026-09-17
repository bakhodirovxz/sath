"""Qt dialoglar (FreeCAD ning PySide shim'i orqali — PySide2/PySide6 ikkalasida ishlaydi)."""

from __future__ import annotations

from PySide import QtCore, QtWidgets

from . import session
from .server_client import ServerError


def _mw():
    import FreeCADGui

    return FreeCADGui.getMainWindow()


def error(msg: str, title: str = "Sath") -> None:
    QtWidgets.QMessageBox.critical(_mw(), title, msg)


def info(msg: str, title: str = "Sath") -> None:
    QtWidgets.QMessageBox.information(_mw(), title, msg)


class LoginDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(_mw())
        self.setWindowTitle("Sath serverga kirish")
        form = QtWidgets.QFormLayout(self)
        self.server = QtWidgets.QLineEdit(session.saved_server())
        self.username = QtWidgets.QLineEdit(session.saved_username())
        self.password = QtWidgets.QLineEdit()
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Server", self.server)
        form.addRow("Login", self.username)
        form.addRow("Parol", self.password)
        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color:#d95c5c")
        form.addRow(self.status)
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.button(QtWidgets.QDialogButtonBox.Ok).setText("Kirish")
        btns.accepted.connect(self.try_login)
        btns.rejected.connect(self.reject)
        form.addRow(btns)
        (self.password if self.username.text() else self.username).setFocus()

    def try_login(self):
        try:
            user = session.login(
                self.server.text().strip(), self.username.text().strip(), self.password.text()
            )
        except ServerError as e:
            self.status.setText(e.message)
            return
        self.user = user
        self.accept()


class ModelBrowser(QtWidgets.QDialog):
    """Loyiha → model → versiya tanlash. Natija: self.selected = (project, model, version|None)."""

    def __init__(self, title="Modelni ochish", need_version=True):
        super().__init__(_mw())
        self.setWindowTitle(title)
        self.resize(720, 480)
        self.need_version = need_version
        self.selected = None
        lay = QtWidgets.QHBoxLayout(self)
        self.projects = QtWidgets.QListWidget()
        self.models = QtWidgets.QListWidget()
        self.versions = QtWidgets.QTreeWidget()
        self.versions.setHeaderLabels(["v", "Holat", "Izoh", "Muallif", "Sana"])
        self.versions.setRootIsDecorated(False)
        for w, label in (
            (self.projects, "Loyihalar"),
            (self.models, "Modellar"),
            (self.versions, "Versiyalar"),
        ):
            box = QtWidgets.QVBoxLayout()
            box.addWidget(QtWidgets.QLabel(label))
            box.addWidget(w)
            lay.addLayout(box, 1 if w is not self.versions else 2)
        right = QtWidgets.QVBoxLayout()
        self.new_model = QtWidgets.QPushButton("Yangi model…")
        self.new_model.clicked.connect(self.create_model)
        self.ok = QtWidgets.QPushButton("Ochish" if need_version else "Tanlash")
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self.finish)
        cancel = QtWidgets.QPushButton("Bekor qilish")
        cancel.clicked.connect(self.reject)
        right.addWidget(self.new_model)
        right.addStretch(1)
        right.addWidget(self.ok)
        right.addWidget(cancel)
        lay.addLayout(right)

        self.projects.currentItemChanged.connect(self.load_models)
        self.models.currentItemChanged.connect(self.load_versions)
        self.versions.currentItemChanged.connect(lambda *_: self.update_ok())
        self.versions.itemDoubleClicked.connect(lambda *_: self.finish())
        self.load_projects()

    def _data(self, item):
        return item.data(QtCore.Qt.UserRole) if item else None

    def load_projects(self):
        self.projects.clear()
        try:
            for p in session.client().projects():
                it = QtWidgets.QListWidgetItem(p["name"])
                it.setData(QtCore.Qt.UserRole, p)
                self.projects.addItem(it)
        except ServerError as e:
            error(e.message)

    def load_models(self, cur, _prev=None):
        self.models.clear()
        self.versions.clear()
        p = self._data(cur)
        if not p:
            return
        self.new_model.setEnabled(p.get("my_role") in ("engineer", "approver"))
        for m in session.client().models(p["id"]):
            it = QtWidgets.QListWidgetItem(f"{m['name']}  ({m['version_count']} versiya)")
            it.setData(QtCore.Qt.UserRole, m)
            self.models.addItem(it)

    def load_versions(self, cur, _prev=None):
        self.versions.clear()
        m = self._data(cur)
        if not m:
            return self.update_ok()
        for v in session.client().versions(m["id"]):
            it = QtWidgets.QTreeWidgetItem(
                [
                    f"v{v['number']}",
                    v["state"],
                    v["message"],
                    v["author_username"],
                    v["created_at"][:16].replace("T", " "),
                ]
            )
            it.setData(0, QtCore.Qt.UserRole, v)
            self.versions.addTopLevelItem(it)
        if self.versions.topLevelItemCount():
            self.versions.setCurrentItem(self.versions.topLevelItem(0))
        self.update_ok()

    def update_ok(self):
        has_model = self._data(self.models.currentItem()) is not None
        has_version = self.versions.currentItem() is not None
        self.ok.setEnabled(has_model and (has_version or not self.need_version))

    def create_model(self):
        p = self._data(self.projects.currentItem())
        if not p:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Yangi model", "Nomi:")
        if ok and name.strip():
            try:
                session.client().create_model(p["id"], name.strip())
                self.load_models(self.projects.currentItem())
            except ServerError as e:
                error(e.message)

    def finish(self):
        p = self._data(self.projects.currentItem())
        m = self._data(self.models.currentItem())
        vi = self.versions.currentItem()
        v = vi.data(0, QtCore.Qt.UserRole) if vi else None
        if not p or not m or (self.need_version and not v):
            return
        self.selected = (p, m, v)
        self.accept()


class CommitDialog(QtWidgets.QDialog):
    def __init__(self, model_name: str, parent_version: dict | None):
        super().__init__(_mw())
        self.setWindowTitle(f"Commit — {model_name}")
        form = QtWidgets.QFormLayout(self)
        self.message = QtWidgets.QPlainTextEdit()
        self.message.setPlaceholderText("Nima o'zgardi?")
        form.addRow("Izoh", self.message)
        if parent_version:
            form.addRow(QtWidgets.QLabel(f"Ota versiya: v{parent_version['number']}"))
        self.submit = QtWidgets.QCheckBox("Darhol tasdiqqa yuborish")
        form.addRow(self.submit)
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.button(QtWidgets.QDialogButtonBox.Ok).setText("Yuklash")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)


class IssuesDialog(QtWidgets.QDialog):
    """Model issue lari ro'yxati; tanlanganda tavsif/izohlar; yangi issue ochish (kamera bilan)."""

    def __init__(self, model_id: int, model_name: str, version_id: int | None):
        super().__init__(_mw())
        self.model_id, self.version_id = model_id, version_id
        self.setWindowTitle(f"Issue lar — {model_name}")
        self.resize(760, 460)
        lay = QtWidgets.QHBoxLayout(self)
        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderLabels(["#", "Sarlavha", "Holat", "Ijrochi"])
        self.list.setRootIsDecorated(False)
        self.list.currentItemChanged.connect(self.show_issue)
        lay.addWidget(self.list, 3)
        right = QtWidgets.QVBoxLayout()
        self.detail = QtWidgets.QTextBrowser()
        right.addWidget(self.detail, 1)
        goto = QtWidgets.QPushButton("Ko'rinishga o'tish")
        goto.clicked.connect(self.goto_view)
        new = QtWidgets.QPushButton("Yangi issue (joriy ko'rinish bilan)")
        new.clicked.connect(self.new_issue)
        self.comment = QtWidgets.QLineEdit()
        self.comment.setPlaceholderText("Izoh… (Enter)")
        self.comment.returnPressed.connect(self.add_comment)
        right.addWidget(goto)
        right.addWidget(self.comment)
        right.addWidget(new)
        lay.addLayout(right, 2)
        self.reload()

    def reload(self):
        self.list.clear()
        for i in session.client().issues(self.model_id):
            it = QtWidgets.QTreeWidgetItem(
                [str(i["id"]), i["title"], i["status"], i["assignee_username"] or "—"]
            )
            it.setData(0, QtCore.Qt.UserRole, i)
            self.list.addTopLevelItem(it)

    def current(self):
        it = self.list.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it else None

    def show_issue(self, cur, _prev=None):
        i = self.current()
        if not i:
            return self.detail.clear()
        full = session.client().issue(i["id"])
        html = f"<b>#{full['id']} {full['title']}</b><br><i>{full['author_username']} · {full['priority']} · {full['status']}</i><p>{full['description']}</p>"
        for c in full["comments"]:
            html += f"<div style='border-left:2px solid #888;padding-left:6px;margin:4px 0'><i>{c['author_username']}</i><br>{c['body']}</div>"
        self.detail.setHtml(html)

    def goto_view(self):
        from . import viewpoint

        i = self.current()
        if i:
            viewpoint.apply(session.client().issue(i["id"])["viewpoint"])

    def add_comment(self):
        i = self.current()
        text = self.comment.text().strip()
        if i and text:
            session.client().comment_issue(i["id"], text)
            self.comment.clear()
            self.show_issue(self.list.currentItem())

    def new_issue(self):
        from . import viewpoint

        title, ok = QtWidgets.QInputDialog.getText(self, "Yangi issue", "Sarlavha:")
        if ok and title.strip():
            session.client().create_issue(
                self.model_id,
                title.strip(),
                version_id=self.version_id,
                viewpoint=viewpoint.capture(),
            )
            self.reload()
