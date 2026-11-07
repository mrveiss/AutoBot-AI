# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Retrieval benchmark gate: ablation runner + accept/reject decision.

Issue #20949 (child of #20948). Extends ``rag_benchmarks`` (reuses its
``BenchmarkSplit`` and deterministic dev/test split) with recall@k, MRR,
nDCG@k, grounding and contradiction rates per technique combination and per
bucket. The retriever is injected, so CI runs it on a fixture index and an
operator runs it on a real index through read-only calls.

Run (see ``main``):
    python -m knowledge.retrieval_gate run --gold GOLD.jsonl --retriever pkg.mod:factory --out report.json
    python -m knowledge.retrieval_gate gate --baseline base.json --candidate cand.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from knowledge.rag_benchmarks import BenchmarkSplit, _deterministic_dev_test_split
from knowledge.retrieval_metrics import (
    contradiction_rate,
    grounding_rate,
    mean,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

logger = get_logger(__name__)

#: Cutoff for recall@k / nDCG@k.
RETRIEVAL_GATE_K = int(os.getenv("AUTOBOT_RETRIEVAL_GATE_K", "5"))
#: Every one of the five metrics must improve by at least this much (absolute).
RETRIEVAL_GATE_MIN_IMPROVEMENT = env_float_clamped(
    "AUTOBOT_RETRIEVAL_GATE_MIN_IMPROVEMENT", 0.01, 0.0, 1.0, positive_finite=True
)
#: Share of queries routed to the dev split.
RETRIEVAL_GATE_DEV_FRACTION = float(os.getenv("AUTOBOT_RETRIEVAL_GATE_DEV_FRACTION", "0.8"))

#: Directory holding versioned gold sets (fixture_<bucket>.jsonl shipped; live_<bucket>.jsonl owner-curated).
RETRIEVAL_GATE_GOLD_DIR = os.getenv("AUTOBOT_RETRIEVAL_GATE_GOLD_DIR") or os.path.join(
    os.path.dirname(__file__), "benchmarks", "gold"
)
#: Which gold set the CLI loads by default: "fixture" (CI) or "live" (owner-curated).
RETRIEVAL_GATE_GOLD_SET = os.getenv("AUTOBOT_RETRIEVAL_GATE_GOLD_SET", "fixture")

BUCKETS = ("docs", "code", "memory", "facts", "patterns", "cross")
TECHNIQUES = ("dense", "bm25", "fusion", "rerank", "query_expansion", "graph", "memory", "cache")
#: metric name -> True when higher is better
METRICS: Dict[str, bool] = {
    "recall": True,
    "mrr": True,
    "ndcg": True,
    "grounding": True,
    "contradiction": False,
}
#: Production default toggles; the baseline every combination is compared with.
DEFAULT_TOGGLES: Dict[str, bool] = {
    "dense": True, "bm25": True, "fusion": True, "rerank": True,
    "query_expansion": True, "graph": False, "memory": False, "cache": False,
}  # fmt: skip


@dataclass(frozen=True)
class GoldQuery:
    """One labelled query. ``gold`` maps doc id -> graded gain."""

    id: str
    query: str
    bucket: str
    gold: Mapping[str, float]


@dataclass
class RetrievalOutput:
    """What a retriever returns for one query under one toggle set."""

    ranked_ids: List[str]
    chunks: List[str] = field(default_factory=list)
    answer: Optional[str] = None


class Retriever(Protocol):
    def __call__(self, query: GoldQuery, toggles: Mapping[str, bool], k: int) -> RetrievalOutput: ...


def load_gold(path: str) -> List[GoldQuery]:
    """Load a JSONL gold set: {id, query, bucket, gold: {doc_id: gain} | [doc_id]}."""
    out: List[GoldQuery] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["bucket"] not in BUCKETS:
                raise ValueError(f"unknown bucket {row['bucket']!r} in query {row['id']!r}")
            gold = row["gold"]
            if not gold:
                raise ValueError(f"query {row['id']!r} has empty gold")
            gains = {d: 1.0 for d in gold} if isinstance(gold, list) else {d: float(g) for d, g in gold.items()}
            out.append(GoldQuery(row["id"], row["query"], row["bucket"], gains))
    return out


def load_gold_set(gold_set: str = RETRIEVAL_GATE_GOLD_SET, directory: str = RETRIEVAL_GATE_GOLD_DIR) -> List[GoldQuery]:
    """Load ``<gold_set>_<bucket>.jsonl`` for every bucket present in *directory*.

    Missing bucket files are skipped; an empty result raises, so a mistyped set
    name cannot silently pass the gate on zero queries.
    """
    out: List[GoldQuery] = []
    for bucket in BUCKETS:
        path = os.path.join(directory, f"{gold_set}_{bucket}.jsonl")
        if os.path.exists(path):
            out.extend(load_gold(path))
    if not out:
        raise FileNotFoundError(f"no {gold_set}_<bucket>.jsonl files in {directory}")
    return out


def gold_fingerprint(queries: Sequence[GoldQuery]) -> str:
    """SHA-256 over the canonical gold rows, so reports can prove the same gold set."""
    rows = sorted((q.id, q.query, q.bucket, sorted(q.gold.items())) for q in queries)
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def select_split(queries: Sequence[GoldQuery], split: BenchmarkSplit) -> List[GoldQuery]:
    """Filter to the deterministic dev/test split (same hashing as rag_benchmarks)."""
    if split == BenchmarkSplit.ALL:
        return list(queries)
    ids = _deterministic_dev_test_split([q.id for q in queries], RETRIEVAL_GATE_DEV_FRACTION)
    keep = ids["dev_ids"] if split == BenchmarkSplit.DEV else ids["test_ids"]
    return [q for q in queries if q.id in keep]


def _score_one(q: GoldQuery, out: RetrievalOutput, k: int) -> Dict[str, Optional[float]]:
    return {
        "recall": recall_at_k(out.ranked_ids, q.gold, k),
        "mrr": reciprocal_rank(out.ranked_ids, q.gold),
        "ndcg": ndcg_at_k(out.ranked_ids, q.gold, k),
        "grounding": grounding_rate(out.answer, out.chunks) if out.answer else None,
    }


def evaluate(
    retriever: Retriever,
    queries: Sequence[GoldQuery],
    toggles: Mapping[str, bool],
    k: int = RETRIEVAL_GATE_K,
    has_conflict: Optional[Callable[[Sequence[str]], bool]] = None,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Score one toggle set: {bucket|'overall': {metric: value|None}}."""
    per_bucket: Dict[str, List[Dict[str, Optional[float]]]] = {}
    texts: Dict[str, List[Sequence[str]]] = {}
    for q in queries:
        out = retriever(q, toggles, k)
        per_bucket.setdefault(q.bucket, []).append(_score_one(q, out, k))
        context = list(out.chunks) + ([out.answer] if out.answer else [])
        texts.setdefault(q.bucket, []).append(context)
    result: Dict[str, Dict[str, Optional[float]]] = {}
    for bucket, rows in per_bucket.items():
        result[bucket] = {m: mean(r[m] for r in rows) for m in METRICS if m != "contradiction"}
        result[bucket]["contradiction"] = contradiction_rate(texts[bucket], has_conflict) if has_conflict else None
    result["overall"] = _overall(result, {b: len(r) for b, r in per_bucket.items()})
    return result


def _overall(
    by_bucket: Mapping[str, Mapping[str, Optional[float]]], sizes: Mapping[str, int]
) -> Dict[str, Optional[float]]:
    """Query-weighted mean across buckets, per metric (None-aware)."""
    out: Dict[str, Optional[float]] = {}
    for m in METRICS:
        pairs = [(by_bucket[b][m], n) for b, n in sizes.items() if by_bucket[b][m] is not None]
        total = sum(n for _, n in pairs)
        out[m] = sum(v * n for v, n in pairs) / total if total else None
    return out


def ablation_combinations(
    base: Mapping[str, bool] = DEFAULT_TOGGLES,
    extra: Sequence[Mapping[str, bool]] = (),
) -> List[Tuple[str, Dict[str, bool]]]:
    """Default, then each technique flipped alone, then caller-supplied combos."""
    combos: List[Tuple[str, Dict[str, bool]]] = [("default", dict(base))]
    for t in TECHNIQUES:
        flipped = dict(base)
        flipped[t] = not base[t]
        combos.append((f"{'-' if base[t] else '+'}{t}", flipped))
    for i, toggles in enumerate(extra, start=1):
        combos.append((f"custom{i}", {**base, **toggles}))
    return combos


def run_ablation(
    retriever: Retriever,
    queries: Sequence[GoldQuery],
    split: BenchmarkSplit = BenchmarkSplit.TEST,
    combos: Optional[Sequence[Tuple[str, Mapping[str, bool]]]] = None,
    k: int = RETRIEVAL_GATE_K,
    has_conflict: Optional[Callable[[Sequence[str]], bool]] = None,
) -> Dict[str, Any]:
    """Run every combination and report metrics plus delta vs 'default'."""
    chosen = select_split(queries, split)
    combos = list(combos) if combos is not None else ablation_combinations()
    runs = {
        name: {"toggles": dict(t), "metrics": evaluate(retriever, chosen, t, k, has_conflict)} for name, t in combos
    }
    base = runs["default"]["metrics"]
    for run in runs.values():
        run["delta_vs_default"] = {
            scope: {m: _delta(run["metrics"][scope][m], base[scope][m]) for m in METRICS} for scope in run["metrics"]
        }
    return {
        "k": k,
        "split": split.value,
        "held_out": split == BenchmarkSplit.TEST,
        "query_count": len(chosen),
        "gold_sha256": gold_fingerprint(queries),
        "runs": runs,
    }


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None else a - b


@dataclass
class GateVerdict:
    accepted: bool
    reasons: List[str]


def gate_decision(
    baseline: Mapping[str, Optional[float]],
    candidate: Mapping[str, Optional[float]],
    min_improvement: float = RETRIEVAL_GATE_MIN_IMPROVEMENT,
) -> GateVerdict:
    """Accept only if the candidate beats the baseline on ALL five metrics (#20948).

    "Beats" means better by at least ``min_improvement`` (lower is better for
    contradiction). A metric that is None on either side is a rejection: an
    unmeasured metric cannot show improvement.
    """
    reasons: List[str] = []
    for m, higher_better in METRICS.items():
        b, c = baseline.get(m), candidate.get(m)
        bad = [side for side, v in (("baseline", b), ("candidate", c)) if v is not None and not math.isfinite(v)]
        if bad:
            reasons.append(f"{m}: non-finite value in {' and '.join(bad)}")
            continue
        if b is None or c is None:
            side = "baseline" if b is None else "candidate"
            reasons.append(f"{m}: not measured in {side}")
            continue
        gain = (c - b) if higher_better else (b - c)
        if gain < min_improvement:
            reasons.append(
                f"{m}: improved by {gain:.4f}, need >= {min_improvement} (baseline {b:.4f}, candidate {c:.4f})"
            )
    return GateVerdict(accepted=not reasons, reasons=reasons)


def gate_reports(baseline: Mapping[str, Any], candidate: Mapping[str, Any], run: str = "default") -> GateVerdict:
    """Compare overall metrics of *run* in a candidate report against the baseline report's default."""
    if baseline.get("split") != "test" or candidate.get("split") != "test":
        return GateVerdict(False, ["both reports must be produced on the held-out test split"])
    if baseline.get("k") != candidate.get("k"):
        return GateVerdict(False, ["reports use different k"])
    if not baseline.get("gold_sha256") or baseline.get("gold_sha256") != candidate.get("gold_sha256"):
        return GateVerdict(False, ["reports were not produced from the same gold set"])
    if not baseline.get("query_count") or baseline.get("query_count") != candidate.get("query_count"):
        return GateVerdict(False, ["reports differ in query_count, or it is zero"])
    b = baseline["runs"]["default"]["metrics"]["overall"]
    c = candidate["runs"][run]["metrics"]["overall"]
    return gate_decision(b, c)


def _load_factory(spec: str) -> Callable[[], Retriever]:
    mod, _, attr = spec.partition(":")
    return getattr(importlib.import_module(mod), attr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="retrieval_gate")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the ablation and write a JSON report")
    r.add_argument("--gold", help="one JSONL file; default: the configured gold set in the gold dir")
    r.add_argument("--retriever", required=True, help="module:factory returning a Retriever")
    r.add_argument("--split", default="test", choices=[s.value for s in BenchmarkSplit])
    r.add_argument("--out", required=True)
    g = sub.add_parser("gate", help="exit 1 unless candidate beats baseline")
    g.add_argument("--baseline", required=True)
    g.add_argument("--candidate", required=True)
    g.add_argument("--run", default="default")
    args = p.parse_args(argv)
    if args.cmd == "run":
        report = run_ablation(
            _load_factory(args.retriever)(),
            load_gold(args.gold) if args.gold else load_gold_set(),
            BenchmarkSplit(args.split),
        )
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
        return 0
    with open(args.baseline, encoding="utf-8") as fh:
        base = json.load(fh)
    with open(args.candidate, encoding="utf-8") as fh:
        cand = json.load(fh)
    verdict = gate_reports(base, cand, args.run)
    logger.info("retrieval gate accepted=%s reasons=%s", verdict.accepted, verdict.reasons)
    sys.stdout.write(json.dumps({"accepted": verdict.accepted, "reasons": verdict.reasons}) + "\n")
    return 0 if verdict.accepted else 1


if __name__ == "__main__":
    sys.exit(main())
