"""Shared state for the HTTP layer: the agency store, each campaign's engine connection, and the run lock."""
import threading

from fastapi import HTTPException

from . import agency, db, reel

A = None
busy = threading.Lock()  # one exploration or seeding at a time across all campaigns
running = {"cid": None}
_opened: set[str] = set()


def init(path=None):
    """(Re)open the agency store; runs the one-time move from the single-campaign version."""
    global A
    agency.close_all()
    _opened.clear()
    if A is not None:
        A.close()
    A = agency.connect(path)
    agency.migrate(A)
    return A


def campaign(cid) -> dict:
    try:
        return agency.campaign(A, cid)
    except KeyError:
        raise HTTPException(404, "no such campaign")


def con(cid):
    campaign(cid)
    c = agency.engine_con(A, cid)
    if cid not in _opened:  # a restart interrupted any Reel that was working
        reel.interrupted(c)
        _opened.add(cid)
    return c


def nf(fn, *a, what="item", **k):
    try:
        return fn(*a, **k)
    except KeyError:
        raise HTTPException(404, f"no such {what}")
    except ValueError as e:
        raise HTTPException(400, str(e))


def is_busy(cid) -> bool:
    return busy.locked() and running["cid"] == cid


def guard(cid, fn, *a):
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "MarkStrap is already working on a campaign; try again when it finishes")
    running["cid"] = cid
    try:
        return fn(*a)
    finally:
        running["cid"] = None
        busy.release()


# ---------- campaign stage, for Home and the campaign header ----------

STAGES = ["Setting up", "Brief to confirm", "Generating concepts", "Concepts to review", "Preparing assets",
          "Ready to launch", "Waiting for results", "Results in", "Next experiment ready"]


def stage(c: dict) -> dict:
    """Where a campaign is, and what (if anything) needs the user."""
    cid = c["id"]
    e = agency.engine_con(A, cid)
    approvals = db.get(e, "approvals", {})
    approved = [k for k, v in approvals.items() if v == "approved"]
    progress = db.get(e, "progress", {}) or {}
    has_real = e.execute("SELECT COUNT(*) FROM ads WHERE real_score IS NOT NULL").fetchone()[0]
    reels = [dict(r) for r in e.execute("SELECT id, ad_id, status, critic FROM reels")]
    reel_ok = db.get(e, "reel_approvals", {})
    insights = db.get(e, "insights", [])
    n_ads = e.execute("SELECT COUNT(*) FROM ads").fetchone()[0]

    def out(i, todo=None, where="brief"):
        return {"stage": STAGES[i], "index": i, "todo": todo, "where": where}
    if c["brief_status"] == "none":
        return out(0, "Prepare the campaign brief", "brief")
    if c["brief_status"] == "draft":
        return out(1, "Review and confirm the brief", "brief")
    if is_busy(cid):
        return out(2, None, "concepts")
    if progress.get("error"):
        return out(2, "Concept generation stopped; try again", "concepts")
    if not n_ads:
        return out(2, "Generate concepts", "concepts")
    if insights and has_real:
        return out(8, None, "next")
    if has_real:
        return out(7, "See what really happened and plan the next experiment", "results")
    if c["published_at"]:
        return out(6, "Add the real results", "results")
    if not approved:
        return out(3, "Review and approve concepts", "concepts")
    if any(not reel_ok.get(r["id"]) for r in reels):
        return out(4, "Finish and approve the Reel", "assets")
    return out(5, "Publish the approved concepts, then mark them published", "launch")


def home() -> dict:
    orgs = agency.list_orgs(A)
    camps = [c for c in agency.campaigns(A) if c["org_id"] in {o["id"] for o in orgs}]
    names = {o["id"]: o["name"] for o in orgs}
    attention, rows = [], []
    for o in orgs:
        pending = A.execute("SELECT COUNT(*) FROM findings WHERE org_id=? AND status='pending' AND section<>'missing'",
                            (o["id"],)).fetchone()[0]
        drafts = A.execute("SELECT COUNT(*) FROM products WHERE org_id=? AND status='draft'", (o["id"],)).fetchone()[0]
        o["pending_findings"], o["draft_products"] = pending, drafts
        o["products"] = A.execute("SELECT COUNT(*) FROM products WHERE org_id=? AND status='approved'",
                                  (o["id"],)).fetchone()[0]
        o["campaigns"] = sum(1 for c in camps if c["org_id"] == o["id"])
        if pending:
            attention.append({"kind": "profile", "text": f"{pending} research finding{'s' if pending > 1 else ''} to review",
                              "org": o["name"], "href": f"#/orgs/{o['id']}/research"})
        if drafts:
            attention.append({"kind": "products", "text": f"{drafts} product{'s' if drafts > 1 else ''} found by research to approve",
                              "org": o["name"], "href": f"#/orgs/{o['id']}/products"})
    for c in camps:
        st = stage(c)
        product = agency.product(A, c["product_id"])["name"] if c["product_id"] else None
        rows.append({"id": c["id"], "name": c["name"], "org": names.get(c["org_id"]), "org_id": c["org_id"],
                     "product": product, "updated": c["updated"], **st})
        if st["todo"]:
            attention.append({"kind": "campaign", "text": st["todo"], "org": names.get(c["org_id"]),
                              "campaign": c["name"], "stage": st["stage"],
                              "href": f"#/campaigns/{c['id']}/{st['where']}"})
    groups = {s: [r for r in rows if r["stage"] == s] for s in STAGES}
    return {"orgs": orgs, "campaigns": rows, "attention": attention,
            "briefs": groups["Brief to confirm"], "concepts": groups["Concepts to review"],
            "assets": groups["Preparing assets"], "waiting": groups["Waiting for results"],
            "done": groups["Next experiment ready"] + groups["Results in"]}
