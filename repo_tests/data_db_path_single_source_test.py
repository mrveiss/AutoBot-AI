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

from repo_tests._paths import repo_root

_ROOTS = ("autobot-backend", "autobot_shared")

#: `os.path.join(..., "autobot_data.db")` or `/ "autobot_data.db"` or an inline
#: literal path ending in it -- any construction of the location from parts.
_HAND_BUILT = re.compile(r"""["']autobot_data\.db["']""")

#: Reading the SSOT key is the sanctioned way, in any of its spellings.
_SSOT_READ = re.compile(r"config\.data_db|misc\.data_db|AUTOBOT_DATA_DB")


def _production_sources():
    root = repo_root()
    for sub in _ROOTS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = set(path.parts)
            if "tests" in parts or "node_modules" in parts or path.name.endswith("_test.py"):
                continue
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
