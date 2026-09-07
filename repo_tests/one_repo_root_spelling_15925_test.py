# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No guard binds the repository root by hand (#15925).

161 bindings in 37 distinct expressions used to answer "where is the tree root".
That is not untidiness: `python_filter_covers_its_guards_test.py` decides which
trees a guard reads by pattern-matching the root binding, so every unanticipated
spelling is a guard its coverage instrument cannot see. Keyed on the identifier
`_REPO_ROOT` it saw 46 of 131; re-keyed on the expression it missed the twelve
writing `.resolve().parent.parent`.

The population is **discovered, not listed**: any module-level assignment whose
value mentions `__file__`. A list of the fourteen known spellings would be
satisfied by a fifteenth, which is the defect this guard exists to prevent —
`_REPO`, `_ROLE`, `_GEN` and `_HOOK` were each one file's invention.

Membership is decided **semantically**, by resolving the expression against the
file's real location, not by matching its text. That is what lets the thirteen
`__file__` bindings that legitimately name something else — the eight `FIXTURES`
in `lint/canonical/rules/`, two `_SELF`, three naming `repo_tests/` — stay
untouched without an allowlist naming them.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from repo_tests._paths import repo_root

#: The one file allowed to bind the root from `__file__`: it is the anchor the
#: helper resolves from, and it cannot ask itself where the tree is.
_ANCHOR = "repo_tests/_paths.py"

#: Files whose migration is blocked by the size ratchet, not by preference: the
#: import costs one line and #14236 freezes a grandfathered file at the size its
#: exemption was granted for. The ratchet is never raised to make a check pass,
#: so these wait for the file to shrink. The exemption CANNOT ROT --
#: `test_a_ratchet_exemption_is_still_blocked` fails the moment one of these has
#: room, which turns "we will get to it" into a failing test rather than a note.
_RATCHET_BLOCKED = {"repo_tests/enum_union_guard_test.py"}

#: Floor on files EXAMINED, not on bindings found. A findings-count floor is
#: satisfied by finding nothing, which is also what a broken sweep reports. 253
#: files parsed when this was written; the floor sits below that so ordinary
#: deletions do not trip it, and far above zero so a collapsed sweep does.
_MIN_FILES_PARSED = 200


def _tracked_repo_tests() -> list[Path]:
    """Guard files, from git rather than a filesystem walk (#15955)."""
    root = repo_root()
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "repo_tests/*.py", "repo_tests/**/*.py"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.split()
    return [root / rel for rel in out]


def _strip_resolve(node: ast.AST) -> ast.AST:
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
        node = node.func.value
    return node


def _parent_hops(node: ast.AST) -> int | None:
    """Number of parent hops if *node* is a `Path(__file__)`-rooted expression.

    Returns a 1-based hop count so `parents[N]` and a chain of N `.parent`s --
    which index differently -- can be compared on one scale.
    """
    hops, cur = 0, _strip_resolve(node)
    while isinstance(cur, ast.Attribute) and cur.attr == "parent":
        hops += 1
        cur = _strip_resolve(cur.value)
    if isinstance(cur, ast.Subscript) and isinstance(cur.value, ast.Attribute) and cur.value.attr == "parents":
        if not (isinstance(cur.slice, ast.Constant) and isinstance(cur.slice.value, int)):
            return None
        hops += cur.slice.value + 1
        cur = _strip_resolve(cur.value.value)
    cur = _strip_resolve(cur)
    if isinstance(cur, ast.Call):
        name = cur.func.attr if isinstance(cur.func, ast.Attribute) else getattr(cur.func, "id", None)
        if name == "Path" and len(cur.args) == 1 and isinstance(cur.args[0], ast.Name) and cur.args[0].id == "__file__":
            return hops
    return None


def _base_of(node: ast.AST) -> ast.AST:
    """Peel a `base / 'a' / 'b'` composition down to its base expression."""
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        node = node.left
    return node


def hand_rolled_roots_in(source: str, file_path: Path, root: Path) -> list[tuple[int, str]]:
    """Module-level bindings in *source* that re-derive *root* from ``__file__``."""
    found: list[tuple[int, str]] = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        if not any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node.value)):
            continue
        hops = _parent_hops(_base_of(node.value))
        if hops is None:
            continue
        # Semantic membership: does this expression actually land on the root?
        resolved = file_path.resolve().parents[hops - 1] if hops > 0 else file_path.resolve()
        if resolved != root:
            continue
        names = [t.id for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, ast.Name)]
        found.append((node.lineno, names[0] if names else "<unnamed>"))
    return found


def test_no_guard_binds_the_repo_root_by_hand() -> None:
    """Every guard obtains the root from `repo_tests._paths.repo_root`."""
    root = repo_root()
    files = _tracked_repo_tests()
    offenders: list[str] = []
    parsed = 0
    for path in files:
        rel = str(path.relative_to(root))
        if rel == _ANCHOR or rel in _RATCHET_BLOCKED:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed += 1
        for lineno, name in hand_rolled_roots_in(source, path, root):
            offenders.append(f"{rel}:{lineno} binds {name}")

    assert parsed >= _MIN_FILES_PARSED, (
        f"the sweep parsed only {parsed} files, below the floor of {_MIN_FILES_PARSED}. "
        "A shrunken population reports 'no hand-rolled roots' for the same reason a "
        "clean tree does, so the count is checked before the finding."
    )
    assert not offenders, (
        "these bindings re-derive the repository root from __file__ instead of "
        "calling repo_tests._paths.repo_root() (#15925):\n  " + "\n  ".join(offenders)
    )


def test_the_detector_reports_a_hand_rolled_binding() -> None:
    """Positive control: the shape this guard exists to catch is caught."""
    anchor = Path(repo_root()) / "repo_tests" / "example_test.py"
    found = hand_rolled_roots_in("REPO_ROOT = Path(__file__).resolve().parents[1]\n", anchor, repo_root())
    assert found == [(1, "REPO_ROOT")]


@pytest.mark.parametrize(
    "source",
    [
        "REPO_ROOT = Path(__file__).resolve().parent.parent\n",
        "_REPO = pathlib.Path(__file__).resolve().parents[1]\n",
        "_WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'\n",
    ],
    ids=["parent-chain", "pathlib-prefixed", "composed"],
)
def test_the_detector_reports_every_spelling_not_just_the_common_one(source: str) -> None:
    """The three spellings a text-keyed detector missed, including the composed form."""
    anchor = Path(repo_root()) / "repo_tests" / "example_test.py"
    assert hand_rolled_roots_in(source, anchor, repo_root()), f"missed: {source!r}"


def test_a_binding_that_names_something_other_than_the_root_is_not_reported() -> None:
    """The contrast that makes the assertion mean something.

    Thirteen `__file__` bindings in this tree legitimately name a subdirectory or
    the file itself. A detector keyed on the *expression* flags them and forces an
    allowlist; one keyed on the resolved *value* does not. Without this case, a
    detector that reported every `__file__` binding would pass every test above.
    """
    anchor = Path(repo_root()) / "repo_tests" / "lint" / "canonical" / "rules" / "example_test.py"
    # `parents[1]` from rules/ is `lint/canonical`, not the root -- the real
    # shape of the eight FIXTURES bindings.
    assert hand_rolled_roots_in("FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'\n", anchor, repo_root()) == []
    # `Path(__file__).resolve()` names the file itself -- the two `_SELF` bindings.
    top = Path(repo_root()) / "repo_tests" / "example_test.py"
    assert hand_rolled_roots_in("_SELF = Path(__file__).resolve()\n", top, repo_root()) == []


def test_a_ratchet_exemption_is_still_blocked() -> None:
    """An exemption granted for a full file must expire when the file has room.

    Without this the set above is a wish list: a file could shrink, the reason
    evaporate, and the entry sit there exempting a migration nothing prevents.
    """
    from repo_tests.python_file_size_ratchet_baseline import RATCHET_BASELINE

    root = repo_root()
    for rel in sorted(_RATCHET_BLOCKED):
        ceiling = RATCHET_BASELINE.get(rel)
        assert ceiling is not None, f"{rel} is exempted for the ratchet but carries no ceiling"
        lines = len((root / rel).read_text(encoding="utf-8").splitlines())
        assert lines >= ceiling, (
            f"{rel} is {ceiling - lines} line(s) under its ceiling of {ceiling}, so the "
            "import that blocked its migration now fits. Migrate it to repo_root() and "
            "drop it from _RATCHET_BLOCKED (#15925)."
        )
