from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload
from app.modules import wish_store as store
from app.modules.wall_projection import project_card, project_cards

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def _swept_conn(ts: datetime):
    """Open a connection, release expired locks with one timestamp, commit.

    Every read (list/detail/mine) and the claim write-path go through this, so
    a TTL release is persisted before any card is projected, so wall and
    detail share exactly the same status view.
    """
    c = connect()
    store.sweep_expired(c, ts)
    c.commit()
    return c

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    ts = now()
    c = _swept_conn(ts)
    cards = project_cards(store.list_wishes(c), ts); c.close(); return cards

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    ts = now()
    c = _swept_conn(ts)
    dto = store.get_wish(c, wid); c.close()
    if not dto: raise HTTPException(404, "not found")
    return project_card(dto, ts)

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    wid = store.insert_wish(c, body.title, body.note)
    c.commit(); c.close(); return {"id": wid}

class WishPatch(BaseModel):
    title: str

@app.patch("/api/wishes/{wid}")
def patch_wish(wid: int, body: WishPatch):
    ts = now()
    c = _swept_conn(ts)
    dto = store.get_wish(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    store.update_title(c, wid, body.title); c.commit()
    dto = store.get_wish(c, wid); c.close()
    return project_card(dto, ts)  # wall and detail read this same card

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    ts = now()
    c = _swept_conn(ts)
    dto = store.get_wish(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(dto["status"], dto["claimer"], ts, dto["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    store.apply_lock(c, wid, lock_payload(body.claimer, ts, store.ttl_seconds()))
    c.commit()
    dto = store.get_wish(c, wid); c.close()
    return project_card(dto, ts)

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    ts = now()
    c = connect()
    dto = store.get_wish(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    if dto["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    store.mark_released(c, wid); c.commit()
    dto = store.get_wish(c, wid); c.close()
    return project_card(dto, ts)

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    ts = now()
    c = connect()
    dto = store.get_wish(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    if dto["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    store.mark_fulfilled(c, wid); c.commit()
    dto = store.get_wish(c, wid); c.close()
    return project_card(dto, ts)

@app.get("/api/mine")
def mine(claimer: str):
    ts = now()
    c = _swept_conn(ts)
    cards = project_cards(store.list_by_claimer(c, claimer), ts); c.close(); return cards

@app.get("/api/done")
def done():
    ts = now()
    c = connect()
    cards = project_cards(store.list_fulfilled(c), ts); c.close(); return cards

@app.get("/api/settings")
def settings():
    c = connect()
    rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close()
    return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
    }
