# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One enumeration helper, and a baseline of the guards that still bypass it (#15926).

Forty guards in `repo_tests/` invoke `git ls-files` themselves, each re-deciding
four things: the pathspec, the anchor, the environment, and what a failure means.

**Three of those four are already settled, and measuring said so.** The scrub is
gated by `tools/lint/check_git_toplevel_env_scrubbed.py` (#14896) — 60
deduplicated call sites in the tree, 59 scrubbed inline, one passing a
deliberate `_test_git_env()`. Anchoring is correct everywhere, in two
conventions (47 `cwd=`, 13 `git -C`). Failure handling is the weakest: 8 sites
pass `check=False` and never inspect `returncode`, so a git failure yields `[]`
— but all 8 carry a reach floor, so none currently reports a clean tree.

What is NOT settled is the fourth. Zero sites use git's own `:(exclude)`
pathspecs; every exclusion is a second matcher in Python over the paths git
already returned. #15510 is what that costs — an exclusion tested against the
ABSOLUTE path fired on every file, because the checkout itself sat under a
directory of that name. `tracked_paths(..., exclude=...)` now passes exclusions
to git, so the matcher that filters is the matcher that enumerated.

**And the defect none of this would have caught:** an enumeration that is not
git at all. `check_git_toplevel_env_scrubbed.iter_shell_files` used
`repo_root.rglob("*.sh")` beside a sibling using `tracked_paths`, and read 215
files from other checkouts. No scrub gate can see that, because there is nothing
to scrub.

So this file is a **baseline that only shrinks**, not a pass/fail line in the
sand: every direct invocation is recorded, and the count may only go down.
Landing the helper without recording the population would leave the migration
unmeasured, which is how "we will migrate the rest" becomes nothing.
"""

from __future__ import annotations

import ast
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

#: Direct `git ls-files` invocations in `repo_tests/`, measured on the tree:
#: **40 awaiting migration, plus 2 deliberate** — the unscrubbed contrast
#: fixture in this file, which must stay a raw call because its whole purpose is
#: to show that an unscrubbed enumeration follows `GIT_DIR`; and the pattern
#: PROBE in `pytest_testpaths_cover_every_test_dir_15183_test.py`, which asks
#: "does this pattern match anything?" — a question whose answer is legitimately
#: no, where `tracked_paths` raises on empty because it answers "enumerate the
#: population" (#15826). An `allow_empty=` flag would be the obvious fix and the
#: wrong one: an optional parameter that switches off a guard is off by default
#: at every site that forgets it.
#:
#: THIS ONLY SHRINKS. It moved 40 -> 41 once, when this module stopped exempting
#: itself from its own census (#15990 review) — the population definition
#: changed, not the tree, and #15897's rule applies: correcting a denominator is
#: not licensing a bypass. Never raise it to make a new bypass pass; route the
#: new guard through `tracked_paths` instead.
#: 42 -> 33: nine plain `git ls-files "*.py"` sites migrated in one batch
#: (#15926). Two candidates were deliberately NOT migrated, and they are a
#: class rather than an oversight: `audio_extension_allowlist_test` and
#: `env_var_bare_cast_test` pass their enumerator to `declare(discover=...)`,
#: and `reach_declarations_test` drives that against an EMPTY tree to prove the
#: floor fires. `tracked_paths` raises there instead of returning `[]`, so
#: migrating them breaks the test that proves their floors work. That is the
#: same empty-population tension described above, reached from the other side:
#: here the empty result is the evidence, not the failure.
MAX_DIRECT_INVOCATIONS = 33

#: Floor on files EXAMINED, not on findings. A findings floor is satisfied by
#: finding nothing, which is also what a collapsed sweep reports.
_MIN_FILES_PARSED = 180

#: Every `subprocess` entry point that executes an argv. `call` and `check_call`
#: were missing, so `subprocess.call(["git", "ls-files"])` bypassed the census
#: (#15990 review) — the function-name dimension of the same generalisation the
#: keyword fix made, applied late because I widened one axis and not the other.
_EXECUTORS = frozenset({"run", "check_output", "check_call", "call", "Popen"})


def _executor_name(func: ast.expr) -> str | None:
    """The called name, matched EXACTLY rather than as a substring.

    `"call" in ast.unparse(func)` would also match `recall`, `caller` and any
    module path containing the word — the same substring weakness a review
    already found in the argv match, one expression up.
    """
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def invokes_ls_files(node: ast.Call) -> bool:
    """Whether *node* is a subprocess invocation of ``git ls-files``.

    `subprocess.run(args=[...])` is the same call as the positional form.
    Reading only `node.args` missed it -- the THIRD keyword-form blind spot in
    this family, after `os.walk(top=)` and `Path.glob(pattern=)`. Three
    instances is the argument for reading the keyword wherever positional argv
    is read, rather than fixing the one shape a review happened to report.
    """
    if _executor_name(node.func) not in _EXECUTORS:
        return False
    argv = list(node.args) + [k.value for k in node.keywords if k.arg == "args"]
    # STRUCTURE, not substring: `["printf", "ls-files"]` matched a substring test
    # and is not git at all. The executable must be `git` and `ls-files` must be
    # one of the argv elements, not a fragment of one (#15990 review).
    for arg in argv:
        if not isinstance(arg, (ast.List, ast.Tuple)):
            continue
        words = [e.value for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if not words:
            continue
        if Path(words[0]).name != "git":
            continue
        if "ls-files" in words[1:]:
            return True
    return False


def _direct_invocations() -> tuple[list[str], int]:
    """`repo_tests` sites that shell out to `git ls-files`, and files PARSED.

    Returns the parse count, not the enumeration count. The floor has to bind to
    what the sweep actually read: a file skipped for `SyntaxError` was never
    examined, and a floor counting `tracked_paths` results cannot tell the
    difference between "parsed 200 files, found none" and "parsed none".
    """
    found: list[str] = []
    parsed = 0
    unreadable: list[str] = []
    for rel in tracked_paths(REPO_ROOT, "repo_tests/*.py"):
        # This module is NOT exempt (#15990 review). A guard that skips itself
        # cannot see a bypass added to itself, and the exact baseline would still
        # pass. Its own fixtures are `ast.parse("...")` string arguments and
        # `git init`/`git add` calls, none of which the structural predicate
        # matches — so including it costs nothing and closes the hole.
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        parsed += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and invokes_ls_files(node):
                found.append(f"{rel}:{node.lineno}")
    assert not unreadable, "tracked files this sweep could not parse:\n  " + "\n  ".join(unreadable)
    return sorted(set(found)), parsed


def _decoy_repository(tmp_path: Path) -> Path:
    """A throwaway repository holding `decoy.py`, created with a SCRUBBED env.

    The scrub matters here, not just in the assertion. An earlier version ran
    `git init` and `git add` inheriting the ambient environment, so under the
    `GIT_DIR` a git hook exports they operated on **the real repository** and
    staged `decoy.py` into its index. The pre-push hook is exactly that
    environment, which is where it happened. A fixture that demonstrates a
    hazard must not be subject to it.
    """
    other = tmp_path / "other"
    other.mkdir()
    env = scrubbed_git_env()
    subprocess.run(["git", "-C", str(other), "init", "-q"], check=True, env=env)  # nosec B603 B607
    (other / "decoy.py").write_text("# not this repository\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "decoy.py"], check=True, env=env)  # nosec B603 B607
    return other


def test_the_direct_invocation_count_only_shrinks() -> None:
    """Equality, not a bound: headroom under a ceiling is where the next one hides."""
    direct, parsed = _direct_invocations()
    assert parsed >= _MIN_FILES_PARSED, (
        f"the sweep PARSED {parsed} files, below the floor of {_MIN_FILES_PARSED} — "
        "a shrunken population reports 'no bypasses' for the same reason a migrated tree does"
    )
    assert len(direct) == MAX_DIRECT_INVOCATIONS, (
        f"{len(direct)} direct `git ls-files` invocations in repo_tests/, but "
        f"MAX_DIRECT_INVOCATIONS says {MAX_DIRECT_INVOCATIONS}. If you migrated one, "
        "lower the constant. If you added one, route it through "
        "`tools.lint._scan_helpers.tracked_paths` instead (#15926):\n  " + "\n  ".join(direct)
    )


def test_the_helper_scrub_is_load_bearing(tmp_path: Path) -> None:
    """With `GIT_DIR` pointed at another repository, the helper still reads THIS one.

    The failure this prevents is silent: `git ls-files` under an inherited
    `GIT_DIR` enumerates the other repository's index and exits 0 with plausible
    output. A hook run in a worktree is handed exactly that environment (#15176).
    """
    other = _decoy_repository(tmp_path)

    previous = os.environ.get("GIT_DIR")
    os.environ["GIT_DIR"] = str(other / ".git")
    try:
        names = tracked_paths(REPO_ROOT, "*.py")
    finally:
        if previous is None:
            os.environ.pop("GIT_DIR", None)
        else:
            os.environ["GIT_DIR"] = previous

    assert "decoy.py" not in names, "the helper enumerated the repository GIT_DIR pointed at"
    assert any(n.startswith("repo_tests/") for n in names), "the helper did not read this tree"


def test_the_scrub_is_what_makes_that_work(tmp_path: Path) -> None:
    """The contrast: an UNSCRUBBED call under the same environment reads the decoy.

    Without this, the test above passes on a machine where `GIT_DIR` never
    mattered, and proves nothing about the scrub. This asserts the hazard is real
    before asserting the helper avoids it.
    """
    other = _decoy_repository(tmp_path)

    env = dict(os.environ)
    env["GIT_DIR"] = str(other / ".git")
    raw = subprocess.run(  # nosec B603 B607  # deliberately unscrubbed: that is the point
        ["git", "ls-files", "*.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    ).stdout.split()

    assert "decoy.py" in raw, (
        "an unscrubbed `git ls-files` did NOT follow GIT_DIR here, so this machine "
        "cannot demonstrate the hazard and the test above is not evidence of the scrub"
    )


def test_exclusions_are_matched_by_git_not_a_second_matcher() -> None:
    """`exclude=` reaches git as a `:(exclude)` pathspec (#15926, #15510)."""
    every = tracked_paths(REPO_ROOT, "*.sh")
    without = tracked_paths(REPO_ROOT, "*.sh", exclude=[".claude"])
    dropped = set(every) - set(without)

    assert dropped, "excluding `.claude` dropped nothing — the pathspec never reached git"
    assert all(d.startswith(".claude/") for d in dropped), f"excluded beyond the pathspec: {sorted(dropped)[:3]}"
    assert all(not p.startswith("/") for p in without), "paths must stay repo-relative, as #15510 requires"


def test_an_exclusion_of_nothing_does_not_silently_empty_the_population() -> None:
    """Contrast: a wrong `:(exclude)` must not be indistinguishable from a strict one.

    Without this, an exclusion syntax error that git treats as "exclude
    everything" would look exactly like a working filter to the test above.
    """
    every = tracked_paths(REPO_ROOT, "*.sh")
    unaffected = tracked_paths(REPO_ROOT, "*.sh", exclude=["no-such-directory-anywhere"])
    assert set(unaffected) == set(every)


def test_the_helper_refuses_an_empty_enumeration() -> None:
    """A population of zero is raised, not returned — #15826's rule, kept here."""
    with pytest.raises(RuntimeError):
        tracked_paths(REPO_ROOT, "*.no-such-suffix-exists")


def test_the_helper_refuses_a_directory_git_cannot_enumerate() -> None:
    """A git failure raises rather than yielding `[]`.

    Eight `repo_tests` sites currently pass `check=False` and never inspect
    `returncode`, so a failure gives them an empty list. All eight carry a reach
    floor today, so none reports clean — but the floor is a second thing that
    must stay correct, and this removes the need for it.
    """
    with tempfile.TemporaryDirectory() as plain:
        with pytest.raises(RuntimeError):
            tracked_paths(Path(plain), "*.py")


def test_the_scrubbed_env_is_what_the_helper_passes() -> None:
    """The scrub is not a parameter a caller may omit — it is in the helper."""
    source = (REPO_ROOT / "tools" / "lint" / "_scan_helpers.py").read_text(encoding="utf-8")
    body = source.split("def tracked_paths")[1].split("\ndef ")[0]
    assert "env=scrubbed_git_env()" in body, "tracked_paths must scrub unconditionally (#15176)"
    assert scrubbed_git_env is not None


def test_the_detector_reads_the_args_keyword_form() -> None:
    """`subprocess.run(args=[...])` is the same invocation (#15990 review).

    Asserted through `invokes_ls_files`, the predicate the sweep actually calls.
    An earlier version of this test re-implemented the argv logic inline and so
    passed identically with the fix reverted -- a contrast at the wrong layer
    cannot see the change it exists for.
    """
    call = next(
        n for n in ast.walk(ast.parse('subprocess.run(args=["git", "ls-files", "*.py"])')) if isinstance(n, ast.Call)
    )
    assert call.args == [], "fixture must use the keyword form for this to mean anything"
    assert invokes_ls_files(call)


def test_the_detector_does_not_report_an_unrelated_subprocess() -> None:
    """Contrast: reading the keyword must not flag every `args=` call."""
    call = next(n for n in ast.walk(ast.parse('subprocess.run(args=["git", "status"])')) if isinstance(n, ast.Call))
    assert not invokes_ls_files(call)


def _nested_repo(tmp_path: Path) -> Path:
    """A throwaway repository WITH SUBDIRECTORIES, built with a scrubbed env.

    The subdirectories are the point (#16013). The previous fixture wrote both
    files at the root, and **in a flat tree a rooted pathspec and a basename
    match return the same answer** — so the one distinction that breaks
    `exclude=` could not arise in the fixture certifying it. A flat fixture is a
    fixture that cannot fail.
    """
    repo = tmp_path / "r"
    (repo / "scripts").mkdir(parents=True)
    (repo / "pkg").mkdir(parents=True)
    env = scrubbed_git_env()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)  # nosec B603 B607
    # BOTH prefixed directories carry a test file, so the two-positive case is
    # symmetric with the one-positive case; otherwise the discriminator between
    # them is the fixture's asymmetry rather than the rooting behaviour.
    for rel in ("a.py", "a_test.py", "scripts/b.py", "scripts/b_test.py", "pkg/c.py", "pkg/c_test.py", "x.min.js"):
        (repo / rel).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)  # nosec B603 B607
    return repo


@pytest.mark.parametrize(
    "positive, entry, removed",
    [
        # The defect: ONE positive pathspec with a directory prefix. `git ls-files`
        # derives a common prefix and anchors traversal to it, so an unrooted
        # exclude matched every entry and emptied the result.
        (["scripts/*.py"], "*_test.py", {"scripts/b_test.py"}),
        # The discriminator: TWO positives under different top-level directories
        # empty the common prefix, and the identical exclude works. Row 4 passing
        # while row 3 fails is the entire defect, so a fixture with only one of
        # these shapes cannot see it (#16013).
        (["scripts/*.py", "pkg/*.py"], "*_test.py", {"scripts/b_test.py", "pkg/c_test.py"}),
        # No prefix at all — the shape that always worked, kept so a fix that
        # breaks it is caught.
        (["*.py"], "*_test.py", {"a_test.py", "scripts/b_test.py", "pkg/c_test.py"}),
        # Bare names: nothing distinguishes a file from a directory as a string.
        (["*"], "a.py", {"a.py"}),
        (["*"], "x.min.js", {"x.min.js"}),
        (["*"], "scripts", {"scripts/b.py", "scripts/b_test.py"}),
        # An already-rooted exclude must not be re-prefixed.
        (["*"], "scripts/*_test.py", {"scripts/b_test.py"}),
        # NO positive pattern at all. An empty `patterns` gave an empty prefix
        # set, so no exclusion pathspec was emitted and the exclude silently did
        # nothing — a full-length, plausible result (#16014 review).
        ([], "scripts", {"scripts/b.py", "scripts/b_test.py"}),
        ([], "a.py", {"a.py"}),
    ],
    ids=[
        "one-prefixed-positive",
        "two-prefixed-positives",
        "unprefixed-positive",
        "bare-file",
        "bare-file-with-dots",
        "bare-directory",
        "already-rooted",
        "no-positive-directory",
        "no-positive-file",
    ],
)
def test_exclude_removes_exactly_the_named_entry(tmp_path: Path, positive: list, entry: str, removed: set) -> None:
    """`exclude=` against every combination of positive shape and entry shape.

    Two variables, and each was wrong on its own: the ROOTING (an unrooted
    exclude under a single prefixed positive removed everything) and the
    FILE-vs-DIRECTORY guess (a bare file name became `name/*` and removed
    nothing). Holding either fixed while varying the other reports a working
    feature.
    """
    repo = _nested_repo(tmp_path)
    everything = set(tracked_paths(repo, *positive))
    kept = set(tracked_paths(repo, *positive, exclude=[entry]))

    assert (
        everything - kept == removed
    ), f"positive={positive} exclude={entry!r} removed {sorted(everything - kept)}, expected {sorted(removed)}"
    assert kept, "the exclusion emptied the population"


def test_the_floor_counts_parses_not_enumerated_paths() -> None:
    """The floor must bind to files READ, not to the list handed to the loop.

    `tracked_paths` can return 200 names while the sweep parses none of them.
    Binding the floor to the enumeration cannot tell those apart, which is the
    denominator-from-the-same-source defect one level up.
    """
    direct, parsed = _direct_invocations()
    enumerated = len(tracked_paths(REPO_ROOT, "repo_tests/*.py"))
    assert parsed <= enumerated, "more parses than files enumerated is impossible"
    assert parsed >= _MIN_FILES_PARSED
    assert isinstance(direct, list)


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.run(["git", "ls-files"])',
        "subprocess.run(args=['git', 'ls-files'])",
        "subprocess.Popen(['git', 'ls-files'])",
        "subprocess.Popen(args=['git', 'ls-files'])",
        "subprocess.check_output(['git', 'ls-files'])",
        "subprocess.check_output(args=['git', 'ls-files'])",
    ],
    ids=["run", "run-kw", "popen", "popen-kw", "check_output", "check_output-kw"],
)
def test_every_argv_form_is_read_positional_and_keyword(source: str) -> None:
    """All three subprocess entry points, both spellings — pinned ahead of a report.

    Three keyword blind spots surfaced in one day (`os.walk(top=)`,
    `Path.glob(pattern=)`, `subprocess.run(args=)`), each patched at the shape
    the review named. `run`, `Popen` and `check_output` all call their first
    parameter `args`, so one predicate covers six spellings — and this asserts
    that rather than waiting for a fourth review to name `Popen(args=)`.
    """
    call = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call))
    assert invokes_ls_files(call), f"missed: {source}"


def test_a_non_git_command_carrying_the_word_is_not_reported() -> None:
    """Contrast for the structural match: `printf ls-files` is not git (#15990).

    A substring test over the argv reported this as a direct invocation. The
    baseline would then move for a subprocess call that never touched git, and
    the census would be measuring something other than what it names.
    """
    call = next(n for n in ast.walk(ast.parse('subprocess.run(["printf", "ls-files"])')) if isinstance(n, ast.Call))
    assert not invokes_ls_files(call)


def test_this_module_is_inside_its_own_census() -> None:
    """A guard that exempts itself cannot see a bypass added to itself.

    Asserted on the census OUTPUT, not on this file's text: an earlier version
    grepped for the exemption line and matched its own assertion string.
    """
    direct, _ = _direct_invocations()
    own = [d for d in direct if Path(__file__).name in d]
    assert own, (
        "this module does not appear in its own census, so a direct `git ls-files` "
        "added here would not move the baseline. It holds exactly one deliberate "
        "invocation — the unscrubbed contrast fixture — and that one must be visible."
    )


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.call(["git", "ls-files"])',
        "subprocess.call(args=['git', 'ls-files'])",
        'subprocess.check_call(["git", "ls-files"])',
        "subprocess.check_call(args=['git', 'ls-files'])",
    ],
    ids=["call", "call-kw", "check_call", "check_call-kw"],
)
def test_the_call_execution_apis_are_covered(source: str) -> None:
    """`call` and `check_call` execute an argv too (#15990 review).

    I widened the KEYWORD axis ahead of a report and left the FUNCTION-NAME axis
    to be reported. Both are the same generalisation; only one got made in time.
    """
    call = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call))
    assert invokes_ls_files(call)


def test_a_name_merely_containing_an_executor_word_is_not_matched() -> None:
    """Exact attribute match, not substring — the flaw already found in the argv test.

    Without this, adding `call` to the set flags `recall(...)`, `caller(...)` and
    anything else whose name contains the word.
    """
    for source in ('recall(["git", "ls-files"])', 'my.caller(["git", "ls-files"])'):
        node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call))
        assert not invokes_ls_files(node), source
