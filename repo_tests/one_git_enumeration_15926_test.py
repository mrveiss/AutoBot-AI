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

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Direct `git ls-files` invocations in `repo_tests/`, measured on the tree.
#: THIS ONLY SHRINKS. Never raise it to make a new bypass pass — route the new
#: guard through `tracked_paths` instead. #15926 tracks driving it to zero.
MAX_DIRECT_INVOCATIONS = 40

#: Floor on files EXAMINED, not on findings. A findings floor is satisfied by
#: finding nothing, which is also what a collapsed sweep reports.
_MIN_FILES_PARSED = 180


def _direct_invocations() -> list[str]:
    """`repo_tests` sites that shell out to `git ls-files` themselves."""
    found: list[str] = []
    for rel in tracked_paths(REPO_ROOT, "repo_tests/*.py"):
        if Path(rel).name == Path(__file__).name:
            continue  # this file names the verb in prose and in its own fixtures
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not any(k in ast.unparse(node.func) for k in ("run", "check_output", "Popen")):
                continue
            if "ls-files" not in " ".join(ast.unparse(a) for a in node.args):
                continue
            found.append(f"{rel}:{node.lineno}")
    return sorted(set(found))


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
    parsed = len(tracked_paths(REPO_ROOT, "repo_tests/*.py"))
    assert parsed >= _MIN_FILES_PARSED, (
        f"the sweep parsed {parsed} files, below the floor of {_MIN_FILES_PARSED} — "
        "a shrunken population reports 'no bypasses' for the same reason a migrated tree does"
    )
    direct = _direct_invocations()
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
