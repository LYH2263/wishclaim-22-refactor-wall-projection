"""Wall-card projection: the ONLY place status text, badges and the claimed
countdown text are produced.

Pure functions over a storage DTO (app.modules.wish_store.to_dto) — no DB
access. The projection never invents state: a claimed wish whose lock has
expired is projected as open, which is exactly the same rule the store's
normalize() persists, so after a TTL sweep the wall card and detail status
can never disagree. Routes and the frontend render these fields verbatim;
no second copy of status/countdown wording may exist anywhere else.
"""
import math

from app.engines.claim_lock import parse_ts

# status -> 投影口径（文案、角标、是否可认领）。唯一一份。
_VIEW = {
    "open":      {"status_text": "可认领", "badge": "可领",   "claimable": True},
    "claimed":   {"status_text": "认领中", "badge": "已锁定", "claimable": False},
    "released":  {"status_text": "已释放", "badge": "可领",   "claimable": True},
    "fulfilled": {"status_text": "已完成", "badge": "已完成", "claimable": False},
}


def is_lock_expired(dto: dict, now) -> bool:
    if dto.get("status") != "claimed" or not dto.get("expires_at"):
        return False
    return parse_ts(dto["expires_at"]) <= now


def effective_state(dto: dict, now) -> str:
    """Persisted status, folded the same way normalize() folds it."""
    if is_lock_expired(dto, now):
        return "open"
    return dto.get("status", "open")


def remaining_seconds(dto: dict, now) -> int | None:
    """Whole seconds left on a live claimed lock; None otherwise."""
    if dto.get("status") != "claimed" or is_lock_expired(dto, now) or not dto.get("expires_at"):
        return None
    secs = math.ceil((parse_ts(dto["expires_at"]) - now).total_seconds())
    return max(secs, 0)


def _clock(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def countdown_text(dto: dict, now) -> str | None:
    """The claimed-lock countdown wording. Generated nowhere else."""
    left = remaining_seconds(dto, now)
    if left is None:
        return None
    return f"认领锁定剩 {_clock(left)}"


def project_state(dto: dict, now) -> dict:
    state = effective_state(dto, now)
    view = _VIEW[state]
    return {
        "state": state,
        "status_text": view["status_text"],
        "badge": view["badge"],
        "claimable": view["claimable"],
        "countdown_text": countdown_text(dto, now),
    }


def project_card(dto: dict, now) -> dict:
    """Wall / mine / done list card: DTO surface fields + projection only."""
    return {
        "id": dto["id"],
        "title": dto.get("title"),
        "note": dto.get("note"),
        "data_quality": dto.get("data_quality"),
        "claimer": dto.get("claimer"),
        **project_state(dto, now),
    }


def project_detail(dto: dict, now) -> dict:
    """Detail stays the truth source: every raw DTO field, plus the same
    projection the wall card gets — status can never diverge between them."""
    return {**dto, **project_state(dto, now)}
