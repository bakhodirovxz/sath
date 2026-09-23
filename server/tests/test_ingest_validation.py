"""A3: kiruvchi qiymat va vaqt tamg'asi validatsiyasi (NaN/inf, kelajak/eski ts, fizik diapazon)."""

from datetime import datetime, timedelta, timezone

import pytest
from ges_server.db import SessionLocal
from ges_server.monitoring import live
from ges_server.orm import Reading


@pytest.fixture
def power(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": "AGG1.P", "name": "Agregat 1", "kind": "power", "unit": "MW", "high_alarm": 30},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _hdr(client, users):
    return users["engineer"]


def _post(client, users, items):
    return client.post(
        f"/api/projects/{users['project_id']}/readings", json=items, headers=_hdr(client, users)
    )


def _sensor(client, users, key):
    rows = client.get(f"/api/projects/{users['project_id']}/sensors", headers=users["viewer"]).json()
    return next(s for s in rows if s["key"] == key)


@pytest.mark.parametrize(
    "bad,reason",
    [("nan", "value_not_finite"), ("inf", "value_not_finite"), ("-inf", "value_not_finite"),
     ("1e400", "value_not_finite"), ("xato", "value_invalid"), (None, "value_invalid")],
)
def test_non_finite_or_non_numeric_value_rejected_per_item(client, users, power, bad, reason):
    """SCADA-06: yaroqsiz qiymat — yozuv bo'yicha rad (sabab bilan), paket 200."""
    r = _post(client, users, [{"key": "AGG1.P", "value": bad}])
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 0 and r.json()["rejected"] == [{"key": "AGG1.P", "reason": reason}]
    with SessionLocal() as db:
        assert db.query(Reading).count() == 0


def test_structurally_invalid_body_is_422(client, users, power):
    assert _post(client, users, [{"key": "AGG1.P", "value": [1]}]).status_code == 422


def test_mixed_batch_accepts_good_items(client, users, power):
    """SCADA-06 qabul: aralash paket — NaN/inf/kelajak ts/matn rad etiladi, qolganlari qabul qilinadi."""
    now = datetime.now(timezone.utc)
    raw = (
        '[{"key": "AGG1.P", "value": 10}, {"key": "AGG1.P", "value": NaN}, {"key": "AGG1.P", "value": Infinity},'
        ' {"key": "AGG1.P", "value": "abc"}, {"key": "AGG1.P", "value": 11, "ts": "2099-01-01T00:00:00Z"},'
        ' {"key": "YOQ", "value": 1}, {"key": "AGG1.P", "value": 12, "ts": "' + now.isoformat() + '"}]'
    )
    r = client.post(
        f"/api/projects/{users['project_id']}/readings", content=raw,
        headers={**_hdr(client, users), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 2 and body["unknown"] == ["YOQ"]
    assert [x["reason"] for x in body["rejected"]] == ["value_not_finite", "value_not_finite", "value_invalid", "ts_future"]
    assert _sensor(client, users, "AGG1.P")["last_value"] == 12
    with SessionLocal() as db:
        assert sorted(x.value for x in db.query(Reading).all()) == [10, 12]


@pytest.mark.parametrize(
    "ts,reason",
    [
        ("9999-12-31T00:00:00Z", "ts_future"),
        ("1970-01-01T00:00:00Z", "ts_too_old"),
        (253402300799.0, {"ts_future", "ts_invalid"}),  # 9999-12-31 unix (Windows: fromtimestamp xato)
        (1e18, "ts_invalid"),  # fromtimestamp OverflowError/OSError
        ("bugun", "ts_invalid"),
    ],
)
def test_out_of_window_or_invalid_ts_is_rejected(client, users, power, ts, reason):
    r = _post(client, users, [{"key": "AGG1.P", "value": 1, "ts": ts}])
    assert r.status_code == 200, r.text
    body = r.json()
    reasons = reason if isinstance(reason, set) else {reason}
    assert body["accepted"] == 0 and len(body["rejected"]) == 1
    assert body["rejected"][0]["key"] == "AGG1.P" and body["rejected"][0]["reason"] in reasons
    # kelajakdagi tamg'a last_ts ni qotirmagan: hozirgi qiymat qabul qilinadi
    r = _post(client, users, [{"key": "AGG1.P", "value": 2}]).json()
    assert r["accepted"] == 1 and r["rejected"] == []
    assert _sensor(client, users, "AGG1.P")["last_value"] == 2


def test_recent_past_and_small_future_skew_are_accepted(client, users, power):
    now = datetime.now(timezone.utc)
    items = [
        {"key": "AGG1.P", "value": 1, "ts": (now - timedelta(days=29)).isoformat()},
        {"key": "AGG1.P", "value": 2, "ts": (now + timedelta(seconds=60)).isoformat()},
        {"key": "AGG1.P", "value": 3, "ts": int((now - timedelta(minutes=1)).timestamp())},
    ]
    r = _post(client, users, items).json()
    assert r["accepted"] == 3 and r["rejected"] == []


def test_csv_import_allows_old_history(client, users, power):
    csv = "ts,value\n2019-01-01T00:00:00Z,5\n2019-01-01T01:00:00Z,6,bad\n"
    r = client.post(
        f"/api/sensors/{power['id']}/import",
        files={"file": ("h.csv", csv, "text/csv")},
        headers=users["engineer"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2 and r.json()["bad"] == 1 and r.json()["rejected"] == []


def test_raw_range_marks_bad(client, users, power):
    r = client.patch(
        f"/api/sensors/{power['id']}", json={"min_raw": 0, "max_raw": 100}, headers=users["engineer"]
    )
    assert r.status_code == 200 and r.json()["max_raw"] == 100
    body = _post(client, users, [{"key": "AGG1.P", "value": 50}, {"key": "AGG1.P", "value": 150}]).json()
    assert body["accepted"] == 2 and body["bad"] == 1
    s = _sensor(client, users, "AGG1.P")
    assert s["last_value"] == 50 and s["alarm"] == "high"  # 150 holatga ta'sir qilmadi
    with SessionLocal() as db:
        qs = [x.quality for x in db.query(Reading).order_by(Reading.id).all()]
        assert qs == ["good", "bad"]
    r = client.patch(
        f"/api/sensors/{power['id']}", json={"clear_raw_range": True}, headers=users["engineer"]
    )
    assert r.json()["min_raw"] is None and r.json()["max_raw"] is None


def test_parse_ts_edge_cases():
    assert live._parse_ts(None) is None
    assert live._parse_ts(True) is None
    assert live._parse_ts(float("nan")) is None
    assert live._parse_ts(1e18) is None
    assert live._parse_ts("1700000000") == datetime.fromtimestamp(1700000000, tz=timezone.utc)
    assert live._parse_ts("2026-01-01T00:00:00").tzinfo is not None
