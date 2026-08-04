# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared utilities and constants for codebase analytics endpoints
"""

from pathlib import Path

from fastapi import HTTPException, Request, status

# Issue #13470: ImportContext, STDLIB_MODULES, COMMON_THIRD_PARTY,
# INTERNAL_MODULE_PREFIXES and is_external_module moved to
# autobot_shared/code_graph/resolver.py, the module both this endpoint and
# services/knowledge/code_indexer.py import the resolver from. Re-exported
# here unchanged so existing importers (dependencies.py, import_tree.py,
# call_graph_resolution_test.py) do not need to change their import path.
from autobot_shared.code_graph import (
    COMMON_THIRD_PARTY,
    INTERNAL_MODULE_PREFIXES,
    STDLIB_MODULES,
    ImportContext,
    is_external_module,
)
from autobot_shared.logging_manager import get_logger

# Logger
logger = get_logger(__name__)

# In-memory storage fallback
_in_memory_storage = {}

__all__ = [
    "COMMON_THIRD_PARTY",
    "INTERNAL_MODULE_PREFIXES",
    "STDLIB_MODULES",
    "ImportContext",
    "is_external_module",
    "authorize_source_access",
    "filter_problems_by_file_existence",
    "get_project_root",
    "require_source_access",
    "resolve_project_root",
    "resolve_scan_root",
    "resolve_source_root",
    "trigger_auto_index_if_unindexed",
]


async def resolve_source_root(source_id: "str | None") -> "Path | None":
    """Resolve the filesystem root for a given source ID.

    Issue #2760: Extracted from duplicated blocks in report.py and stats.py.
    Both endpoints contained identical 10-line blocks; this single helper
    replaces both.

    Args:
        source_id: The source identifier to look up, or None.

    Returns:
        Path to the source clone directory, or None if unresolvable.
    """
    if not source_id:
        return None
    try:
        from api.codebase_analytics.source_storage import get_source

        source = await get_source(source_id)
        if source and source.clone_path:
            return Path(source.clone_path)
    except Exception as exc:
        logger.debug("Could not resolve source root for %s: %s", source_id, exc)
    return None


async def resolve_scan_root(source_id: "str | None", use_default: bool = True) -> Path:
    """Resolve the filesystem root a source-scoped analytics scan must read.

    Issue #12330: Several filesystem-scanning analytics endpoints accepted a
    ``source_id`` "for API consistency" but ignored it, scanning AutoBot's own
    project root regardless of the selected code source -- cross-project data
    leakage. This resolves the requested source's clone path so scans are scoped
    to the caller's project.

    When ``source_id`` is falsy and ``use_default`` is True, the default (most
    recently indexed) source is resolved first to avoid silently mixing projects
    (matches the stats.py/report.py pattern, #2653). Falls back to the resolved
    AutoBot project root only when no source can be resolved (e.g. dev checkout
    with no registered sources).

    Issue #12393: The fallback uses ``resolve_project_root()`` (the git-walk-up /
    deployed ``code_source`` probe, #10730) rather than the plain
    ``get_project_root()`` (hardcoded ``parents[4]``). In the deployed standalone
    rsync layout ``parents[4]`` resolves to ``/opt/autobot`` -- not a git repo --
    so the plain helper silently scanned the wrong tree in production. In a dev
    checkout the two are equivalent, so this fallback is unchanged there.

    Args:
        source_id: The requested source identifier, or None.
        use_default: When True, resolve the default source if source_id is None.

    Returns:
        Path to the resolved source clone directory, or the resolved AutoBot
        project root.
    """
    if not source_id and use_default:
        try:
            from api.codebase_analytics.source_storage import get_default_source_id

            source_id = await get_default_source_id()
        except Exception as exc:
            logger.debug("resolve_scan_root: default source lookup failed: %s", exc)

    source_root = await resolve_source_root(source_id)
    if source_root:
        return source_root
    return Path(resolve_project_root())


# Issue #12364: sources whose auto-index has already been fired this process
# lifetime, so a burst of concurrent panel requests against an unindexed
# source triggers exactly one background indexing job instead of a flood of
# duplicate ones queued behind each other.
_auto_index_inflight: set[str] = set()


async def trigger_auto_index_if_unindexed(source_id: "str | None") -> None:
    """Fire-and-forget background indexing for a source with no index yet.

    Issue #12364: The indexed store is the single source of truth for
    converged analytics panels, but a freshly-registered source (or one
    registered before auto-index-on-registration existed) has nothing in it
    until a job runs. Panels fall back to the live filesystem walk for that
    one request *and* call this helper so the index gets populated in the
    background -- the next request (and every panel sharing the index) is
    then served from ChromaDB without anyone running a manual step.

    No-op when source_id is falsy, already triggered this process lifetime,
    or the source cannot be resolved to a clone path.
    """
    if not source_id or source_id in _auto_index_inflight:
        return
    _auto_index_inflight.add(source_id)
    try:
        from api.codebase_analytics.source_storage import get_source  # noqa: PLC0415

        source = await get_source(source_id)
        if not source or not source.clone_path:
            return

        from .sources import _trigger_indexing  # noqa: PLC0415

        await _trigger_indexing(source)
    except Exception as exc:
        logger.debug("Auto-index trigger failed for %s: %s", source_id, exc)


# Sentinel ownership id for an authenticated, non-service caller whose token
# carries no derivable identity. It can never equal a real ``owner_id``, so
# ``_is_visible`` denies another owner's PRIVATE source while still allowing
# public/shared/unowned ones — i.e. fail-closed, rather than the see-all that a
# bare ``None`` would grant (#12375 review item c).
_NO_OWNER_ID = "\x00::codebase-analytics::no-owner::"


def _caller_owner_id(user: "dict | None") -> "str | None":
    """Derive the caller's ownership identity from an auth user dict (#12358).

    Mirrors how ``owner_id`` is written when a source is created (see
    ``llc/api/sprints.py``): the user ``id``, falling back to the legacy
    ``user_id`` key.

    Only the internal service API key — which ``auth_middleware`` mints as
    ``{"service": True}`` with no id — is trusted for unscoped access (returns
    ``None`` → ``_is_visible`` see-all). Any *other* authenticated caller with no
    derivable id (e.g. an SLM-minted token carrying identity only in ``sub``)
    fails closed to ``_NO_OWNER_ID`` so admin role alone cannot expose another
    owner's PRIVATE source (#12375 review item c).
    """
    if not user:
        return None
    caller = str(user.get("id") or user.get("user_id") or "")
    if caller:
        return caller
    if user.get("service"):
        return None
    return _NO_OWNER_ID


async def authorize_source_access(source_id: "str | None", user: "dict | None") -> None:
    """Enforce that ``user`` may access the code source ``source_id`` (#12358).

    The codebase-analytics router is admin-gated, but an individual source can be
    PRIVATE to a specific owner; admin role alone must not expose one admin's
    private source to another. This reuses ``_is_visible`` — the same
    owner/shared/public model ``list_sources`` uses — so authorization stays
    consistent rather than inventing a parallel check.

    No-op when ``source_id`` is falsy (the scan then falls back to the caller's
    default source or the AutoBot project root). Raises 404 (never 403) on an
    unknown or unauthorized source so cross-tenant source existence is not
    disclosed, matching the repository's cross-tenant 404 convention.
    """
    if not source_id:
        return
    from api.codebase_analytics.source_storage import _is_visible, get_source

    source = await get_source(source_id)
    if source is None or not _is_visible(source, _caller_owner_id(user)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code source not found",
        )


async def require_source_access(request: Request) -> None:
    """FastAPI dependency: authorize the request's ``source_id`` against the caller.

    Applied at the analytics router level (#12358) so every source-scoped
    endpoint enforces per-source ownership on top of the admin gate. Reads
    ``source_id`` from the path or query string; endpoints that take source_id
    in the request body (the index and pattern-analyze endpoints) authorize it
    inside their own handlers via ``authorize_source_access`` (#12375).
    """
    from auth_middleware import get_current_user  # noqa: PLC0415

    user = await get_current_user(request)
    source_id = request.path_params.get("source_id") or request.query_params.get("source_id")
    await authorize_source_access(source_id, user)


# Project root helper
def get_project_root() -> Path:
    """
    Get the project root directory (4 levels up from this file).

    Returns:
        Path: Project root directory
    """
    return Path(__file__).resolve().parents[4]


def resolve_project_root() -> str:
    """
    Resolve the real git repository root robustly for dev and deployed layouts.

    Issue #10730: In the deployed layout autobot-backend is a standalone rsync
    dir under /opt/autobot, so ``parents[4]`` resolves to /opt/autobot which is
    NOT a git repo.  The actual repository lives in the sibling code_source dir.

    Strategy (first match wins):
    1. Walk up from this file looking for a directory containing `.git`.
    2. If no git repo found walking up, look for a sibling/child ``code_source``
       directory that itself contains ``.git`` (deployed layout).
    3. Fall back to ``parents[4]`` so dev checkouts keep working unchanged.

    Returns:
        str: Absolute path to the resolved project root.
    """
    current = Path(__file__).resolve()

    # Walk up the directory tree looking for a .git entry
    for parent in current.parents:
        if (parent / ".git").exists():
            logger.debug("resolve_project_root: found git root via walk-up: %s", parent)
            return str(parent)

    # No .git found walking up — check for deployed-layout sibling code_source
    # The walk exhausted all parents; the last ``parent`` is the filesystem root.
    # Re-anchor from the hard-coded parents[4] candidate and look around it.
    candidate = Path(__file__).resolve().parents[4]
    for probe in (
        candidate / "code_source",  # /opt/autobot/code_source
        candidate.parent / "code_source",  # one level higher, just in case
    ):
        if (probe / ".git").exists():
            logger.debug("resolve_project_root: found git root via code_source probe: %s", probe)
            return str(probe)

    # Final fallback: original parents[4] (works in dev checkout)
    logger.debug("resolve_project_root: falling back to parents[4]: %s", candidate)
    return str(candidate)


def filter_problems_by_file_existence(
    problems: list[dict],
    root_path: "Path | str | None" = None,
) -> list[dict]:
    """
    Filter LLM-indexed problems to only those whose file_path exists on disk.

    Issue #2724: The analytics problems scanner can produce findings that
    reference file paths that do not exist in the indexed repository (hallucinated
    paths from LLM analysis).  This validator resolves each relative file_path
    against root_path and drops any finding whose path cannot be confirmed on
    disk.  Validated findings receive ``file_verified: True`` so callers can
    distinguish them from raw, unvalidated data.

    Args:
        problems: List of problem dicts as returned by ChromaDB queries.
                  Each dict may contain a ``file_path`` key with a relative
                  path string.
        root_path: Absolute base directory to resolve relative paths against.
                   Defaults to the project root when None or empty.

    Returns:
        Filtered list containing only problems whose file_path exists.
        Each retained problem gains ``file_verified: True``.
    """
    if not problems:
        return problems

    base = Path(root_path) if root_path else Path(resolve_project_root())

    validated: list[dict] = []
    dropped = 0

    for problem in problems:
        fp = problem.get("file_path", "")
        if not fp:
            # No file_path — keep as-is (cannot validate)
            validated.append({**problem, "file_verified": False})
            continue

        full_path = (base / fp).resolve()
        if not full_path.is_relative_to(base.resolve()):
            dropped += 1
            logger.debug(
                "Dropping problem with path traversal outside root: %s (resolved: %s)",
                fp,
                full_path,
            )
            continue
        if full_path.exists():
            validated.append({**problem, "file_verified": True})
        else:
            dropped += 1
            logger.debug(
                "Dropping problem with non-existent file path: %s (resolved: %s)",
                fp,
                full_path,
            )

    if dropped:
        logger.info(
            "File path validation: dropped %d/%d problems with non-existent paths (#2724)",
            dropped,
            len(problems),
        )

    return validated
