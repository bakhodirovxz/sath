"""Analitik simulyatsiyani alohida jarayonda, vaqt chegarasi bilan bajarish (J12).

Sof Python sikli thread dan to'xtatilmaydi (GIL) — shuning uchun hisob `multiprocessing` (spawn)
jarayonida bajariladi; muddat o'tsa jarayon o'ldiriladi. Bu modul faqat `ges_sim` ni import qiladi
(bola jarayon tez ishga tushsin). `isolate=False` — shu jarayonda (testlar, GES_SIM_ISOLATE=false).
"""

from __future__ import annotations

import json
import multiprocessing as mp


class SimTimeout(Exception):
    pass


def compute(kind: str, params: dict) -> dict:
    """Bola jarayonda ham, to'g'ridan-to'g'ri ham chaqiriladi."""
    from ges_sim import catalog, custom, scenario

    if kind == "hydro":
        return scenario.run(params)
    if kind == "custom":
        return custom.run(params["template"], params.get("inputs") or {})
    if kind in catalog.REGISTRY:
        return catalog.run(kind, params)
    if kind == "_sleep":  # test: vaqt chegarasi
        import time

        time.sleep(float(params.get("seconds", 1)))
        return {"summary": {}}
    raise ValueError(f"Noma'lum simulyatsiya turi: {kind}")


def _child(conn, kind: str, params: dict) -> None:
    try:
        out = compute(kind, params)
        conn.send(("ok", json.dumps(out)))
    except Exception as e:  # noqa: BLE001 — xato matni ota jarayonga
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def run_isolated(kind: str, params: dict, timeout_s: float) -> dict:
    """Alohida jarayonda; muddat o'tsa SimTimeout, xato bo'lsa RuntimeError."""
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, kind, params), daemon=True)
    proc.start()
    child.close()
    try:
        if parent.poll(timeout_s):
            status, payload = parent.recv()
        else:
            proc.kill()
            raise SimTimeout(
                f"hisob {timeout_s:.0f} s ichida tugamadi — parametrlarni (davomiylik, qadam, "
                "oraliqlar soni) kamaytiring"
            )
    finally:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        parent.close()
    if status != "ok":
        raise RuntimeError(payload)
    return json.loads(payload)
