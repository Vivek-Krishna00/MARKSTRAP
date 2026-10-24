PY := .venv/bin/python
-include .env
export

.PHONY: help setup dev test up down logs gen falkordb index clean site ai-check

help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## venv + deps + .env
	python3 -m venv .venv
	$(PY) -m pip install -q -e ".[dev]"
	@test -f .env || cp .env.example .env

dev:  ## run API + dashboard locally on :8000
	$(PY) -m uvicorn engine.api:app --reload --port 8000

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
