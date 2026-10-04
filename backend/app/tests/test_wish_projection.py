from datetime import datetime, timedelta, timezone

from app.modules import wish_projection as proj

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _dto(status="open", claimer=None, expires_at=None, title="x"):
    return {
        "id": 1, "title": title, "note": "", "status": status,
        "claimer": claimer, "claimed_at": None, "expires_at": expires_at,
        "data_quality": "clean",
    }


def test_open_is_claimable_without_countdown():
    s = proj.project_state(_dto(), NOW)
    assert s == {"state": "open", "status_text": "可认领", "badge": "可领",
                 "claimable": True, "countdown_text": None}


def test_live_claim_is_locked_with_countdown():
    dto = _dto("claimed", "alice", (NOW + timedelta(seconds=3661)).isoformat())
    s = proj.project_state(dto, NOW)
    assert s["state"] == "claimed" and s["status_text"] == "认领中"
    assert s["badge"] == "已锁定" and s["claimable"] is False
    # claimed 倒计时文案只在投影模块生成：唯一格式在这里钉死
    assert s["countdown_text"] == "认领锁定剩 01:01:01"


def test_countdown_counts_down():
    dto = _dto("claimed", "alice", (NOW + timedelta(seconds=60)).isoformat())
    assert proj.project_state(dto, NOW)["countdown_text"] == "认领锁定剩 00:01:00"
    assert proj.project_state(dto, NOW + timedelta(seconds=59))["countdown_text"] == "认领锁定剩 00:00:01"


def test_expired_lock_projects_as_open():
    dto = _dto("claimed", "ghost", (NOW - timedelta(seconds=1)).isoformat())
    s = proj.project_state(dto, NOW)
    assert s["state"] == "open" and s["claimable"] is True
    assert s["status_text"] == "可认领" and s["countdown_text"] is None


def test_terminal_states():
    assert proj.project_state(_dto("fulfilled", "alice"), NOW)["status_text"] == "已完成"
    s = proj.project_state(_dto("released"), NOW)
    assert s["status_text"] == "已释放" and s["claimable"] is True


def test_card_and_detail_share_one_projection():
    dto = _dto("claimed", "alice", (NOW + timedelta(minutes=5)).isoformat())
    card = proj.project_card(dto, NOW)
    detail = proj.project_detail(dto, NOW)
    assert card["state"] == detail["state"]
    assert card["status_text"] == detail["status_text"]
    assert card["badge"] == detail["badge"]
    assert card["claimable"] == detail["claimable"]
    assert card["countdown_text"] == detail["countdown_text"]
    # 详情仍是真源：保留全部原始 DTO 字段
    assert detail["status"] == "claimed" and detail["claimer"] == "alice"
