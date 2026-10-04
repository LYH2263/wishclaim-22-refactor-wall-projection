from datetime import datetime, timedelta, timezone

from app.modules.wall_projection import project_card, project_cards

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _dto(status="open", claimer=None, claimed_at=None, expires_at=None, title="x", **kw):
    return {
        "id": 1, "title": title, "note": "", "status": status,
        "claimer": claimer, "claimed_at": claimed_at, "expires_at": expires_at,
        "data_quality": "clean", **kw,
    }


def test_open_card_is_claimable_with_chinese_copy():
    card = project_card(_dto(), NOW)
    assert card["status_text"] == "可认领" and card["badge"] == "可领"
    assert card["claimable"] is True and card["countdown_text"] is None


def test_claimed_lock_has_countdown_only_in_projection():
    dto = _dto(status="claimed", claimer="alice",
               claimed_at=(NOW - timedelta(seconds=30)).isoformat(),
               expires_at=(NOW + timedelta(seconds=3661)).isoformat())
    card = project_card(dto, NOW)
    assert card["claimable"] is False
    assert card["status_text"] == "锁定中"
    assert card["countdown_text"].startswith("剩余 ") and card["countdown_text"] == "剩余 01:01:01"


def test_expired_lock_projects_as_claimable_before_sweep_persists():
    dto = _dto(status="claimed", claimer="ghost",
               expires_at=(NOW - timedelta(seconds=1)).isoformat())
    card = project_card(dto, NOW)
    assert card["claimable"] is True
    assert card["status_text"] == "可认领"
    assert card["countdown_text"] is None  # never shows a negative countdown


def test_fulfilled_and_released_are_not_claimable():
    assert project_card(_dto(status="fulfilled"), NOW)["claimable"] is False
    card = project_card(_dto(status="released"), NOW)
    assert card["claimable"] is True and card["status_text"] == "已释放，可重新认领"


def test_empty_title_falls_back_to_display_title():
    assert project_card(_dto(title=""), NOW)["display_title"] == "（无标题）"


def test_project_cards_is_one_to_one():
    cards = project_cards([_dto(title="a"), _dto(title="b")], NOW)
    assert [c["title"] for c in cards] == ["a", "b"]
