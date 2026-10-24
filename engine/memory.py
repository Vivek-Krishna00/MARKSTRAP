"""Audience memory: real wins and flops, plus what each simulated person did on the feed (MiroFish's Zep role).

MEMORY_BACKEND=graphiti: Graphiti on a graph database, recalled by meaning (needs an embeddings endpoint).
  GRAPH_DB=falkordb (FALKORDB_HOST/PORT/USERNAME/PASSWORD) or neo4j (NEO4J_URI/USER/PASSWORD) — local or hosted.
Otherwise, or if the graph is unreachable: SQLite, newest first, and the LLM judges similarity.
SQLite is always written, so the graph is an index over it and never the only copy.
Two groups never mix: "audience" holds real results (reality judges); "audience-sim" holds simulated history.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

GROUP, SIM_GROUP = "audience", "audience-sim"
REAL = ("win", "flop")
_g = None
_loop = None
_down = False  # ponytail: after one failure, SQLite for the rest of the process; restart to retry the graph
log = logging.getLogger(__name__)


def _run(coro):
    # One long-lived loop: Graphiti's async DB client must stay on the loop it was created on.
    global _loop
    if _loop is None:
        import threading
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


def _driver():
    if os.getenv("GRAPH_DB", "falkordb") == "neo4j":
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
        return Neo4jDriver(os.environ["NEO4J_URI"], os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD"))
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    return FalkorDriver(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")),
                        username=os.getenv("FALKORDB_USERNAME") or None, password=os.getenv("FALKORDB_PASSWORD") or None)


def _graphiti():
    global _g
    if _g is None:
        from graphiti_core import Graphiti
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

        from . import llm
        if os.getenv("LLM_PROVIDER") == "vertex":  # ponytail: token taken once; rebuild _g if runs outlive an hour
            key, base = llm.gcp_token(), llm.vertex_base() + "/endpoints/openapi"
        else:
            key, base = os.getenv("LLM_API_KEY", "none"), os.getenv("LLM_BASE_URL")
        _g = Graphiti(
            graph_driver=_driver(),
            llm_client=OpenAIGenericClient(LLMConfig(api_key=key, base_url=base, model=os.getenv("LLM_MODEL"))),
            embedder=OpenAIEmbedder(OpenAIEmbedderConfig(
                api_key=os.getenv("EMBED_API_KEY") or key, base_url=os.getenv("EMBED_BASE_URL") or base,
                embedding_model=os.getenv("EMBED_MODEL", "nomic-embed-text"))),
        )
        _run(_g.build_indices_and_constraints())
    return _g


def _on():
    return os.getenv("MEMORY_BACKEND") == "graphiti" and not _down


def _graph(call):
    """Run a Graphiti call; on any failure log it and let the caller use SQLite instead."""
    global _down
    try:
        return call(_graphiti())
    except Exception as e:  # unreachable graph must not stop a campaign
        log.warning("graph memory unavailable, using SQLite until restart: %s", e)
        _down = True
        return None


def remember(con, term: int, kind: str, text: str):
    con.execute("INSERT INTO memory (term, kind, text) VALUES (?,?,?)", (term, kind, text))
    con.commit()
    if _on():
        _graph(lambda g: _run(g.add_episode(
            name=f"{kind}-t{term}", episode_body=f"Real-world {kind}: {text}",
            source_description="real campaign result", reference_time=datetime.now(timezone.utc),
            group_id=GROUP)))


def recall(con, query: str, k: int = 5) -> list[str]:
    """Real results only: the simulation's own history never teaches the audience what works."""
    if _on():
        edges = _graph(lambda g: _run(g.search(query, group_ids=[GROUP], num_results=k)))
        if edges is not None:
            return [e.fact for e in edges]
    rows = con.execute(f"SELECT kind, text FROM memory WHERE kind IN {REAL} ORDER BY id DESC LIMIT ?", (k,)).fetchall()
    return [f"{r['kind'].upper()}: {r['text']}" for r in rows]


def remember_feed(con, term: int, episodes: list[dict]):
    """episodes: [{"people": [names], "text": "..."}] from audience/feed.py (MiroFish's batched activity text)."""
    for ep in episodes:
        con.execute("INSERT INTO memory (term, kind, text) VALUES (?,?,?)",
                    (term, "sim:" + "|".join(ep["people"]), ep["text"]))
    con.commit()
    if _on():
        for i, ep in enumerate(episodes):
            if _graph(lambda g: _run(g.add_episode(
                    name=f"feed-t{term}-{i}", episode_body=ep["text"], source_description="simulated social feed",
                    reference_time=datetime.now(timezone.utc), group_id=SIM_GROUP))) is None:
                break


def recall_person(con, name: str, k: int = 3) -> list[str]:
    """What this person did on earlier feeds, so they remember across terms like MiroFish agents."""
    if _on():
        edges = _graph(lambda g: _run(g.search(f"What did {name} do?", group_ids=[SIM_GROUP], num_results=k)))
        if edges is not None:
            return [e.fact for e in edges]
    rows = con.execute("SELECT text FROM memory WHERE kind LIKE ? ORDER BY id DESC LIMIT ?",
                       (f"sim:%{name}%", 20)).fetchall()
    return [line for r in rows for line in r["text"].splitlines() if f"] {name}:" in line][:k]
