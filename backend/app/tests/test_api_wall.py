import pytest
from datetime import timedelta

from fastapi.testclient import TestClient

from app import main
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # enters lifespan so seed.init_db() creates tables
        yield c


def _wall(client, payload_id):
    return next(c for c in client.get("/api/wishes").json() if c["id"] == payload_id)


def test_seed_expired_lock_is_released_on_wall_and_detail_alike(client):
    """TTL sweep: wall and detail must both flip to open — never split-brain."""
    wall = next(c for c in client.get("/api/wishes").json() if c["title"] == "过期锁样例")
    assert wall["status"] == "open"
    assert wall["claimable"] is True and wall["status_text"] == "可认领"
    assert wall["countdown_text"] is None
    detail = client.get(f"/api/wishes/{wall['id']}").json()
    assert detail["status"] == wall["status"]
    assert detail["claimable"] == wall["claimable"]
    assert detail["status_text"] == wall["status_text"]


def test_claimed_card_agrees_between_wall_and_detail(client):
    wid = client.post("/api/wishes", json={"title": "手套", "note": ""}).json()["id"]
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "bob"})
    wall = _wall(client, wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    for key in ("status", "status_text", "badge", "claimable", "countdown_text", "claimer"):
        assert wall[key] == detail[key]
    assert wall["status"] == "claimed" and wall["claimable"] is False
    assert wall["countdown_text"] is not None  # countdown copy born in projection only


def test_ttl_expiry_then_wall_and_detail_both_reclaimable(client, monkeypatch):
    wid = client.post("/api/wishes", json={"title": "台灯", "note": ""}).json()["id"]
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "carol"}).raise_for_status()
    base = main.now()
    monkeypatch.setattr(main, "now", lambda: base + timedelta(days=2))
    wall = _wall(client, wid)
    detail = client.get(f"/api/wishes/{wid}").json()
    assert wall["status"] == "open" and detail["status"] == "open"
    assert wall["claimable"] is True and detail["claimable"] is True
    assert wall["status_text"] == detail["status_text"] == "可认领"
    # the freed lock really is claimable again through the write path
    again = client.post(f"/api/wishes/{wid}/claim", json={"claimer": "dave"}).json()
    assert again["status"] == "claimed" and again["claimer"] == "dave"


def test_rename_is_reflected_on_wall_and_detail(client):
    wid = client.post("/api/wishes", json={"title": "旧名", "note": ""}).json()["id"]
    patched = client.patch(f"/api/wishes/{wid}", json={"title": "新名"}).json()
    assert patched["title"] == "新名"
    assert _wall(client, wid)["title"] == "新名"
    assert client.get(f"/api/wishes/{wid}").json()["title"] == "新名"
