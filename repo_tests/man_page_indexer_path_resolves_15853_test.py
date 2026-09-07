# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The man-page indexer is where the refresh task looks for it (#15853).

`knowledge_tasks._run_indexing_subprocess` -- now
`tasks.man_page_indexing.run_indexing_subprocess` -- shelled out to
`"scripts/utilities/index_all_man_pages.py"` -- relative to the process working
directory, and there is no `scripts/utilities/` at the repository root at all.
The script is real; it lives under `autobot-infrastructure/shared/`. So the
refresh returned its `failed` dict on every run, with the subprocess's stderr
truncated into a generic message, and system knowledge was presumably never
refreshed by this task.

Same defect class as #15845, whose hook pointed at an indexer that was never
created: a wired path that resolves nowhere, degrading quietly instead of
failing loudly.

**The path is read out of the module under test, never restated here.** A test
carrying its own copy of the path passes when the module's copy moves alone,
which is precisely the failure it exists to catch.

**And the callers are discovered, not listed (#15902).** This guard used to name
two files. A third file naming the indexer -- a new task, a new service, a
script -- passed by not being on the list, and the guard's silence would have
read as coverage. That is the same shape as #15724's publisher registry, where a
third implementation existed unregistered while the guard reported a complete
set: enumeration there was not merely incomplete, it reported completeness.

So the sweep is every tracked ``*.py``, and what it asserts is that the set of
files invoking the indexer in *executable* code is exactly the one module that
should. Comments and docstrings are stripped first -- the module documents the
old cwd-relative path directly above the constant that replaced it, so a raw
match is satisfied by the explanation of the fix rather than by the fix.

**Two known limits, stated rather than half-covered.**

A name built by concatenation -- ``"index_all_man_" + "pages.py"`` -- is missed.
A partial constant-folder for a form nobody writes would be worse than a
recorded gap: it would cover the easy cases and read as covering all of them.
*Implicit* concatenation (adjacent string literals) IS caught, because ``ast``
merges them into one ``Constant`` before ``unparse`` runs -- that is the form
someone actually reaches for when a path gets long, and it works by a property
of the AST rather than by design here.

The floor counts files **parsed**, not files opened: ``executable_source``
returns ``None`` for a file it cannot parse, and those are skipped rather than
counted. A floor tracking the larger set is satisfied by files that contribute
nothing, which is how a floor stops being a reach check.
"""

import ast
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]
_MODULE = REPO_ROOT / "autobot-backend/tasks/man_page_indexing.py"
_CALLER = REPO_ROOT / "autobot-backend/tasks/knowledge_tasks.py"

#: The script's basename, as any caller would have to spell it.
_INDEXER_NAME = "index_all_man_pages.py"

#: The one module that may invoke the indexer. Not an allowlist -- an expectation:
#: a second entry here is a second copy of the invocation, which is the drift this
#: guard exists to catch, and adding one should require saying why in review.
_EXPECTED_EXECUTORS = frozenset({"autobot-backend/tasks/man_page_indexing.py"})

#: Files that name the indexer in code without invoking it, by path, with the
#: reason. Recorded rather than inferred from context: "it looked like a test" is
#: not a property a sweep can check, and a guess that happens to be right this
#: time is not a rule.
_ALLOWED = {
    "repo_tests/man_page_indexer_path_resolves_15853_test.py": "this guard; the name is its subject",
    "autobot-backend/api/api_endpoint_migrations_test.py": (
        "PARKED under #15173 and skipped -- 1017 source-text assertions frozen by #5359 Option C. "
        "Its assertion that `refresh_system_knowledge` contains the script name describes the "
        "pre-#15853 shape and would fail if it ran; the file is not to be edited."
    ),
}

#: Below this the sweep collapsed rather than the tree being clean. Bound to files
#: examined, never to references found -- a floor tracking findings relaxes as the
#: tree improves, and this population should stay at one.
_MIN_FILES_SWEPT = 4_000


def _tracked_python_files() -> List[str]:
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return [n for n in completed.stdout.split("\n") if n and not n.startswith(".worktrees/")]


def executable_source(text: str) -> Optional[str]:
    """*text* with comments and docstrings removed, other string literals kept.

    Both of those have to go and nothing else may. A comment mentioning the
    indexer is documentation, and this module's own comment quotes the very
    literal the check looks for; a docstring is the same thing in a different
    token type. But the reference itself **is** a string literal —
    ``subprocess.run([sys.executable, "index_all_man_pages.py"])`` — so blanking
    every string blanks the thing being detected. The first version of this
    function did exactly that and the fixture test caught it.

    Comments disappear for free: ``ast.unparse`` never emits them. Docstrings
    are removed explicitly, as the leading string statement of a module, class
    or function, plus any bare string expression used as a comment.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ""
        # `orelse`, `handlers` and `finalbody` as well as `body`: a bare string
        # in an `else:` or `except:` block is the same comment-shaped statement,
        # and reading only `body` reported it as executable code.
        for attr in ("body", "orelse", "finalbody", "handlers"):
            # `isinstance(..., list)`: `ast.Lambda.body` and `ast.IfExp.body` are
            # single expressions, not statement lists, and iterating one raises.
            statements = getattr(node, attr, None)
            for stmt in statements if isinstance(statements, list) else []:
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    stmt.value.value = ""
    return ast.unparse(tree)


def files_naming_the_indexer() -> Tuple[List[str], int]:
    """``(paths naming it in executable code, files swept)``."""
    found: List[str] = []
    swept = 0
    for name in _tracked_python_files():
        try:
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        source = executable_source(text)
        if source is None:
            # Unparseable. NOT counted: `executable_source` returns "" for a file
            # it cannot parse, so counting it here would let the floor track the
            # files *opened* while the check only sees the files *parsed*. The
            # docstring on the floor says "files examined", and examined has to
            # mean examined -- a superset floor is satisfied by files that
            # contribute nothing, which is how a floor stops being a reach check.
            continue
        swept += 1
        if _INDEXER_NAME in source:
            found.append(name)
    return sorted(found), swept


_FOUND, _SWEPT = files_naming_the_indexer()


def _module_source() -> str:
    """The module's code, with comment lines removed.

    The module documents the old cwd-relative path in a comment directly above
    the constant that replaced it. Matching raw text, "the bad literal is gone"
    is then false while the code is correct -- the explanation of the fix sits
    nearer to the fix than anything else does, and it is made of the very string
    the check looks for. Same reason the #15724 publish-contract guard strips
    comments before matching.
    """
    text = _MODULE.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _indexer_path_expression() -> str:
    """The right-hand side of MAN_PAGE_INDEXER, as written in the module."""
    tree = ast.parse(_module_source())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MAN_PAGE_INDEXER" for t in node.targets
        ):
            return ast.unparse(node.value)
    raise AssertionError("MAN_PAGE_INDEXER is not defined -- this test would prove nothing")


def _resolved_indexer() -> Path:
    """Resolve the module's expression to a real path, without importing the backend.

    Importing `knowledge_tasks` pulls in Celery and the whole task graph. The
    expression is a chain of `/` operands, so the string literals in it are the
    path segments -- read them from the AST instead.
    """
    expression = _indexer_path_expression()
    assert "PATH.PROJECT_ROOT" in expression, f"MAN_PAGE_INDEXER is not anchored to the project root: {expression}"
    segments = re.findall(r"'([^']+)'|\"([^\"]+)\"", expression)
    parts = [a or b for a, b in segments]
    assert parts, f"no path segments found in {expression}"
    return REPO_ROOT.joinpath(*parts)


def test_the_indexer_path_is_anchored_to_the_repo_root_not_the_cwd():
    """A cwd-relative path resolves differently under Celery, systemd and pytest."""
    expression = _indexer_path_expression()

    assert "PATH.PROJECT_ROOT" in expression, expression
    assert not re.search(
        r"^['\"]scripts/", expression
    ), "the indexer is addressed relative to the process working directory"


def test_the_indexer_exists_where_the_task_looks_for_it():
    """The defect itself, with the path read from the caller rather than restated."""
    indexer = _resolved_indexer()

    assert indexer.is_file(), (
        f"knowledge_tasks resolves the man-page indexer to {indexer.relative_to(REPO_ROOT)}, " "which does not exist"
    )


def test_a_missing_indexer_is_reported_by_path():
    """Absence must be distinguishable from a run that failed.

    The old code returned the subprocess's truncated stderr, so "the indexer is
    not where we looked" and "the indexer ran and failed" produced the same
    message.
    """
    source = _module_source()

    assert "MAN_PAGE_INDEXER.is_file()" in source, "nothing checks whether the indexer exists before shelling out to it"
    assert re.search(
        r"not found at \{MAN_PAGE_INDEXER\}", source
    ), "the not-found message does not name the path it looked for"


def test_the_subprocess_invokes_the_anchored_path():
    """The constant must be what is executed.

    Defining an anchored constant and then passing a literal to `subprocess.run`
    would satisfy every assertion above while changing nothing.
    """
    source = _module_source()

    assert "[sys.executable, str(MAN_PAGE_INDEXER)]" in source, "the subprocess does not execute MAN_PAGE_INDEXER"
    assert (
        "scripts/utilities/index_all_man_pages.py" not in source
    ), "the cwd-relative literal is still present in the module"


def test_the_caller_delegates_rather_than_carrying_its_own_path():
    """`knowledge_tasks` must not regrow its own copy of the invocation.

    The helpers moved out because that module sits at its file-size ceiling and
    a grandfathered file may not grow (#14236). A second copy of the path here
    would be both the drift this guard exists to catch and a ceiling breach.
    """
    caller = "\n".join(
        line for line in _CALLER.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )

    assert "from tasks.man_page_indexing import run_indexing_subprocess" in caller
    assert "index_all_man_pages.py" not in caller, "knowledge_tasks names the indexer script again; it should delegate"


def test_the_sweep_examined_the_repository() -> None:
    """Runs first: the assertion below passes vacuously over an empty sweep.

    Bound to files examined, not to references found. A sweep that collects
    nothing reports "only the expected executor names the indexer", which is
    exactly what a clean tree reports.
    """
    assert _SWEPT >= _MIN_FILES_SWEPT, (
        f"swept only {_SWEPT} Python file(s), floor {_MIN_FILES_SWEPT}. FIX THE SWEEP — "
        "a clean result below this floor asserts nothing."
    )


def test_only_the_expected_module_invokes_the_indexer() -> None:
    """Discovered, not listed (#15902).

    The previous version of this file named two modules and checked those. A
    third file naming the indexer passed by not being on the list — and the
    guard's silence would have read as coverage of a caller it had never seen.
    """
    unexpected = [name for name in _FOUND if name not in _EXPECTED_EXECUTORS and name not in _ALLOWED]
    assert not unexpected, (
        f"{len(unexpected)} file(s) name {_INDEXER_NAME} in executable code but are neither the "
        f"expected executor nor allowed ({_SWEPT} files swept):\n"
        + "\n".join(f"  {name}" for name in unexpected)
        + f"\n\nThe invocation belongs in {sorted(_EXPECTED_EXECUTORS)[0]}, which anchors it to the "
        "project root and reports absence by path. A second copy is the drift #15853 fixed, "
        "returning. If the mention is legitimate, add it to `_ALLOWED` with the reason."
    )


def test_the_expected_executor_is_still_there() -> None:
    """The other direction, and the one a discovery sweep gets wrong.

    `test_only_the_expected_module_invokes_the_indexer` passes when NOTHING
    invokes the indexer — a repository that had deleted the caller entirely
    would look clean. This is what makes the expectation two-sided.
    """
    missing = sorted(_EXPECTED_EXECUTORS - set(_FOUND))
    assert not missing, (
        f"{missing} no longer names {_INDEXER_NAME} in executable code. Either the invocation "
        "moved — in which case `_EXPECTED_EXECUTORS` should say where — or nothing indexes man "
        "pages any more and this guard is watching an empty room."
    )


def stale_allowlist_entries(allowed, found) -> List[str]:
    """Entries in *allowed* that no longer appear in *found*.

    Extracted so it can be tested against a fixture. It was the one check in
    this file with nothing proving it fires — asserted rather than demonstrated,
    in a file whose whole subject is the difference.
    """
    return sorted(path for path in allowed if path not in found)


def test_the_staleness_check_reports_an_entry_nothing_needs() -> None:
    """The fixture that SHOULD trip it, and the answer to the strongest
    objection against keeping an allowlist at all.

    A tree where every entry is still live says nothing about whether a dead one
    would be caught, which is exactly the enumerate-vs-discover complaint this
    guard exists to answer — applied to the exemption list rather than to the
    callers.
    """
    assert stale_allowlist_entries({"gone.py": "reason"}, ["still/here.py"]) == ["gone.py"]


def test_the_staleness_check_passes_a_live_entry() -> None:
    """The contrast case. Without it, a function returning every key satisfies
    the assertion above."""
    assert stale_allowlist_entries({"live.py": "reason"}, ["live.py", "other.py"]) == []


def test_every_allowlist_entry_still_names_the_indexer() -> None:
    """An allowlist is a measurement, and measurements go stale.

    An entry whose file no longer mentions the indexer is a permanent exemption
    for a condition that no longer exists — and the next file at that path
    inherits it silently.
    """
    stale = stale_allowlist_entries(_ALLOWED, _FOUND)
    assert not stale, (
        f"`_ALLOWED` exempts {stale}, which no longer name {_INDEXER_NAME} in executable code. "
        "Remove the entry: an exemption nothing needs is one the next file at that path inherits."
    )


def test_a_new_caller_would_be_caught() -> None:
    """The fixture that SHOULD trip it — proving reach rather than asserting it.

    A tree that currently passes says nothing about whether a third caller would
    be found; that is the whole failure this issue describes.
    """
    fixture = f'import subprocess\nsubprocess.run(["python", "{_INDEXER_NAME}"])\n'

    assert _INDEXER_NAME in executable_source(fixture)


def test_a_comment_or_docstring_mention_is_not_a_caller() -> None:
    """The contrast case. Without it, a detector that reported every file
    containing the string would satisfy the assertion above.

    Both forms matter here: this module's own comment quotes the old
    cwd-relative literal directly above the constant that replaced it.
    """
    commented = f'# the indexer lives at scripts/utilities/{_INDEXER_NAME}\nx = 1\n'
    documented = f'"""Refreshes man pages via {_INDEXER_NAME}."""\nx = 1\n'

    assert _INDEXER_NAME not in executable_source(commented)
    assert _INDEXER_NAME not in executable_source(documented)
