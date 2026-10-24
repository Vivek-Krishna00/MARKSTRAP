# Architecture — MarkStrap Campaign Engine (MVP)

The simulation filters, reality judges. Everything else serves that loop.

```
               ┌──────────────────────── one term ────────────────────────┐
 campaign ──►  │ 1 INTERACT (nurture)   best ad per caste ─► mentor LLM ─► lesson │
 goal, market, │ 2 PRODUCE & JUDGE      teams (1 agent/breed) ─► ad JSON          │
 ad_type       │   (genomes frozen)     ad + recalled memory ─► audience LLM      │
               │                        ─► reactions + per-part reasons ─► score  │
               │                        boredom: same style seen recently ↓       │
               │                        shortlist if score ≥ bar + penalty×demotions│
               │ 3 REPRODUCE (queens)   per caste: elite kept, gate → eligible     │
               │                        queens pick parents ─► keeper | explorer   │
               │                        child inherits genome + caste lessons      │
               │                        no offspring 3 terms ─► archive (revivable)│
               └──────────────────────────────────────────────────────────────────┘
                     │ shortlist.csv                          ▲
                     ▼                                        │ real_score overrides sim,
               human posts on real platforms ─► results.csv ──┘ shared by team; flop/win
                                                                 written to audience memory
```

## Components

| Part | File | Open-source tech |
|---|---|---|
| LLM for every agent | `engine/llm.py` | any open model behind an OpenAI-compatible API (Qwen, Llama via vLLM/Ollama) |
| Evolution loop | `engine/evolve.py` | Python stdlib |
| Store (agents, ads, lineage, dial log) | `engine/db.py` | SQLite |
| Audience personas | `engine/personas.py` | 30-facet IPIP-NEO-120 copula (n=271,547) from developmental-agent-simulator |
| Audience memory | `engine/memory.py` | Graphiti + FalkorDB (or SQLite fallback) |
| API + dashboard | `engine/api.py`, `web/index.html` | FastAPI, vanilla JS |
| Config / dials | `config.yaml` | YAML |

## Nature · nurture · breeders
- **Nature** — `agents.genome` (prompt, strategy, lessons), fixed breed + caste, `parents`, `child_kind`.
- **Nurture** — phase 1 lessons stored per caste in `meta.lessons`; land in children at birth, never mid-life.
- **Breeders** — `queens` table, rules `top` / `untried` / `wild`; rated on children's fitness, culled after
  `queen_poor_terms` below-median terms and replaced.

## Audience personas (from developmental-agent-simulator)
- Personality is **sampled, not invented**: correlated facet percentiles from a copula fitted on 271,547 IPIP-NEO-120
  respondents, turned into behavioural sentences (extreme deciles first). The LLM only adds name + media habits.
- Facets over Big Five domains: their 27B pilot got the expected action 21/24 with facet language vs 8/24 with domains.
  No activation steering needed.
- Judge prompt carries "tendencies, not obligations" (situational variability research: no caricatures).
- Not taken: memory decay, mood, hormones, sleep, household, lifespan; attention model (household-shaped, uncalibrated).

## Cut for the hackathon (from the design notes' MVP brief)
- OASIS feed for the interact phase → one mentor LLM call per term. Add OASIS when cultural copying needs a real feed.
- Graphiti is opt-in (`MEMORY_BACKEND=graphiti`): it needs an embeddings endpoint.
- No image rendering; visuals are evolved as descriptions (the design defers rendering to survivors anyway).
- Later per design: Loka, relegation, team economy, executives, classifier judge (D69–D71), fine-tuning.
