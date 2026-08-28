# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15181: a test module's ``Path(__file__)``-anchored data file must be there.

``autobot-infrastructure/shared/tests/test_redis_db_ssot.py`` resolved its SSOT
YAML with ``parents[2]`` where ``parents[1]`` is the file's directory-of-record.
The anchor was one level too high for the whole life of the file, so its fixture
asserted on a path no checkout has ever had and all four tests ERRORED at setup.
They had never executed once, and nothing said so: an error at fixture setup in a
tree that no routine invocation collects is indistinguishable from silence.

That is the third defect of this exact shape found in that one directory (#15161
repointed a conftest at a module that had moved and a directory that does not
exist; #15182 covered the vacuous assertion filed alongside this). Three is not
evidence there are only three, which is why this sweep is repository-wide rather
than scoped to the file that prompted it.

WHAT IS CHECKED
---------------
Every ``test_*.py`` / ``*_test.py`` / ``conftest.py`` on disk is parsed. Any
expression of the form ``Path(__file__)[.resolve()][.parent... | .parents[N]] /
"literal" / ...`` whose final segment names a FILE (it carries one of the
suffixes below) is resolved and must exist.

Reached by parsing, not by running: a module behind a collection error, excluded
by a marker, or in a tree no workflow names is swept exactly like any other. That
matters here specifically — this defect class lives where nothing runs.

WHAT IS DELIBERATELY NOT CHECKED, AND WHY
-----------------------------------------
* Directory anchors (a final segment with no suffix). Tests legitimately build
  output and scratch directories that do not exist until something writes them —
  ``scripts/test_first_remediation.py:32`` names ``.worktrees``, which lives
  outside the checkout by design. Requiring those to exist would be wrong.
* Anything under a ``scripts/`` directory. Those modules are named ``test_*`` but
  are operator utilities, not collected tests; they probe for absent paths on
  purpose and branch on ``.exists()``.
* Expressions with a non-literal segment (an f-string, a variable, a ``tmp_path``
  fixture). Their value is not knowable statically, and guessing would produce
  false failures that train people to add allowlist entries.
* ``os.path.dirname(__file__)`` chains. None exist in a test module today; the
  ``Path`` form is the one the codebase uses and the one the defect appeared in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from autobot_shared.paths import project_root

#: Final segments with one of these suffixes name a file that must be on disk.
#: A segment with any other suffix, or none, is treated as a directory and skipped
#: — see "WHAT IS DELIBERATELY NOT CHECKED" above.
DATA_SUFFIXES = frozenset(
    {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".txt", ".csv", ".sql", ".env", ".md", ".xml", ".sh", ".py"}
)

SKIP_DIR_PARTS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", "scripts", "dist", "build"})

#: Floor on the swept population. The failure mode a path guard has is not a false
#: failure but a silent shrink to nothing — an extractor that stops matching reports
#: a clean tree. Measured at 111 on the branch that added this file. RATCHET: raise
#: it when the population genuinely grows; lower it only with a stated reason.
MIN_SWEPT_EXPRESSIONS = 100

#: Anchors that are already wrong on this branch and are NOT fixed here, because
#: they sit outside #15181's scope. Each is a real defect of the same shape, found
#: by this guard's first run and reported rather than absorbed. Remove an entry
#: when its site is fixed; never add one to make a new failure pass.
#:
#: * ``autobot-backend/tests/unit/test_agents_status_pg_optional.py:54`` builds
#:   ``parents[3] / "api" / "agent_org.py"``. The module is at
#:   ``autobot-backend/api/agent_org.py``, which is ``parents[2]``; ``parents[3]``
#:   is the repository root. It is inert today only because the enclosing
#:   ``_import_func`` discards the spec it just built and returns ``None``.
KNOWN_UNRESOLVED = frozenset({"autobot-backend/tests/unit/test_agents_status_pg_optional.py"})


def _anchor_levels(node: ast.AST) -> int | None:
    """Directories up from the module file, or None if not a ``Path(__file__)`` anchor."""
    levels = 0
    while True:
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            index = node.slice
            if not (isinstance(index, ast.Constant) and isinstance(index.value, int)):
                return None
            levels += index.value + 1
            node = node.value.value
        elif isinstance(node, ast.Attribute) and node.attr == "parent":
            levels += 1
            node = node.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
            node = node.func.value
        elif _is_path_of_file(node):
            return levels
        else:
            return None


def _is_path_of_file(node: ast.AST) -> bool:
    """True for the literal expression ``Path(__file__)``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "__file__"
    )


def _literal_segments(node: ast.BinOp) -> tuple[ast.AST, list[str]] | None:
    """Peel ``base / "a" / "b"`` into its base and its literal segments."""
    segments: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        segments.append(node.right.value)
        node = node.left
    segments.reverse()
    return node, segments


def _outermost_divisions(tree: ast.AST) -> list[ast.BinOp]:
    """Every ``/`` chain, counted once at its outermost node rather than per link."""
    nested = {
        id(node.left)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.left, ast.BinOp)
    }
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and id(node) not in nested
    ]


def _test_modules(root: Path) -> list[Path]:
    """Every module pytest would treat as a test file, plus conftest."""
    return sorted(
        path
        for path in root.rglob("*.py")
        if not SKIP_DIR_PARTS.intersection(path.parts)
        and (path.name.startswith("test_") or path.name.endswith("_test.py") or path.name == "conftest.py")
    )


def _file_anchors(module: Path) -> list[tuple[int, str, Path]]:
    """(lineno, expression-as-written, resolved path) for each anchored data file."""
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found: list[tuple[int, str, Path]] = []
    for division in _outermost_divisions(tree):
        peeled = _literal_segments(division)
        if peeled is None:
            continue
        base, segments = peeled
        levels = _anchor_levels(base)
        if levels is None or not segments or Path(segments[-1]).suffix not in DATA_SUFFIXES:
            continue
        anchor = module.resolve()
        for _ in range(levels):
            anchor = anchor.parent
        found.append((division.lineno, "/".join(segments), anchor.joinpath(*segments)))
    return found


def _sweep(root: Path) -> list[tuple[Path, int, str, Path]]:
    return [(module, *anchor) for module in _test_modules(root) for anchor in _file_anchors(module)]


@pytest.fixture(scope="module")
def swept() -> list[tuple[Path, int, str, Path]]:
    return _sweep(project_root())


class TestEveryAnchoredDataFileExists:
    def test_no_test_module_anchors_a_data_file_that_is_not_there(self, swept) -> None:
        root = project_root()
        missing = [
            f"{module.relative_to(root)}:{line}  ->  {resolved}"
            for module, line, _expr, resolved in swept
            if not resolved.exists() and str(module.relative_to(root)) not in KNOWN_UNRESOLVED
        ]
        assert not missing, (
            "These test modules resolve a data file that does not exist. A fixture that "
            "cannot find its data errors at setup, which reads as silence in a tree "
            "nothing routinely collects (#15181):\n  " + "\n  ".join(missing)
        )

    def test_the_swept_population_has_not_collapsed(self, swept) -> None:
        """A guard that matches nothing reports a clean tree. Assert it still matches."""
        assert len(swept) >= MIN_SWEPT_EXPRESSIONS, (
            f"only {len(swept)} anchored data-file expressions were found, below the "
            f"recorded floor of {MIN_SWEPT_EXPRESSIONS} — the extractor has probably "
            "stopped matching rather than the codebase having shrunk"
        )

    def test_the_issue_15181_site_is_swept_and_resolves(self, swept) -> None:
        """The originating file, asserted by name so the sweep cannot lose it."""
        root = project_root()
        site = "autobot-infrastructure/shared/tests/test_redis_db_ssot.py"
        hits = [entry for entry in swept if str(entry[0].relative_to(root)) == site]
        assert len(hits) == 1, f"{site} contributes {len(hits)} anchored data files to the sweep, expected 1"
        assert hits[0][3].exists(), f"{site} still resolves to a missing file: {hits[0][3]}"
        assert hits[0][3].name == "redis-databases.yaml"

    def test_the_grandfathered_set_is_down_only(self, swept) -> None:
        """Every allowlisted module must still be swept, and still be broken.

        An entry that no longer fails is an entry to delete — otherwise the set
        grows into a place to hide new defects.
        """
        root = project_root()
        still_missing = {
            str(module.relative_to(root)) for module, _line, _expr, resolved in swept if not resolved.exists()
        }
        stale = KNOWN_UNRESOLVED - still_missing
        assert not stale, f"these entries are fixed and must be removed from KNOWN_UNRESOLVED: {sorted(stale)}"
        assert len(KNOWN_UNRESOLVED) <= 1, "KNOWN_UNRESOLVED is a down-only ratchet; a new defect is fixed, not listed"


class TestTheExtractorItself:
    """The sweep above is only worth its floor if the extractor reads real syntax."""

    @pytest.mark.parametrize(
        "expression,levels",
        [
            ('Path(__file__).parent / "a.yaml"', 1),
            ('Path(__file__).parent.parent / "a.yaml"', 2),
            ('Path(__file__).resolve().parents[0] / "a.yaml"', 1),
            ('Path(__file__).resolve().parents[1] / "a.yaml"', 2),
            ('Path(__file__).resolve().parents[2] / "config" / "a.yaml"', 3),
        ],
    )
    def test_each_anchor_spelling_resolves_to_the_right_depth(self, expression: str, levels: int) -> None:
        division = ast.parse(expression, mode="eval").body
        peeled = _literal_segments(division)
        assert peeled is not None
        assert _anchor_levels(peeled[0]) == levels

    def test_a_non_literal_segment_is_not_guessed_at(self) -> None:
        division = ast.parse('Path(__file__).parent / name / "a.yaml"', mode="eval").body
        assert _literal_segments(division) is None

    def test_an_anchor_that_is_not_the_module_file_is_ignored(self) -> None:
        division = ast.parse('Path(cwd).parent / "a.yaml"', mode="eval").body
        peeled = _literal_segments(division)
        assert peeled is not None
        assert _anchor_levels(peeled[0]) is None

    def test_the_15181_anchor_off_by_one_is_detectable(self, tmp_path: Path) -> None:
        """The mutation, asserted rather than described: parents[2] must not resolve."""
        module = tmp_path / "shared" / "tests" / "test_probe.py"
        module.parent.mkdir(parents=True)
        (tmp_path / "shared" / "config").mkdir(parents=True)
        (tmp_path / "shared" / "config" / "redis-databases.yaml").write_text("{}\n", encoding="utf-8")

        module.write_text(
            "from pathlib import Path\n"
            'GOOD = Path(__file__).resolve().parents[1] / "config" / "redis-databases.yaml"\n',
            encoding="utf-8",
        )
        assert [anchor[2].exists() for anchor in _file_anchors(module)] == [True]

        module.write_text(
            "from pathlib import Path\n"
            'BAD = Path(__file__).resolve().parents[2] / "config" / "redis-databases.yaml"\n',
            encoding="utf-8",
        )
        assert [anchor[2].exists() for anchor in _file_anchors(module)] == [False]

    def test_a_chain_is_counted_once_not_per_link(self) -> None:
        tree = ast.parse('Path(__file__).parent / "a" / "b" / "c.yaml"')
        assert len(_outermost_divisions(tree)) == 1
