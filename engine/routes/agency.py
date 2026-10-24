"""Organizations, their knowledge base and research, products, campaign setup, and Home."""
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import agency, brief, evolve, hub, research

r = APIRouter(prefix="/api")
MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".mov", ".webm")
MAX_MB = evolve.CFG["reel"]["upload_max_mb"]


class OrgIn(BaseModel):
    name: str = ""
    fields: dict = {}


class FindingIn(BaseModel):
    status: str | None = None
    value: str | None = None


class BulkIn(BaseModel):
    ids: list[str]
    status: str


class ProductIn(BaseModel):
    name: str = ""
    fields: dict = {}
    status: str | None = None


class MergeIn(BaseModel):
    other: str


class SourceIn(BaseModel):
    confidential: bool | None = None
    product_id: str | None = "__keep__"


class CampaignIn(BaseModel):
    org_id: str
    name: str
    product_id: str | None = None
    fields: dict = {}


def _org(oid):
    return hub.nf(agency.get_org, hub.A, oid, what="organization")


@r.get("/home")
def home():
    return hub.home()


# ---------- organizations ----------

@r.get("/orgs")
def orgs():
    return hub.home()["orgs"]


@r.post("/orgs")
def create_org(o: OrgIn):
    return hub.nf(agency.create_org, hub.A, o.name, o.fields)


@r.get("/orgs/{oid}")
def org(oid: str):
    o = _org(oid)
    a = hub.A
    st = agency.get_meta(a, f"research:{oid}", {})
    srcs = agency.sources(a, oid)
    return {**o, "fields_list": agency.ORG_FIELDS, "labels": agency.LABELS,
            "sections": {k: v[0] for k, v in agency.SECTIONS.items()},
            "sources": [{k: v for k, v in s.items() if k != "text"} | {"chars": len(s["text"] or "")} for s in srcs],
            "findings": agency.findings(a, oid), "profile": agency.profile(a, oid),
            "products": agency.products(a, oid, include_hidden=True), "campaigns": [
                {**c, **hub.stage(c)} for c in agency.campaigns(a, oid)],
            "research": st, "research_plan": research.plan(o)}


@r.patch("/orgs/{oid}")
def update_org(oid: str, o: OrgIn):
    _org(oid)
    return agency.update_org(hub.A, oid, o.name or None, o.fields)


@r.delete("/orgs/{oid}")
def archive_org(oid: str):
    hub.nf(agency.archive_org, hub.A, oid, what="organization")
    return {"ok": True}


# ---------- knowledge base ----------

def _uploads(oid) -> Path:
    p = agency.campaign_dir(hub.A).parent / "uploads" / oid
    p.mkdir(parents=True, exist_ok=True)
    return p


@r.post("/orgs/{oid}/sources")
async def add_source(oid: str, text: str = Form(""), url: str = Form(""), name: str = Form(""),
                     product_id: str = Form(""), confidential: bool = Form(False), file: UploadFile | None = None):
    _org(oid)
    pid = product_id or None
    added = []
    try:
        if file is not None:
            data = await file.read()
            if len(data) > MAX_MB * 1024 * 1024:
                raise ValueError(f"files up to {MAX_MB} MB")
            fname = Path(file.filename or "file").name
            path = None
            if fname.lower().endswith(MEDIA):
                safe = re.sub(r"[^\w.-]", "_", fname)[-80:]
                path = _uploads(oid) / f"{len(list(_uploads(oid).iterdir()))}-{safe}"
                path.write_bytes(data)
            added.append(agency.add_source(hub.A, oid, "file", name or fname, brief.read_file(fname, data),
                                           product_id=pid, path=str(path) if path else None,
                                           confidential=confidential))
        if url.strip():
            u = research.normalise_url(url)
            pg = research.fetch(u)
            added.append(agency.add_source(hub.A, oid, "link", name or pg["title"] or u, pg["text"], product_id=pid,
                                           url=pg["url"], confidential=confidential))
        if text.strip():
            added.append(agency.add_source(hub.A, oid, "note", name or text.strip()[:60], text, product_id=pid,
                                           confidential=confidential))
    except HTTPException:
        raise
    except Exception as e:  # an unreadable link or file should not lose the rest
        raise HTTPException(400, f"could not read that: {str(e)[:200]}")
    if not added:
        raise HTTPException(400, "add a link, a note or a file")
    return [{k: v for k, v in s.items() if k != "text"} for s in added]


@r.get("/sources/{sid}")
def get_source(sid: str):
    return hub.nf(agency.source, hub.A, sid, what="source")


@r.get("/sources/{sid}/file")
def source_file(sid: str):
    s = hub.nf(agency.source, hub.A, sid, what="source")
    if not s["path"] or not Path(s["path"]).is_file():
        raise HTTPException(404, "no file stored for this source")
    return FileResponse(s["path"])


@r.patch("/sources/{sid}")
def update_source(sid: str, s: SourceIn):
    hub.nf(agency.source, hub.A, sid, what="source")
    pid = ... if s.product_id == "__keep__" else (s.product_id or None)
    return agency.update_source(hub.A, sid, s.confidential, pid)


@r.delete("/sources/{sid}")
def remove_source(sid: str):
    hub.nf(agency.remove_source, hub.A, sid, what="source")
    return {"ok": True}


# ---------- research (only with the user's approval) ----------

class ResearchIn(BaseModel):
    approved: bool = False


@r.post("/orgs/{oid}/research")
def start_research(oid: str, body: ResearchIn):
    _org(oid)
    if not body.approved:
        raise HTTPException(400, "research runs only after you approve what it will read")
    if (agency.get_meta(hub.A, f"research:{oid}", {}) or {}).get("status") == "running":
        raise HTTPException(409, "research is already running")
    agency.put_meta(hub.A, f"research:{oid}", {"status": "running", "step": "Starting", "error": None})
    path = agency.path_of(hub.A.execute("PRAGMA database_list").fetchone()[2])
    threading.Thread(target=research.run, args=(str(path), oid), daemon=True).start()
    return agency.get_meta(hub.A, f"research:{oid}")


@r.patch("/findings/{fid}")
def review_finding(fid: str, f: FindingIn):
    return hub.nf(agency.review_finding, hub.A, fid, f.status, f.value, what="finding")


@r.post("/findings/bulk")
def bulk_findings(b: BulkIn):
    return [hub.nf(agency.review_finding, hub.A, i, b.status, what="finding") for i in b.ids]


@r.delete("/findings/{fid}")
def remove_finding(fid: str):
    hub.nf(agency.remove_finding, hub.A, fid, what="finding")
    return {"ok": True}


# ---------- products ----------

@r.post("/orgs/{oid}/products")
def create_product(oid: str, p: ProductIn):
    _org(oid)
    return hub.nf(agency.create_product, hub.A, oid, p.name, p.fields)


@r.get("/products/{pid}")
def get_product(pid: str):
    p = hub.nf(agency.product, hub.A, pid, what="product")
    return {**p, "fields_list": agency.PRODUCT_FIELDS,
            "sources": [{k: v for k, v in s.items() if k != "text"} for s in agency.sources(hub.A, p["org_id"], pid)],
            "campaigns": [c for c in agency.campaigns(hub.A, p["org_id"]) if c["product_id"] == pid]}


@r.patch("/products/{pid}")
def update_product(pid: str, p: ProductIn):
    return hub.nf(agency.update_product, hub.A, pid, p.name or None, p.fields, p.status, what="product")


@r.post("/products/{pid}/merge")
def merge_product(pid: str, m: MergeIn):
    return hub.nf(agency.merge_products, hub.A, pid, m.other, what="product")


# ---------- campaign setup ----------

def _first(*pairs):
    for value, src in pairs:
        if value and str(value).strip():
            return {"value": str(value).strip(), "from": src}
    return None


def prefill(oid: str, pid: str | None) -> dict:
    """Useful starting values for a new campaign, each with where it came from."""
    a = hub.A
    o = _org(oid)
    prof = agency.profile(a, oid)
    p = agency.product(a, pid) if pid else None
    if p and p["status"] != "approved":
        raise HTTPException(400, "approve the product's information first")
    of, pf = o["fields"], (p or {}).get("fields", {})
    pn = f"Product · {p['name']}" if p else ""
    sec = lambda k: "; ".join(str(i["value"]) for i in prof["sections"].get(k, []))  # noqa: E731
    out = {
        "audience": _first((pf.get("customers"), f"{pn} · intended customers"),
                           (of.get("customers"), "Organization · target customers"),
                           (sec("customer_groups"), "Organization profile · customer groups")),
        "market": _first((of.get("market"), "Organization · primary market")),
        "offer": _first((pf.get("pricing"), f"{pn} · pricing or offer")),
        "required_messages": _first((pf.get("value_proposition"), f"{pn} · value proposition"),
                                    (sec("value_propositions"), "Organization profile · value propositions")),
        "destination": _first((pf.get("links"), f"{pn} · website links"), (of.get("website"), "Organization · website")),
        "brand_rules": _first((" ".join(x for x in [pf.get("brand_requirements", ""),
                                                    f"Colours: {of['colours']}" if of.get("colours") else ""] if x),
                               f"{pn or 'Organization'} · brand requirements and colours")),
        "prohibited_claims": _first((pf.get("prohibited_claims"), f"{pn} · claims that must not be made"),
                                    (sec("claims_need_evidence"), "Organization profile · claims that need evidence")),
        "tone": _first((of.get("voice"), "Organization · brand voice"),
                       (sec("brand_voice"), "Organization profile · brand voice")),
    }
    return {k: v for k, v in out.items() if v}


@r.get("/prefill")
def get_prefill(org: str, product: str | None = None):
    return {"fields": prefill(org, product or None), "objectives": list(brief.OBJECTIVES),
            "fields_list": agency.CAMPAIGN_FIELDS}


@r.get("/campaigns")
def list_campaigns():
    return hub.home()["campaigns"]


@r.post("/campaigns")
def create_campaign(c: CampaignIn):
    _org(c.org_id)
    if c.fields.get("objective") and c.fields["objective"] not in brief.OBJECTIVES:
        raise HTTPException(400, f"objective must be one of {sorted(brief.OBJECTIVES)}")
    pre = prefill(c.org_id, c.product_id)
    # Where each value came from: pre-filled and unchanged keeps its origin; anything else is campaign-only.
    sources = {k: (pre[k]["from"] if k in pre and str(v).strip() == pre[k]["value"] else "Set for this campaign")
               for k, v in c.fields.items() if str(v).strip()}
    return hub.nf(agency.create_campaign, hub.A, c.org_id, c.name, c.product_id, c.fields, sources)
