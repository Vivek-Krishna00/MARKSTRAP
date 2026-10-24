import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """`make test` exports .env; tests must never reach the live graph, OASIS feed or LLM."""
    for k in ("MEMORY_BACKEND", "AUDIENCE_BACKEND", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
