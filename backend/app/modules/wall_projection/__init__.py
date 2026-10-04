"""Wall-card projection: the ONLY place display text is derived.

Consumes storage DTOs from wish_store and produces view cards carrying
status_text / badge / countdown_text. No route or frontend code is allowed to
rebuild status copy — especially the claimed countdown, which may be generated
nowhere else.

`claimable` deliberately reuses claim_lock.claim_allowed so the wall's
"can I claim?" answer is the same rule the claim write-path enforces. Cards
are normally projected after wish_store.sweep_expired with the same `now`,
which keeps the wall and detail in lockstep after a TTL release.
"""
from datetime import datetime

from app.engines.claim_lock import claim_allowed, parse_ts

_STATUS_TEXT = {
    "open": "可认领",
    "claimed": "锁定中",
    "released": "已释放，可重新认领",
    "fulfilled": "已完成",
}
_BADGE = {
    "open": "可领",
    "claimed": "锁定",
    "released": "已释放",
    "fulfilled": "已完成",
}


def _countdown_text(dto: dict, now: datetime) -> str | None:
    """Claimed countdown copy — generated only here, only for live locks."""
    if dto["status"] != "claimed" or not dto["expires_at"]:
        return None
    remain = parse_ts(dto["expires_at"]) - now
    secs = int(remain.total_seconds())
    if secs <= 0:
        return None  # expired: sweep flips it to open with the same `now`
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days:
        return f"剩余 {days}天{hours}时"
    return f"剩余 {hours:02d}:{mins:02d}:{secs:02d}"


def project_card(dto: dict, now: datetime) -> dict:
    """Project one storage DTO into a wall/detail view card (pure)."""
    expired_live_lock = (
        dto["status"] == "claimed"
        and bool(dto["expires_at"])
        and parse_ts(dto["expires_at"]) <= now
    )
    # Expired locks are reclaimable until sweep persists the release; project
    # them as open so display never lies ahead of the write.
    effective_status = "open" if expired_live_lock else dto["status"]
    return {
        "id": dto["id"],
        "title": dto["title"],
        "display_title": dto["title"] or "（无标题）",
        "note": dto["note"],
        "status": dto["status"],
        "status_text": _STATUS_TEXT.get(effective_status, effective_status),
        "badge": _BADGE.get(effective_status, effective_status),
        "claimer": dto["claimer"],
        "claimed_at": dto["claimed_at"],
        "expires_at": dto["expires_at"],
        "countdown_text": _countdown_text(dto, now),
        "claimable": bool(claim_allowed(dto["status"], dto["claimer"], now, dto["expires_at"])["ok"]),
        "data_quality": dto["data_quality"],
    }


def project_cards(dtos: list[dict], now: datetime) -> list[dict]:
    return [project_card(d, now) for d in dtos]
