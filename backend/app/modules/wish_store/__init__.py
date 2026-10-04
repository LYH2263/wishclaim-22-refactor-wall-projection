"""Wish storage: DTO reads/writes and the single source of TTL normalization.

TTL sweep lives ONLY here. Any read that can surface a wish to a user
(list / detail / mine / claim pre-check) must go through `normalize` first,
on the same connection the subsequent SELECT uses, so an expired lock can
never appear claimable on the wall while detail still shows claimed
(or the reverse). Detail remains the truth source: callers get the raw
DTO back via `to_dto`, projections live in app.modules.wish_projection.
"""
from app.db import connect
from app.engines.claim_lock import release_if_expired

COLS = ("id", "title", "note", "status", "claimer", "claimed_at", "expires_at", "data_quality")


def get_setting(c, key: str, default=None):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def ttl(c) -> int:
    return int(get_setting(c, "ttl_seconds", 86400))


def to_dto(row) -> dict:
    """Raw stored wish — the truth source. Projection never touches the DB."""
    return dict(row) if row is not None else None


def normalize(c, now) -> int:
    """The one and only TTL sweep: expire claimed locks in place.

    Runs inside the caller's transaction before its SELECT, so wall list
    and detail derive from the same persisted state. Returns release count.
    """
    released = 0
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now)
        if rel:
            c.execute(
                "UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                (rel["status"], rel["claimer"], rel["claimed_at"], rel["expires_at"], r["id"]),
            )
            released += 1
    if released:
        c.commit()
    return released


def list_dtos(c) -> list[dict]:
    return [to_dto(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]


def list_fulfilled_dtos(c) -> list[dict]:
    return [to_dto(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled' ORDER BY id DESC")]


def list_mine_dtos(c, claimer: str) -> list[dict]:
    return [to_dto(r) for r in c.execute(
        "SELECT * FROM wishes WHERE claimer=? ORDER BY id DESC", (claimer,))]


def get_dto(c, wid: int) -> dict | None:
    return to_dto(c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone())


def insert(c, title: str, note: str) -> int:
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
        (title, note, "open", "clean"),
    )
    c.commit()
    return cur.lastrowid


def save_lock(c, wid: int, payload: dict) -> None:
    c.execute(
        "UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
        (payload["status"], payload["claimer"], payload["claimed_at"], payload["expires_at"], wid),
    )
    c.commit()


def save_release(c, wid: int) -> None:
    c.execute(
        "UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?",
        (wid,),
    )
    c.commit()


def save_fulfill(c, wid: int) -> None:
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit()


def update_title(c, wid: int, title: str) -> None:
    c.execute("UPDATE wishes SET title=? WHERE id=?", (title, wid))
    c.commit()


def open_connection():
    """Exposed so routes keep one connection across normalize + read/write."""
    return connect()
