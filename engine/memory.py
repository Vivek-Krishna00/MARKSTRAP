"""Audience memory of real flops and wins.

MEMORY_BACKEND=graphiti: Graphiti on FalkorDB, recalled by meaning (needs an embeddings endpoint).
Otherwise: the last N lessons from SQLite go into the audience prompt and the LLM judges similarity.
Either way there is no hand-coded similarity metric.
"""
import asyncio
import os
from datetime import datetime, timezone

GROUP = "audience"
_g = None
_loop = None


def _run(coro):
    # One long-lived loop: Graphiti's async DB client must stay on the loop it was created on.
    global _loop
    if _loop is None:
        import threading
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


def _graphiti():
    global _g
    if _g is None:
        from graphiti_core import Graphiti
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

        base, key = os.getenv("LLM_BASE_URL"), os.getenv("LLM_API_KEY", "none")
        _g = Graphiti(
            graph_driver=FalkorDriver(host=os.getenv("FALKORDB_HOST", "localhost"),
                                      port=int(os.getenv("FALKORDB_PORT", "6379"))),
            llm_client=OpenAIGenericClient(LLMConfig(api_key=key, base_url=base, model=os.getenv("LLM_MODEL"))),
            embedder=OpenAIEmbedder(OpenAIEmbedderConfig(
                api_key=key, base_url=os.getenv("EMBED_BASE_URL") or base,
                embedding_model=os.getenv("EMBED_MODEL", "nomic-embed-text"))),
        )
        _run(_g.build_indices_and_constraints())
    return _g


def _on():
    return os.getenv("MEMORY_BACKEND") == "graphiti"


def remember(con, term: int, kind: str, text: str):
    con.execute("INSERT INTO memory (term, kind, text) VALUES (?,?,?)", (term, kind, text))
    con.commit()
    if _on():
        _run(_graphiti().add_episode(
            name=f"{kind}-t{term}", episode_body=f"Real-world {kind}: {text}",
            source_description="real campaign result", reference_time=datetime.now(timezone.utc),
            group_id=GROUP))


def recall(con, query: str, k: int = 5) -> list[str]:
    if _on():
        edges = _run(_graphiti().search(query, group_ids=[GROUP], num_results=k))
        return [e.fact for e in edges]
    rows = con.execute("SELECT kind, text FROM memory ORDER BY id DESC LIMIT ?", (k,)).fetchall()
    return [f"{r['kind'].upper()}: {r['text']}" for r in rows]
