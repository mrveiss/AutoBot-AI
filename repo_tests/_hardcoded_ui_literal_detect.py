# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enumeration and per-file scan for the hard-coded UI text ratchet (#12732).

The detectors are `repo_tests/_ui_literal_scan.py`, shared with the SLM console's
zero-baseline guard (#15665); this module adds only what the ratchet owns: the
filesystem walk over both apps, the boundary predicate, and the reach
declaration. `hardcoded_ui_literal_ratchet_12732_test.py` re-derives the
template and attribute kinds with `repo_tests/_ui_literal_rederive.py` -- a
different enumeration (`git ls-files`) and a different matcher (regex).

The boundary and the shrink rule are stated in
`repo_tests/_hardcoded_ui_literal_baseline.py`.
"""

from __future__ import annotations

from pathlib import Path

from repo_tests._reach import declare
from repo_tests._ui_literal_scan import literals_in, ts_literals

APP_TREES: tuple[Path, ...] = (
    Path("autobot-frontend/src"),
    Path("autobot-slm-frontend/src"),
)
_EXCLUDED_NAME_PARTS = (".stories.", ".spec.", ".test.")


def is_scanned_path(rel: str) -> bool:
    """The boundary predicate; the re-derivation restates it rather than import it."""
    parts = rel.split("/")
    name = parts[-1]
    return not ("__tests__" in parts or any(p in name for p in _EXCLUDED_NAME_PARTS))


def scanned_files(root: Path) -> list[str]:
    """Repo-relative POSIX paths of every `.vue` file in scope, sorted."""
    out: list[str] = []
    for tree in APP_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*.vue"):
            rel = path.relative_to(root).as_posix()
            if "node_modules" not in path.parts and is_scanned_path(rel):
                out.append(rel)
    return sorted(out)


#: The `.ts` modules scanned, script kind only (#19885): the formatters, whose option
#: objects (`nullText:`, `zeroText:`) are where a size or empty-value text was held.
FORMATTER_GLOB = "utils/format*.ts"


def formatter_files(root: Path) -> list[str]:
    """Repo-relative POSIX paths of every scanned formatter module, sorted."""
    out = [
        path.relative_to(root).as_posix()
        for tree in APP_TREES
        if (root / tree).is_dir()
        for path in (root / tree).glob(FORMATTER_GLOB)
    ]
    return sorted(rel for rel in out if is_scanned_path(rel))


def scan(root: Path) -> dict[str, list[tuple[str, str]]]:
    """Per-file (kind, literal) for every file that has at least one."""
    out: dict[str, list[tuple[str, str]]] = {}
    sources = [(rel, literals_in) for rel in scanned_files(root)] + [
        (rel, ts_literals) for rel in formatter_files(root)
    ]
    for rel, detector in sources:
        found = detector((root / rel).read_text(encoding="utf-8", errors="replace"))
        if found:
            out[rel] = found
    return out


REACH_UI_LITERAL_FILES = declare(
    "hardcoded-ui-literal-scan",
    discover=scanned_files,
    floor=571,  # mid-window: population 591, window (551, 591)
    growth=40,
    skips=0,
    what=".vue files scanned for hard-coded UI text",
    roots=tuple(f"{tree.as_posix()}/" for tree in APP_TREES),
)
