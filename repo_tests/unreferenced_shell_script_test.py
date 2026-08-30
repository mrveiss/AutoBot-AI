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

#15127 worked the original 21-entry baseline down to zero across four batches.
With nothing left to grandfather, the down-only baseline module and its ratchet
assertions are gone: ``TestNoNewUnreferencedScript`` below now enforces the
down-only end state directly -- every tracked script must be referenced, full
stop -- instead of via a subtraction against a list that is now permanently
empty. The regression classes for each already-landed batch stay: they are
what stops a decision this issue made from quietly rotting.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = "autobot-infrastructure/shared/scripts"
RUNBOOK = "docs/runbooks/ROTATE_SSH_KEYS.md"

#: The tree held 118 tracked scripts when this guard landed. The floor is well
#: below that: it exists to catch the enumeration collapsing (a moved directory,
#: a broken glob), not to freeze the count.
MINIMUM_EXPECTED_SCRIPTS = 90

#: Files that must not count as a reference, as repo-relative paths.
#:
#: Naming a script here is NOT a reference to it -- neither this module's own
#: mentions nor a baseline/ledger file that records a path because something
#: was *found* in it, not because anything calls it. Counting either would make
#: an entry "referenced" the instant it was written down, which is how
#: ensure-frontend-dependencies.sh sat unreferenced for a year while this guard
#: reported it clean: its only mention was a hardcoded-value finding against it
#: in pipeline-scripts/hardcoded_values_baseline.txt (#15127).
#:
#: Matched against ``git grep -l`` output, which is repo-relative by
#: construction, so this comparison is unaffected by where the checkout lives.
#: Deliberately NOT an absolute-path substring: that is the bug class behind
#: #15121 / #15140, where a filter matching on the absolute path answered
#: differently under ``.worktrees/`` than in an ordinary CI checkout.
NOT_A_REFERENCE = frozenset(
    {
        "repo_tests/unreferenced_shell_script_test.py",
        "pipeline-scripts/hardcoded_values_baseline.txt",
    }
)


def _git(*args: str) -> list[str]:
    """#15246: env scrubbed -- this deliberately reads the REAL repo (cwd=
    REPO_ROOT), and a scrub makes that authoritative instead of contingent on
    an inherited GIT_DIR happening to agree with it.
    """
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        env=scrubbed_git_env(),
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

    Without this the guard is self-defeating: naming a script somewhere that
    is not a caller makes it "referenced", so the guard passes while asserting
    the opposite of the truth. It failed in CI exactly that way once and passed
    locally only because the file doing the naming was still untracked --
    ``git grep`` reads tracked content, so an uncommitted file is invisible to
    the scan. A local pass carried no information, which is #15091 in miniature.
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


class TestNoNewUnreferencedScript:
    """The down-only end state (#15127): every tracked script must be referenced.

    The baseline module is gone -- it reached zero and was deleted alongside
    this ratchet (AC4). There is nothing left to subtract, so this is the same
    assertion this class made throughout #15127, now unconditional.
    """

    def test_every_script_is_referenced(self, scripts):
        offenders = sorted(unreferenced(scripts))
        assert not offenders, (
            "these scripts have no inbound reference from any other tracked file:\n  "
            + "\n  ".join(offenders)
            + "\n\nGive each one a caller, or document it as an operator procedure where an "
            "operator would look, or retire it."
        )


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

    @pytest.mark.parametrize("name,document", sorted(KEPT.items()))
    def test_kept_script_is_referenced_by_its_document(self, scripts, name, document):
        path = f"{SCRIPT_DIR}/{name}"
        assert path in scripts, f"{name} was kept and documented but is no longer tracked"
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


class TestTheSecondBatchThisIssueResolved:
    """#15127 batch two: two retired, two wired in, two documented.

    Same standard as batch one -- a kept script is pinned to the document whose
    entry is the reason it is not debris, and a wired-in script is pinned to the
    defect that made it unrunnable, not merely to "is referenced".
    """

    RETIRED = (
        "start_seq.sh",
        "utilities/ollama_thread_utility.sh",
    )

    #: Files retired alongside a script because nothing else named them.
    RETIRED_COMPANIONS = (
        f"{SCRIPT_DIR}/utilities/ollama.service.new",
        "autobot-infrastructure/shared/systemd/ollama.service.new",
    )

    #: kept script -> the file whose reference is the reason it is not debris.
    KEPT = {
        "backup_ollama_models.sh": f"{SCRIPT_DIR}/README.md",
        "build_secure_sandbox.sh": f"{SCRIPT_DIR}/README.md",
        "utilities/security-audit.sh": f"{SCRIPT_DIR}/README.md",
        "debug_chat_system.sh": "docs/development/MCP_DEBUG_SCENARIOS.md",
    }

    #: The build context the sandbox Dockerfile's COPY paths resolve against.
    SANDBOX_CONTEXT = "autobot-infrastructure/shared"

    @pytest.mark.parametrize("name", RETIRED)
    def test_retired_script_is_gone_from_tree_and_baseline(self, scripts, name):
        path = f"{SCRIPT_DIR}/{name}"
        assert path not in scripts, f"{name} was retired but is tracked again"

    @pytest.mark.parametrize("path", RETIRED_COMPANIONS)
    def test_retired_companion_file_is_gone(self, path):
        """Both ollama.service.new copies existed only for the retired utility.

        Each also pinned a PATH from one developer's machine, so re-adding one
        would reintroduce a unit file that cannot work on any other host.
        """
        assert not (REPO_ROOT / path).exists(), f"{path} was retired with its only caller but is back"

    @pytest.mark.parametrize("name,document", sorted(KEPT.items()))
    def test_kept_script_is_referenced_by_its_document(self, scripts, name, document):
        path = f"{SCRIPT_DIR}/{name}"
        assert path in scripts, f"{name} was kept and documented but is no longer tracked"
        text = (REPO_ROOT / document).read_text(encoding="utf-8")
        assert name in text, (
            f"{document} no longer names {name}. That entry is the whole reason the script is "
            "not debris -- restore it or retire the script (#15127)."
        )

    def test_the_sandbox_builder_can_reach_every_input_it_builds_from(self):
        """The builder named a Dockerfile path that had not held it since the moves.

        ``autobot/secure-sandbox:latest`` is what ``secure_sandbox_executor.py``
        runs code-execution containers from, and this script is its only builder,
        so a stale ``-f`` here means the image can never be produced.
        """
        context = REPO_ROOT / self.SANDBOX_CONTEXT
        dockerfile = context / "docker/secure-sandbox.Dockerfile"
        assert dockerfile.is_file(), "the sandbox Dockerfile must sit in the context its COPY paths assume"

        copied = re.findall(r"^COPY\s+(\S+)\s", dockerfile.read_text(encoding="utf-8"), re.MULTILINE)
        assert copied, "no COPY instructions found; the parse is broken, not the Dockerfile"
        missing = sorted(source for source in copied if not (context / source).exists())
        assert not missing, f"the sandbox Dockerfile COPYs paths absent from its build context: {missing}"

    def test_the_sandbox_builder_refuses_to_tag_an_unhardened_image(self):
        """It used to build a bare alpine and tag it as the hardened sandbox.

        The executor and the code-execution smoke gate both treat that tag as
        proof of hardening, so a silent downgrade defeats the boundary itself.
        """
        builder = (REPO_ROOT / SCRIPT_DIR / "build_secure_sandbox.sh").read_text(encoding="utf-8")
        assert "docker/secure-sandbox.Dockerfile" in builder
        assert "FROM alpine" not in builder, "the fabricated fallback Dockerfile is back"
        assert builder.count("docker build") == 1, (
            "more than one build in the sandbox builder means a fallback image can be tagged "
            "autobot/secure-sandbox:latest when the hardened build fails"
        )

    def test_the_chat_debugger_anchors_its_helpers_to_the_project_root(self):
        """It sourced project_root.sh and then ignored it, so it ran only from the root."""
        debugger = (REPO_ROOT / SCRIPT_DIR / "debug_chat_system.sh").read_text(encoding="utf-8")
        assert "node .mcp/autobot-mcp-server.js" not in debugger
        assert 'node "${PROJECT_ROOT}/.mcp/autobot-mcp-server.js"' in debugger
        assert (REPO_ROOT / ".mcp/autobot-mcp-server.js").is_file()
        assert 'chmod +x "$0"' not in debugger, "a script must not chmod itself on every run"

    def test_the_security_audit_does_not_stop_at_its_first_finding(self):
        """``set -e`` plus a post-increment on a zero counter aborted the audit.

        The arithmetic result of the first bump is 0, which bash reports as exit
        status 1, so the sweep died the moment it found something -- before the
        remaining checks and the summary.
        """
        audit = (REPO_ROOT / SCRIPT_DIR / "utilities/security-audit.sh").read_text(encoding="utf-8")
        assert "set -e" in audit, "the guard below only matters while this runs under set -e"
        bumps = re.findall(r"^\s*\(\(\s*\w+\s*(?:\+\+|\+=)", audit, re.MULTILINE)
        assert not bumps, f"arithmetic-command counter bumps are back under set -e: {bumps}"


class TestTheTwoScriptsThisIssueResolved:
    def test_the_retired_script_is_gone(self, scripts):
        retired = f"{SCRIPT_DIR}/diagnose_startup_performance.sh"
        assert retired not in scripts

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
