"""One campaign: brief, concepts, review, assets and Reels, launch, real results and the next experiment.

Every route is scoped to /api/campaigns/{cid}; the campaign's own engine database does the work.
"""
import csv
import io
import json
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .. import agency, brief, concepts, db, evolve, hub, reality, reel, render
from .. import reel_providers as P

r = APIRouter(prefix="/api/campaigns/{cid}")
files = APIRouter()

RESULT_COLS = ["ad_id", "platform", "headline", "audience", "impressions", "reach", "clicks", "signups", "purchases",
               "saves", "shares", "comments", "replies", "reposts", "watch_time", "avg_view_duration",
               "completion_rate", "rewatches", "cost", "revenue", "hours_live", "engagement_first_hours"]
NUMERIC = [c for c in RESULT_COLS if c not in ("ad_id", "platform", "headline", "audience")]
DECISIONS = ("approved", "rejected", "saved", "revise", "")


class FieldsIn(BaseModel):
    name: str | None = None
    fields: dict = {}


class BriefEdit(BaseModel):
    brief: dict


class Confirm(BaseModel):
    brief: dict
    answers: str = ""


class Decision(BaseModel):
    status: str
    feedback: str = ""


class Revise(BaseModel):
    feedback: str


class Combine(BaseModel):
    parts: dict


class Rows(BaseModel):
    rows: list[dict]


class Published(BaseModel):
    published: bool = True


class ReelApproval(BaseModel):
    approved: bool = True


class Dial(BaseModel):
    name: str
    value: float


def _ads(con, where="1=1", args=()):
    return [db.row(x) for x in con.execute(f"SELECT * FROM ads WHERE {where}", args)]


def _ad(con, ad_id):
    x = con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not x:
        raise HTTPException(404, "no such concept")
    return db.row(x)


def _confidential(c):
    a = hub.A
    return [s["text"] for s in agency.sources(a, c["org_id"]) if s["confidential"]]


# ---------- the campaign ----------

@r.get("")
def view(cid: str):
    c = hub.campaign(cid)
    con = hub.con(cid)
    o = agency.get_org(hub.A, c["org_id"])
    p = agency.product(hub.A, c["product_id"]) if c["product_id"] else None
    approvals = db.get(con, "approvals", {})
    return {**c, "org": {"id": o["id"], "name": o["name"]}, "product": p and {"id": p["id"], "name": p["name"]},
            **hub.stage(c), "busy": hub.is_busy(cid), "progress": db.get(con, "progress", {}),
            "term": evolve.term_no(con), "concept_count": con.execute("SELECT COUNT(*) FROM ads").fetchone()[0],
            "people": len(db.get(con, "personas", []) or []), "approvals": approvals,
            "approved": [k for k, v in approvals.items() if v == "approved"],
            "reels": [dict(x) for x in con.execute("SELECT id, ad_id, status FROM reels ORDER BY updated DESC")],
            "reel_approvals": db.get(con, "reel_approvals", {}), "insights": db.get(con, "insights", []),
            "metrics": reality.metrics_for(c["fields"].get("objective")), "objectives": list(brief.OBJECTIVES),
            "fields_list": agency.CAMPAIGN_FIELDS, "results_count": con.execute(
                "SELECT COUNT(*) FROM ads WHERE real_score IS NOT NULL").fetchone()[0]}


@r.patch("")
def edit(cid: str, f: FieldsIn):
    c = hub.campaign(cid)
    if f.fields.get("objective") and f.fields["objective"] not in brief.OBJECTIVES:
        raise HTTPException(400, "unknown objective")
    changed = {k: "Set for this campaign" for k, v in f.fields.items() if v != c["fields"].get(k)}
    agency.update_campaign(hub.A, cid, **({"name": f.name} if f.name else {}), fields=f.fields, field_sources=changed)
    return view(cid)


# ---------- brief ----------

def _materials(c) -> str:
    out = []
    for s in agency.sources(hub.A, c["org_id"], origin="provided"):
        if s["product_id"] and s["product_id"] != c["product_id"]:
            continue
        tag = " [confidential: use to understand, never quote]" if s["confidential"] else ""
        out.append(f"### {s['name']}{tag}\n{s['text']}")
    return "\n\n".join(out)


@r.post("/brief")
def make_brief(cid: str):
    c = hub.campaign(cid)
    if c["fields"].get("objective") not in brief.OBJECTIVES:
        raise HTTPException(400, "choose the campaign objective first")
    p = agency.product(hub.A, c["product_id"]) if c["product_id"] else None
    b = brief.extract(agency.profile_text(agency.profile(hub.A, c["org_id"])), agency.product_text(p), c["fields"],
                      _materials(c))
    b["objective"] = c["fields"]["objective"]
    agency.update_campaign(hub.A, cid, brief=b, brief_status="draft")
    return view(cid)


@r.put("/brief")
def edit_brief(cid: str, e: BriefEdit):
    c = hub.campaign(cid)
    if c["brief_status"] == "none":
        raise HTTPException(400, "prepare the brief first")
    agency.update_campaign(hub.A, cid, brief={**c["brief"], **e.brief}, brief_status="draft")
    return view(cid)


def _seed(cid, b, c):
    con = hub.con(cid)
    if db.get(con, "campaign"):  # re-confirming starts the concepts over; lessons and identity stay
        con = agency.reset_engine(hub.A, cid)
    obj = c["fields"]["objective"]
    evolve.seed_campaign(con, c["fields"].get("goal") or b.get("success_metric", ""), b.get("audience", ""),
                         brief.OBJECTIVES[obj], brief.engine_brief(b, c["fields"]), brief.constraints(c["fields"], b))


@r.post("/brief/confirm")
def confirm(cid: str, body: Confirm):
    c = hub.campaign(cid)
    if c["brief_status"] == "none":
        raise HTTPException(400, "prepare the brief first")
    b = {**c["brief"], **body.brief}
    if body.answers.strip():
        b["client_answers"] = body.answers.strip()
        b["missing"] = []
    hub.guard(cid, _seed, cid, b, c)
    agency.update_campaign(hub.A, cid, brief=b, brief_status="confirmed")
    return view(cid)


# ---------- concepts ----------

@r.post("/explore")
def explore(cid: str, rounds: int = 3):
    c = hub.campaign(cid)
    if c["brief_status"] != "confirmed":
        raise HTTPException(400, "confirm the brief before generating concepts")
    con = hub.con(cid)
    if not hub.busy.acquire(blocking=False):
        raise HTTPException(409, "MarkStrap is already working on a campaign; try again when it finishes")
    hub.running["cid"] = cid
    db.put(con, "progress", {"done": 0, "total": rounds, "error": None, "step": "Drafting concepts"})
    conf = _confidential(c)

    def work():
        try:
            for i in range(rounds):
                evolve.run_generation(con)
                db.put(con, "progress", {"done": i + 1, "total": rounds, "error": None,
                                         "step": "Drafting and testing concepts"})
            db.put(con, "progress", {"done": rounds, "total": rounds, "error": None, "step": "Writing the reviews"})
            for g in concepts.distinct(_ads(con), db.get(con, "approvals", {})):
                try:
                    concepts.review(con, g["lead"], conf)
                except Exception:  # a review can be retried from the concept card
                    pass
            db.put(con, "progress", {"done": rounds, "total": rounds, "error": None, "step": ""})
        except Exception as e:  # shown in the UI instead of dying silently in a thread
            db.put(con, "progress", {"done": 0, "total": rounds, "error": str(e)[:300]})
        finally:
            hub.running["cid"] = None
            hub.busy.release()

    threading.Thread(target=work, daemon=True).start()
    return {"started": rounds}


def _concept(con, ad, people, d, reviews, decisions, reels):
    dem = (con.execute("SELECT n FROM demotions WHERE style=?", (ad["style"],)).fetchone() or [0])[0]
    rv = reviews.get(ad["id"])
    if rv and rv.get("key") != concepts._key(ad):
        rv = None
    c = ad["content"]
    return {"id": ad["id"], "content": c, "approach": concepts.approach_label(ad["style"]),
            "decision": decisions.get(ad["id"], ""), "score": concepts.explain(ad, d, dem),
            "audience": concepts.audience_breakdown(ad, people), "review": rv,
            "reasons": {p: concepts.part_reasons(ad, p) for p in ("copy", "visual", "posting")},
            "recommended": concepts.recommended(ad, rv), "shortlisted": bool(ad["shortlisted"]),
            "real_score": ad["real_score"], "revised_from": c.get("revised_from"),
            "combined_from": c.get("combined_from"), "reel": next((x for x in reels if x["ad_id"] == ad["id"]), None),
            "image": (render.OUT / f"{ad['id']}.png").exists()}


@r.get("/concepts")
def list_concepts(cid: str):
    con = hub.con(cid)
    people = db.get(con, "personas", []) or []
    d, reviews, decisions = evolve.dials(con), db.get(con, "reviews", {}), db.get(con, "approvals", {})
    reels = [dict(x) for x in con.execute("SELECT id, ad_id, status FROM reels")]
    groups = concepts.distinct(_ads(con), decisions)
    return {"concepts": [{**_concept(con, g["lead"], people, d, reviews, decisions, reels),
                          "variations": [{"id": v["id"], "headline": v["content"].get("headline"),
                                          "score": round(v["sim_score"] or 0, 3), "decision": decisions.get(v["id"], "")}
                                         for v in g["variations"]]} for g in groups],
            "people": len(people), "limits": concepts.LIMITS, "busy": hub.is_busy(cid),
            "progress": db.get(con, "progress", {}), "parts": list(concepts.COMBINE_PARTS)}


@r.get("/concepts/{ad_id}")
def one_concept(cid: str, ad_id: str):
    con = hub.con(cid)
    reels = [dict(x) for x in con.execute("SELECT id, ad_id, status FROM reels")]
    return _concept(con, _ad(con, ad_id), db.get(con, "personas", []) or [], evolve.dials(con),
                    db.get(con, "reviews", {}), db.get(con, "approvals", {}), reels)


@r.post("/concepts/{ad_id}/review")
def review(cid: str, ad_id: str, force: bool = False):
    c, con = hub.campaign(cid), hub.con(cid)
    ad = _ad(con, ad_id)
    try:
        concepts.review(con, ad, _confidential(c), force)
    except Exception as e:  # model outage: say so, keep the page usable
        raise HTTPException(502, f"the review could not be written: {str(e)[:200]}")
    return one_concept(cid, ad_id)


@r.post("/concepts/{ad_id}/decision")
def decide(cid: str, ad_id: str, d: Decision):
    con = hub.con(cid)
    _ad(con, ad_id)
    if d.status not in DECISIONS:
        raise HTTPException(400, f"decision must be one of {DECISIONS}")
    ap = db.get(con, "approvals", {})
    if d.status:
        ap[ad_id] = d.status
    else:
        ap.pop(ad_id, None)
    db.put(con, "approvals", ap)
    if d.feedback.strip():
        fb = db.get(con, "feedback", {})
        fb.setdefault(ad_id, []).append(d.feedback.strip())
        db.put(con, "feedback", fb)
    return {"approvals": ap, "feedback": db.get(con, "feedback", {}).get(ad_id, [])}


@r.post("/concepts/{ad_id}/revise")
def revise(cid: str, ad_id: str, body: Revise):
    con = hub.con(cid)
    _ad(con, ad_id)
    if not body.feedback.strip():
        raise HTTPException(400, "say what should change")
    new = hub.guard(cid, concepts.revise, con, ad_id, body.feedback.strip())
    ap = db.get(con, "approvals", {})
    ap[ad_id] = ap.get(ad_id) if ap.get(ad_id) == "approved" else "revise"
    db.put(con, "approvals", ap)
    return one_concept(cid, new)


@r.post("/concepts/combine")
def combine(cid: str, body: Combine):
    con = hub.con(cid)
    for aid in body.parts.values():
        _ad(con, aid)
    try:
        new = hub.guard(cid, concepts.combine, con, body.parts)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return one_concept(cid, new)


@r.get("/feedback")
def feedback(cid: str):
    return db.get(hub.con(cid), "feedback", {})


# ---------- assets ----------

@r.post("/concepts/{ad_id}/image")
def image(cid: str, ad_id: str):
    con = hub.con(cid)
    if db.get(con, "approvals", {}).get(ad_id) != "approved":
        raise HTTPException(400, "approve the concept before making its image")
    ad = _ad(con, ad_id)
    camp = db.get(con, "campaign") or {}
    try:
        render.render(ad_id, ad["content"], camp.get("brief", {}), camp.get("constraints", {}))
    except Exception as e:  # provider quota or outage: tell the user, don't 500
        raise HTTPException(502, f"image generation failed: {e}")
    return {"url": f"/renders/{ad_id}.png"}


# ---------- Reels ----------

def _reel(con, rid):
    try:
        return reel.view(con, rid)
    except KeyError:
        raise HTTPException(404, "no such reel")


def _reel_out(cid, con, rid):
    v = _reel(con, rid)
    v["approved"] = bool(db.get(con, "reel_approvals", {}).get(rid))
    v["capabilities"] = capabilities()
    return v


def _reel_bg(cid, rid, fn):
    """Long work runs in a thread with its own connection; the UI polls the shared one."""
    con = hub.con(cid)
    _reel(con, rid)
    if not reel.claim(rid):
        raise HTTPException(409, "this reel is already working")
    path = agency.engine_path(hub.A, cid)
    ok = db.get(con, "reel_approvals", {})
    if ok.pop(rid, None):  # any change to the cut needs a fresh final approval
        db.put(con, "reel_approvals", ok)

    def work():
        own = db.connect(path)
        try:
            fn(own, rid)
        except Exception:  # recorded on the reel by the stage that failed
            pass
        finally:
            reel.release(rid)
            own.close()
    threading.Thread(target=work, daemon=True).start()
    return _reel_out(cid, con, rid)


def _idle(rid):
    if rid in reel._running:
        raise HTTPException(409, "wait for the current run to finish")


@r.post("/concepts/{ad_id}/reel")
def create_reel(cid: str, ad_id: str):
    con = hub.con(cid)
    ad = _ad(con, ad_id)
    if db.get(con, "approvals", {}).get(ad_id) != "approved":
        raise HTTPException(400, "approve the concept before making a Reel")
    existing = con.execute("SELECT id FROM reels WHERE ad_id=?", (ad_id,)).fetchone()
    if existing:
        return _reel_out(cid, con, existing["id"])
    rid = reel.create(con, ad_id, reel.prefill(ad, db.get(con, "campaign") or {}))
    return _reel_out(cid, con, rid)


@r.get("/reels/{rid}")
def get_reel(cid: str, rid: str):
    return _reel_out(cid, hub.con(cid), rid)


@r.patch("/reels/{rid}/brief")
def edit_reel_brief(cid: str, rid: str, fields: dict):
    con = hub.con(cid)
    _idle(rid)
    b = _reel(con, rid)["brief"]
    b.update({k: v for k, v in fields.items() if k in b})  # only known brief fields
    try:
        b["durationSeconds"] = float(b["durationSeconds"])
    except (TypeError, ValueError):
        raise HTTPException(400, "duration must be a number of seconds")
    if not 6 <= b["durationSeconds"] <= 90:
        raise HTTPException(400, "duration must be 6-90 seconds")
    if b.get("platform") not in reel.PLATFORMS.values():
        raise HTTPException(400, f"platform must be one of {sorted(reel.PLATFORMS.values())}")
    if b.get("voice") not in ("on", "off") or b.get("captions") not in ("on", "off"):
        raise HTTPException(400, "voice and captions are on or off")
    if isinstance(b.get("colors"), str):
        b["colors"] = [c for c in b["colors"].replace(",", " ").split() if c.startswith("#")]
    reel.save(con, rid, brief=b)
    return _reel_out(cid, con, rid)


@r.post("/reels/{rid}/assets")
async def add_reel_asset(cid: str, rid: str, file: UploadFile, role: str = Form("product"), note: str = Form("")):
    con = hub.con(cid)
    _reel(con, rid)
    try:
        reel.add_asset(con, rid, role, file.filename or "file", await file.read(), note)
    except Exception as e:  # bad type, too big, not really an image
        raise HTTPException(400, f"could not add that file: {e}")
    return _reel_out(cid, con, rid)


@r.post("/reels/{rid}/library/{sid}")
def add_reel_from_library(cid: str, rid: str, sid: str, role: str = "product", note: str = ""):
    """Reuse an image, logo or video from the organization's knowledge base."""
    con = hub.con(cid)
    _reel(con, rid)
    s = hub.nf(agency.source, hub.A, sid, what="source")
    if s["org_id"] != hub.campaign(cid)["org_id"] or not s["path"] or not Path(s["path"]).is_file():
        raise HTTPException(400, "that file is not in this organization's knowledge base")
    try:
        reel.add_asset(con, rid, role, Path(s["path"]).name, Path(s["path"]).read_bytes(), note)
    except Exception as e:
        raise HTTPException(400, f"could not add that file: {e}")
    return _reel_out(cid, con, rid)


@r.post("/reels/{rid}/storyboard")
def make_storyboard(cid: str, rid: str):
    return _reel_bg(cid, rid, reel.storyboard)


@r.put("/reels/{rid}/scenes/{sid}")
def edit_scene(cid: str, rid: str, sid: str, fields: dict):
    con = hub.con(cid)
    _idle(rid)
    try:
        reel.update_scene(con, rid, sid, fields)
    except KeyError:
        raise HTTPException(404, "no such scene")
    except (ValueError, TypeError) as e:  # pydantic ValidationError is a ValueError
        raise HTTPException(400, f"scene not saved: {str(e)[:300]}")
    return _reel_out(cid, con, rid)


@r.post("/reels/{rid}/produce")
def produce_reel(cid: str, rid: str):
    if not _reel(hub.con(cid), rid).get("spec"):
        raise HTTPException(400, "make a storyboard first")
    return _reel_bg(cid, rid, reel.produce)


@r.post("/reels/{rid}/scenes/{sid}/regenerate")
def regenerate_scene(cid: str, rid: str, sid: str):
    con = hub.con(cid)
    _idle(rid)
    try:
        reel.regenerate(con, rid, sid)
    except KeyError:
        raise HTTPException(404, "no such scene")
    return _reel_bg(cid, rid, reel.produce)


@r.post("/reels/{rid}/scenes/{sid}/replace")
async def replace_scene(cid: str, rid: str, sid: str, file: UploadFile):
    con = hub.con(cid)
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
    return _reel_bg(cid, rid, reel.produce)


@r.post("/reels/{rid}/export")
def export_reel(cid: str, rid: str):
    if not (_reel(hub.con(cid), rid).get("renders") or {}).get("preview"):
        raise HTTPException(400, "produce a preview first")
    return _reel_bg(cid, rid, reel.export)


@r.post("/reels/{rid}/approve")
def approve_reel(cid: str, rid: str, a: ReelApproval):
    con = hub.con(cid)
    v = _reel(con, rid)
    if a.approved and not (v.get("renders") or {}).get("final"):
        raise HTTPException(400, "export the final MP4 before approving it")
    ok = db.get(con, "reel_approvals", {})
    if a.approved:
        ok[rid] = time.time()
    else:
        ok.pop(rid, None)
    db.put(con, "reel_approvals", ok)
    return _reel_out(cid, con, rid)


def capabilities() -> dict:
    """What production can really do right now, in plain words, shown before anything is generated."""
    av = P.available()
    notes = []
    if not av["image"]:
        notes.append("Generated images aren't available yet: scenes use your uploaded photos and motion graphics.")
    if not av["video"]:
        notes.append("Generated video clips aren't available: use your own footage or animated stills.")
    if av["tts"] == "silent":
        notes.append("The voice model isn't installed: Reels render with a silent voice track and captions.")
    if av["text"] == "mock":
        notes.append("No writing model is connected: the storyboard comes from a template you can edit.")
    notes.append("Music follows your direction only when you upload a track; otherwise a simple generated bed plays.")
    return {"providers": av, "notes": notes}


# ---------- launch ----------

@r.get("/launch")
def launch(cid: str):
    c, con = hub.campaign(cid), hub.con(cid)
    approvals, reviews = db.get(con, "approvals", {}), db.get(con, "reviews", {})
    ok = db.get(con, "reel_approvals", {})
    eng = db.get(con, "campaign") or {}
    items = []
    for aid in [k for k, v in approvals.items() if v == "approved"]:
        x = con.execute("SELECT * FROM ads WHERE id=?", (aid,)).fetchone()
        if not x:
            continue
        ad = db.row(x)
        cc = ad["content"]
        rl = con.execute("SELECT id, status, renders FROM reels WHERE ad_id=?", (aid,)).fetchone()
        rv = reviews.get(aid) or {}
        items.append({
            "id": aid, "name": cc.get("concept_name") or cc.get("headline"), "headline": cc.get("headline"),
            "caption": cc.get("body"), "platform": cc.get("platform"), "format": cc.get("format"),
            "post_time": cc.get("post_time"), "visual": cc.get("visual"),
            "image": (render.OUT / f"{aid}.png").exists(),
            "reel": rl and {"id": rl["id"], "status": rl["status"], "approved": bool(ok.get(rl["id"])),
                            "final": bool((json.loads(rl["renders"] or "{}")).get("final"))},
            "check_before_posting": rv.get("human_review", []),
        })
    b = c["brief"]
    return {"items": items, "destination": (eng.get("brief") or {}).get("destination") or b.get("action", ""),
            "requirements": {"Restrictions": b.get("restrictions", ""), "Brand": b.get("brand_requirements", ""),
                             "Dates": " → ".join(x for x in (c["fields"].get("start"), c["fields"].get("end")) if x),
                             "Budget": c["fields"].get("budget", "")},
            "measure": {"objective": c["fields"].get("objective"), "metrics": reality.metrics_for(
                c["fields"].get("objective")), "success": b.get("success_metric", "")},
            "published_at": c["published_at"]}


@r.get("/launch.csv")
def launch_csv(cid: str):
    """Approved concepts only: the results sheet a person fills after posting."""
    con = hub.con(cid)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(RESULT_COLS)
    for i in [k for k, v in db.get(con, "approvals", {}).items() if v == "approved"]:
        a = con.execute("SELECT id, content FROM ads WHERE id=?", (i,)).fetchone()
        if a:
            cc = json.loads(a["content"])
            w.writerow([a["id"], cc.get("platform", ""), cc.get("headline", "")])
    name = agency.campaign(hub.A, cid)["name"]
    return Response(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename={reel.safe_name(name)}-results.csv"})


@r.post("/published")
def published(cid: str, p: Published):
    """The user says they published it themselves. MarkStrap never posts anything."""
    hub.campaign(cid)
    agency.update_campaign(hub.A, cid, published_at=time.time() if p.published else None)
    return view(cid)


# ---------- real results ----------

def _import(cid, rows):
    con = hub.con(cid)
    clean = []
    for x in rows:
        row = {k: (str(v).strip() if v is not None else "") for k, v in x.items() if k in RESULT_COLS}
        for k in NUMERIC:
            if row.get(k):
                try:
                    if float(row[k].replace(",", "")) < 0:
                        raise ValueError
                    row[k] = str(float(row[k].replace(",", "")))
                except ValueError:
                    raise HTTPException(400, f"{k} must be a number of zero or more (got '{row[k]}')")
        if row.get("ad_id") and any(row.get(k) for k in NUMERIC):
            clean.append(row)
    if not clean:
        raise HTTPException(400, "enter at least one number for one concept")
    try:
        n = evolve.import_results(con, clean)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"could not import results: {e}")
    stored = db.get(con, "results_rows", [])
    db.put(con, "results_rows", stored + [{**x, "at": time.time()} for x in clean])
    c = hub.campaign(cid)
    if not c["published_at"]:
        agency.update_campaign(hub.A, cid, published_at=time.time())
    return {"imported": n}


@r.post("/results")
async def results_csv(cid: str, file: UploadFile):
    hub.campaign(cid)
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    return _import(cid, rows)


@r.post("/results/rows")
def results_rows(cid: str, body: Rows):
    hub.campaign(cid)
    return _import(cid, body.rows)


@r.get("/reality")
def get_reality(cid: str):
    return reality.compare(hub.con(cid))


@r.post("/next")
def next_experiment(cid: str):
    con = hub.con(cid)
    ads = _ads(con, "real_score IS NOT NULL")
    if not ads:
        raise HTTPException(400, "add real results first")
    camp = db.get(con, "campaign")
    try:
        ins = brief.next_experiment(camp, ads, reality.compare(con))
    except Exception as e:
        raise HTTPException(502, f"the recommendation could not be written: {str(e)[:200]}")
    camp.setdefault("brief", {})["current_experiment"] = ins.get("next")  # concepts follow it from the next round
    db.put(con, "campaign", camp)
    hist = db.get(con, "insights", [])
    hist.insert(0, {**ins, "term": evolve.term_no(con), "at": time.time()})
    db.put(con, "insights", hist)
    return ins


# ---------- engine console (advanced) ----------

@r.get("/engine")
def engine_state(cid: str):
    con = hub.con(cid)
    agents = [db.row(x) for x in con.execute("SELECT * FROM agents ORDER BY fitness DESC")]
    ads = [db.row(x) for x in con.execute("SELECT * FROM ads ORDER BY term DESC, sim_score DESC LIMIT 60")]
    births = {x[0]: x[1] for x in con.execute("SELECT born, COUNT(*) FROM agents WHERE born>0 GROUP BY born")}
    return {
        "campaign": db.get(con, "campaign"), "term": evolve.term_no(con), "busy": hub.is_busy(cid),
        "dials": evolve.dials(con), "pending": db.get(con, "pending", {}),
        "personas": db.get(con, "personas", []), "lessons": db.get(con, "lessons", {}),
        "agents": agents, "ads": ads, "births": births,
        "queens": [dict(q) for q in con.execute("SELECT * FROM queens")],
        "memory": [dict(m) for m in con.execute("SELECT * FROM memory ORDER BY id DESC LIMIT 20")],
        "dial_log": [dict(m) for m in con.execute("SELECT * FROM dial_log ORDER BY id DESC LIMIT 20")],
        "name": hub.campaign(cid)["name"]}


@r.post("/engine/generation")
def generation(cid: str):
    if hub.campaign(cid)["brief_status"] != "confirmed":
        raise HTTPException(400, "confirm the brief first")
    return {"term": hub.guard(cid, evolve.run_generation, hub.con(cid))}


@r.post("/engine/dial")
def dial(cid: str, d: Dial):
    con = hub.con(cid)
    try:
        evolve.set_dial(con, d.name, int(d.value) if d.value.is_integer() else d.value)
    except KeyError as e:
        raise HTTPException(400, str(e))
    return {"pending": db.get(con, "pending")}


@r.post("/engine/snapshot")
def snapshot(cid: str):
    src = Path(agency.engine_path(hub.A, cid))
    sid = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy(src, src.with_name(f"{src.stem}-snap-{sid}.db"))
    return {"id": sid}


@r.post("/engine/rollback/{sid}")
def rollback(cid: str, sid: str):
    dst = Path(agency.engine_path(hub.A, cid))
    snap = dst.with_name(f"{dst.stem}-snap-{Path(sid).name}.db")
    if not snap.exists():
        raise HTTPException(404, "no such snapshot")
    if hub.busy.locked():
        raise HTTPException(409, "wait for the current run to finish")
    shutil.copy(snap, dst)
    agency.reopen(hub.A, cid)
    return {"ok": True}


@r.post("/engine/revive/{agent_id}")
def revive(cid: str, agent_id: str):
    evolve.revive(hub.con(cid), agent_id)
    return {"ok": True}


@r.get("/engine/lineage/{agent_id}")
def lineage(cid: str, agent_id: str):
    tree = evolve.lineage(hub.con(cid), agent_id)
    if not tree:
        raise HTTPException(404, "no such agent")
    return tree


@r.get("/engine/ads.csv")
def ads_csv(cid: str):
    con = hub.con(cid)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(RESULT_COLS)
    for a in con.execute("SELECT id, content FROM ads WHERE shortlisted=1 AND real_score IS NULL"):
        cc = json.loads(a["content"])
        w.writerow([a["id"], cc.get("platform", ""), cc.get("headline", "")])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=shortlist.csv"})


# ---------- files ----------

@files.get("/campaigns/{cid}/reels/{rid}/{name}")
def reel_file(cid: str, rid: str, name: str):
    """preview.mp4 / final.mp4, an uploaded asset by id, or a scene's current visual by scene id."""
    v = _reel(hub.con(cid), rid)
    name = Path(name).name
    if name in ("preview.mp4", "final.mp4"):
        path = reel.folder(rid) / name
    else:
        a = next((a for a in v["assets"] if a["id"] == name), None)
        s = next((s for s in v["scenes"] if s["id"] == name), None)
        path = Path(a["path"]) if a else Path(((s or {}).get("state") or {}).get("asset", {}).get("path") or "")
    if not path.is_file():
        raise HTTPException(404, "not made yet")
    dl = name == "final.mp4"
    return FileResponse(path, filename=f"{reel.safe_name(v['spec']['title'] if v.get('spec') else rid)}.mp4"
                        if dl else None)


@files.get("/renders/{ad_id}.png")
def rendered(ad_id: str):
    path = render.OUT / f"{Path(ad_id).name}.png"
    if not path.exists():
        raise HTTPException(404, "not rendered yet")
    return FileResponse(path)


@files.get("/api/capabilities")
def get_capabilities():
    return capabilities()
