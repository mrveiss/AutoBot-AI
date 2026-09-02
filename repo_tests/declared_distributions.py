# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The declaration oracle three guards ask "is this distribution declared?" (#15518).

``embedded_python_dependency_declared_test.py`` (#14876),
``hard_optional_dependency_declared_test.py`` and
``infra_script_imports_resolve_test.py`` (#14518) each answer that question the
same way, and each carried its own byte-identical copy of the function that
answers it. All three globbed ``requirements*.txt`` **by filename**, so all
three missed every manifest under ``requirements-ci/`` -- ``agent.txt``,
``ai-ml.txt``, ``langchain.txt`` and nine more are requirements files that are
not *named* ``requirements*``. Measured: 20 of the 32 tracked manifests were
read, 184 distributions declared.

The direction of that miss is false positives -- an import declared only in
``requirements-ci/ai-ml.txt`` reads as declared nowhere -- so it broke nothing
visible, and none of the three floors could see the gap: each asserted it had
read ``>= 15`` files and it had read 24, comfortably above a floor set while
blind. ``scripts/check_constraint_drift.py`` had already worked this out and
globs both shapes; the guards had not.

Widened here to ``requirements*/*.txt`` as well, and consolidated into one
module so the next divergence has nowhere to happen: three copies of an oracle
are three chances for one of them to be fixed alone.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Directory names excluded by path RELATIVE to the repository root, never
#: absolute: a checkout that itself lives under a directory named ``venv`` would
#: otherwise match every file, skip everything, and report an empty declaration
#: set -- which turns every third-party import into a finding (#14484).
SKIP_PARTS = frozenset({".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"})

#: Both shapes a requirements file takes here. ``requirements*.txt`` anywhere,
#: plus every ``*.txt`` inside a ``requirements*`` directory -- the second is
#: what ``requirements-ci/ai-ml.txt`` needs and what #15518 was filed about.
#: Kept in step with ``scripts/check_constraint_drift.py``.
MANIFEST_PATTERNS: tuple[str, ...] = ("requirements*.txt", "requirements*/*.txt", "pyproject.toml")

#: First token on a requirements line, quoted or not, is the distribution name.
_NAME = re.compile(r'^["\']?([A-Za-z0-9][A-Za-z0-9._-]*)')


def _manifests(repo_root: Path) -> list[Path]:
    """Every requirements/pyproject file in this checkout, de-duplicated and ordered."""
    found: set[Path] = set()
    for pattern in MANIFEST_PATTERNS:
        for path in repo_root.rglob(pattern):
            if any(part in SKIP_PARTS for part in path.relative_to(repo_root).parts):
                continue
            found.add(path)
    return sorted(found)


def declared_distributions(repo_root: Path) -> tuple[set[str], int]:
    """Every distribution named by a manifest in this checkout, and the file count.

    The count is the population floor's subject: an oracle that read nothing
    would declare nothing and make every third-party import a finding, so the
    callers assert on it before trusting the set.
    """
    names: set[str] = set()
    files = 0
    for path in _manifests(repo_root):
        files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = _NAME.match(line)
            if match:
                names.add(match.group(1).lower().replace("-", "_"))
    return names, files
