# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""B1 (#12555) micro-benchmark — symbolic drawer index vs semantic verbatim search.

The merge gate for ``AUTOBOT_VERBATIM_SYMBOLIC_INDEX``: flip the flag on in
production ONLY if this benchmark shows the symbolic path is **latency-faster
with no recall@k regression** against the existing semantic ``search`` on a
representative corpus. Otherwise leave it off and record the numbers on #12555.

Requires a live Redis + ChromaDB (it exercises the real ``VerbatimStore``), so
it is a standalone script, not a unit test.

Usage::

    AUTOBOT_VERBATIM_SYMBOLIC_INDEX=1 python -m benchmarks.verbatim_symbolic_benchmark
"""

import argparse
import asyncio
import statistics
import time
from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from memory.verbatim_store import get_verbatim_store

logger = get_logger(__name__)

# Synthetic corpus: each entity gets a "decision" turn (relevant) plus filler.
_ENTITIES = [f"ClientAcme{i:03d}" for i in range(50)]


def _build_corpus() -> Tuple[List[Tuple[str, int, str, str]], Dict[str, str]]:
    """Return (turns, ground_truth). turns = (session_id, turn, role, text);
    ground_truth maps an entity query -> the chunk text that answers it."""
    turns: List[Tuple[str, int, str, str]] = []
    truth: Dict[str, str] = {}
    for i, ent in enumerate(_ENTITIES):
        decision = f"We decided that {ent} pricing stays flat through Q3 after review."
        turns.append((f"sess{i}", 0, "assistant", decision))
        truth[f"{ent} pricing decision"] = decision
        # filler turns that mention the entity only incidentally
        for j in range(4):
            turns.append((f"sess{i}", j + 1, "user", f"Some unrelated chatter number {j} for {ent}."))
    return turns, truth


def _recall_at_k(results: List[dict], answer: str, k: int) -> float:
    top = results[:k]
    return 1.0 if any(answer in (r.get("text") or "") for r in top) else 0.0


async def _seed(store) -> None:
    turns, _ = _build_corpus()
    for session_id, turn, role, text in turns:
        await store.append(session_id=session_id, turn=turn, role=role, text=text)


async def _measure(store, method_name: str, queries: Dict[str, str], k: int) -> Tuple[float, float]:
    """Return (median_latency_ms, recall_at_k) for the named store method."""
    method = getattr(store, method_name)
    latencies: List[float] = []
    recalls: List[float] = []
    for query, answer in queries.items():
        t0 = time.perf_counter()
        results = await method(query, limit=k)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        recalls.append(_recall_at_k(results or [], answer, k))
    return statistics.median(latencies), sum(recalls) / len(recalls)


async def main(k: int) -> None:
    store = await get_verbatim_store()
    logger.info("Seeding synthetic verbatim corpus ...")
    await _seed(store)
    _, truth = _build_corpus()

    sem_lat, sem_recall = await _measure(store, "search", truth, k)
    sym_lat, sym_recall = await _measure(store, "search_symbolic", truth, k)

    logger.info("semantic : median=%.2fms recall@%d=%.3f", sem_lat, k, sem_recall)
    logger.info("symbolic : median=%.2fms recall@%d=%.3f", sym_lat, k, sym_recall)
    faster = sym_lat < sem_lat
    no_regress = sym_recall >= sem_recall
    verdict = "ADOPT (flag-on)" if (faster and no_regress) else "KEEP OFF"
    logger.info(
        "VERDICT: %s — faster=%s (%.2fx), recall-neutral=%s",
        verdict,
        faster,
        (sem_lat / sym_lat) if sym_lat else float("inf"),
        no_regress,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verbatim symbolic-index benchmark (B1 #12555)")
    parser.add_argument("-k", type=int, default=5, help="recall@k / result limit")
    args = parser.parse_args()
    asyncio.run(main(args.k))
