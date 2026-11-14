# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the retrieval benchmark gate (#20949) against hand-computed values."""

from __future__ import annotations

import json
import math

import pytest

from knowledge import retrieval_gate as rg
from knowledge.rag_benchmarks import BenchmarkSplit
from knowledge.retrieval_metrics import (
    contradiction_rate,
    grounding_rate,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

# Hand-computed 3-query fixture (k=3):
#   Q1 gold {a,b} ranked [x,a,y,b,z]: recall 1/2, RR 1/2, nDCG (1/log2 3)/(1+1/log2 3)
#   Q2 gold {c}   ranked [c,..]     : 1, 1, 1
#   Q3 gold {d}   ranked [p,q,r]    : 0, 0, 0
Q1 = (["x", "a", "y", "b", "z"], {"a", "b"})
Q2 = (["c", "m", "n"], {"c"})
Q3 = (["p", "q", "r"], {"d"})
NDCG1 = (1 / math.log2(3)) / (1 + 1 / math.log2(3))


def test_recall_hand_values():
    assert recall_at_k(*Q1[:1], Q1[1], 3) == pytest.approx(0.5)
    assert recall_at_k(Q1[0], Q1[1], 5) == pytest.approx(1.0)
    assert recall_at_k(Q3[0], Q3[1], 3) == 0.0
    assert recall_at_k(["a"], set(), 3) == 0.0
    mean = sum(recall_at_k(r, g, 3) for r, g in (Q1, Q2, Q3)) / 3
    assert mean == pytest.approx(0.5)


def test_mrr_hand_values():
    assert reciprocal_rank(*Q1) == pytest.approx(0.5)
    assert reciprocal_rank(*Q2) == 1.0
    assert reciprocal_rank(*Q3) == 0.0
    assert sum(reciprocal_rank(r, g) for r, g in (Q1, Q2, Q3)) / 3 == pytest.approx(0.5)


def test_ndcg_hand_values():
    assert NDCG1 == pytest.approx(0.386853, abs=1e-6)
    assert ndcg_at_k(Q1[0], Q1[1], 3) == pytest.approx(NDCG1)
    assert ndcg_at_k(Q2[0], Q2[1], 3) == pytest.approx(1.0)
    assert ndcg_at_k(Q3[0], Q3[1], 3) == 0.0
    assert sum(ndcg_at_k(r, g, 3) for r, g in (Q1, Q2, Q3)) / 3 == pytest.approx((NDCG1 + 1) / 3)


def test_ndcg_graded_and_duplicates():
    # DCG = 1 + 3/log2(3); ideal = 3 + 1/log2(3)
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert ndcg_at_k(["b", "a"], {"a": 3, "b": 1}, 2) == pytest.approx(expected)
    assert expected == pytest.approx(0.796708, abs=1e-6)
    # a repeated doc earns gain once
    assert ndcg_at_k(["a", "a"], {"a": 1}, 2) == pytest.approx(1.0)


def test_grounding_rate_hand_value():
    answer = "Redis runs on port 6379. The moon is cheese."
    assert grounding_rate(answer, ["Redis runs on port 6379 by default"]) == pytest.approx(0.5)
    assert grounding_rate(answer, []) == 0.0
    assert grounding_rate("", ["x"]) is None


def test_contradiction_rate_hand_value():
    texts = [["a"], ["b"], ["c"], ["a", "b"]]
    assert contradiction_rate(texts, lambda t: len(t) == 2) == pytest.approx(0.25)
    assert contradiction_rate([], lambda t: True) is None


# ---- ablation / gate ------------------------------------------------------

GOLD = [
    rg.GoldQuery("q1", "one", "docs", {"a": 1.0, "b": 1.0}),
    rg.GoldQuery("q2", "two", "code", {"c": 1.0}),
    rg.GoldQuery("q3", "three", "facts", {"d": 1.0}),
]
RANKINGS = {"q1": ["x", "a", "y", "b", "z"], "q2": ["c", "m", "n"], "q3": ["p", "q", "r"]}


def fake_retriever(query, toggles, k):
    """Rerank toggle moves gold first; otherwise the fixture ranking."""
    ranked = list(RANKINGS[query.id])
    if toggles["rerank"]:
        gold = [d for d in ranked if d in query.gold]
        ranked = gold + [d for d in ranked if d not in query.gold]
    return rg.RetrievalOutput(ranked, ["Redis runs on port 6379"], "Redis runs on port 6379.")


def test_evaluate_overall_matches_hand_values():
    off = {**rg.DEFAULT_TOGGLES, "rerank": False}
    m = rg.evaluate(fake_retriever, GOLD, off, k=3)
    assert m["overall"]["recall"] == pytest.approx(0.5)
    assert m["overall"]["mrr"] == pytest.approx(0.5)
    assert m["overall"]["ndcg"] == pytest.approx((NDCG1 + 1) / 3)
    assert m["overall"]["grounding"] == pytest.approx(1.0)
    assert m["overall"]["contradiction"] is None
    assert m["docs"]["recall"] == pytest.approx(0.5)
    assert m["facts"]["mrr"] == 0.0


def test_ablation_reports_every_metric_and_delta():
    report = rg.run_ablation(fake_retriever, GOLD, BenchmarkSplit.ALL, k=3, has_conflict=lambda t: False)
    names = list(report["runs"])
    assert names[0] == "default"
    assert len(names) == 1 + len(rg.TECHNIQUES)
    for run in report["runs"].values():
        for scope in run["metrics"].values():
            assert set(scope) == set(rg.METRICS)
    drop = report["runs"]["-rerank"]["delta_vs_default"]["overall"]
    assert drop["recall"] < 0 and drop["mrr"] < 0 and drop["ndcg"] < 0
    assert report["runs"]["default"]["metrics"]["overall"]["contradiction"] == 0.0
    assert report["held_out"] is False


def test_split_is_deterministic_and_test_marks_held_out():
    a = rg.select_split(GOLD, BenchmarkSplit.TEST)
    assert a == rg.select_split(GOLD, BenchmarkSplit.TEST)
    dev = rg.select_split(GOLD, BenchmarkSplit.DEV)
    assert {q.id for q in a}.isdisjoint({q.id for q in dev})
    assert rg.run_ablation(fake_retriever, GOLD, BenchmarkSplit.TEST, k=3)["held_out"] is True


def test_gate_decision_requires_all_five_metrics_to_improve():
    base = {"recall": 0.5, "mrr": 0.5, "ndcg": 0.5, "grounding": 0.8, "contradiction": 0.1}
    better = {"recall": 0.6, "mrr": 0.6, "ndcg": 0.6, "grounding": 0.9, "contradiction": 0.05}
    assert rg.gate_decision(base, better).accepted
    for m in rg.METRICS:  # each single metric failing to improve rejects
        same = {**better, m: base[m]}
        v = rg.gate_decision(base, same)
        assert not v.accepted and any(r.startswith(m) for r in v.reasons)
    assert not rg.gate_decision(base, base).accepted
    # contradiction is lower-is-better: a rise rejects
    assert not rg.gate_decision(base, {**better, "contradiction": 0.2}).accepted
    # margin: below min_improvement is not an improvement
    tiny = {k: v + (-0.001 if k == "contradiction" else 0.001) for k, v in base.items()}
    assert not rg.gate_decision(base, tiny, min_improvement=0.01).accepted
    assert rg.gate_decision(base, tiny, min_improvement=0.0005).accepted


def test_gate_decision_none_on_either_side_rejects():
    base = {"recall": 0.5, "mrr": 0.5, "ndcg": 0.5, "grounding": 0.8, "contradiction": 0.1}
    better = {"recall": 0.6, "mrr": 0.6, "ndcg": 0.6, "grounding": 0.9, "contradiction": 0.05}
    assert not rg.gate_decision(base, {**better, "grounding": None}).accepted
    assert not rg.gate_decision({**base, "contradiction": None}, better).accepted


def test_gate_reports_requires_held_out_and_same_k():
    test_split = rg.run_ablation(fake_retriever, GOLD, BenchmarkSplit.TEST, k=3)
    all_split = rg.run_ablation(fake_retriever, GOLD, BenchmarkSplit.ALL, k=3)
    assert not rg.gate_reports(all_split, test_split).accepted
    assert not rg.gate_reports(test_split, {**test_split, "k": 9}).accepted


def test_cli_run_and_gate_exit_codes(tmp_path, monkeypatch, capsys):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        "\n".join(json.dumps({"id": q.id, "query": q.query, "bucket": q.bucket, "gold": list(q.gold)}) for q in GOLD),
        encoding="utf-8",
    )
    monkeypatch.setattr(rg, "_load_factory", lambda spec: (lambda: fake_retriever))
    out = tmp_path / "r.json"
    assert rg.main(["run", "--gold", str(gold), "--retriever", "x:y", "--split", "test", "--out", str(out)]) == 0
    # default vs itself: no improvement -> exit 1; "-rerank" vs default is a regression -> exit 1
    assert rg.main(["gate", "--baseline", str(out), "--candidate", str(out)]) == 1
    assert rg.main(["gate", "--baseline", str(out), "--candidate", str(out), "--run=-rerank"]) == 1


def test_load_gold_rejects_unknown_bucket(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(json.dumps({"id": "1", "query": "q", "bucket": "nope", "gold": ["a"]}), encoding="utf-8")
    with pytest.raises(ValueError):
        rg.load_gold(str(p))


# ---- shipped gold sets ----------------------------------------------------


def test_every_shipped_gold_file_is_valid():
    import glob
    import os

    corpus = set(__import__("knowledge.retrieval_gate_fixture", fromlist=["x"]).load_corpus())
    files = sorted(glob.glob(os.path.join(rg.RETRIEVAL_GATE_GOLD_DIR, "*_*.jsonl")))
    gold_files = [f for f in files if not f.endswith("fixture_corpus.jsonl")]
    names = {os.path.basename(f) for f in gold_files}
    assert names >= {f"fixture_{b}.jsonl" for b in rg.BUCKETS}
    seen = set()
    for path in gold_files:
        bucket = os.path.basename(path).split("_", 1)[1][: -len(".jsonl")]
        assert bucket in rg.BUCKETS, path
        queries = rg.load_gold(path)
        assert queries, path
        for q in queries:
            assert q.bucket == bucket and q.query and q.gold, (path, q.id)
            assert q.id not in seen
            seen.add(q.id)
            if path.rsplit("/", 1)[-1].startswith("fixture_"):
                assert set(q.gold) <= corpus, (q.id, set(q.gold) - corpus)
    # both splits get queries, so the held-out set is non-empty
    allq = rg.load_gold_set("fixture")
    assert rg.select_split(allq, BenchmarkSplit.TEST) and rg.select_split(allq, BenchmarkSplit.DEV)


def test_load_gold_set_unknown_set_raises():
    with pytest.raises(FileNotFoundError):
        rg.load_gold_set("nope")


def test_fixture_run_is_deterministic_and_finds_gold():
    from knowledge.retrieval_gate_fixture import factory

    queries = rg.load_gold_set("fixture")
    one = rg.run_ablation(factory(), queries, BenchmarkSplit.ALL, k=3)
    two = rg.run_ablation(factory(), queries, BenchmarkSplit.ALL, k=3)
    assert one == two
    overall = one["runs"]["default"]["metrics"]["overall"]
    assert overall["recall"] > 0.8 and overall["mrr"] > 0.7
    assert overall["grounding"] is None and overall["contradiction"] is None
    assert set(one["runs"]["default"]["metrics"]) == set(rg.BUCKETS) | {"overall"}


# ---- review fixes ---------------------------------------------------------

_BASE = {"recall": 0.5, "mrr": 0.5, "ndcg": 0.5, "grounding": 0.8, "contradiction": 0.1}
_BETTER = {"recall": 0.6, "mrr": 0.6, "ndcg": 0.6, "grounding": 0.9, "contradiction": 0.05}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_gate_decision_rejects_non_finite(bad, side):
    base, cand = dict(_BASE), dict(_BETTER)
    (base if side == "baseline" else cand)["ndcg"] = bad
    v = rg.gate_decision(base, cand)
    assert not v.accepted and any(r.startswith("ndcg: non-finite") for r in v.reasons)


@pytest.mark.parametrize("raw", ["0", "-0.5", "nan", "inf"])
def test_min_improvement_never_zero_negative_or_non_finite(raw, monkeypatch):
    import importlib

    monkeypatch.setenv("AUTOBOT_RETRIEVAL_GATE_MIN_IMPROVEMENT", raw)
    try:
        mod = importlib.reload(rg)
        assert mod.RETRIEVAL_GATE_MIN_IMPROVEMENT == 0.01
    finally:
        monkeypatch.delenv("AUTOBOT_RETRIEVAL_GATE_MIN_IMPROVEMENT")
        importlib.reload(rg)


def test_gate_reports_requires_same_gold_and_non_zero_queries():
    rep = rg.run_ablation(fake_retriever, GOLD, BenchmarkSplit.TEST, k=3)
    assert rep["gold_sha256"] == rg.gold_fingerprint(GOLD)
    other = rg.run_ablation(fake_retriever, GOLD[:2], BenchmarkSplit.TEST, k=3)
    v = rg.gate_reports(rep, {**rep, "gold_sha256": "0" * 64})
    assert not v.accepted and "same gold set" in v.reasons[0]
    assert not rg.gate_reports(rep, {**rep, "query_count": rep["query_count"] + 1}).accepted
    zero = {**rep, "query_count": 0}
    v = rg.gate_reports(zero, zero)
    assert not v.accepted and "query_count" in v.reasons[0]
    assert other["gold_sha256"] != rep["gold_sha256"]


def test_load_gold_rejects_empty_gold(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(json.dumps({"id": "1", "query": "q", "bucket": "docs", "gold": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="empty gold"):
        rg.load_gold(str(p))
