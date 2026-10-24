# Parameters

Every number of the personality module lives in `config.yaml` → `personality:` (and `audience:`).
Tags: **[V]** implemented from supported evidence · **[D]** direction or ordering only, magnitude is a free default ·
**[U]** no usable evidence, placeholder. Ledger: `docs/research/personality_ledger.md`.
Never present [D] or [U] numbers as scientific.

| Name | Default | Tag | Ledger | Rationale |
|---|---|---|---|---|
| `h2` | 0.40 | V | P1 | Twin heritability; SNP figures (P1c) deliberately not used. Recovered by the twin test (≈0.39). |
| facet correlation | fitted matrix | V (data) | D1 | Used for G and every E innovation, so facets cluster within domains and domains correlate as in the data. |
| raw-score marginals | fitted counts | V (data) | D1 | `to_percentiles` maps z through them, keeping real skew. |
| `ref_age` | 30 | U | — | Age at which variance splits exactly h2 / 1-h2. |
| `shared_env_var` | 0.0 | V | P3 | Shared family environment ≈ 0; kept off. |
| `env_variance_curve` | 0.20 @0 … 1.00 @30 … 1.45 @80 | D (shape U) | P2 | Must rise with age so the heritable share falls; concave so rank-order stability rises. |
| `maturation.N` | 0 @20, −0.25 @40, −0.30 @80 (z) | D (size U) | P4 | Direction only: N falls, most change 20–40. |
| `maturation.A` | 0 @20, +0.20 @40, +0.30 @80 | D (size U) | P4 | Direction only. |
| `maturation.C` | 0 @20, +0.25 @40, +0.30 @80 | D (size U) | P4 | Direction only. |
| Stability / Plasticity grouping | (−N, A, C) / (E, O), equal weights | D | P10 | Grouping from the literature; equal weights are a default. |
| `disinhibition_weights` | N5 +1, E5 +1, C5 −1, C6 −1, C3 −1 | U | — | **Owner to confirm or replace.** No recorded bucketing. |
| `delta_clamp` | 0.10 z | U | P6, P7 | Life-event effects are small; clamp keeps any caller honest. |
| `delta_age_window` | flat 1.0 | D (shape U) | P6 | Hook for "effects concentrate in young adulthood"; off by default. |
| `delta_reversion_halflife` | null (permanent) | U | — | Persistence of trait change is unknown. |
| `origin_offsets` | empty | U | P9 | Culture / attachment / role tables; never invented. |
| `audience.age_range` | 18–45 | U | — | Ages of simulated people; set per campaign audience. |
| `seed` | "markstrap" | — | — | Salt for all sha256 draws. |
