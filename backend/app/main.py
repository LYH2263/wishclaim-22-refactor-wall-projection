from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.modules import wish_projection as proj
from app.modules import wish_store as store
from app.engines.claim_lock import claim_allowed, lock_payload

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    # normalize + SELECT on one connection: expired locks are persisted as
    # open before projection, so wall and detail share one status口径.
    c = store.open_connection(); t = now()
    store.normalize(c, t)
    cards = [proj.project_card(d, t) for d in store.list_dtos(c)]
    c.close(); return cards

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    # Same normalize-before-read as the list; detail is the truth source
    # (raw DTO fields) carrying the same projection object as its wall card.
    c = store.open_connection(); t = now()
    store.normalize(c, t)
    dto = store.get_dto(c, wid); c.close()
    if not dto: raise HTTPException(404, "not found")
    return proj.project_detail(dto, t)

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = store.open_connection()
    wid = store.insert(c, body.title, body.note); c.close(); return {"id": wid}

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    c = store.open_connection(); t = now()
    store.normalize(c, t)  # may persist an expired lock as open
    dto = store.get_dto(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(dto["status"], dto["claimer"], t, dto["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    p = lock_payload(body.claimer, t, store.ttl(c))
    store.save_lock(c, wid, p); c.close(); return p

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = store.open_connection(); t = now()
    store.normalize(c, t)  # 过期锁先落回 open，再判释放——与墙/详情同口径
    dto = store.get_dto(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    if dto["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    store.save_release(c, wid); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = store.open_connection(); t = now()
    store.normalize(c, t)  # 过期锁不可核销：TTL 口径对所有状态转移写路径一致
    dto = store.get_dto(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    if dto["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    store.save_fulfill(c, wid); c.close(); return {"ok": True, "status": "fulfilled"}

class WishPatch(BaseModel):
    title: str

@app.patch("/api/wishes/{wid}")
def patch_wish(wid: int, body: WishPatch):
    # Title is a single stored column: wall projection and detail both read
    # it from the same row, so one UPDATE keeps them钉在一起.
    c = store.open_connection()
    dto = store.get_dto(c, wid)
    if not dto: c.close(); raise HTTPException(404, "not found")
    store.update_title(c, wid, body.title)
    dto = store.get_dto(c, wid); c.close()
    return proj.project_detail(dto, now())

@app.get("/api/mine")
def mine(claimer: str):
    c = store.open_connection(); t = now()
    store.normalize(c, t)  # expired locks lose their claimer here, dropping out of mine
    cards = [proj.project_card(d, t) for d in store.list_mine_dtos(c, claimer)]
    c.close(); return cards

@app.get("/api/done")
def done():
    c = store.open_connection()
    cards = [proj.project_card(d, now()) for d in store.list_fulfilled_dtos(c)]
    c.close(); return cards

@app.get("/api/settings")
def settings():
    c = store.open_connection()
    rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
    }
