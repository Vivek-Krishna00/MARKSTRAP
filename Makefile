PY := .venv/bin/python
-include .env
export

.PHONY: help setup audience-setup reel-setup reel-demo dev test up down logs gen falkordb index clean site ai-check

help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## venv + deps + .env
	python3 -m venv .venv
	$(PY) -m pip install -q -e ".[dev]"
	@test -f .env || cp .env.example .env

audience-setup:  ## Python 3.11 venv for the MiroFish/OASIS audience (AUDIENCE_BACKEND=oasis)
	$(PY) -m pip install -q uv
	test -x audience/.venv/bin/python || .venv/bin/uv venv -q -p 3.11 audience/.venv
	.venv/bin/uv pip install -q -p audience/.venv/bin/python -r audience/requirements.txt

dev:  ## run API + dashboard locally on :8000
	$(PY) -m uvicorn engine.api:app --reload --port 8000

reel-setup:  ## Reel Director voice: Piper TTS (open source) + one English voice (~60 MB) in data/voices
	$(PY) -m pip install -q piper-tts
	mkdir -p data/voices && cd data/voices && ../../$(PY) -m piper.download_voices en_US-lessac-medium

reel-demo:  ## render the demo reel fixture with no paid provider (scratch DB): make reel-demo FINAL=1
	DB_PATH=data/reel-demo.db REEL_TEXT_PROVIDER=mock $(PY) -m engine.cli reel-demo $(if $(FINAL),--final)

site:  ## build the website (site/ -> web/site, served at /)
	cd site && npm install --no-audit --no-fund && npm run build

ai-check:  ## verify the brain and image APIs from .env with one real call each
	$(PY) -m engine.cli check-ai --image

test:  ## run tests (fake LLM, no network)
	$(PY) -m pytest -q tests

gen:  ## run N generations from the CLI: make gen N=3
	$(PY) -m engine.cli run-generation -n $(or $(N),1)

falkordb:  ## start only FalkorDB (for MEMORY_BACKEND=graphiti while running `make dev`)
	docker compose up -d falkordb

up:  ## build and run everything in Docker
	docker compose up -d --build

down:  ## stop Docker stack
	docker compose down

logs:  ## follow engine logs
	docker compose logs -f engine

index:  ## re-index the repo into codebase-memory-mcp
	codebase-memory-mcp cli index_repository '{"repo_path":"$(CURDIR)"}'

clean:  ## wipe local campaign data
	rm -rf data
