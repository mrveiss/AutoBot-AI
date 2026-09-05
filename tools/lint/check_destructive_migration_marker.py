#!/usr/bin/env python3
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


def is_destructive(source: str) -> bool:
    return any(op in source for op in DESTRUCTIVE_OPS)


def check(path: Path) -> list[str]:
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
    if is_destructive(source) and MARKER not in source:
        return [
            f"{path.name}: drops a column, table or constraint without a "
            f"`{MARKER}` statement saying what it touches and why nothing is lost."
        ]
    return []


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
    findings = [f for path in paths for f in check(path)]
    for finding in findings:
        print(f"[{HOOK_ID}] {finding}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
