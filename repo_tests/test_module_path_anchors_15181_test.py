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

UNPARSEABLE IS AN UNKNOWN, NOT AN ABSENCE
-----------------------------------------
This sweep's whole claim is that it PARSES rather than imports, so it reaches
modules hidden behind a collection error. A module too broken to parse is
therefore the case most likely to be hiding a bad anchor — and it is the one case
a ``except SyntaxError: return []`` would silently score as clean, contributing
zero anchors and passing. That is #15202 item 3 reproduced inside the guard
written to answer it, and #14975 already settled the precedent the other way: a
file the size gate could not read became a violation, not a pass.

So ``_file_anchors`` raises and ``_sweep`` records the module in a second list,
which ``test_no_test_module_is_unreadable_by_the_sweep`` fails on. Measured on
the branch that added this file: 0 unreadable of 1995 modules, so failing loudly
costs nothing today. ``KNOWN_UNPARSEABLE`` is a down-only escape hatch and is deliberately empty —
an entry there is a statement that a tracked test module does not parse, which
is a defect in its own right and has to be argued for at the site. An earlier
revision of this file also grandfathered one unresolved anchor,
``autobot-backend/tests/unit/test_agents_status_pg_optional.py:54`` (a
``parents[3]`` that should have been ``parents[2]``, inert only because the
enclosing ``_import_func`` discarded the spec it built and returned ``None``).
#15251 fixed both the anchor and the swallow, so the grandfather entry is gone;
``test_the_previously_grandfathered_anchor_now_resolves`` pins that it stays
fixed.
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

SKIP_DIR_PARTS = frozenset(
    {".git", ".worktrees", "node_modules", ".venv", "venv", "__pycache__", "scripts", "dist", "build"}
)

#: Floor on the swept population. The failure mode a path guard has is not a false
#: failure but a silent shrink to nothing — an extractor that stops matching reports
#: a clean tree. Measured at 111 on the branch that added this file. RATCHET: raise
#: it when the population genuinely grows; lower it only with a stated reason.
MIN_SWEPT_EXPRESSIONS = 100

#: Test modules that do not parse and are therefore swept blind. Empty on purpose:
#: measured at 0 of 1995 on the branch that added this file. Down-only: an entry
#: here is an admission that a tracked test module is syntactically broken, which
#: is its own defect, not a waiver.
KNOWN_UNPARSEABLE: frozenset[str] = frozenset()


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
    """Every module pytest would treat as a test file, plus conftest.

    Skipped parts are matched RELATIVE to the root, never against the absolute
    path. All work here happens inside ``.worktrees/<branch>/``, so matching the
    absolute path would let the root's own location skip the entire sweep — which
    it did, silently, the first time ``.worktrees`` was added to the set.
    """
    return sorted(
        path
        for path in root.rglob("*.py")
        if not SKIP_DIR_PARTS.intersection(path.relative_to(root).parts)
        and (path.name.startswith("test_") or path.name.endswith("_test.py") or path.name == "conftest.py")
    )


def _file_anchors(module: Path) -> list[tuple[int, str, Path]]:
    """(lineno, expression-as-written, resolved path) for each anchored data file.

    Raises rather than returning ``[]`` when the module cannot be read. See
    ``UNPARSEABLE IS AN UNKNOWN, NOT AN ABSENCE`` in the module docstring.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
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


def _sweep(root: Path) -> tuple[list[tuple[Path, int, str, Path]], list[tuple[Path, str]]]:
    """(anchors, unreadable). A module that cannot be parsed lands in the second list."""
    anchors: list[tuple[Path, int, str, Path]] = []
    unreadable: list[tuple[Path, str]] = []
    for module in _test_modules(root):
        try:
            found = _file_anchors(module)
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError) as failure:
            unreadable.append((module, f"{type(failure).__name__}: {failure}"))
            continue
        anchors.extend((module, *anchor) for anchor in found)
    return anchors, unreadable


@pytest.fixture(scope="module")
def sweep_result() -> tuple[list[tuple[Path, int, str, Path]], list[tuple[Path, str]]]:
    return _sweep(project_root())


@pytest.fixture(scope="module")
def swept(sweep_result) -> list[tuple[Path, int, str, Path]]:
    return sweep_result[0]


@pytest.fixture(scope="module")
def unreadable(sweep_result) -> list[tuple[Path, str]]:
    return sweep_result[1]


class TestEveryAnchoredDataFileExists:
    def test_no_test_module_anchors_a_data_file_that_is_not_there(self, swept) -> None:
        root = project_root()
        missing = [
            f"{module.relative_to(root)}:{line}  ->  {resolved}"
            for module, line, _expr, resolved in swept
            if not resolved.exists()
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

    def test_the_previously_grandfathered_anchor_now_resolves(self, swept) -> None:
        """#15251: the one entry KNOWN_UNRESOLVED ever grandfathered must stay fixed.

        ``test_agents_status_pg_optional.py:54`` used to anchor at ``parents[3]``
        (the repo root) instead of ``parents[2]`` (``autobot-backend``), inert only
        because the enclosing ``_import_func`` discarded the spec and returned
        ``None``. Both are fixed; this pins the anchor so a regression is caught by
        this guard directly rather than only by the swallow it used to hide behind.
        """
        root = project_root()
        site = "autobot-backend/tests/unit/test_agents_status_pg_optional.py"
        hits = [entry for entry in swept if str(entry[0].relative_to(root)) == site]
        assert len(hits) == 1, f"{site} contributes {len(hits)} anchored data files to the sweep, expected 1"
        assert hits[0][3].exists(), f"{site} still resolves to a missing file: {hits[0][3]}"
        assert hits[0][3].name == "agent_org.py"


class TestAModuleTheSweepCannotReadIsNotClean:
    """#15202 item 3: an unparseable file is an unknown, not an absence."""

    def test_no_test_module_is_unreadable_by_the_sweep(self, unreadable) -> None:
        root = project_root()
        offenders = [
            f"{module.relative_to(root)}  ->  {reason}"
            for module, reason in unreadable
            if str(module.relative_to(root)) not in KNOWN_UNPARSEABLE
        ]
        assert not offenders, (
            "These test modules could not be parsed, so this sweep saw NONE of their "
            "path anchors and scored them clean without reading them. A file too broken "
            "to parse is the one most likely to be hiding a bad anchor — fix it, or add "
            "it to KNOWN_UNPARSEABLE with a reason:\n  " + "\n  ".join(offenders)
        )

    def test_the_unparseable_set_is_down_only_and_still_earned(self, unreadable) -> None:
        root = project_root()
        still_unreadable = {str(module.relative_to(root)) for module, _reason in unreadable}
        stale = KNOWN_UNPARSEABLE - still_unreadable
        assert not stale, f"these modules parse again and must leave KNOWN_UNPARSEABLE: {sorted(stale)}"
        assert not KNOWN_UNPARSEABLE, (
            "KNOWN_UNPARSEABLE was empty when this guard was written and is down-only. "
            "A tracked test module that does not parse is a defect to fix, not to list."
        )


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

    def test_an_unparseable_module_raises_rather_than_reporting_no_anchors(self, tmp_path: Path) -> None:
        """The behaviour chosen for #15202 item 3, pinned rather than described.

        The fixture carries a real anchor so the assertion cannot pass for the
        trivial reason that there was nothing to find: the SAME text parses to one
        anchor once the syntax error is removed.
        """
        anchored = 'GOOD = Path(__file__).parent / "data.yaml"\n'
        module = tmp_path / "test_broken.py"

        module.write_text("from pathlib import Path\n" + anchored + "def oops(:\n", encoding="utf-8")
        with pytest.raises(SyntaxError):
            _file_anchors(module)

        module.write_text("from pathlib import Path\n" + anchored, encoding="utf-8")
        assert len(_file_anchors(module)) == 1, "the fixture must contribute an anchor when it parses"

    def test_the_sweep_records_an_unparseable_module_instead_of_dropping_it(self, tmp_path: Path) -> None:
        """End to end: a broken module reaches the `unreadable` list, not the floor."""
        module = tmp_path / "test_broken.py"
        module.write_text("def oops(:\n", encoding="utf-8")

        anchors, unreadable = _sweep(tmp_path)

        assert anchors == []
        assert [entry[0] for entry in unreadable] == [module]
        assert unreadable[0][1].startswith("SyntaxError")

    def test_a_chain_is_counted_once_not_per_link(self) -> None:
        tree = ast.parse('Path(__file__).parent / "a" / "b" / "c.yaml"')
        assert len(_outermost_divisions(tree)) == 1
