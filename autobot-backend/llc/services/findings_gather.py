# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Gather analytics findings for a project, scoped by code source (#11271).

Real analytics fetch call (from api/codebase_analytics/endpoints/stats.py):
  - ``get_code_collection()`` from ``api.codebase_analytics.storage`` (sync, run via asyncio.to_thread)
  - ``_fetch_problems_from_chromadb(collection, problem_type=None, source_id=<str>)``
    from ``api.codebase_analytics.endpoints.stats``
  Both are lazy-imported here to avoid the heavy ``api.codebase_analytics.__init__``
  which pulls in routes/tasks/audit chains.

Patch targets for tests:
  - ``api.codebase_analytics.source_storage.get_source``
  - ``api.codebase_analytics.endpoints.stats._fetch_problems_from_chromadb``
  - ``api.codebase_analytics.storage.get_code_collection``
"""

import asyncio
import logging
from pathlib import Path

from autobot_shared.status_enums import Severity

logger = logging.getLogger(__name__)

#: The severities a code-source finding carries, most severe first. Order comes from
#: ``Severity.rank`` -- this names the subset, it does not restate the ordering (#19336).
_GATHERED = tuple(sorted((Severity.HIGH, Severity.MEDIUM, Severity.LOW), key=lambda s: -s.rank))


def _at_or_above(sev: str) -> tuple[str, ...]:
    """Return severity values that are >= ``sev`` in priority order (high first).

    >>> _at_or_above("medium")
    ('high', 'medium')
    >>> _at_or_above("low")
    ('high', 'medium', 'low')
    >>> _at_or_above("high")
    ('high',)
    """
    floor = Severity.rank_of(sev)
    if floor < 0:
        logger.warning("gather_findings: unknown min_severity %r — keeping all findings", sev)
        floor = Severity.UNKNOWN.rank  # unknown severity → keep all
    return tuple(s.value for s in _GATHERED if s.rank >= floor)


async def gather_findings(project, min_severity: str, session) -> list[dict]:
    """Fetch analytics findings for *project*, filtered to >= *min_severity*.

    Resolves ``project.code_source_id`` → CodeSource via source_storage,
    then calls the real ChromaDB query used by the /problems endpoint.

    Args:
        project: ORM row or SimpleNamespace with a ``code_source_id`` attribute.
        min_severity: Minimum severity to include (``"high"``, ``"medium"``, or ``"low"``).
        session: AsyncSession (passed through; not used directly here but required by
                 the service-layer contract so callers have a consistent signature).

    Returns:
        List of finding dicts with keys: type, severity, file_path, line_number,
        description, suggestion — ordered high → medium → low, then by insertion order.

    Raises:
        ValueError: When ``project.code_source_id`` is None or the CodeSource is
                    missing / not in ``ready`` status.
    """
    code_source_id = getattr(project, "code_source_id", None)
    if not code_source_id:
        raise ValueError(f"Project {getattr(project, 'id', project)!r} has no code_source_id")

    source = await _get_source(code_source_id)
    if source is None:
        raise ValueError(f"CodeSource {code_source_id!r} not found")
    status = getattr(source, "status", None)
    status_val = status.value if hasattr(status, "value") else str(status)
    if status_val != "ready":
        raise ValueError(f"CodeSource {code_source_id!r} is not ready (status={status_val!r})")

    # Pass the source's checkout as source_root so the analytics query's
    # file-existence filter (#2724) drops findings referencing files that no
    # longer exist in THIS source — matching the /problems endpoint.
    clone_path = getattr(source, "clone_path", None)
    source_root = Path(clone_path) if clone_path else None
    raw = await _fetch_all_problems(code_source_id, source_root)
    keep = set(_at_or_above(min_severity))
    filtered = [f for f in raw if f.get("severity", "").lower() in keep]
    filtered.sort(key=lambda f: -Severity.rank_of(f.get("severity", "low")))

    logger.info(
        "gather_findings: source=%s min=%s raw=%d kept=%d",
        code_source_id,
        min_severity,
        len(raw),
        len(filtered),
    )
    return filtered


async def _get_source(code_source_id: str):
    """Lazy-import get_source and call it."""
    from api.codebase_analytics.source_storage import get_source  # noqa: PLC0415

    return await get_source(code_source_id)


async def _fetch_all_problems(source_id: str, source_root: Path | None) -> list[dict]:
    """Lazy-import ChromaDB helpers and return all problems for *source_id*.

    Mirrors the /problems endpoint (stats.py):
      1. get_code_collection()  — sync, run in thread
      2. _fetch_problems_from_chromadb(collection, problem_type=None, source_id=source_id,
         source_root=source_root)  — source_root drives the file-existence filter (#2724)
    Returns an empty list when ChromaDB is unavailable.
    """
    from api.codebase_analytics.endpoints.stats import (  # noqa: PLC0415
        _fetch_problems_from_chromadb,
    )
    from api.codebase_analytics.storage import get_code_collection  # noqa: PLC0415

    collection = await asyncio.to_thread(get_code_collection)
    if not collection:
        logger.warning("_fetch_all_problems: ChromaDB collection unavailable for source=%s", source_id)
        return []
    return _fetch_problems_from_chromadb(collection, problem_type=None, source_id=source_id, source_root=source_root)
