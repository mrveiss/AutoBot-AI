# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cross-file anti-pattern analysis hook for the codebase indexing pipeline (#6747).

The production per-file analyzer at
``code_intelligence.anti_pattern_detector.AntiPatternDetector.analyze_file()``
cannot detect rules that need a whole-codebase class index — LSP violations
(parent class lookup) and consolidation opportunities (pairwise enum / class
shape comparison).  Those rules live in
``code_analysis.src.anti_pattern_detector.AntiPatternDetector`` and need a
directory-level pass.

This module bridges the gap: a single ``run_cross_file_analysis()`` call at
indexing finalization runs only the cross-file rules and persists every
finding to ChromaDB with ``type="problem"`` so they surface in
``/codebase/problems`` alongside the per-file results.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List  # noqa: F401  (List used in pub API)

from autobot_shared.async_compat import fire_and_forget, run_or_schedule
from autobot_shared.logging_manager import get_logger

from .chromadb_storage import make_problem_dict
from .fork_findings import ForkPassOutcome, run_fork_pass

logger = get_logger(__name__)


def _antipattern_to_problem(ap: Any, file_category: str = "code") -> Dict[str, Any]:
    """Map an ``AntiPatternInstance`` to the canonical problem dict (#6759).

    Uses ``make_problem_dict`` from ``chromadb_storage`` as the single source
    of truth for the schema, so adding a new persistence field only requires
    updating that factory.  We prefix the type with ``code_smell_`` to match
    the convention from ``analyzers.py::_run_anti_pattern_analysis``.
    """
    pattern_type = ap.pattern_type.value if hasattr(ap, "pattern_type") else "unknown"
    severity = ap.severity.value if hasattr(ap, "severity") else "medium"
    return make_problem_dict(
        problem_type=f"code_smell_{pattern_type}",
        severity=severity,
        file_path=getattr(ap, "file_path", ""),
        line=getattr(ap, "line_number", 0),
        description=getattr(ap, "description", ""),
        suggestion=getattr(ap, "suggestion", ""),
        file_category=file_category,
    )


async def _persist_to_chromadb(
    problems: List[Dict[str, Any]],
    source_id: str | None,
    progress_callback=None,
) -> int:
    """Append cross-file findings to the existing problems collection.

    Returns the number persisted.  Reuses the same batch helper as the
    per-file path so dashboard grouping/filtering is unchanged.
    """
    if not problems:
        return 0
    try:
        from api.codebase_analytics.problem_storage import (
            _store_problems_batch_to_chromadb,
        )
        from api.codebase_analytics.storage import get_code_collection_async

        collection = await get_code_collection_async()
        if collection is None:
            logger.warning("[#6747] Cross-file findings ready but ChromaDB unavailable; skipping persistence")
            return 0

        # The batch helper expects a starting index; we use a high offset to
        # avoid colliding with per-file problem IDs.  A timestamp-derived
        # base would also work; the dashboard just needs unique doc_ids.
        import time as _time

        start_idx = int(_time.time() * 1000) & 0x7FFFFFFF
        # #18055: forward the callback so this write ticks the watchdog too.
        # It runs in the finalize phase, which has no other progress signal --
        # an unreported write here is the same silent window that killed every
        # run before the per-file path was chunked.
        # The count comes from the writer, not from len(problems): a chunk
        # that fails is skipped, so reporting the offered count would log
        # more persisted than exists.
        return await _store_problems_batch_to_chromadb(
            collection,
            problems,
            start_idx,
            source_id=source_id,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        logger.warning("[#6747] Failed to persist cross-file findings: %s", exc)
        return 0


@dataclass
class CrossFileOutcome:
    """What the cross-file pass did, so a zero can be told from "did not run".

    ``ran`` is False when the AST rules never executed (``reason`` says why);
    it is True with ``findings == 0`` only when they ran and found nothing.
    ``forks`` reports the symbol-fork sweep the same way, with its own reach.
    """

    ran: bool
    reason: str | None = None
    findings: int = 0
    persisted: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    forks: ForkPassOutcome | None = None


async def _detect_findings(root_path: str, exclude_patterns: List[str] | None) -> tuple[List[Any] | None, str | None]:
    """The AST-rule findings, or ``(None, reason)`` when the rules did not run."""
    try:
        from code_analysis.src.anti_pattern_detector import AntiPatternDetector
    except Exception as exc:  # pragma: no cover — env-dependent import chain
        logger.warning("[#6747] AntiPatternDetector not importable: %s", exc)
        return None, f"AntiPatternDetector not importable: {exc}"
    try:
        detector = AntiPatternDetector()
        return await detector.analyze_cross_file_only(root_path=root_path, exclude_patterns=exclude_patterns), None
    except Exception as exc:
        logger.warning("[#6747] Cross-file analysis failed: %s", exc)
        return None, f"cross-file rules raised {type(exc).__name__}: {exc}"


async def analyze_cross_file_with_outcome(
    root_path: str,
    source_id: str | None = None,
    exclude_patterns: List[str] | None = None,
    progress_callback=None,
) -> CrossFileOutcome:
    """Run the cross-file rules AND the symbol-fork sweep; say what each did.

    Issue #6747 hooks this into the scanner finalize step so LSP, consolidation
    and (#18067) fork findings appear in ``/codebase/problems`` after every
    index run. Every path that previously returned a bare ``0`` -- rules not
    importable, root missing, rules raised, rules found nothing -- is now a
    distinct outcome, because "ran and found nothing" and "never ran" are
    different claims and the old ``0`` made them one.
    """
    if not Path(root_path).exists():
        logger.warning("[#6747] root_path %s does not exist; skipping", root_path)
        return CrossFileOutcome(ran=False, reason=f"root_path {root_path} does not exist")
    findings, reason = await _detect_findings(root_path, exclude_patterns)
    forks = await asyncio.to_thread(run_fork_pass, root_path)
    problems = [_antipattern_to_problem(ap) for ap in findings or []] + forks.problems
    by_type: Dict[str, int] = {}
    for problem in problems:
        by_type[problem["type"]] = by_type.get(problem["type"], 0) + 1
    persisted = await _persist_to_chromadb(problems, source_id=source_id, progress_callback=progress_callback)
    logger.info(
        "[#6747] Cross-file analysis: rules_ran=%s, %d findings (%d forks, fork_pass_ran=%s), %d persisted: %s",
        findings is not None,
        len(problems),
        forks.clusters,
        forks.ran,
        persisted,
        by_type,
    )
    return CrossFileOutcome(
        ran=findings is not None,
        reason=reason,
        findings=len(problems),
        persisted=persisted,
        by_type=by_type,
        forks=forks,
    )


async def run_cross_file_analysis(
    root_path: str,
    source_id: str | None = None,
    exclude_patterns: List[str] | None = None,
    progress_callback=None,
) -> int:
    """Number of findings persisted; the outcome itself is the richer answer.

    Kept for callers that only want the count. A caller that must tell "found
    nothing" from "did not run" uses :func:`analyze_cross_file_with_outcome`.
    """
    outcome = await analyze_cross_file_with_outcome(root_path, source_id, exclude_patterns, progress_callback)
    return outcome.persisted


def schedule_cross_file_analysis(
    root_path: str,
    source_id: str | None = None,
) -> None:
    """Fire-and-forget launcher for the cross-file pass.

    Mirrors the pattern used by ``progress_tracker._invalidate_quality_cache``:
    detect a running event loop and spawn a task on it; fall back to
    ``asyncio.run`` in sync contexts.  Never raises into the caller — scan
    finalization must not fail because the cross-file pass had a hiccup.
    """
    try:
        asyncio.get_running_loop()
        fire_and_forget(run_cross_file_analysis(root_path, source_id), name="cross-file-analysis")
    except RuntimeError:
        try:
            run_or_schedule(run_cross_file_analysis(root_path, source_id))
        except Exception as exc:  # pragma: no cover
            logger.warning("[#6747] Cross-file analysis scheduling failed: %s", exc)
