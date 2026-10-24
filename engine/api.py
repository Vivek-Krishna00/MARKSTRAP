"""HTTP API + dashboard. Run: uvicorn engine.api:app"""
import csv
import io
import json
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import brief, db, evolve, reel, render

app = FastAPI(title="MarkStrap Campaign Engine")
con = db.connect()
reel.interrupted(con)
busy = threading.Lock()  # ponytail: one run at a time, single-campaign engine


RESULT_COLS = ["ad_id", "platform", "headline", "impressions", "reach", "clicks", "signups", "purchases", "saves",
               "shares", "comments", "replies", "reposts", "watch_time", "avg_view_duration", "completion_rate",
               "rewatches", "hours_live", "engagement_first_hours"]


class Campaign(BaseModel):
    goal: str
    market: str
    ad_type: str


class Dial(BaseModel):
    name: str
    value: float


WEB = Path(__file__).resolve().parent.parent / "web"


if (WEB / "site" / "assets").exists():  # built by `make site`
    app.mount("/assets", StaticFiles(directory=WEB / "site" / "assets"), name="site-assets")


@app.get("/")
def index():
    site = WEB / "site" / "index.html"
    return FileResponse(site if site.exists() else WEB / "app.html")


@app.get("/favicon.png")
def favicon():
    return FileResponse(WEB / "favicon.png")


@app.get("/app")
def user_app():
    return FileResponse(WEB / "app.html")


@app.get("/console")
def console():
    return FileResponse(WEB / "console.html")


@app.get("/api/state")
def state():
    agents = [db.row(r) for r in con.execute("SELECT * FROM agents ORDER BY fitness DESC")]
    ads = [db.row(r) for r in con.execute("SELECT * FROM ads ORDER BY term DESC, sim_score DESC LIMIT 60")]
    births = {r[0]: r[1] for r in con.execute("SELECT born, COUNT(*) FROM agents WHERE born>0 GROUP BY born")}
    return {
        "campaign": db.get(con, "campaign"), "term": evolve.term_no(con), "busy": busy.locked(),
        "dials": evolve.dials(con), "pending": db.get(con, "pending", {}),
        "personas": db.get(con, "personas", []), "lessons": db.get(con, "lessons", {}),
        "agents": agents, "ads": ads, "births": births,
        "queens": [dict(q) for q in con.execute("SELECT * FROM queens")],
        "memory": [dict(m) for m in con.execute("SELECT * FROM memory ORDER BY id DESC LIMIT 20")],
        "dial_log": [dict(m) for m in con.execute("SELECT * FROM dial_log ORDER BY id DESC LIMIT 20")],
        "approvals": db.get(con, "approvals", {}), "insights": db.get(con, "insights", []),
        "progress": db.get(con, "progress", {}),
        "org": [{"name": m["name"], "kind": m["kind"]} for m in brief.load_org()["materials"]],
        "draft": brief.load_org().get("draft"),
        "renders": sorted(p.stem for p in render.OUT.glob("*.png")) if render.OUT.exists() else [],
        "reels": [dict(r) for r in con.execute("SELECT id, ad_id, status FROM reels ORDER BY updated DESC")],
    }


def _guard(fn, *a):
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "a generation is already running")
    try:
        return fn(*a)
    finally:
        busy.release()


@app.post("/api/campaign")
def campaign(c: Campaign):
    global con
    con = db.new_campaign(con)
    _guard(evolve.seed_campaign, con, c.goal, c.market, c.ad_type)
    return state()


@app.post("/api/generation")
def generation():
    return {"term": _guard(evolve.run_generation, con)}


@app.post("/api/results")
async def results(file: UploadFile):
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    try:
        n = evolve.import_results(con, rows)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"could not import results: {e}")
    return {"imported": n}


@app.post("/api/dial")
def dial(d: Dial):
    try:
        evolve.set_dial(con, d.name, int(d.value) if d.value.is_integer() else d.value)
    except KeyError as e:
        raise HTTPException(400, str(e))
    return {"pending": db.get(con, "pending")}


@app.post("/api/snapshot")
def snapshot():
    return {"id": db.snapshot()}


@app.post("/api/rollback/{sid}")
def rollback(sid: str):
    global con
    con.close()
    db.rollback(sid)
    con = db.connect()
    return {"ok": True}


@app.post("/api/revive/{agent_id}")
def revive(agent_id: str):
    evolve.revive(con, agent_id)
    return {"ok": True}


@app.get("/api/lineage/{agent_id}")
def lineage(agent_id: str):
    tree = evolve.lineage(con, agent_id)
    if not tree:
        raise HTTPException(404, "no such agent")
    return tree


@app.get("/api/ads.csv")
def ads_csv():
    """Shortlisted ads as a results template: a person posts them, fills metrics, re-uploads."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(RESULT_COLS)
    for a in con.execute("SELECT id, content FROM ads WHERE shortlisted=1 AND real_score IS NULL"):
        c = json.loads(a["content"])
        w.writerow([a["id"], c.get("platform", ""), c.get("headline", "")])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=shortlist.csv"})


# ---------- agency flow: materials -> brief -> explore -> approve -> launch -> measure -> next ----------

@app.post("/api/materials")
async def add_material(text: str = Form(""), url: str = Form(""), file: UploadFile | None = None):
    org = brief.load_org()
    try:
        if file is not None:
            org["materials"].append({"name": file.filename, "kind": "file",
                                     "text": brief.read_file(file.filename, await file.read())})
        if url:
            org["materials"].append({"name": url, "kind": "link", "text": brief.read_url(url)})
        if text.strip():
            org["materials"].append({"name": text.strip()[:40], "kind": "note", "text": text})
    except Exception as e:  # a bad link or unreadable file should not lose the other materials
        raise HTTPException(400, f"could not read material: {e}")
    brief.save_org(org)
    return {"materials": len(org["materials"])}


@app.delete("/api/materials/{i}")
def remove_material(i: int):
    org = brief.load_org()
    org["materials"].pop(i)
    brief.save_org(org)
    return {"materials": len(org["materials"])}


class BriefIn(BaseModel):
    objective: str
    constraints: dict


@app.post("/api/brief")
def make_brief(b: BriefIn):
    if b.objective not in brief.OBJECTIVES:
        raise HTTPException(400, "unknown objective")
    draft = {"objective": b.objective, "constraints": b.constraints,
             "brief": brief.extract(b.objective, b.constraints)}
    org = brief.load_org()
    org["draft"] = draft
    brief.save_org(org)
    return draft


class Confirm(BaseModel):
    brief: dict
    answers: str = ""


@app.post("/api/brief/confirm")
def confirm_brief(c: Confirm):
    global con
    org = brief.load_org()
    d = org.get("draft") or {}
    if not d:
        raise HTTPException(400, "make a brief first")
    b = {**c.brief, "client_answers": c.answers} if c.answers else c.brief
    con = db.new_campaign(con)
    _guard(evolve.seed_campaign, con, b.get("goal", ""), b.get("audience", ""),
           brief.OBJECTIVES[d["objective"]], b, d["constraints"])
    return state()


@app.post("/api/explore")
def explore(rounds: int = 3):
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "already exploring")
    db.put(con, "progress", {"done": 0, "total": rounds, "error": None})

    def work():
        try:
            for i in range(rounds):
                evolve.run_generation(con)
                db.put(con, "progress", {"done": i + 1, "total": rounds, "error": None})
        except Exception as e:  # surface to the UI instead of dying silently in a thread
            db.put(con, "progress", {"done": 0, "total": rounds, "error": str(e)[:300]})
        finally:
            busy.release()

    threading.Thread(target=work, daemon=True).start()
    return {"started": rounds}


class Approval(BaseModel):
    status: str  # approved | rejected | ""


@app.post("/api/ads/{ad_id}/approval")
def approve(ad_id: str, a: Approval):
    ap = db.get(con, "approvals", {})
    if a.status:
        ap[ad_id] = a.status
    else:
        ap.pop(ad_id, None)
    db.put(con, "approvals", ap)
    return ap


@app.get("/api/launch.csv")
def launch_csv():
    """Approved ads only: the results sheet a person fills after posting."""
    ids = [k for k, v in db.get(con, "approvals", {}).items() if v == "approved"]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(RESULT_COLS)
    for i in ids:
        a = con.execute("SELECT id, content FROM ads WHERE id=?", (i,)).fetchone()
        if a:
            c = json.loads(a["content"])
            w.writerow([a["id"], c.get("platform", ""), c.get("headline", "")])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=markstrap-results.csv"})


@app.post("/api/next")
def propose_next():
    ads = [db.row(r) for r in con.execute("SELECT * FROM ads WHERE real_score IS NOT NULL")]
    if not ads:
        raise HTTPException(400, "import real results first")
    ins = brief.next_experiment(db.get(con, "campaign"), ads)
    camp = db.get(con, "campaign")
    camp.setdefault("brief", {})["current_experiment"] = ins.get("next")  # makers see the hypothesis from the next round on
    db.put(con, "campaign", camp)
    hist = db.get(con, "insights", [])
    hist.insert(0, {**ins, "term": evolve.term_no(con)})
    db.put(con, "insights", hist)
    return ins


@app.post("/api/ads/{ad_id}/render")
def render_ad(ad_id: str):
    """Render one approved concept as an image ad."""
    if db.get(con, "approvals", {}).get(ad_id) != "approved":
        raise HTTPException(400, "approve the concept before rendering it")
    ad = db.row(con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone())
    camp = db.get(con, "campaign") or {}
    try:
        render.render(ad_id, ad["content"], camp.get("brief", {}), camp.get("constraints", {}))
    except Exception as e:  # provider quota or outage: tell the user, don't 500
        raise HTTPException(502, f"image generation failed: {e}")
    return {"url": f"/renders/{ad_id}.png"}


@app.get("/renders/{ad_id}.png")
def rendered(ad_id: str):
    path = render.OUT / f"{Path(ad_id).name}.png"
    if not path.exists():
        raise HTTPException(404, "not rendered yet")
    return FileResponse(path)


# ---------- Reel Director: approved concept -> storyboard -> produce -> preview -> export ----------

def _reel(rid):
    try:
        return reel.view(con, rid)
    except KeyError:
        raise HTTPException(404, "no such reel")


def _reel_bg(rid, fn):
    """Long work runs in a thread; status, stage and errors are stored on the reel and polled by the UI."""
    _reel(rid)
    if not reel.claim(rid):
        raise HTTPException(409, "this reel is already working")

    path = con.execute("PRAGMA database_list").fetchone()[2]

    def work():
        own = db.connect(path)  # its own connection: the UI polls the shared one while this writes
        try:
            fn(own, rid)
        except Exception:  # recorded on the reel by the stage that failed; logged too in case recording failed
            traceback.print_exc()
        finally:
            reel.release(rid)
            own.close()
    threading.Thread(target=work, daemon=True).start()
    return _reel(rid)


def _idle(rid):
    if rid in reel._running:
        raise HTTPException(409, "wait for the current run to finish")


@app.post("/api/ads/{ad_id}/reel")
def create_reel(ad_id: str):
    ad = con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad:
        raise HTTPException(404, "no such concept")
    rid = reel.create(con, ad_id, reel.prefill(db.row(ad), db.get(con, "campaign") or {}))
    return _reel(rid)


@app.get("/api/reels/{rid}")
def get_reel(rid: str):
    return _reel(rid)


@app.patch("/api/reels/{rid}/brief")
def edit_reel_brief(rid: str, fields: dict):
    _idle(rid)
    b = _reel(rid)["brief"]
    b.update({k: v for k, v in fields.items() if k in b or k in ("voice", "language")})  # only known brief fields
    try:
        b["durationSeconds"] = float(b["durationSeconds"])
    except (TypeError, ValueError):
        raise HTTPException(400, "duration must be a number of seconds")
    if not 6 <= b["durationSeconds"] <= 90:
        raise HTTPException(400, "duration must be 6-90 seconds")
    if b.get("platform") not in reel.PLATFORMS.values():
        raise HTTPException(400, f"platform must be one of {sorted(reel.PLATFORMS.values())}")
    if isinstance(b.get("colors"), str):
        b["colors"] = [c for c in b["colors"].replace(",", " ").split() if c.startswith("#")]
    reel.save(con, rid, brief=b)
    return _reel(rid)


@app.post("/api/reels/{rid}/assets")
async def add_reel_asset(rid: str, file: UploadFile, role: str = Form("product"), note: str = Form("")):
    _reel(rid)
    try:
        reel.add_asset(con, rid, role, file.filename or "file", await file.read(), note)
    except Exception as e:  # bad type, too big, not really an image
        raise HTTPException(400, f"could not add that file: {e}")
    return _reel(rid)


@app.post("/api/reels/{rid}/storyboard")
def make_storyboard(rid: str):
    return _reel_bg(rid, reel.storyboard)


@app.put("/api/reels/{rid}/scenes/{sid}")
def edit_scene(rid: str, sid: str, fields: dict):
    _idle(rid)
    try:
        reel.update_scene(con, rid, sid, fields)
    except KeyError:
        raise HTTPException(404, "no such scene")
    except (ValueError, TypeError) as e:  # pydantic ValidationError is a ValueError
        raise HTTPException(400, f"scene not saved: {str(e)[:300]}")
    return _reel(rid)


@app.post("/api/reels/{rid}/produce")
def produce_reel(rid: str):
    if not _reel(rid).get("spec"):
        raise HTTPException(400, "make a storyboard first")
    return _reel_bg(rid, reel.produce)


@app.post("/api/reels/{rid}/scenes/{sid}/regenerate")
def regenerate_scene(rid: str, sid: str):
    """New take of one scene, then re-assemble: other scenes are reused (their hashes are unchanged)."""
    _idle(rid)
    try:
        reel.regenerate(con, rid, sid)
    except KeyError:
        raise HTTPException(404, "no such scene")
    return _reel_bg(rid, reel.produce)


@app.post("/api/reels/{rid}/scenes/{sid}/replace")
async def replace_scene(rid: str, sid: str, file: UploadFile):
    _idle(rid)
    if sid not in reel.scene_state(con, rid):
        raise HTTPException(404, "no such scene")
    try:
        a = reel.add_asset(con, rid, "product", file.filename or "file", await file.read(), f"replacement for {sid}")
    except Exception as e:
        raise HTTPException(400, f"could not add that file: {e}")
    if a["kind"] not in ("image", "video"):
        raise HTTPException(400, "replace a scene with an image or a video")
    reel.replace(con, rid, sid, a["id"])
    return _reel_bg(rid, reel.produce)


@app.post("/api/reels/{rid}/export")
def export_reel(rid: str):
    if not (_reel(rid).get("renders") or {}).get("preview"):
        raise HTTPException(400, "produce a preview first")
    return _reel_bg(rid, reel.export)


@app.get("/reels/{rid}/{name}")
def reel_file(rid: str, name: str):
    """preview.mp4 / final.mp4, an uploaded asset by id, or a scene's current visual by scene id."""
    r = _reel(rid)
    name = Path(name).name
    if name in ("preview.mp4", "final.mp4"):
        path = reel.folder(rid) / name
    else:
        a = next((a for a in r["assets"] if a["id"] == name), None)
        s = next((s for s in r["scenes"] if s["id"] == name), None)
        path = Path(a["path"]) if a else Path(((s or {}).get("state") or {}).get("asset", {}).get("path") or "")
    if not path.is_file():
        raise HTTPException(404, "not made yet")
    dl = name == "final.mp4"
    return FileResponse(path, filename=f"{reel.safe_name(r['spec']['title'] if r.get('spec') else rid)}.mp4" if dl else None)
