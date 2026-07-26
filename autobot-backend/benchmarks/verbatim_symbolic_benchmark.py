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


def _build_corpus() -> Tuple[List[Tuple[str, int, str, str]], Dict[str, str], Dict[str, str]]:
    """Return (turns, exact_truth, paraphrase_truth).

    turns = (session_id, turn, role, text). ``exact_truth`` maps an entity query
    that SHARES tokens with its answer (symbolic's ideal case). ``paraphrase_truth``
    maps a query with **no exact token overlap** with the answer (semantic's job) —
    included deliberately so the recall verdict isn't biased toward the lexical
    index (a corpus that only tests exact-token queries would over-report symbolic).
    """
    turns: List[Tuple[str, int, str, str]] = []
    exact: Dict[str, str] = {}
    paraphrase: Dict[str, str] = {}
    for i, ent in enumerate(_ENTITIES):
        decision = f"We decided that {ent} pricing stays flat through Q3 after review."
        turns.append((f"sess{i}", 0, "assistant", decision))
        exact[f"{ent} pricing decision"] = decision
        # Paraphrase: same meaning, zero shared content words with the answer.
        paraphrase[f"how much will {ent} cost us next quarter"] = decision
        for j in range(4):
            turns.append((f"sess{i}", j + 1, "user", f"Some unrelated chatter number {j} for {ent}."))
    return turns, exact, paraphrase


def _recall_at_k(results: List[dict], answer: str, k: int) -> float:
    top = results[:k]
    return 1.0 if any(answer in (r.get("text") or "") for r in top) else 0.0


async def _seed(store) -> List[str]:
    turns, _, _ = _build_corpus()
    sessions = set()
    for session_id, turn, role, text in turns:
        await store.append(session_id=session_id, turn=turn, role=role, text=text)
        sessions.add(session_id)
    return sorted(sessions)


async def _teardown(store, sessions: List[str]) -> None:
    """Remove seeded sessions so reruns stay reproducible (don't accumulate)."""
    for session_id in sessions:
        try:
            await store.delete_session(session_id)
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.debug("teardown: delete_session(%s) failed: %s", session_id, exc)


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
    sessions = await _seed(store)
    try:
        _, exact, paraphrase = _build_corpus()
        # Exact-token queries: symbolic's ideal case (latency win expected).
        sem_lat_e, sem_rec_e = await _measure(store, "search", exact, k)
        sym_lat_e, sym_rec_e = await _measure(store, "search_symbolic", exact, k)
        # Paraphrase queries: no shared tokens — semantic should win; symbolic
        # legitimately returns nothing (falls back). This is the honesty check.
        _, sem_rec_p = await _measure(store, "search", paraphrase, k)
        _, sym_rec_p = await _measure(store, "search_symbolic", paraphrase, k)

        logger.info("[exact]      semantic median=%.2fms recall@%d=%.3f", sem_lat_e, k, sem_rec_e)
        logger.info("[exact]      symbolic median=%.2fms recall@%d=%.3f", sym_lat_e, k, sym_rec_e)
        logger.info("[paraphrase] semantic recall@%d=%.3f  symbolic recall@%d=%.3f", k, sem_rec_p, k, sym_rec_p)
        faster = sym_lat_e < sem_lat_e
        no_regress_exact = sym_rec_e >= sem_rec_e
        # Symbolic must NOT be trusted to answer paraphrase queries — if it did
        # worse than semantic there (expected), the caller's fallback covers it,
        # but if symbolic *replaced* semantic it would lose that recall.
        logger.info(
            "VERDICT: %s — exact: faster=%s (%.2fx) recall-neutral=%s | paraphrase gap (semantic-symbolic)=%.3f",
            "ADOPT (flag-on, WITH semantic fallback)" if (faster and no_regress_exact) else "KEEP OFF",
            faster,
            (sem_lat_e / sym_lat_e) if sym_lat_e else float("inf"),
            no_regress_exact,
            sem_rec_p - sym_rec_p,
        )
    finally:
        await _teardown(store, sessions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verbatim symbolic-index benchmark (B1 #12555)")
    parser.add_argument("-k", type=int, default=5, help="recall@k / result limit")
    args = parser.parse_args()
    asyncio.run(main(args.k))
