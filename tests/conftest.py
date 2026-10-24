import os
import tempfile

import pytest

# Before any engine module is imported: the app must never open or migrate the repo's data/ folder in tests.
_TMP = tempfile.mkdtemp(prefix="markstrap-test-")
os.environ["AGENCY_DB"] = os.path.join(_TMP, "agency.db")
os.environ["DB_PATH"] = os.path.join(_TMP, "engine.db")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """`make test` exports .env; tests must never reach the live graph, OASIS feed or LLM."""
    for k in ("MEMORY_BACKEND", "AUDIENCE_BACKEND", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
