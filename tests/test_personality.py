"""Personality module tests (docs/research/personality_spec.md section 9). Population checks validate the
implementation of the design, not the science: they are reported, never tuned to pass."""
import ast
import inspect

import numpy as np
import pytest

from engine import llm, personality as P


def fresh(aid, age=0, **kw):
    return P.create_personality(aid, age, **kw)


def corr(a, b):
    return float(np.corrcoef(a, b)[0, 1])


# ---------- unit ----------

def test_thirty_facets_six_per_domain_and_derived_readouts_are_pure():
    assert len(P.FACETS) == 30 and all(len(i) == 6 for i in P.DOMAINS.values())
    z = P.personality_at(fresh("u1"), 30)
    assert P.domains(z) == P.domains(z.copy()) and P.metatraits(z) == P.metatraits(z.copy())


def test_changing_metatrait_weights_changes_only_derived_values(monkeypatch):
    s = fresh("u2")
    z, before = P.personality_at(s, 30), P.metatraits(P.personality_at(s, 30))
    monkeypatch.setitem(P.CFG, "disinhibition_weights", {"N5": 1})
    after = P.metatraits(z)
    assert np.array_equal(z, P.personality_at(s, 30))
    assert after["disinhibition"] != before["disinhibition"] and after["stability"] == before["stability"]


def test_personality_at_is_pure():
    s = fresh("u3")
    g, d = s.G.copy(), list(s.deltas)
    a, b = P.personality_at(s, 33.5), P.personality_at(s, 33.5)
    assert a.tobytes() == b.tobytes() and np.array_equal(s.G, g) and s.deltas == d


def test_order_independence_with_and_without_cache():
    ages = [10, 20, 30, 40]
    s1, s2 = fresh("u4"), fresh("u4")
    forward = {a: P.personality_at(s1, a) for a in ages}
    backward = {a: P.personality_at(s2, a) for a in reversed(ages)}
    for a in ages:
        direct = P.personality_at(fresh("u4"), a)  # empty cache
        assert forward[a].tobytes() == backward[a].tobytes() == direct.tobytes()


def test_skip_equivalence_exact():
    s = fresh("u5")
    for age in range(41):
        stepped = P.personality_at(s, age)
    assert stepped.tobytes() == P.personality_at(fresh("u5"), 40).tobytes()


def test_deltas_clamped_age_bounded_and_removable():
    s = fresh("u6")
    base25, base35 = P.personality_at(s, 25), P.personality_at(s, 35)
    P.apply_trait_delta(s, 30, "C", 5.0, "test")
    assert s.deltas[0][2] == P.CFG["delta_clamp"]
    assert np.array_equal(P.personality_at(s, 25), base25)
    moved = P.personality_at(s, 35) - base35
    assert np.allclose(moved[P.DOMAINS["C"]], P.CFG["delta_clamp"]) and np.allclose(np.delete(moved, P.DOMAINS["C"]), 0)
    s.deltas.clear()
    assert P.personality_at(s, 35).tobytes() == base35.tobytes()


# ---------- determinism ----------

def test_same_inputs_same_state_and_purposes_are_independent():
    assert np.array_equal(fresh("d1").G, fresh("d1").G) and not np.array_equal(fresh("d1").G, fresh("d2").G)
    draws = {p: P._draw("d1", 0, p) for p in P.PURPOSES}
    assert len({v.tobytes() for v in draws.values()}) == len(P.PURPOSES)
    with pytest.raises(AssertionError):
        P._draw("d1", 0, "made_up_purpose")


# ---------- no archetypes ----------

def test_static_no_archetype_branching():
    tree = ast.parse(inspect.getsource(P))
    banned = {"sex", "gender", "role", "occupation", "name", "agent_type", "mbti", "archetype"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.Compare, ast.match_case if hasattr(ast, "match_case") else ast.If)):
            words = {n.id.lower() for n in ast.walk(node) if isinstance(n, ast.Name)} | \
                    {n.attr.lower() for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not words & banned, ast.unparse(node)
    code = ast.unparse(tree).lower()
    assert "mbti" not in code.replace(P.__doc__.lower(), "") and "intj" not in code


def test_identical_seeds_ignore_non_personality_attributes():
    a = P.personality_at(fresh("same", context={"role": "ceo", "sex": "f"}), 30)
    b = P.personality_at(fresh("same"), 30)
    assert a.tobytes() == b.tobytes()  # no offset table configured -> attributes cannot matter


# ---------- cost ----------

def test_reads_are_lazy_cached_and_never_call_the_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: pytest.fail("personality must not call the LLM"))
    assert not [n for n in dir(P) if "tick" in n.lower() or n.lower().startswith("step")]
    s = fresh("c1")  # genesis draws G only
    calls = []
    real = P._draw
    monkeypatch.setattr(P, "_draw", lambda *a: calls.append(a) or real(*a))
    P.personality_at(s, 40)
    assert len(calls) == 41  # years 0..40, once
    calls.clear()
    P.personality_at(s, 40)
    assert calls == []       # cached: O(1)


# ---------- population validation ----------

N = 1500


def adult_domains(states, age=30):
    return np.array([list(P.domains(P.personality_at(s, age)).values()) for s in states])


def twin_r(pairs):
    a = adult_domains([p[0] for p in pairs])
    b = adult_domains([p[1] for p in pairs])
    return float(np.mean([corr(a[:, d], b[:, d]) for d in range(5)]))


def test_twin_study_recovers_h2_and_no_shared_environment():
    mz, dz = [], []
    for i in range(N):
        g = P.founder_genes(f"mzg{i}")
        mz.append((fresh(f"mz{i}a", genes=g), fresh(f"mz{i}b", genes=g)))
        parents = [P.founder_genes(f"dzm{i}"), P.founder_genes(f"dzf{i}")]
        dz.append(tuple(fresh(f"dz{i}{k}", genes=P.inherit_genes(parents, f"dz{i}{k}")) for k in "ab"))
    r_mz, r_dz = twin_r(mz), twin_r(dz)
    h2_hat = 2 * (r_mz - r_dz)
    print(f"\ntwin study: rMZ={r_mz:.3f} rDZ={r_dz:.3f} Falconer h2={h2_hat:.3f} (configured {P.CFG['h2']})")
    assert abs(h2_hat - P.CFG["h2"]) < 0.12
    assert abs(r_mz - P.CFG["h2"]) < 0.06 and abs(r_dz - P.CFG["h2"] / 2) < 0.06


def test_rank_order_stability_rises_and_heritable_share_falls_with_age():
    people = [fresh(f"r{i}") for i in range(N)]
    z = {a: np.array([P.personality_at(s, a) for s in people]) for a in (10, 15, 40, 45, 70)}
    stab = lambda a, b: np.mean([corr(z[a][:, f], z[b][:, f]) for f in range(30)])
    young, adult = stab(10, 15), stab(40, 45)
    print(f"\nrank-order r: 10->15 {young:.3f}, 40->45 {adult:.3f}")
    assert adult > young
    g = np.array([s.G for s in people]) * np.sqrt(P.CFG["h2"])
    share = lambda a: np.mean([np.var(g[:, f]) / np.var(z[a][:, f]) for f in range(30)])
    print(f"heritable share: age 10 {share(10):.2f}, 40 {share(40):.2f}, 70 {share(70):.2f}")
    assert share(10) > share(40) > share(70)


def test_maturity_direction_and_metatrait_clusters():
    people = [fresh(f"m{i}") for i in range(N)]
    d20, d40 = adult_domains(people, 20), adult_domains(people, 40)
    n, e, o, a, c = range(5)
    assert d40[:, n].mean() < d20[:, n].mean()
    assert d40[:, a].mean() > d20[:, a].mean() and d40[:, c].mean() > d20[:, c].mean()
    assert corr(-d40[:, n], d40[:, a]) > 0 and corr(d40[:, a], d40[:, c]) > 0 and corr(-d40[:, n], d40[:, c]) > 0
    assert corr(d40[:, e], d40[:, o]) > 0


def test_tails_come_from_the_shared_sampler():
    pct = [P.to_percentiles(P.personality_at(fresh(f"t{i}"), 30)) for i in range(N)]
    extreme = [p for p in pct if np.mean([p[f"A{k}"] for k in range(1, 7)]) < 20 and
               np.mean([p[f"O{k}"] for k in range(1, 7)]) > 70]
    assert extreme  # disagreeable + open people exist without any special code path
