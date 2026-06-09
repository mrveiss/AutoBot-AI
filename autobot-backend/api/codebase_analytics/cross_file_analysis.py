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
from pathlib import Path
from typing import Any, Dict, List  # noqa: F401  (List used in pub API)

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger

from .chromadb_storage import make_problem_dict

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
) -> int:
    """Append cross-file findings to the existing problems collection.

    Returns the number persisted.  Reuses the same batch helper as the
    per-file path so dashboard grouping/filtering is unchanged.
    """
    if not problems:
        return 0
    try:
        from api.codebase_analytics.chromadb_storage import (
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
        await _store_problems_batch_to_chromadb(collection, problems, start_idx, source_id=source_id)
        return len(problems)
    except Exception as exc:
        logger.warning("[#6747] Failed to persist cross-file findings: %s", exc)
        return 0


async def run_cross_file_analysis(
    root_path: str,
    source_id: str | None = None,
    exclude_patterns: List[str] | None = None,
) -> int:
    """Run the four cross-file rules over ``root_path`` and persist findings.

    Issue #6747: Hooks into the scanner finalize step so LSP and consolidation
    findings appear in ``/codebase/problems`` after every index run.

    Args:
        root_path: Directory the scan ran over.
        source_id: Optional source scope tag for per-source filtering.
        exclude_patterns: Optional override for the analyzer's exclude list.
            Pass ``None`` (default) to use the analyzer's production defaults
            (skips ``test_``, ``__pycache__``, ``node_modules``, ...).  Tests
            can pass ``["__pycache__"]`` to keep fixtures discoverable when
            they live under pytest's ``tmp_path``-rooted ``test_*`` dirs.

    Returns:
        Number of findings persisted to ChromaDB.
    """
    try:
        from code_analysis.src.anti_pattern_detector import AntiPatternDetector
    except Exception as exc:  # pragma: no cover — env-dependent import chain
        logger.warning("[#6747] AntiPatternDetector not importable: %s", exc)
        return 0

    if not Path(root_path).exists():
        logger.warning("[#6747] root_path %s does not exist; skipping", root_path)
        return 0

    detector = AntiPatternDetector()
    try:
        findings = await detector.analyze_cross_file_only(root_path=root_path, exclude_patterns=exclude_patterns)
    except Exception as exc:
        logger.warning("[#6747] Cross-file analysis failed: %s", exc)
        return 0

    if not findings:
        logger.info("[#6747] Cross-file analysis: 0 findings")
        return 0

    problems = [_antipattern_to_problem(ap) for ap in findings]
    persisted = await _persist_to_chromadb(problems, source_id=source_id)
    logger.info(
        "[#6747] Cross-file analysis: %d findings, %d persisted to ChromaDB",
        len(findings),
        persisted,
    )
    return persisted


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
        loop = asyncio.get_running_loop()
        loop.create_task(run_cross_file_analysis(root_path, source_id))
    except RuntimeError:
        try:
            run_or_schedule(run_cross_file_analysis(root_path, source_id))
        except Exception as exc:  # pragma: no cover
            logger.warning("[#6747] Cross-file analysis scheduling failed: %s", exc)
