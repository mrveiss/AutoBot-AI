#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
r"""A destructive migration must say why it is safe (#15776).

A migration that drops a column, table or constraint is the one change this
repository cannot undo: a rolling update runs it while the previous release is
still serving, so a column dropped in release N that release N-1 still writes
loses data with no rollback. 80 of 90 migrations here are destructive
(drop_table 50, drop_column 33, drop_constraint 7) and until now nothing read
`migrations/versions/` at all.

THE FLOOR, NOT AN ALLOWLIST
---------------------------
The five most recent destructive migrations (082-086) each carry a literal
`NO DATA LOSS` statement explaining what they touch; the 75 below carry none.
The convention started at 082 and has held 5 of 5 since, unenforced. So the
rule is a single number rather than 75 entries: every destructive migration at
revision >= FLOOR carries the statement. No entry can outlive its own fix,
because there are no entries (#15762's defect cannot occur), nothing strands on
a rename (#15566's cannot either), and retrofitting 081 moves the floor down by
one with no list to edit.

REVISION, NOT FILENAME
----------------------
The `revision` string is authoritative -- alembic uses it, the filename is
convention -- and reading it removes the parser that could silently drop a file
it did not recognise. Two migrations use letter-suffixed revisions (`036b`,
`043b`), which a `^\d{3}$` filename parse drops without a word.

Lexical comparison is then correct *for revisions in the dated shape only*.
Measured: `9` and `87` both compare above `20260822_082` because '9' > '2', and
alembic's own default hex id (`alembic revision` with no --rev-id) sorts above
the floor when it starts with a letter and BELOW it when it starts with 0 or 1 --
silently exempting a destructive migration. Hence condition 2 below: a revision
that is not in the dated shape fails, with its own message.
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from pathlib import Path

# tools/lint/ is not a package; make the sibling helper importable however this
# module is loaded (script, pre-commit entry, importlib from the test).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import enforce_reach  # noqa: E402

#: Revision at which the data-safety statement became the convention.
FLOOR = "20260822_082"

#: The only revisions predating the dated scheme. Below any floor by inspection.
PRE_CONVENTION = frozenset({"001", "002"})

DATED_REVISION = re.compile(r"^\d{8}_\d{3}[a-z]?$")

DESTRUCTIVE_OPS = ("drop_column", "drop_table", "drop_constraint")

#: The same operations spelled as SQL. ``op.execute("ALTER TABLE t DROP COLUMN c")``
#: contains none of DESTRUCTIVE_OPS, so a migration could drop a column through
#: raw SQL and be waved through by a name-only scan (#15776 review).
DESTRUCTIVE_SQL = re.compile(r"\bDROP\s+(COLUMN|TABLE|CONSTRAINT)\b", re.IGNORECASE)

#: Where a model would still declare a column this migration drops. Scoped to
#: the ORM rather than the whole tree deliberately: a bare grep for a column
#: named ``name`` or ``status`` matches everywhere and a guard that cries wolf
#: is a guard someone silences.
MODEL_ROOTS = (
    "autobot-backend/models",
    "autobot-backend/llc/models",
    "autobot-backend/user_management/models",
    "autobot-slm-backend/models",
)

MARKER = "NO DATA LOSS"

#: Floor for migrations *parsed*, not violations found. 90 exist today; a
#: scanner whose discovery breaks finds zero violations and prints the same
#: clean line as a clean tree.
MIGRATION_FLOOR = 70

HOOK_ID = "destructive-migration-marker"


def revision_of(source: str) -> str | None:
    """The module-level ``revision`` assignment, or None if absent/not a literal."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else node.targets if isinstance(node, ast.Assign) else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "revision":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    return None


def upgrade_body(source: str) -> ast.FunctionDef | None:
    """The ``upgrade()`` definition, which is the only half that can lose data.

    A ``downgrade()`` dropping a column is not destructive in the sense this
    guard exists for -- it reverses an ``upgrade()`` that added one, and the
    model *should* still declare it. Scanning the whole module treated a correct
    downgrade as a violation: measured on
    ``20260824_084_device_capability_scoping.py``, whose three drops are all in
    ``downgrade()`` and whose columns the ``MobileDevice`` model still declares,
    exactly as they should.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "upgrade":
            return node
    return None


def is_destructive(source: str) -> bool:
    """True when ``upgrade()`` drops something -- not merely when the file does."""
    upgrade = upgrade_body(source)
    if upgrade is None:
        return False
    if any(op in ast.dump(upgrade) for op in DESTRUCTIVE_OPS):
        return True
    return any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and DESTRUCTIVE_SQL.search(node.value)
        for node in ast.walk(upgrade)
    )


def dropped_columns(source: str) -> list[tuple[str, str]]:
    """``(table, column)`` for every ``op.drop_column("t", "c")`` literal.

    Only literal pairs are read. A call built from variables is invisible here,
    which is a stated gap rather than a silent one -- the marker still applies to
    it, and pretending otherwise would be the same overreach as a bare grep.
    """
    upgrade = upgrade_body(source)
    if upgrade is None:
        return []
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if name != "drop_column" or len(node.args) < 2:
            continue
        table, column = node.args[0], node.args[1]
        if all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in (table, column)):
            pairs.append((table.value, column.value))
    return pairs


#: Floor for the model scan. The cross-source check is only as good as the files
#: it reads: with none, `models_still_declaring` finds no declarers and the
#: data-loss check passes **having scanned nothing** -- the same shape as a
#: violation-bound floor, one layer inside this guard (#15776 review).
MIN_MODEL_FILES = 20


class ModelScanUnreachable(RuntimeError):
    """Raised when the model scan cannot see enough to answer."""


def _model_files(repo_root: Path) -> list[Path]:
    """Every ORM module under :data:`MODEL_ROOTS`, or a raise.

    A missing root is a configuration error, not an empty result: renaming a
    package would otherwise turn the cross-source check off silently while it
    kept reporting success.
    """
    missing = [root for root in MODEL_ROOTS if not (repo_root / root).is_dir()]
    if missing:
        raise ModelScanUnreachable(f"configured model root(s) missing: {', '.join(missing)}")
    files = [path for root in MODEL_ROOTS for path in (repo_root / root).rglob("*.py") if "_test" not in path.name]
    if len(files) < MIN_MODEL_FILES:
        raise ModelScanUnreachable(f"model scan reached {len(files)} file(s); floor is {MIN_MODEL_FILES}")
    return files


@functools.lru_cache(maxsize=4)
def _model_index(repo_root: Path) -> dict[tuple[str, str], tuple[str, ...]]:
    """``(table, column) -> declaring models``, built once per repository.

    Previously each dropped column re-read and re-parsed every model file, so a
    full sweep cost migrations x columns x models parses. The mapping is
    immutable for the run, so it is built once (#15776 review).
    """
    index: dict[tuple[str, str], list[str]] = {}
    for path in _model_files(repo_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            table = _tablename_of(node)
            if table is None:
                continue
            for column in _declared_columns(node):
                index.setdefault((table, column), []).append(f"{path.name}:{node.name}")
    return {key: tuple(value) for key, value in index.items()}


def models_still_declaring(repo_root: Path, table: str, column: str) -> list[str]:
    """Model files that declare *column* on the class owning *table*.

    The table is matched through ``__tablename__`` and the column through an
    assignment to ``Column(...)``/``mapped_column(...)``, so the two are tied
    together by the class rather than by a name appearing somewhere in the same
    file. That is what keeps this from firing on every ``name`` and ``status``.

    What it proves: the CURRENT tree still declares the column being dropped, so
    the running release writes it. What it cannot prove is the N-1 case -- that
    is a fact about deployed code, and it is why the marker is a sentence a human
    writes rather than a checkbox.
    """
    return list(_model_index(repo_root).get((table, column), ()))


def _assignment_targets(node: ast.stmt) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


def _tablename_of(class_node: ast.ClassDef) -> str | None:
    """The literal ``__tablename__`` this class declares, if any."""
    for node in class_node.body:
        for target in _assignment_targets(node):
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                value = getattr(node, "value", None)
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    return None


def _declared_columns(class_node: ast.ClassDef) -> set[str]:
    """Column names this class declares, by attribute name and by explicit name.

    ``mapped_column`` is included alongside ``Column`` because both are live in
    this repository, and ``Column("explicit_name", ...)`` names the column
    independently of the attribute it is bound to -- a class can therefore
    declare a column under a name that never appears as an identifier.
    """
    columns: set[str] = set()
    for node in class_node.body:
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Call):
            continue
        callee = value.func.attr if isinstance(value.func, ast.Attribute) else getattr(value.func, "id", None)
        if callee not in ("Column", "mapped_column"):
            continue
        for target in _assignment_targets(node):
            if isinstance(target, ast.Name):
                columns.add(target.id)
        if value.args and isinstance(value.args[0], ast.Constant) and isinstance(value.args[0].value, str):
            columns.add(value.args[0].value)
    return columns


def _marker_in_docstring(source: str) -> bool:
    """The marker must be in the **module docstring**, where the policy puts it.

    ``MARKER in source`` was satisfied by the words appearing in a code comment,
    in a column name, or anywhere else in the file -- including in a migration
    that merely mentions the convention (#15776 review). The statement is meant
    to be the first thing a reader of the migration sees.
    """
    try:
        docstring = ast.get_docstring(ast.parse(source))
    except SyntaxError:
        return False
    return bool(docstring) and MARKER in docstring


def check(path: Path, repo_root: Path | None = None) -> list[str]:
    """Findings for one migration. Three conditions, three distinct messages."""
    source = path.read_text(encoding="utf-8")
    revision = revision_of(source)

    # 1. Unreadable revision -> fail. Never skip: an input that cannot be read
    #    and reports clean is indistinguishable from a clean input.
    if revision is None:
        return [f"{path.name}: no readable module-level `revision` assignment; the floor cannot be applied"]

    # 2. Undated revision -> fail, naming the CONVENTION rather than the floor.
    #    A revision the floor cannot be compared against is a different defect
    #    from a missing marker and deserves different text.
    if not DATED_REVISION.match(revision) and revision not in PRE_CONVENTION:
        return [
            f"{path.name}: revision {revision!r} is not in this repository's "
            f"YYYYMMDD_NNN[x] form, so it cannot be ordered against the floor. "
            f"Alembic's default hex id sorts arbitrarily either side of it."
        ]

    # 3. The marker itself, for destructive migrations at or above the floor.
    if revision in PRE_CONVENTION or revision < FLOOR:
        return []
    findings: list[str] = []
    if is_destructive(source) and not _marker_in_docstring(source):
        findings.append(
            f"{path.name}: drops a column, table or constraint without a "
            f"`{MARKER}` statement saying what it touches and why nothing is lost."
        )

    # A separate check with its own message: a missing sentence and a column the
    # running release still writes are different defects, and only the second one
    # loses data.
    if repo_root is not None:
        try:
            _model_index(repo_root)
        except ModelScanUnreachable as exc:
            # Loudly, and once: a cross-source check that scanned nothing
            # reports the same clean line as a tree with nothing to report.
            return findings + [f"{path.name}: cross-source column check cannot run -- {exc}"]
        for table, column in dropped_columns(source):
            declarers = models_still_declaring(repo_root, table, column)
            if declarers:
                findings.append(
                    f"{path.name}: drops {table}.{column}, which the model still declares "
                    f"({', '.join(declarers)}). The running release writes this column -- expand "
                    f"and dual-write first, contract in the NEXT release."
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    versions = repo_root / "autobot-backend" / "migrations" / "versions"
    args = sys.argv[1:] if argv is None else argv
    if args:
        paths = sorted(Path(a) for a in args if a.endswith(".py") and "migrations/versions" in a)
        full_repo = False
    else:
        paths = sorted(versions.glob("*.py"))
        full_repo = True
    # The floor counts migrations PARSED, not violations found: a scanner whose
    # discovery breaks reports zero violations and prints the same clean line as
    # a clean tree. Full-repo mode only -- pre-commit legitimately passes a
    # changed-file list with no migrations in it.
    if enforce_reach(len(paths), MIGRATION_FLOOR, hook=HOOK_ID, full_repo=full_repo):
        return 1
    findings = [f for path in paths for f in check(path, repo_root)]
    for finding in findings:
        print(f"[{HOOK_ID}] {finding}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
