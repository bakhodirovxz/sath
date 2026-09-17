"""Sath server bilan ishlash — faqat standart kutubxona (FreeCAD ichidagi Python da qo'shimcha paket yo'q).

FreeCAD dan mustaqil: pytest bilan alohida test qilinadi.
"""

from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request


class ServerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class GesClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # --- Ichki ---

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        params: dict | None = None,
        raw: bool = False,
        timeout: float | None = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = request.Request(url, data=body, method=method)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with request.urlopen(req, timeout=timeout or self.timeout) as resp:
                data = resp.read()
                if raw:
                    return data
                return json.loads(data) if data else None
        except error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail", e.reason)
            except Exception:
                detail = e.reason
            raise ServerError(e.code, str(detail)) from None
        except error.URLError as e:
            raise ServerError(0, f"Serverga ulanib bo'lmadi: {e.reason}") from None

    def _json(self, method: str, path: str, data: dict | None = None, **kw) -> Any:
        body = json.dumps(data).encode() if data is not None else None
        return self._request(method, path, body=body, content_type="application/json", **kw)

    # --- Auth ---

    def login(self, username: str, password: str) -> str:
        body = parse.urlencode({"username": username, "password": password}).encode()
        r = self._request(
            "POST", "/api/auth/login", body=body, content_type="application/x-www-form-urlencoded"
        )
        self.token = r["access_token"]
        return self.token

    def me(self) -> dict:
        return self._json("GET", "/api/auth/me")

    def health(self) -> dict:
        return self._json("GET", "/api/health")

    # --- Loyihalar / modellar / versiyalar ---

    def projects(self) -> list[dict]:
        return self._json("GET", "/api/projects")

    def project(self, project_id: int) -> dict:
        return self._json("GET", f"/api/projects/{project_id}")

    def model(self, model_id: int) -> dict:
        return self._json("GET", f"/api/models/{model_id}")

    def models(self, project_id: int) -> list[dict]:
        return self._json("GET", f"/api/projects/{project_id}/models")

    def create_model(self, project_id: int, name: str, description: str = "") -> dict:
        return self._json(
            "POST", f"/api/projects/{project_id}/models", {"name": name, "description": description}
        )

    def versions(self, model_id: int) -> list[dict]:
        return self._json("GET", f"/api/models/{model_id}/versions")

    def version(self, version_id: int) -> dict:
        return self._json("GET", f"/api/versions/{version_id}")

    def download_version(self, version_id: int, dest: Path) -> Path:
        data = self._request("GET", f"/api/versions/{version_id}/file", raw=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def upload_version(
        self, model_id: int, path: Path, message: str = "", parent_id: int | None = None
    ) -> dict:
        """Commit: IFC faylni yangi versiya sifatida yuklash (multipart/form-data)."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []

        def field(name: str, value: str) -> None:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            )

        field("message", message)
        if parent_id is not None:
            field("parent_id", str(parent_id))
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode()
            + path.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return self._request(
            "POST",
            f"/api/models/{model_id}/versions",
            body=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def desktop_latest(self) -> dict | None:
        """Serverdagi eng yangi desktop paketi: {version, kind, url, size, files} yoki None."""
        try:
            return self._json("GET", "/api/desktop/latest")
        except ServerError as e:
            if e.status == 404:
                return None
            raise

    # --- Taqriz ---

    def change_requests(self, model_id: int) -> list[dict]:
        return self._json("GET", f"/api/models/{model_id}/change-requests")

    def create_change_request(
        self, model_id: int, version_id: int, title: str, description: str = ""
    ) -> dict:
        return self._json(
            "POST",
            f"/api/models/{model_id}/change-requests",
            {"version_id": version_id, "title": title, "description": description},
        )

    def issues(self, model_id: int) -> list[dict]:
        return self._json("GET", f"/api/models/{model_id}/issues")

    def issue(self, issue_id: int) -> dict:
        return self._json("GET", f"/api/issues/{issue_id}")

    def create_issue(self, model_id: int, title: str, **fields) -> dict:
        return self._json("POST", f"/api/models/{model_id}/issues", {"title": title, **fields})

    def comment_issue(self, issue_id: int, body: str, viewpoint: dict | None = None) -> dict:
        return self._json(
            "POST", f"/api/issues/{issue_id}/comments", {"body": body, "viewpoint": viewpoint}
        )

    def change_request(self, cr_id: int) -> dict:
        return self._json("GET", f"/api/change-requests/{cr_id}")

    def review_change_request(self, cr_id: int, decision: str, comment: str = "") -> dict:
        """decision: approve | request_changes | comment"""
        return self._json(
            "POST",
            f"/api/change-requests/{cr_id}/reviews",
            {"decision": decision, "comment": comment},
        )

    def merge_change_request(self, cr_id: int) -> dict:
        return self._json("POST", f"/api/change-requests/{cr_id}/merge")

    def reject_change_request(self, cr_id: int) -> dict:
        return self._json("POST", f"/api/change-requests/{cr_id}/reject")

    # --- Simulyatsiya ---

    def sim_example(self) -> dict:
        return self._json("GET", "/api/sim/example")

    def ges_params(self, version_id: int) -> dict:
        """IFC dagi Pset_GES_* dan agregatlar/quvurlar/suv tashlagich parametrlari."""
        return self._json("GET", f"/api/versions/{version_id}/ges-params")

    def create_sim(
        self, model_id: int, name: str, version_id: int | None, params: dict, kind: str = "hydro"
    ) -> dict:
        return self._json(
            "POST",
            f"/api/models/{model_id}/sim",
            {"name": name, "version_id": version_id, "kind": kind, "params": params},
        )

    def sim_catalog(self) -> dict:
        """Barcha simulyatsiya turlari: meta, forma maydonlari (web bilan bir xil)."""
        return self._json("GET", "/api/sim/catalog")

    def sim_prefill(self, model_id: int, kind: str, version_id: int | None = None) -> dict:
        q = f"?kind={kind}" + (f"&version_id={version_id}" if version_id else "")
        return self._json("GET", f"/api/models/{model_id}/sim/prefill{q}")

    def safety_check(self, model_id: int, version_id: int | None = None) -> dict:
        q = f"?version_id={version_id}" if version_id else ""
        return self._json("POST", f"/api/models/{model_id}/sim/safety-check{q}", timeout=600)

    def diff(self, version_id: int, from_version_id: int | None = None) -> dict:
        """Versiyalar farqi (birinchi marta katta IFC da bir necha daqiqa; keyin kesh)."""
        q = f"?from={from_version_id}" if from_version_id else ""
        return self._json("GET", f"/api/versions/{version_id}/diff{q}", timeout=900)

    def sensors(self, project_id: int, model_id: int | None = None) -> list[dict]:
        q = f"?model_id={model_id}" if model_id else ""
        return self._json("GET", f"/api/projects/{project_id}/sensors{q}")

    # --- Raqamli egizak / holat monitoringi ---

    def twin(self, project_id: int) -> dict:
        """Egizak holati: head_gross_m, units[{name, measured_mw, expected_mw, deviation_pct, efficiency, running}],
        expected_total_mw, measured_total_mw, safety[{name, value, unit, ok, note}], status."""
        return self._json("GET", f"/api/projects/{project_id}/twin")

    def plant_health(self, project_id: int) -> dict:
        """Sog'liq: plant_score, assets[{asset_id, name, element_guid, score, level, problems, tips}]."""
        return self._json("GET", f"/api/projects/{project_id}/health")

    def readings(self, sensor_id: int, hours: float = 24, limit: int = 2000) -> list[dict]:
        """Sensor tarixi [{ts, value, (min, max)}] — vaqt mashinasi/grafik uchun."""
        return self._json("GET", f"/api/sensors/{sensor_id}/readings?hours={hours}&limit={limit}")

    def sim_jobs(self, model_id: int) -> list[dict]:
        return self._json("GET", f"/api/models/{model_id}/sim")

    def sim_job(self, job_id: int) -> dict:
        return self._json("GET", f"/api/sim/{job_id}")

    def sim_result(self, job_id: int) -> dict:
        return self._json("GET", f"/api/sim/{job_id}/result")

    # --- Bildirishnomalar ---

    def notifications(self, unread: bool = True, limit: int = 30) -> list[dict]:
        return self._json(
            "GET", f"/api/notifications?unread={'true' if unread else 'false'}&limit={limit}"
        )

    def mark_notifications_read(self, ids: list[int] | None = None) -> dict:
        return self._json("POST", "/api/notifications/read", {"ids": ids})
