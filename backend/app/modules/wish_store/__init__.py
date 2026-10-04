"""Wish storage: owns every SQL statement against wishes/settings.

This module is the ONLY place that reads or writes wish rows. It returns plain
storage DTOs (raw column dicts) and never derives display text — that belongs
to wall_projection. Detail views keep consuming the same DTO as the source of
truth.
"""
from datetime import datetime

from app.db import connect
from app.engines.claim_lock import release_if_expired

COLUMNS = ("id", "title", "note", "status", "claimer", "claimed_at", "expires_at", "data_quality")
DEFAULT_TTL_SECONDS = 86400


def _dto(r) -> dict:
    return {k: r[k] for k in COLUMNS}


def ttl_seconds() -> int:
    c = connect()
    try:
        row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone()
    finally:
        c.close()
    return int(row["value"] if row else DEFAULT_TTL_SECONDS)


def sweep_expired(c, now: datetime) -> list[int]:
    """Release every claimed wish whose lock expired at/before `now`.

    Runs on both list and detail reads with the same timestamp, so the wall and
    detail can never disagree about a TTL-freed wish. Mutates + leaves commit
    to the caller. Returns released wish ids.
    """
    released = []
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now)
        if rel:
            c.execute(
                "UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                (rel["status"], None, None, None, r["id"]),
            )
            released.append(r["id"])
    return released


def list_wishes(c) -> list[dict]:
    return [_dto(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]


def get_wish(c, wid: int) -> dict | None:
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    return _dto(r) if r else None


def list_by_claimer(c, claimer: str) -> list[dict]:
    return [_dto(r) for r in c.execute("SELECT * FROM wishes WHERE claimer=? ORDER BY id DESC", (claimer,))]


def list_fulfilled(c) -> list[dict]:
    return [_dto(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled' ORDER BY id DESC")]


def insert_wish(c, title: str, note: str) -> int:
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
        (title, note, "open", "clean"),
    )
    return cur.lastrowid


def apply_lock(c, wid: int, lock: dict) -> None:
    c.execute(
        "UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
        (lock["status"], lock["claimer"], lock["claimed_at"], lock["expires_at"], wid),
    )


def mark_released(c, wid: int) -> None:
    c.execute(
        "UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?",
        (wid,),
    )


def mark_fulfilled(c, wid: int) -> None:
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))


def update_title(c, wid: int, title: str) -> None:
    c.execute("UPDATE wishes SET title=? WHERE id=?", (title, wid))
