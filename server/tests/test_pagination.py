"""D4: list_projects so'rovlar soni loyihalar sonidan mustaqil; kursorli sahifalash; DB tomonda siyraklashtirish."""

from datetime import datetime, timedelta, timezone

from ges_server.db import SessionLocal, engine
from ges_server.monitoring import live
from ges_server.orm import Model, Project, ProjectMember, Role, User
from sqlalchemy import event


class _Counter:
    def __init__(self):
        self.n = 0

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.n += 1


def _count_queries(fn):
    c = _Counter()
    event.listen(engine, "before_cursor_execute", c)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", c)
    return c.n


def test_list_projects_constant_queries(client, users, admin):
    uid = users["ids"]["engineer"]
    with SessionLocal() as db:
        creator = db.query(User).filter_by(username="admin").one().id
        for i in range(60):
            p = Project(name=f"L{i:03d}", created_by=creator)
            db.add(p)
            db.flush()
            db.add(ProjectMember(project_id=p.id, user_id=uid, role=Role.viewer if i % 2 else Role.engineer))
            for _ in range(i % 3):
                db.add(Model(project_id=p.id, name=f"M{_}{i}"))
        db.commit()
    n_small = _count_queries(lambda: client.get("/api/projects?limit=5", headers=users["engineer"]))
    r = client.get("/api/projects?limit=500", headers=users["engineer"])
    n_big = _count_queries(lambda: client.get("/api/projects?limit=500", headers=users["engineer"]))
    rows = r.json()
    assert len(rows) == 61 and n_big == n_small  # 1 loyiha (fixture) + 60
    assert n_big <= 6  # auth (user) + loyihalar + model soni + rollar (+ audit/sessiya)
    by = {x["name"]: x for x in rows}
    assert by["L004"]["model_count"] == 1 and by["L005"]["model_count"] == 2 and by["L006"]["model_count"] == 0
    assert by["L004"]["my_role"] == "engineer" and by["L005"]["my_role"] == "viewer"
    # admin ham doimiy
    n_admin = _count_queries(lambda: client.get("/api/projects", headers=admin))
    assert n_admin <= 5 and all(x["my_role"] == "approver" for x in client.get("/api/projects", headers=admin).json())
    # kursor: after_id bo'yicha id tartibi, qidiruv
    page1 = client.get("/api/projects?limit=10", headers=admin).json()
    assert len(page1) == 10
    ids = [x["id"] for x in client.get("/api/projects?limit=1000&after_id=0", headers=admin).json()]
    assert ids == sorted(ids) and len(ids) == 61
    nxt = client.get(f"/api/projects?limit=1000&after_id={ids[30]}", headers=admin).json()
    assert [x["id"] for x in nxt] == ids[31:]
    assert [x["name"] for x in client.get("/api/projects?q=L05", headers=admin).json()] == [f"L05{i}" for i in range(10)]


def test_users_members_sensors_cursors(client, users, admin):
    pid = users["project_id"]
    page = client.get("/api/users?limit=2", headers=admin).json()
    assert len(page) == 2
    all_ids = [u["id"] for u in client.get("/api/users?after_id=0&limit=100", headers=admin).json()]
    assert all_ids == sorted(all_ids) and len(all_ids) >= 5
    assert [u["id"] for u in client.get(f"/api/users?after_id={all_ids[1]}&limit=100", headers=admin).json()] == all_ids[2:]
    assert [u["username"] for u in client.get("/api/users?q=view", headers=admin).json()] == ["viewer"]
    m = client.get(f"/api/projects/{pid}/members?limit=2", headers=users["viewer"]).json()
    assert len(m) == 2 and m[0]["username"]
    m2 = client.get(f"/api/projects/{pid}/members?after_id={m[-1]['user_id']}", headers=users["viewer"]).json()
    assert len(m2) == 1 and m2[0]["user_id"] > m[-1]["user_id"]
    for i in range(7):
        client.post(f"/api/projects/{pid}/sensors", json={"key": f"S{i}", "name": f"Z{7 - i}", "kind": "value", "unit": ""}, headers=users["engineer"])
    s_all = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
    assert [x["name"] for x in s_all] == sorted(x["name"] for x in s_all)  # limit siz — nom tartibi, hammasi
    s1 = client.get(f"/api/projects/{pid}/sensors?limit=3&after_id=0", headers=users["viewer"]).json()
    s2 = client.get(f"/api/projects/{pid}/sensors?limit=10&after_id={s1[-1]['id']}", headers=users["viewer"]).json()
    assert [x["id"] for x in s1 + s2] == sorted(x["id"] for x in s_all)


def test_readings_downsampled_in_db_and_alarm_cursor(client, users):
    pid = users["project_id"]
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "RES.H", "name": "H", "kind": "level", "unit": "m", "high_alarm": 5}, headers=users["engineer"])
    sid = r.json()["id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        live._bulk_insert_readings(db, [{"sensor_id": sid, "ts": now - timedelta(hours=2) + timedelta(seconds=2 * i), "value": float(i % 10), "quality": "good", "src_ts": None} for i in range(3600)])
        db.commit()
    r = client.get(f"/api/sensors/{sid}/readings?hours=3&limit=100", headers=users["viewer"]).json()
    assert r["tier"] == "raw" and r["total"] == 3600 and 90 <= len(r["points"]) <= 101
    assert all(p["min"] <= p["v"] <= p["max"] for p in r["points"]) and r["points"][5]["max"] == 9 and r["points"][5]["min"] == 0
    r2 = client.get(f"/api/sensors/{sid}/readings?hours=3&limit=5000", headers=users["viewer"]).json()
    assert len(r2["points"]) == 3600
    # alarm jurnali kursori
    for v in (6, 1, 7, 1, 8, 1):
        client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": v}], headers=users["engineer"])
    ev = client.get(f"/api/projects/{pid}/alarm-events?limit=2", headers=users["viewer"]).json()
    ev2 = client.get(f"/api/projects/{pid}/alarm-events?limit=10&before_id={ev[-1]['id']}", headers=users["viewer"]).json()
    assert len(ev) == 2 and len(ev2) == 1 and ev2[0]["id"] < ev[-1]["id"] < ev[0]["id"]
    # buyruqlar/jurnal kursori (bo'sh ro'yxatda ham parametr qabul qilinadi)
    assert client.get(f"/api/projects/{pid}/commands?before_id=5", headers=users["viewer"]).status_code == 200
    assert client.get(f"/api/projects/{pid}/journal?before_id=5", headers=users["viewer"]).status_code == 200
