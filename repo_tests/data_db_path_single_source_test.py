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

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOTS = ("autobot-backend", "autobot_shared")

#: The filename, for the cheap pre-filter only. The real decision is made by
#: `_path_literals`, because a regex cannot tell a path from prose that happens
#: to name the file -- `description="... use 'local' for autobot_data.db"` is
#: documentation, not a construction, and matching it would make the guard cry
#: wolf on a Pydantic field description.
_FILENAME = "autobot_data.db"


def _path_literals(text: str) -> list[str]:
    """String constants that are a PATH ending in the filename, parsed as code.

    A path literal has no whitespace: `"data/autobot_data.db"` is a path,
    `"Use 'local' for autobot_data.db instead"` is a sentence. Asking the AST
    for string constants and then testing their shape separates the two; a
    regex over raw characters cannot, because both are quoted text.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if value.endswith(_FILENAME) and not any(c.isspace() for c in value):
            found.append(f"line {node.lineno}: {value}")
    return found


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


def _reads_the_ssot_key(text: str) -> bool:
    """Whether *text* contains an EXECUTABLE read of the key, parsed as code.

    A regex over raw text earns the exemption from a comment or a docstring:
    `# TODO: switch to config.data_db` would have exempted a module that never
    reads it. The exemption has to be a real attribute access or a real env
    lookup, so the question is asked of the AST, not of the characters.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False  # unparseable: cannot establish a read, so do not exempt
    for node in ast.walk(tree):
        # config.data_db / settings.misc.data_db / anything.data_db.
        # `ast.Load` specifically: `config.data_db = x` is a WRITE, and a module
        # that assigns the key while still building its own path has not read it.
        if isinstance(node, ast.Attribute) and node.attr == "data_db" and isinstance(node.ctx, ast.Load):
            return True
        # os.getenv("AUTOBOT_DATA_DB") / os.environ["AUTOBOT_DATA_DB"]
        if isinstance(node, ast.Constant) and node.value == "AUTOBOT_DATA_DB":
            return True
    return False


def test_no_module_builds_the_data_db_path_without_reading_the_ssot_key():
    """A literal `autobot_data.db` is fine in prose or as a fallback beside the key."""
    offenders = []
    for path, text in _production_sources():
        if _FILENAME not in text:
            continue  # cheap pre-filter; the AST pass below decides
        literals = _path_literals(text)
        if not literals:
            continue  # named only in prose or a docstring
        if _reads_the_ssot_key(text):
            continue  # reads the key; a literal fallback beside it is allowed
        rel = path.relative_to(repo_root())
        offenders.extend(f"{rel}:{lit}" for lit in literals)
    assert not offenders, (
        "these modules name autobot_data.db without reading `config.data_db` --\n"
        "the store's location is declared once, in SSOT config:\n  " + "\n  ".join(offenders)
    )


def test_the_matcher_discriminates():
    """Contrast pair -- otherwise a broken regex passes as happily as a clean tree."""
    assert _path_literals('os.path.join(base, "data", "autobot_data.db")')
    assert _path_literals("p = Path(d) / 'autobot_data.db'")
    # A path prefix inside the quotes is the same construction.
    assert _path_literals('p = Path("data/autobot_data.db")')
    # Prose naming the file is documentation, not a construction.
    assert not _path_literals("f = Field(description=\"Use 'local' for autobot_data.db\")")
    assert not _path_literals("# the local autobot_data store")
    assert _reads_the_ssot_key("_LOCAL_DB_PATH = config.data_db")
    assert _reads_the_ssot_key('p = os.getenv("AUTOBOT_DATA_DB")')
    assert not _reads_the_ssot_key("base = config.base_dir")
    # Assigning the key is not reading it.
    assert not _reads_the_ssot_key("config.data_db = '/tmp/x.db'")
    # The exemption is not earned by naming the key in prose.
    assert not _reads_the_ssot_key("# TODO: switch to config.data_db one day")
    assert not _reads_the_ssot_key('"""Docstring mentioning AUTOBOT_DATA_DB."""')
