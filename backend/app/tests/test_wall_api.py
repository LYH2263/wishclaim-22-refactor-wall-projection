"""Wall/detail 同口径 API 测例：TTL 释放、认领锁定、改 title 后投影必须一致。"""
import os
import tempfile
from datetime import datetime, timezone

_tmp = tempfile.mkdtemp(prefix="wishclaim-test-")
os.environ["DATA_DIR"] = _tmp

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app import main  # noqa: E402
from app.main import app  # noqa: E402

FROZEN = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    # 冻结时钟：墙列表与详情在不同 HTTP 调用里也不会因跨秒导致倒计时差 1s
    monkeypatch.setattr(main, "now", lambda: FROZEN)
    with TestClient(app) as c:
        yield c


def _card(rows, wid):
    return next(r for r in rows if r["id"] == wid)


def test_expired_lock_wall_and_detail_both_open(client):
    """TTL 扫释放后：墙可认领态与详情 status 同钉（seed 里的 2020 过期锁）。"""
    wall = client.get("/api/wishes").json()
    ghost = next(r for r in wall if r["title"] == "过期锁样例")
    wid = ghost["id"]
    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()

    assert card["state"] == "open" and card["claimable"] is True
    assert detail["state"] == "open" and detail["claimable"] is True
    assert card["state"] == detail["state"]
    assert card["status_text"] == detail["status_text"] == "可认领"
    assert card["countdown_text"] is None and detail["countdown_text"] is None
    # sweep 已落库：详情真源 status 也是 open，而不是"墙 open / 详情 claimed"
    assert detail["status"] == "open" and detail["claimer"] is None


def test_live_claim_wall_and_detail_both_locked(client):
    wid = client.post("/api/wishes", json={"title": "杯"}).json()["id"]
    assert client.post(f"/api/wishes/{wid}/claim", json={"claimer": "alice"}).status_code == 200
    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()

    assert card["state"] == "claimed" and card["claimable"] is False
    assert detail["state"] == "claimed" and detail["claimable"] is False
    assert card["status_text"] == detail["status_text"] == "认领中"
    # claimed 倒计时文案只来自投影模块，墙与详情同一份（时钟冻结，逐字相等）
    assert card["countdown_text"] == detail["countdown_text"] == "认领锁定剩 24:00:00"
    # 第二个认领人被互斥挡住
    assert client.post(f"/api/wishes/{wid}/claim", json={"claimer": "bob"}).status_code == 409


def test_reclaim_expired_after_short_ttl_succeeds(client):
    """把锁直接置过期：墙显示可领、新认领成功，详情同步。"""
    import sqlite3
    from app.db import db_path
    wid = client.post("/api/wishes", json={"title": "秒"}).json()["id"]
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "alice"})
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE wishes SET expires_at='2020-01-01T00:00:00+00:00' WHERE id=?", (wid,))
    conn.commit(); conn.close()

    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    assert card["state"] == detail["state"] == "open"
    r = client.post(f"/api/wishes/{wid}/claim", json={"claimer": "bob"})
    assert r.status_code == 200 and r.json()["claimer"] == "bob"
    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    assert card["state"] == detail["state"] == "claimed"
    assert detail["claimer"] == "bob"


def test_patch_title_is_shared_by_wall_and_detail(client):
    """改 title 后墙卡片与详情同钉：存储只有一份 title。"""
    wid = client.post("/api/wishes", json={"title": "旧标题"}).json()["id"]
    r = client.patch(f"/api/wishes/{wid}", json={"title": "新标题"})
    assert r.status_code == 200 and r.json()["title"] == "新标题"
    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    assert card["title"] == detail["title"] == "新标题"


def test_mine_drops_expired_locks(client):
    import sqlite3
    from app.db import db_path
    wid = client.post("/api/wishes", json={"title": "掉出我的"}).json()["id"]
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "carol"})
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE wishes SET expires_at='2020-01-01T00:00:00+00:00' WHERE id=?", (wid,))
    conn.commit(); conn.close()

    mine = client.get("/api/mine", params={"claimer": "carol"}).json()
    assert all(r["id"] != wid for r in mine)
    card = _card(client.get("/api/wishes").json(), wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    assert card["state"] == detail["state"] == "open"
