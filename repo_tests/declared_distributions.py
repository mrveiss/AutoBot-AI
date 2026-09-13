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

Widened here to ``requirements*/*.txt``, then closed over ``-r``/``-c`` includes
so a manifest reached only through an include line is read too --
``constraints/shared.txt`` matches no filename pattern and is pulled in only by
``-c``. Measured after: 37 files, 197 distributions. The two halves overlap on
today's tree by design; the glob covers a manifest no include references yet,
the closure covers one no filename pattern can describe.

Consolidated into one module so the next divergence has nowhere to happen:
three copies of an oracle are three chances for one of them to be fixed alone.
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

#: ``-r``/``-c`` and their long spellings. A manifest reached only through an
#: include line need not be *named* anything in particular: ``constraints/
#: shared.txt`` is pulled in by ``-c`` and matches no filename pattern above,
#: so the closure is what makes the population complete rather than merely wide.
_INCLUDE = re.compile(r"^\s*-(?:r|c|-requirement|-constraint)\s*=?\s*(\S+)")


def _globbed(repo_root: Path) -> set[Path]:
    """Manifests found by filename or directory shape, before the include closure."""
    found: set[Path] = set()
    for pattern in MANIFEST_PATTERNS:
        for path in repo_root.rglob(pattern):
            if any(part in SKIP_PARTS for part in path.relative_to(repo_root).parts):
                continue
            found.add(path.resolve())
    return found


def _includes_of(path: Path) -> set[Path]:
    """Files this manifest pulls in with ``-r`` or ``-c``, resolved against its own dir."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    targets: set[Path] = set()
    for line in text.splitlines():
        match = _INCLUDE.match(line)
        if match:
            target = (path.parent / match.group(1)).resolve()
            if target.is_file():
                targets.add(target)
    return targets


def _manifests(repo_root: Path) -> list[Path]:
    """Every manifest in this checkout: globbed, then closed over ``-r``/``-c``."""
    found = _globbed(repo_root)
    pending = list(found)
    while pending:
        for target in _includes_of(pending.pop()):
            if target in found:
                continue
            if any(part in SKIP_PARTS for part in target.relative_to(repo_root).parts):
                continue
            found.add(target)
            pending.append(target)
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
