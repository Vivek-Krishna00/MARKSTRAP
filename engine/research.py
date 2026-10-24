"""Organization research, run only after the user approves the plan.

Reads the organization's own website (a few pages, same domain), the home page of each competitor the user
listed, and the Wikipedia article if there is one. Everything read is stored as a research source. One extraction
call turns sources into findings; agency.label_for decides each label from where the evidence quote really is.
Nothing becomes part of the profile until the user approves it.
"""
import ipaddress
import json
import re
import socket
import time
import uuid
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx

from . import agency, evolve, llm

CFG = evolve.CFG["research"]
# Wikimedia refuses agents without a contact URL (meta.wikimedia.org/wiki/User-Agent_policy).
UA = {"User-Agent": "MarkStrap/0.2 (https://github.com/Vivek-Krishna00/MARKSTRAP; open-source marketing research)"}
SKIP = ("script", "style", "noscript", "svg", "nav", "footer")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.links, self.skip, self.title, self._in_title = [], [], 0, "", False

    def handle_starttag(self, tag, attrs):
        self.skip += tag in SKIP
        self._in_title = tag == "title" and not self.skip and not self.title  # the page title, not an SVG's
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        self.skip -= tag in SKIP and self.skip > 0
        self._in_title = False

    def handle_data(self, d):
        if self._in_title:
            self.title += d.strip()
        elif not self.skip and d.strip():
            self.text.append(d.strip())


def normalise_url(url: str) -> str:
    url = (url or "").strip()
    if url and not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def _public(url: str):
    """Refuse links that point inside this machine or network."""
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError(f"cannot reach {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"{host} is not a public address")


def fetch(url: str) -> dict:
    url = normalise_url(url)
    if not re.match(r"^https?://", url):
        raise ValueError("only http(s) links")
    _public(url)
    r = httpx.get(url, follow_redirects=True, timeout=CFG["timeout_s"], headers=UA)
    r.raise_for_status()
    p = _Page()
    p.feed(r.text)
    return {"url": str(r.url), "title": p.title[:120], "text": " ".join(p.text)[:CFG["page_chars"]],
            "links": [urljoin(str(r.url), h) for h in p.links]}


def crawl(url: str, max_pages: int) -> list[dict]:
    """Home page first, then same-domain links whose path names what a profile needs (about, products...)."""
    home = fetch(url)
    domain = urlparse(home["url"]).netloc.removeprefix("www.")
    seen, out = {home["url"].rstrip("/")}, [home]
    words = CFG["priority_words"]
    cands = []
    for link in home["links"]:
        u = urlparse(link)
        if u.scheme not in ("http", "https") or u.netloc.removeprefix("www.") != domain:
            continue
        clean = f"{u.scheme}://{u.netloc}{u.path}".rstrip("/")
        if clean in seen or re.search(r"\.(pdf|jpg|png|zip|mp4)$", clean, re.I):
            continue
        seen.add(clean)
        score = sum(w in u.path.lower() for w in words)
        cands.append((-score, len(u.path), clean))
    for _, _, link in sorted(cands)[:max_pages - 1]:
        try:
            out.append(fetch(link))
        except Exception:  # one broken page should not stop the research
            continue
    return out


def wikipedia(name: str) -> dict | None:
    base = "https://en.wikipedia.org/w/api.php"
    r = httpx.get(base, params={"action": "opensearch", "search": name, "limit": 1, "format": "json"},
                  timeout=CFG["timeout_s"], headers=UA)
    r.raise_for_status()
    hits = r.json()
    if not hits or len(hits) < 2 or not hits[1]:
        return None
    title = hits[1][0]
    r = httpx.get(base, params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": title,
                                "format": "json", "redirects": 1}, timeout=CFG["timeout_s"], headers=UA)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]
    text = next(iter(pages.values())).get("extract", "")
    if not text:
        return None
    return {"url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}", "title": title,
            "text": text[:CFG["wikipedia_chars"]]}


def plan(org: dict) -> dict:
    """Exactly what research will read, shown to the user before they approve it."""
    f = org["fields"]
    comps = [normalise_url(c) for c in re.split(r"[,\n]+", f.get("competitors", "")) if "." in c and " " not in c.strip()]
    return {"website": normalise_url(f.get("website", "")) or None, "max_pages": CFG["max_pages"],
            "competitors": comps, "wikipedia": org["name"],
            "materials": "Everything already in the knowledge base"}


def _progress(a, org_id, **p):
    agency.put_meta(a, f"research:{org_id}", {**agency.get_meta(a, f"research:{org_id}", {}), **p})


def run(path: str, org_id: str):
    """Background job with its own connection; progress and errors are stored for the UI to poll."""
    a = agency.connect(path)
    try:
        org = agency.get_org(a, org_id)
        pl = plan(org)
        _progress(a, org_id, status="running", step="Reading the website", error=None, started=time.time())
        notes = []
        # Re-running replaces earlier research sources; the organization's own materials stay.
        for s in agency.sources(a, org_id, origin="research"):
            agency.remove_source(a, s["id"])
        if pl["website"]:
            try:
                for pg in crawl(pl["website"], pl["max_pages"]):
                    agency.add_source(a, org_id, "crawl", pg["title"] or pg["url"], pg["text"], origin="research",
                                      url=pg["url"])
            except Exception as e:
                notes.append(f"Website could not be read: {str(e)[:120]}")
        _progress(a, org_id, step="Reading competitor sites")
        for c in pl["competitors"]:
            try:
                pg = fetch(c)
                agency.add_source(a, org_id, "crawl", f"Competitor: {pg['title'] or pg['url']}", pg["text"],
                                  origin="research", url=pg["url"])
            except Exception as e:
                notes.append(f"{c} could not be read: {str(e)[:80]}")
        _progress(a, org_id, step="Checking Wikipedia")
        try:
            w = wikipedia(org["name"])
            if w:
                agency.add_source(a, org_id, "wikipedia", f"Wikipedia: {w['title']}", w["text"],
                                  origin="research", url=w["url"])
        except Exception as e:
            notes.append(f"Wikipedia could not be read: {str(e)[:80]}")
        _progress(a, org_id, step="Organizing the findings")
        n = extract(a, org_id)
        a.execute("UPDATE orgs SET researched_at=? WHERE id=?", (time.time(), org_id))
        a.commit()
        _progress(a, org_id, status="done", step="", notes=notes, finished=time.time(), found=n)
    except Exception as e:  # surfaced to the UI, never a silent thread death
        _progress(a, org_id, status="failed", error=str(e)[:300])
    finally:
        a.close()


def extract(a, org_id: str) -> int:
    """One extraction call over every source; labels are decided here in Python from the evidence quotes."""
    org = agency.get_org(a, org_id)
    srcs = [s for s in agency.sources(a, org_id) if (s["text"] or "").strip()]
    budget, chunks = CFG["prompt_chars"], []
    for s in srcs:
        piece = f"[{s['id']}] ({'from the organization' if s['origin'] == 'provided' else 'public source'}) " \
                f"{s['name']}\n{s['text'][:max(0, budget)]}"
        budget -= len(piece)
        chunks.append(piece)
        if budget <= 0:
            break
    sections = {k: v[0] for k, v in agency.SECTIONS.items()}
    out = llm.chat_json(
        "You are a careful marketing researcher building a client profile. Use ONLY the sources given. "
        "Every finding must cite one source id and copy a short exact quote from it as evidence. "
        "If something is not in the sources, list it as missing instead of guessing.",
        f"Organization: {org['name']}\nWhat the organization told us: {json.dumps(org['fields'])}\n\n"
        f"Sections: {json.dumps(sections)}\n\nSources:\n" + "\n\n".join(chunks) + "\n\n"
        'Return {"findings": [{"section": "<section key>", "value": str, "source": "<source id>", '
        '"evidence": str (exact words copied from that source)}], '
        '"products": [{"name": str, "description": str, "category": str, "customers": str, '
        '"value_proposition": str, "features": str, "pricing": str, "source": "<source id>", "evidence": str}], '
        '"missing": [str] (important things a marketer needs that the sources do not say)}', temperature=0.2)
    by_id = {s["id"]: s for s in srcs}
    mn = CFG["min_quote_chars"]
    a.execute("DELETE FROM findings WHERE org_id=? AND status='pending'", (org_id,))
    a.commit()
    reviewed = {(f["section"], agency._norm(json.dumps(f["value"]))) for f in agency.findings(a, org_id)}
    run_id, n = uuid.uuid4().hex[:6], 0
    for f in out.get("findings", []):
        sec, val = f.get("section"), str(f.get("value") or "").strip()
        if sec not in agency.SECTIONS or not val or (sec, agency._norm(json.dumps(val))) in reviewed:
            continue
        cited = [by_id[f["source"]]] if f.get("source") in by_id else []
        label, ids = agency.label_for(sec, f.get("evidence", ""), cited, mn)
        agency.add_finding(a, org_id, sec, val, label, ids, f.get("evidence", ""), run_id)
        n += 1
    filled = {f["section"] for f in agency.findings(a, org_id) if f["status"] != "rejected"}
    gaps = [str(m) for m in out.get("missing", []) if str(m).strip()]
    gaps += [f"{agency.SECTIONS[s][0]}: nothing found" for s in agency.SECTIONS if s not in filled]
    for m in gaps:
        agency.add_finding(a, org_id, "missing", m, "missing", [], "", run_id)
    known = {agency._norm(p["name"]) for p in agency.products(a, org_id, include_hidden=True)}
    for p in out.get("products", []):
        name = str(p.get("name") or "").strip()
        if not name or agency._norm(name) in known:
            continue
        cited = [by_id[p["source"]]] if p.get("source") in by_id else []
        label, ids = agency.label_for("products", p.get("evidence", ""), cited, mn)
        fields = {k: str(p.get(k) or "") for k in ("description", "category", "customers", "value_proposition",
                                                    "features", "pricing") if p.get(k)}
        agency.create_product(a, org_id, name, fields, origin="research",
                              field_labels={**{k: label for k in fields}, "_sources": ids,
                                            "_evidence": p.get("evidence", "")})
        known.add(agency._norm(name))
        n += 1
    return n
