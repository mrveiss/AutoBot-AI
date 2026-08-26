# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A shell script under the infrastructure tree must be reachable from something (#15079).

Two scripts sat there with zero inbound references. Both had been dead since the
#926 restructure and neither had ever had a caller -- the introducing commits
added none. Nothing noticed for a year, because nothing was looking.

A reference is any mention in any other tracked file: a caller, a workflow step,
or a documented operator procedure. That last one matters -- a genuine manual
tool is not debris, but it has to be written down where an operator would find
it, and this guard is what makes that documentation load-bearing rather than
optional.

The enumeration is asserted before it is used. A sweep that silently returns
nothing would report a clean tree forever, which is exactly how #15087 shipped.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests.unreferenced_shell_script_baseline import KNOWN_UNREFERENCED

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = "autobot-infrastructure/shared/scripts"
RUNBOOK = "docs/runbooks/ROTATE_SSH_KEYS.md"

#: The tree held 118 tracked scripts when this guard landed. The floor is well
#: below that: it exists to catch the enumeration collapsing (a moved directory,
#: a broken glob), not to freeze the count.
MINIMUM_EXPECTED_SCRIPTS = 90

#: This guard's own bookkeeping, as repo-relative paths.
#:
#: Naming a script here is NOT a reference to it. The baseline lists every known
#: orphan by path and this module names the scripts #15079 resolved, so counting
#: them would make each entry "referenced" the instant it was written down --
#: the guard would then pass forever while reporting the opposite of the truth.
#:
#: Matched against ``git grep -l`` output, which is repo-relative by
#: construction, so this comparison is unaffected by where the checkout lives.
#: Deliberately NOT an absolute-path substring: that is the bug class behind
#: #15121 / #15140, where a filter matching on the absolute path answered
#: differently under ``.worktrees/`` than in an ordinary CI checkout.
NOT_A_REFERENCE = frozenset(
    {
        "repo_tests/unreferenced_shell_script_baseline.py",
        "repo_tests/unreferenced_shell_script_test.py",
    }
)


def _git(*args: str) -> list[str]:
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    if result.returncode not in (0, 1):  # 1 = git grep found nothing
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.split()


def tracked_scripts() -> list[str]:
    """Every tracked ``.sh`` under the infrastructure script tree."""
    return sorted(path for path in _git("ls-files") if path.startswith(f"{SCRIPT_DIR}/") and path.endswith(".sh"))


def _files_mentioning(names: list[str]) -> list[str]:
    """Tracked text files containing any of *names*, in one git grep pass."""
    patterns: list[str] = []
    for name in names:
        patterns += ["-e", name]
    return _git("grep", "-I", "-F", "-l", *patterns)


def unreferenced(scripts: list[str]) -> list[str]:
    """Scripts mentioned by no tracked file other than themselves."""
    names = sorted({Path(path).name for path in scripts})
    mentions: dict[str, set[str]] = {name: set() for name in names}
    for candidate in _files_mentioning(names):
        try:
            text = (REPO_ROOT / candidate).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in names:
            if name in text:
                mentions[name].add(candidate)
    return [path for path in scripts if not (mentions[Path(path).name] - {path} - NOT_A_REFERENCE)]


@pytest.fixture(scope="module")
def scripts() -> list[str]:
    return tracked_scripts()


class TestEnumeration:
    """The sweep must prove it swept something before any verdict is drawn."""

    def test_enumeration_is_not_empty(self, scripts):
        assert scripts, (
            f"no tracked .sh files found under {SCRIPT_DIR}/ -- the sweep found nothing, "
            "which is a broken enumeration, not a clean tree (#15087)"
        )

    def test_enumeration_has_not_collapsed(self, scripts):
        assert len(scripts) >= MINIMUM_EXPECTED_SCRIPTS, (
            f"only {len(scripts)} scripts enumerated under {SCRIPT_DIR}/, expected at least "
            f"{MINIMUM_EXPECTED_SCRIPTS}; if the tree really shrank, lower the floor deliberately"
        )

    def test_the_reference_search_finds_something(self, scripts):
        """A grep that returns nothing would mark every script unreferenced."""
        names = sorted({Path(path).name for path in scripts})
        assert _files_mentioning(names), "the reference search matched no file at all"


class TestOwnBookkeepingIsNotAReference:
    """The guard must not count its own records as references (#15079 review).

    Without this the guard is self-defeating: writing a script into the baseline
    makes it "referenced", so the ratchet passes while asserting the opposite of
    the truth. It failed in CI exactly that way and passed locally only because
    both files were still untracked -- ``git grep`` reads tracked content, so an
    uncommitted baseline is invisible to the scan. A local pass carried no
    information, which is #15091 in miniature.
    """

    def test_bookkeeping_files_are_tracked(self):
        """Untracked bookkeeping is invisible to git grep and the scan changes answer."""
        tracked = set(_git("ls-files"))
        missing = sorted(NOT_A_REFERENCE - tracked)
        assert not missing, (
            "these are not tracked, so git grep cannot see them and this guard would "
            f"silently give a different verdict here than in CI: {missing}"
        )

    def test_bookkeeping_paths_still_exist(self):
        """A rename would silently stop the exclusion applying."""
        for relative in sorted(NOT_A_REFERENCE):
            assert (REPO_ROOT / relative).is_file(), f"{relative} no longer exists"

    def test_bookkeeping_paths_are_repo_relative(self):
        """#15121 / #15140: an absolute-path filter answers differently under .worktrees/."""
        for relative in sorted(NOT_A_REFERENCE):
            assert not relative.startswith("/"), f"{relative} must be repo-relative"

    def test_every_baselined_script_is_named_only_by_the_bookkeeping(self, scripts):
        """Proves the exclusion is doing the work, for every entry.

        Sampling one entry proved it for a script chosen by alphabetical
        accident, and the subject would drift silently the moment a batch
        removed that name (#15144 review). Iterating costs one grep per entry.
        """
        baselined = sorted(KNOWN_UNREFERENCED & set(scripts))
        assert baselined, "baseline holds no script that exists; nothing to prove against"
        offenders: dict[str, list[str]] = {}
        for path in baselined:
            mentioning = set(_files_mentioning([Path(path).name])) - {path}
            assert mentioning, f"expected {path} to be named by the bookkeeping at least"
            outside = sorted(mentioning - NOT_A_REFERENCE)
            if outside:
                offenders[path] = outside
        assert not offenders, (
            "these are named outside this guard's bookkeeping, so they are genuinely "
            "referenced and must leave KNOWN_UNREFERENCED:\n  "
            + "\n  ".join(f"{k} <- {v}" for k, v in sorted(offenders.items()))
        )


class TestNoNewUnreferencedScript:
    def test_every_script_is_referenced_or_baselined(self, scripts):
        offenders = sorted(set(unreferenced(scripts)) - KNOWN_UNREFERENCED)
        assert not offenders, (
            "these scripts have no inbound reference from any other tracked file:\n  "
            + "\n  ".join(offenders)
            + "\n\nGive each one a caller, or document it as an operator procedure where an "
            "operator would look, or retire it. Adding it to KNOWN_UNREFERENCED is not an "
            "option -- that list is down-only (#15079)."
        )


class TestBaselineRatchetsDownOnly:
    def test_no_baselined_script_has_gained_a_reference(self, scripts):
        """A script that is now referenced must leave the baseline in the same change."""
        still_unreferenced = set(unreferenced(scripts))
        stale = sorted(KNOWN_UNREFERENCED & set(scripts) - still_unreferenced)
        assert not stale, "these are referenced now and must be removed from KNOWN_UNREFERENCED:\n  " + "\n  ".join(
            stale
        )

    def test_no_baselined_script_has_disappeared(self, scripts):
        """A retired script must leave the baseline too, or the list rots."""
        gone = sorted(KNOWN_UNREFERENCED - set(scripts))
        assert not gone, "these no longer exist and must be removed from KNOWN_UNREFERENCED:\n  " + "\n  ".join(gone)

    def test_baseline_is_not_empty_while_it_is_still_being_worked_through(self):
        """Guards the guard: an accidentally emptied baseline would mask nothing.

        This is the inverse of the usual empty-enumeration trap. If the baseline
        is ever legitimately emptied, delete it and this assertion together --
        that is the success condition, and it should be a deliberate change.
        """
        assert KNOWN_UNREFERENCED, "baseline emptied; remove the file and this test together"


class TestTheBatchThisIssueResolved:
    """#15127 batch one: five retired, two wired in, three recorded.

    Each kept script is pinned to the document that references it, not merely to
    "is referenced" -- that weaker form is what #15079 review found passing on
    this module's own mention of the filename.
    """

    RETIRED = (
        "git-askpass.sh",
        "start_vnc.sh",
        "utilities/create_github_issues.sh",
        "utilities/load-env.sh",
        "utilities/sync-grafana-dashboards.sh",
    )

    #: kept script -> the file whose reference is the reason it is not debris.
    KEPT = {
        "cleanup-disk-space.sh": f"{SCRIPT_DIR}/README.md",
        "install-doc-sync-hook.sh": f"{SCRIPT_DIR}/README.md",
        "monitor_testing.sh": f"{SCRIPT_DIR}/README.md",
        "utilities/start-seq-forwarder.sh": f"{SCRIPT_DIR}/README.md",
        "network/fix-wsl-networking.sh": "docs/developer/WSL2_NETWORKING.md",
    }

    @pytest.mark.parametrize("name", RETIRED)
    def test_retired_script_is_gone_from_tree_and_baseline(self, scripts, name):
        path = f"{SCRIPT_DIR}/{name}"
        assert path not in scripts, f"{name} was retired but is tracked again"
        assert path not in KNOWN_UNREFERENCED, f"{name} was retired but still sits in the baseline"

    @pytest.mark.parametrize("name,document", sorted(KEPT.items()))
    def test_kept_script_is_referenced_by_its_document(self, scripts, name, document):
        path = f"{SCRIPT_DIR}/{name}"
        assert path in scripts, f"{name} was kept and documented but is no longer tracked"
        assert path not in KNOWN_UNREFERENCED
        text = (REPO_ROOT / document).read_text(encoding="utf-8")
        assert name in text, (
            f"{document} no longer names {name}. That entry is the whole reason the script is "
            "not debris -- restore it or retire the script (#15127)."
        )

    def test_the_wired_in_scripts_point_at_files_that_exist(self):
        """Both were unrunnable from any directory: each named a path #781 removed."""
        installer = (REPO_ROOT / SCRIPT_DIR / "install-doc-sync-hook.sh").read_text(encoding="utf-8")
        assert (
            'HOOK_SOURCE="$PROJECT_ROOT/autobot-infrastructure/shared/scripts/hooks/post-commit-doc-sync"' in installer
        )
        assert (REPO_ROOT / SCRIPT_DIR / "hooks/post-commit-doc-sync").is_file()

        forwarder = (REPO_ROOT / SCRIPT_DIR / "utilities/start-seq-forwarder.sh").read_text(encoding="utf-8")
        assert 'FORWARDER="${SCRIPT_DIR}/../seq_log_forwarder.py"' in forwarder
        assert (REPO_ROOT / SCRIPT_DIR / "seq_log_forwarder.py").is_file()
        runs_pip = re.compile(r"^\s*(sudo\s+)?(pip3?|python3?\s+-m\s+pip)\s+install\b", re.MULTILINE)
        assert not runs_pip.search(forwarder), (
            "a helper script must not install into the caller's interpreter; naming the command in "
            "an error message is fine, running it is not"
        )


class TestTheTwoScriptsThisIssueResolved:
    def test_the_retired_script_is_gone(self, scripts):
        retired = f"{SCRIPT_DIR}/diagnose_startup_performance.sh"
        assert retired not in scripts
        assert retired not in KNOWN_UNREFERENCED

    def test_the_wired_in_script_is_referenced_by_the_runbook(self, scripts):
        """The runbook entry is the wire-in. Name it, or this passes on its own mention.

        Before #15129's review this asserted only "not unreferenced", which this
        module satisfied by naming the script in the line above -- green while the
        runbook entry it protects could have been deleted outright.
        """
        wired = f"{SCRIPT_DIR}/test-service-auth-deployment.sh"
        assert wired in scripts, "the service-auth pre-deployment check was removed"
        mentioning = set(_files_mentioning([Path(wired).name])) - {wired} - NOT_A_REFERENCE
        assert RUNBOOK in mentioning, (
            f"{RUNBOOK} no longer names the pre-deployment check; the wire-in is gone. "
            f"Named instead by: {sorted(mentioning) or 'nothing'}"
        )
        assert wired not in unreferenced(scripts)
        assert wired not in KNOWN_UNREFERENCED
