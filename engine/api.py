"""HTTP API + dashboard. Run: uvicorn engine.api:app"""
import csv
import io
import json
import threading
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import brief, db, evolve, render

app = FastAPI(title="MarkStrap Campaign Engine")
con = db.connect()
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
