# MarkStrap audience personality module — spec (revised)

Revision of the "MiroFish: Personality Module" brief. Implemented in `engine/personality.py`, tested in
`tests/test_personality.py`, parameters in `config.yaml` → `personality:` and `docs/PARAMETERS.md`, evidence in
`docs/research/personality_ledger.md`.

## What changed from the original brief, and why

| # | Original brief | Revised | Why |
|---|---|---|---|
| 1 | Facet correlation matrix is [U]; build one from within-domain loadings and guessed between-domain correlations | Use the **fitted Gaussian copula** (30×30 latent correlation, n=271,547, ledger D1) for G and every E innovation | Data already exists in the repo; a guessed matrix would be worse and would need its own [U] tags |
| 2 | `to_percentiles` = normal CDF of z, clipped ±3 SD | Normal CDF, then map through the copula's **empirical raw-score marginals** (17 bins per facet), mid-rank percentile, 0–100 | Keeps real skew of each facet; the same mapping the persona sampler already used; 0–100 matches the behaviour-text compiler |
| 3 | "Var(G) = h2" | `z = √h2·G + E + …` with G ~ MVN(0, R) and Var(E(ref_age)) = 1−h2 | States how total variance stays 1 at the reference age; same derivation as devsim `temperament.inherited` |
| 4 | Twin pairs: "G correlated 0.5" | Siblings = two children of the same two founders: `G = ½(G_m+G_f) + √(1−n/4)·segregation` | Reuses devsim's inheritance rule; gives r = 0.5 exactly and works for one known parent too |
| 5 | Seeding helper must exist in the repo | sha256(seed : id : key : purpose) → numpy Generator, as in devsim | The helper did not exist in MarkStrap; devsim's pattern is order-independent by construction |
| 6 | Stability / Plasticity with no citation | Ledger **P10** (DeYoung, Peterson & Higgins 2002), tagged [D], equal weights | Every number or grouping needs a ledger ID |
| 7 | "Other modules read personality"; no readout defined for the simulator | Integration readout: `to_percentiles` → `describe()` behaviour text → OASIS profile `persona` / `user_char` | MiroFish fills this slot with **LLM-written MBTI + hard-coded archetypes** (media → ISTJ, experts → ENTJ/INTJ); that is what this module replaces |
| 8 | Genesis at any age | Same, and the **age is sampled before** the LLM writes name and habits; the LLM is told the age and personality are fixed | Prevents the LLM from re-inventing the person around a different age |
| 9 | Per-year loop only on first evaluation | Same, plus: the fractional year draws nothing at a whole age, so a repeat read costs zero draws | Makes "later reads O(1)" literally true |

Everything else in the original brief stands: lazy closed form, no archetypes, no LLM calls, evidence discipline,
clamped trait-change events, the public interface and the test list.

## Model

Stored state: `agent_id`, 30-facet `G`, 30 context offsets (default zero), optional `family` key, sparse delta list,
and a cache that is never needed for correctness. Domains and metatraits are always derived.

```
z(age) = √h2 · G + E(age) + M(age) + Σ deltas(record.age ≤ age) + O_context
G        ~ MVN(0, R)                       purpose pers_genetic, keyed by agent (or inherited from parents)
E(age)   = Σ_{k ≤ ⌊age⌋} √(v(k) − v(k−1)) · ε_k  + fractional part of the current year
           ε_k ~ MVN(0, R), purpose pers_env_innovation, keyed (agent, k)
           v(age) = (1 − h2) · curve(age) / curve(ref_age)          rising, concave curve  [D P2, shape U]
           + √shared_env_var · C_family                              purpose pers_env_baseline; default off [P3]
M(age)   = one shared piecewise-linear table per domain              N ↓, A ↑, C ↑, mostly 20–40 [D P4]
deltas   = apply_trait_delta(...), clamped to ±delta_clamp × age-window multiplier, logged with source_tag [U P6 P7]
O_context= additive per-facet tables selected by explicit context keys; empty by default [P9]
```

## Interface

```python
create_personality(agent_id, genesis_age=0, context=None, genes=None, family=None) -> PersonalityState
personality_at(state, age) -> np.ndarray[30]       # z values, pure and deterministic
domains(z) -> {N, E, O, A, C}
metatraits(z) -> {stability, plasticity, disinhibition}
to_percentiles(z) -> {facet: 0–100}
apply_trait_delta(state, age, target, delta, source_tag)   # target = facet code or domain letter
founder_genes(agent_id), inherit_genes(parent_genes, child_id)
```

## Integration with the MiroFish/OASIS audience

`engine/personas.sample_people(n, seed)` → (age, percentiles) per person → `describe()` gives at most eight
behaviour sentences, extreme deciles first, plus the "tendencies, not obligations" guard. That text is the agent's
persona in the OASIS profile. No MBTI field is written.

## Open items for the owner

- `disinhibition_weights` are [U]: confirm or replace.
- `env_variance_curve`, maturation magnitudes, `ref_age`, `delta_clamp` and `audience.age_range` are free defaults.
- The copula data comes from a repo with no licence: confirm reuse with its author.
