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

import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests.unreferenced_shell_script_baseline import KNOWN_UNREFERENCED

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = "autobot-infrastructure/shared/scripts"

#: The tree held 118 tracked scripts when this guard landed. The floor is well
#: below that: it exists to catch the enumeration collapsing (a moved directory,
#: a broken glob), not to freeze the count.
MINIMUM_EXPECTED_SCRIPTS = 90


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
    return [path for path in scripts if not (mentions[Path(path).name] - {path})]


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


class TestTheTwoScriptsThisIssueResolved:
    def test_the_retired_script_is_gone(self, scripts):
        retired = f"{SCRIPT_DIR}/diagnose_startup_performance.sh"
        assert retired not in scripts
        assert retired not in KNOWN_UNREFERENCED

    def test_the_wired_in_script_is_referenced(self, scripts):
        """It is documented in docs/runbooks/ROTATE_SSH_KEYS.md, so it must not be unreferenced."""
        wired = f"{SCRIPT_DIR}/test-service-auth-deployment.sh"
        assert wired in scripts, "the service-auth pre-deployment check was removed"
        assert wired not in unreferenced(scripts)
        assert wired not in KNOWN_UNREFERENCED
