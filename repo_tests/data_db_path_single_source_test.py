# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The location of autobot_data.db comes from SSOT config, not hand-built paths.

`config.data_db` (`AUTOBOT_DATA_DB`) is the one place the shared SQLite store's
location is declared. `nl_database_service.py` and `conversation_file_manager.py`
already read it. `skills/db.py` reassembled the same path from `config.base_dir`
plus literal segments, so it could not be repointed with the others and a
deployment that moved the store would have left it reading a stale location.

A path reassembled from literals is a second declaration of one fact -- the same
shape as a package version restated in a second manifest. This guard keeps the
count at one.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOTS = ("autobot-backend", "autobot_shared")

#: `os.path.join(..., "autobot_data.db")` or `/ "autobot_data.db"` or an inline
#: literal path ending in it -- any construction of the location from parts.
_HAND_BUILT = re.compile(r"""["']autobot_data\.db["']""")

#: Reading the SSOT key is the sanctioned way, in any of its spellings.
_SSOT_READ = re.compile(r"config\.data_db|misc\.data_db|AUTOBOT_DATA_DB")


def _discover(root: Path) -> list[Path]:
    """Production Python under ROOTS -- the population this guard must reach."""
    found: list[Path] = []
    for sub in _ROOTS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = set(path.parts)
            if "tests" in parts or "node_modules" in parts or path.name.endswith("_test.py"):
                continue
            found.append(path)
    return found


def _all_python(root: Path) -> int:
    """Every `.py` under ROOTS, tests included -- the reference population."""
    total = 0
    for sub in _ROOTS:
        base = root / sub
        if base.is_dir():
            total += sum(1 for p in base.rglob("*.py") if "node_modules" not in p.parts)
    return total


#: Measured 2026-10-07: 2,776 production files of 4,754 total `.py` under ROOTS
#: -- 58.4%. Expressed as a fraction of that reference rather than an absolute
#: floor, because the reference exists and a fraction scales: an absolute number
#: goes stale the moment the tree grows, and the first version of this
#: declaration picked 2,000 "to leave room", which is 776 below the live
#: population -- precisely the weak floor `verify_floor` refuses, since it would
#: pass while most of the tree stopped being reached.
#:
#: 0.50 against a 0.584 reading: the band below is the share of production code
#: that could become test code before the sweep is meaningfully narrower.
PRODUCTION_PY = declare(
    "data-db-path-production-python",
    discover=_discover,
    reference=_all_python,
    min_fraction=0.50,
    roots=_ROOTS,
    what="production Python files scanned for a hand-built autobot_data.db path (#18060)",
)


def _production_sources():
    for path in PRODUCTION_PY.discover(repo_root()):
        yield path, path.read_text(encoding="utf-8", errors="replace")


def test_no_module_builds_the_data_db_path_without_reading_the_ssot_key():
    """A literal `autobot_data.db` is fine in prose or as a fallback beside the key."""
    offenders = []
    for path, text in _production_sources():
        if not _HAND_BUILT.search(text):
            continue
        if _SSOT_READ.search(text):
            continue  # reads the key; a literal fallback beside it is allowed
        rel = path.relative_to(repo_root())
        for lineno, line in enumerate(text.splitlines(), 1):
            if _HAND_BUILT.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:90]}")
    assert not offenders, (
        "these modules name autobot_data.db without reading `config.data_db` --\n"
        "the store's location is declared once, in SSOT config:\n  " + "\n  ".join(offenders)
    )


def test_the_matcher_discriminates():
    """Contrast pair -- otherwise a broken regex passes as happily as a clean tree."""
    assert _HAND_BUILT.search('os.path.join(base, "data", "autobot_data.db")')
    assert _HAND_BUILT.search("Path(d) / 'autobot_data.db'")
    assert not _HAND_BUILT.search("# the local autobot_data store")
    assert _SSOT_READ.search("_LOCAL_DB_PATH = config.data_db")
    assert not _SSOT_READ.search("config.base_dir")
