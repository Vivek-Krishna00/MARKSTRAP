"""The agency store: organizations, their knowledge, findings, products and campaigns.

Organization -> products -> campaigns. Each campaign keeps its own engine database (the evolution loop in
evolve.py runs unchanged inside it), so campaigns never mix. Lessons from real results travel only between
campaigns of the same organization.
"""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import db

ORG_FIELDS = ["website", "industry", "description", "market", "customers", "voice", "colours", "competitors", "notes"]
PRODUCT_FIELDS = ["description", "category", "customers", "problems", "value_proposition", "features", "benefits",
                  "proof_points", "pricing", "links", "brand_requirements", "prohibited_claims"]
CAMPAIGN_FIELDS = ["objective", "goal", "audience", "market", "platforms", "format", "offer", "destination", "start",
                   "end", "budget", "success_metric", "required_messages", "required_assets", "brand_rules",
                   "prohibited_claims", "language", "tone", "instructions"]
# Profile sections. "fact" sections are confirmed by a quote; "inference" sections are always the AI's reading.
SECTIONS = {
    "summary": ("Organization summary", "fact"),
    "customer_groups": ("Customer groups", "fact"),
    "problems": ("Problems it solves", "fact"),
    "value_propositions": ("Value propositions", "inference"),
    "differentiators": ("Differentiators", "inference"),
    "proof_points": ("Proof points", "fact"),
    "brand_personality": ("Brand personality", "inference"),
    "brand_voice": ("Brand voice", "inference"),
    "visual_identity": ("Visual identity", "fact"),
    "competitors": ("Competitors", "fact"),
    "claims": ("Important claims", "fact"),
    "claims_need_evidence": ("Claims that need evidence", "inference"),
}
LABELS = {"provided": "Provided by the organization", "research": "Found through research",
          "ai": "Suggested by AI", "unconfirmed": "Unconfirmed", "missing": "Missing"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY, name TEXT, fields TEXT, researched_at REAL, created REAL, updated REAL, archived INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, org_id TEXT, product_id TEXT, kind TEXT, origin TEXT, name TEXT, text TEXT, path TEXT,
  url TEXT, confidential INT DEFAULT 0, added REAL);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY, org_id TEXT, product_id TEXT, section TEXT, value TEXT, label TEXT, source_ids TEXT,
  evidence TEXT, status TEXT DEFAULT 'pending', edited INT DEFAULT 0, run_id TEXT, created REAL);
CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, org_id TEXT, name TEXT, fields TEXT, field_labels TEXT, status TEXT, merged_into TEXT,
  origin TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY, org_id TEXT, product_id TEXT, name TEXT, fields TEXT, field_sources TEXT, brief TEXT,
  brief_status TEXT DEFAULT 'none', published_at REAL, db_file TEXT, created REAL, updated REAL);
"""
_JSON = ("fields", "field_sources", "brief", "value", "source_ids", "field_labels")
_lock = threading.RLock()  # one connection is shared by request handlers


def path_of(path=None) -> Path:
    return Path(path or os.getenv("AGENCY_DB", "data/agency.db"))


def connect(path=None):
    p = path_of(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def campaign_dir(a) -> Path:
    return Path(a.execute("PRAGMA database_list").fetchone()[2]).parent / "campaign-data"


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in _JSON:
        if k in d:
            d[k] = json.loads(d[k]) if d[k] else ({} if k not in ("source_ids",) else [])
    return d


def _w(a, sql, args=()):
    with _lock:
        cur = a.execute(sql, args)
        a.commit()
        return cur


def _clean(fields: dict, allowed) -> dict:
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in (fields or {}).items() if k in allowed}


# ---------- organizations ----------

def create_org(a, name: str, fields: dict | None = None) -> dict:
    if not (name or "").strip():
        raise ValueError("an organization needs a name")
    oid, t = _id("org"), time.time()
    _w(a, "INSERT INTO orgs (id, name, fields, created, updated) VALUES (?,?,?,?,?)",
       (oid, name.strip(), json.dumps(_clean(fields, ORG_FIELDS)), t, t))
    return get_org(a, oid)


def get_org(a, oid) -> dict:
    o = _row(a.execute("SELECT * FROM orgs WHERE id=?", (oid,)).fetchone())
    if not o:
        raise KeyError(oid)
    return o


def list_orgs(a) -> list[dict]:
    return [_row(r) for r in a.execute("SELECT * FROM orgs WHERE archived=0 ORDER BY updated DESC")]


def update_org(a, oid, name=None, fields=None) -> dict:
    o = get_org(a, oid)
    f = {**o["fields"], **_clean(fields, ORG_FIELDS)}
    _w(a, "UPDATE orgs SET name=?, fields=?, updated=? WHERE id=?", ((name or o["name"]).strip(), json.dumps(f),
                                                                     time.time(), oid))
    return get_org(a, oid)


def archive_org(a, oid):
    get_org(a, oid)
    _w(a, "UPDATE orgs SET archived=1, updated=? WHERE id=?", (time.time(), oid))


# ---------- knowledge base ----------

def add_source(a, org_id, kind, name, text, origin="provided", product_id=None, path=None, confidential=False,
               url=None) -> dict:
    get_org(a, org_id)
    sid = _id("src")
    _w(a, "INSERT INTO sources (id, org_id, product_id, kind, origin, name, text, path, url, confidential, added)"
          " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
       (sid, org_id, product_id, kind, origin, name, text, path, url, int(confidential), time.time()))
    _touch(a, org_id)
    return source(a, sid)


def source(a, sid) -> dict:
    s = _row(a.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone())
    if not s:
        raise KeyError(sid)
    return s


def sources(a, org_id, product_id=..., origin=None) -> list[dict]:
    sql, args = "SELECT * FROM sources WHERE org_id=?", [org_id]
    if product_id is not ...:
        sql += " AND product_id IS ?"
        args.append(product_id)
    if origin:
        sql += " AND origin=?"
        args.append(origin)
    return [_row(r) for r in a.execute(sql + " ORDER BY added", args)]


def update_source(a, sid, confidential=None, product_id=...):
    s = source(a, sid)
    _w(a, "UPDATE sources SET confidential=?, product_id=? WHERE id=?",
       (int(s["confidential"] if confidential is None else confidential),
        s["product_id"] if product_id is ... else product_id, sid))
    return source(a, sid)


def remove_source(a, sid):
    s = source(a, sid)
    _w(a, "DELETE FROM sources WHERE id=?", (sid,))
    if s["path"]:
        Path(s["path"]).unlink(missing_ok=True)


def _touch(a, org_id):
    _w(a, "UPDATE orgs SET updated=? WHERE id=?", (time.time(), org_id))


# ---------- findings (research results awaiting the user's review) ----------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def quote_in(evidence: str, text: str, min_chars: int) -> bool:
    e = _norm(evidence)
    return len(e) >= min_chars and e in _norm(text)


def label_for(section: str, evidence: str, cited: list[dict], min_chars: int) -> tuple[str, list[str]]:
    """The label comes from where the quote really is, never from the model's own claim."""
    backing = [s for s in cited if quote_in(evidence, s.get("text") or "", min_chars)]
    if not backing:
        return "unconfirmed", []
    if SECTIONS.get(section, ("", "fact"))[1] == "inference":
        return "ai", [s["id"] for s in backing]
    if any(s["origin"] == "provided" for s in backing):
        return "provided", [s["id"] for s in backing if s["origin"] == "provided"]
    return "research", [s["id"] for s in backing]


def add_finding(a, org_id, section, value, label, source_ids=(), evidence="", run_id=None, product_id=None) -> dict:
    fid = _id("fnd")
    _w(a, "INSERT INTO findings (id, org_id, product_id, section, value, label, source_ids, evidence, run_id, created)"
          " VALUES (?,?,?,?,?,?,?,?,?,?)",
       (fid, org_id, product_id, section, json.dumps(value), label, json.dumps(list(source_ids)), evidence, run_id,
        time.time()))
    return finding(a, fid)


def finding(a, fid) -> dict:
    f = _row(a.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone())
    if not f:
        raise KeyError(fid)
    return f


def findings(a, org_id, status=None) -> list[dict]:
    sql, args = "SELECT * FROM findings WHERE org_id=?", [org_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    return [_row(r) for r in a.execute(sql + " ORDER BY created", args)]


def review_finding(a, fid, status=None, value=None) -> dict:
    f = finding(a, fid)
    if status not in (None, "pending", "approved", "rejected"):
        raise ValueError("status must be pending, approved or rejected")
    edited = f["edited"] or (value is not None and value != f["value"])
    # An edited finding is the organization's own statement from now on.
    label = "provided" if value is not None and value != f["value"] else f["label"]
    _w(a, "UPDATE findings SET status=?, value=?, edited=?, label=? WHERE id=?",
       (status or f["status"], json.dumps(f["value"] if value is None else value), int(edited), label, fid))
    return finding(a, fid)


def remove_finding(a, fid):
    finding(a, fid)
    _w(a, "DELETE FROM findings WHERE id=?", (fid,))


def profile(a, org_id) -> dict:
    """What campaigns may use: the organization's own fields plus findings the user approved. Nothing else."""
    o = get_org(a, org_id)
    secs = {}
    for f in findings(a, org_id, "approved"):
        secs.setdefault(f["section"], []).append({"value": f["value"], "label": f["label"], "id": f["id"]})
    return {"name": o["name"], "fields": o["fields"], "sections": secs, "researched_at": o["researched_at"]}


def profile_text(p: dict) -> str:
    lines = [f"Organization: {p['name']}"]
    lines += [f"{k}: {v}" for k, v in p["fields"].items() if v]
    for sec, items in p["sections"].items():
        title = SECTIONS.get(sec, (sec,))[0]
        lines.append(f"{title}: " + "; ".join(str(i["value"]) for i in items))
    return "\n".join(lines)


# ---------- products ----------

def create_product(a, org_id, name, fields=None, origin="manual", status=None, field_labels=None) -> dict:
    get_org(a, org_id)
    if not (name or "").strip():
        raise ValueError("a product needs a name")
    pid, t = _id("prd"), time.time()
    # Typed in by the user = provided and usable; found by research = waits for approval.
    status = status or ("approved" if origin == "manual" else "draft")
    _w(a, "INSERT INTO products (id, org_id, name, fields, field_labels, status, origin, created, updated)"
          " VALUES (?,?,?,?,?,?,?,?,?)",
       (pid, org_id, name.strip(), json.dumps(_clean(fields, PRODUCT_FIELDS)), json.dumps(field_labels or {}),
        status, origin, t, t))
    _touch(a, org_id)
    return product(a, pid)


def product(a, pid) -> dict:
    p = _row(a.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())
    if not p:
        raise KeyError(pid)
    return p


def products(a, org_id, include_hidden=False) -> list[dict]:
    sql = "SELECT * FROM products WHERE org_id=?" + ("" if include_hidden else " AND status IN ('draft','approved')")
    return [_row(r) for r in a.execute(sql + " ORDER BY created", (org_id,))]


def update_product(a, pid, name=None, fields=None, status=None) -> dict:
    p = product(a, pid)
    if status not in (None, "draft", "approved", "archived"):
        raise ValueError("status must be draft, approved or archived")
    new = _clean(fields, PRODUCT_FIELDS)
    labels = {**p["field_labels"], **{k: "provided" for k, v in new.items() if v != p["fields"].get(k)}}
    _w(a, "UPDATE products SET name=?, fields=?, field_labels=?, status=?, updated=? WHERE id=?",
       ((name or p["name"]).strip(), json.dumps({**p["fields"], **new}), json.dumps(labels), status or p["status"],
        time.time(), pid))
    return product(a, pid)


def merge_products(a, keep_id, drop_id) -> dict:
    """Combine a duplicate into another product: empty fields are filled, sources and campaigns re-pointed."""
    keep, drop = product(a, keep_id), product(a, drop_id)
    if keep["org_id"] != drop["org_id"] or keep_id == drop_id:
        raise ValueError("merge two different products of the same organization")
    fields = {**{k: v for k, v in drop["fields"].items() if v}, **{k: v for k, v in keep["fields"].items() if v}}
    labels = {**drop["field_labels"], **keep["field_labels"]}
    with _lock:
        a.execute("UPDATE products SET fields=?, field_labels=?, updated=? WHERE id=?",
                  (json.dumps(fields), json.dumps(labels), time.time(), keep_id))
        a.execute("UPDATE products SET status='merged', merged_into=?, updated=? WHERE id=?",
                  (keep_id, time.time(), drop_id))
        a.execute("UPDATE sources SET product_id=? WHERE product_id=?", (keep_id, drop_id))
        a.execute("UPDATE campaigns SET product_id=? WHERE product_id=?", (keep_id, drop_id))
        a.commit()
    return product(a, keep_id)


def product_text(p: dict | None) -> str:
    if not p:
        return "No specific product: the campaign is for the organization as a whole."
    return "\n".join([f"Product: {p['name']}"] + [f"{k}: {v}" for k, v in p["fields"].items() if v])


# ---------- campaigns ----------

_cons: dict[str, sqlite3.Connection] = {}


def create_campaign(a, org_id, name, product_id=None, fields=None, field_sources=None, db_file=None) -> dict:
    get_org(a, org_id)
    if product_id:
        p = product(a, product_id)
        if p["org_id"] != org_id:
            raise ValueError("that product belongs to another organization")
        if p["status"] != "approved":
            raise ValueError("approve the product's information before using it in a campaign")
    if not (name or "").strip():
        raise ValueError("a campaign needs a name")
    cid, t = _id("cmp"), time.time()
    fresh = db_file is None  # an existing engine file (migration) is used as it is, never written to here
    db_file = db_file or str(campaign_dir(a) / f"{cid}.db")
    _w(a, "INSERT INTO campaigns (id, org_id, product_id, name, fields, field_sources, brief, db_file, created, updated)"
          " VALUES (?,?,?,?,?,?,?,?,?,?)",
       (cid, org_id, product_id, name.strip(), json.dumps(_clean(fields, CAMPAIGN_FIELDS)),
        json.dumps(field_sources or {}), "{}", db_file, t, t))
    if fresh:
        con = engine_con(a, cid)
        db.put(con, "org_id", org_id)
        db.put(con, "campaign_id", cid)
        db.put(con, "memory_group", org_id)
        inherit_lessons(a, cid)
    return campaign(a, cid)


def inherit_lessons(a, cid):
    """Real wins and flops from this organization's other campaigns: what this client has learned so far."""
    c = campaign(a, cid)
    con = engine_con(a, cid)
    rows = []
    for other in a.execute("SELECT id FROM campaigns WHERE org_id=? AND id<>?", (c["org_id"], cid)):
        rows += [tuple(r) for r in engine_con(a, other["id"]).execute(
            "SELECT term, kind, text FROM memory WHERE kind IN ('win','flop')")]
    con.executemany("INSERT INTO memory (term, kind, text) VALUES (?,?,?)", rows)
    con.commit()


def campaign(a, cid) -> dict:
    c = _row(a.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
    if not c:
        raise KeyError(cid)
    return c


def campaigns(a, org_id=None) -> list[dict]:
    sql, args = "SELECT * FROM campaigns", ()
    if org_id:
        sql, args = sql + " WHERE org_id=?", (org_id,)
    return [_row(r) for r in a.execute(sql + " ORDER BY updated DESC", args)]


def update_campaign(a, cid, **f) -> dict:
    c = campaign(a, cid)
    if "fields" in f:
        f["fields"] = {**c["fields"], **_clean(f["fields"], CAMPAIGN_FIELDS)}
    if "field_sources" in f:
        f["field_sources"] = {**c["field_sources"], **f["field_sources"]}
    cols = {k: json.dumps(v) if k in _JSON else v for k, v in f.items()
            if k in ("name", "product_id", "fields", "field_sources", "brief", "brief_status", "published_at")}
    if cols:
        _w(a, f"UPDATE campaigns SET {', '.join(f'{k}=?' for k in cols)}, updated=? WHERE id=?",
           (*cols.values(), time.time(), cid))
    return campaign(a, cid)


def engine_con(a, cid) -> sqlite3.Connection:
    with _lock:
        if cid not in _cons:
            _cons[cid] = db.connect(campaign(a, cid)["db_file"])
        return _cons[cid]


def engine_path(a, cid) -> str:
    return campaign(a, cid)["db_file"]


def reset_engine(a, cid):
    """Archive the campaign's engine database and start a fresh one (keeps lessons and identity)."""
    with _lock:
        con = engine_con(a, cid)
        meta = {k: db.get(con, k) for k in ("org_id", "campaign_id", "memory_group")}
        _cons[cid] = con = db.new_campaign(con, campaign(a, cid)["db_file"])
        for k, v in meta.items():
            if v is not None:
                db.put(con, k, v)
    return con


def reopen(a, cid):
    """After the engine file was replaced on disk (rollback), drop the cached connection."""
    with _lock:
        c = _cons.pop(cid, None)
        if c:
            c.close()
    return engine_con(a, cid)


def close_all():
    with _lock:
        for c in _cons.values():
            c.close()
        _cons.clear()


def get_meta(a, k, default=None):
    r = a.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def put_meta(a, k, v):
    _w(a, "INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v)))


# ---------- one-time move from the single-campaign app ----------

def migrate(a, org_file="data/org.json", engine_file=None):
    """data/org.json and data/engine.db become the first organization and campaign. The engine file is
    referenced where it is, never moved or rewritten here."""
    if get_meta(a, "migrated") or list_orgs(a):
        put_meta(a, "migrated", True)
        return None
    org_path, engine_path_ = Path(org_file), Path(engine_file or db.DB_PATH)
    has_org = org_path.exists()
    has_campaign = False
    if engine_path_.exists():
        probe = sqlite3.connect(engine_path_)
        try:
            has_campaign = bool(probe.execute("SELECT v FROM meta WHERE k='campaign'").fetchone())
        except sqlite3.Error:
            has_campaign = False
        probe.close()
    if not (has_org or has_campaign):
        put_meta(a, "migrated", True)
        return None
    old = json.loads(org_path.read_text()) if has_org else {"materials": []}
    o = create_org(a, "My organization", {"notes": "Moved from the earlier single-campaign version."})
    for m in old.get("materials", []):
        add_source(a, o["id"], m.get("kind", "note"), m.get("name", "material"), m.get("text", ""))
    cid = None
    if has_campaign:
        con = db.connect(engine_path_)
        camp = db.get(con, "campaign") or {}
        con.close()
        draft = old.get("draft") or {}
        c = create_campaign(a, o["id"], camp.get("brief", {}).get("offering") or camp.get("goal") or "Current campaign",
                            fields={"objective": draft.get("objective", ""), "goal": camp.get("goal", ""),
                                    "audience": camp.get("market", "")},
                            db_file=str(engine_path_))
        brief = {**camp.get("brief", {}), "objective": draft.get("objective", "")}
        update_campaign(a, c["id"], brief=brief, brief_status="confirmed")
        cid = c["id"]
    put_meta(a, "migrated", True)
    return {"org": o["id"], "campaign": cid}
