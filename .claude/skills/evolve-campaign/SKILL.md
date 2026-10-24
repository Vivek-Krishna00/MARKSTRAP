---
name: evolve-campaign
description: Seed a MarkStrap campaign, run generations, inspect lineages and import real results with the engine CLI. Use when asked to run, demo, debug or inspect the campaign engine.
---

All commands read `.env` (via `make`) for the OpenAI-compatible LLM endpoint. The CLI works on one engine file
(`DB_PATH`, default `data/engine.db`). Campaigns made in the app each have their own file,
`data/campaign-data/<campaign id>.db`: point `DB_PATH` at it to inspect one (the console does the same at
`/console?campaign=<id>`).

1. Seed: `.venv/bin/python -m engine.cli new-campaign "<goal>" "<target market>" --type direct|brand`
   (wipes `data/engine.db`; run `snapshot` first to keep the old campaign).
2. Evolve: `make gen N=3`. Each term = interact (lessons) → produce & judge (frozen) → queens reproduce, agents age.
3. Inspect: `top-ads`, `show-team <ad_id>`, `show-lineage <agent_id>`, `show-dials`.
4. Reality: download `/api/ads.csv` (shortlisted ads), a human posts them, fills metrics, then
   `import-results <csv>`. Flops are written to audience memory and demote the style.
5. Tune: `set <dial> <value>` — applies from the next term, logged in `dial_log`.

Invariants to keep when changing code (tests in `tests/test_engine.py` cover them):
simulation only demotes, never deletes a genome; breeds never go extinct; children stay in their caste;
real scores override sim and are shared by the whole team; dial changes apply next term only.
