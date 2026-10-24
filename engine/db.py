"""SQLite store: every agent, ad, queen, lineage and dial change, so any result is traceable."""
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/engine.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, breed TEXT, caste TEXT, genome TEXT, parents TEXT, child_kind TEXT,
  queen TEXT, born INT, last_offspring INT, alive INT DEFAULT 1, fitness REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ads (
  id TEXT PRIMARY KEY, term INT, ad_type TEXT, style TEXT, team TEXT, content TEXT,
  reactions TEXT, sim_score REAL, real_score REAL, real_raw REAL, shortlisted INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS queens (
  id TEXT PRIMARY KEY, rule TEXT, rating REAL DEFAULT 0, poor_terms INT DEFAULT 0, alive INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS demotions (style TEXT PRIMARY KEY, n INT);
CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, term INT, kind TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS dial_log (id INTEGER PRIMARY KEY, term INT, dial TEXT, value TEXT, ts REAL);
"""


def connect(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def get(con, k, default=None):
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def put(con, k, v):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v)))
    con.commit()


def row(r):
    d = dict(r)
    for k in ("genome", "parents", "team", "content", "reactions"):
        if k in d and d[k]:
            d[k] = json.loads(d[k])
    return d


def new_campaign(con, path=None):
    """Archive the current campaign and start a fresh one that keeps the shared campaign memory."""
    path = Path(path or DB_PATH)
    lessons = [tuple(r) for r in con.execute("SELECT term, kind, text FROM memory")]
    con.close()
    if path.exists():
        archive = path.parent / "campaigns"
        archive.mkdir(exist_ok=True)
        shutil.move(path, archive / f"{time.strftime('%Y%m%d-%H%M%S')}.db")
    con = connect(path)
    con.executemany("INSERT INTO memory (term, kind, text) VALUES (?,?,?)", lessons)
    con.commit()
    return con


def snapshot(path=None):
    src = Path(path or DB_PATH)
    sid = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy(src, src.with_name(f"snap-{sid}.db"))
    return sid


def rollback(sid, path=None):
    dst = Path(path or DB_PATH)
    shutil.copy(dst.with_name(f"snap-{sid}.db"), dst)
