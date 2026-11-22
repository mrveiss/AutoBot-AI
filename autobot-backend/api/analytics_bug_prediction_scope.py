# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source scoping for the bug-prediction routes (#18030, #20513).

The routes used to take a filesystem ``path`` (default ``"."``) and scanned the server's own
working directory whichever source the page had selected. The tree they read is now the selected
source's clone, resolved here and nowhere else; everything they cache or store is keyed by that
source.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from api.codebase_analytics.endpoints.shared import resolve_scan_root
from api.source_scope import require_source_id
from autobot_shared.security.path_http import require_contained_relative_path

_WHAT = "bug-prediction scan"


async def scan_root(source_id: str) -> Path:
    """The selected source's clone directory: the only tree a bug-prediction scan may read.

    Raises ``UnresolvedSourceError`` (404) when the source has no checkout, and ``ValueError``
    for an empty or malformed id; there is no fallback to the install tree or the working directory.
    """
    return await resolve_scan_root(require_source_id(source_id, _WHAT))


def scoped_key(base: str, source_id: str) -> str:
    """``base`` for ONE source, so no result or history is shared between sources."""
    return f"{base}:{require_source_id(source_id, 'bug-prediction key')}"


def file_in_source(root: Path, file_path: str) -> Path:
    """``file_path`` (relative to the source root) as an existing path inside that root, or a 4xx."""
    return require_contained_relative_path(file_path, root, must_exist=True)


def contained_files(root: Path, candidates: Iterable[Path]) -> Iterator[Path]:
    """The candidates that are real paths inside ``root``: a symlink, or anything resolving outside, is dropped.

    ``rglob`` follows a symlinked ``*.py`` to its target, and the analysis would then read a host file
    the source never contained.
    """
    real_root = root.resolve()
    for candidate in candidates:
        try:
            if not candidate.is_symlink() and candidate.resolve().is_relative_to(real_root):
                yield candidate
        except OSError:
            continue


def relative_to_root(file_path: Path, root: Path) -> str:
    """The repo-relative POSIX path git reports for ``file_path``."""
    return file_path.relative_to(root).as_posix()
