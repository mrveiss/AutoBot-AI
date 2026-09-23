# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two hardcoded-value entry points must agree on which files are in scope (#17329).

`pipeline-scripts/detect-hardcoded-values.sh` walks a fixed list of directories.
`autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values` sees
whatever is staged. The list lived in the scan alone, so the hook never applied
it, and any staged file outside those trees was:

* **blocked** on commit by the hook,
* **invisible** to the scan, and therefore
* **impossible** to baseline -- the baseline is keyed to what the scan finds and
  ``--audit-baseline`` fails on an entry the scan cannot reproduce.

The only way to commit such a file was ``--no-verify``, which switches off every
other hook to get past one. That is not a policy anyone chose; it is two callers
disagreeing about scope, and it stayed invisible because each side was correct on
its own.

The fix is one list in the shared rules library, read by both. These checks are
the half that stops it drifting apart again -- a second literal list would
reintroduce the gap while every individual file still looked right.
"""

import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

REPO = repo_root()
RULES = REPO / "scripts" / "lib" / "hardcoded-value-rules.sh"
SCAN = REPO / "pipeline-scripts" / "detect-hardcoded-values.sh"
HOOK = REPO / "autobot-infrastructure" / "shared" / "scripts" / "hooks" / "pre-commit-hardcoded-values"


def _code(path: Path) -> str:
    """The file's executable lines only.

    Comment lines are stripped before any containment check. Without this the
    checks below pass on their own explanation: the first version of this guard
    asserted `"hv_path_in_scan_dirs" in body`, and when the call was deleted
    from `get_files_to_scan` the string still matched the comment above it that
    describes the call. The guard reported green on the exact regression it
    exists to catch -- found by running that mutation rather than by reading it.
    """
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )


def _bash(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["bash", "-c", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_shared_library_owns_the_directory_list():
    """The list is defined once, where both callers can read it."""
    assert RULES.exists(), f"the shared rule library is missing: {RULES}"
    source = _code(RULES)
    assert "HV_SCAN_DIRS=(" in source, (
        "scripts/lib/hardcoded-value-rules.sh no longer defines HV_SCAN_DIRS -- "
        "if the scope moved, both callers must move with it"
    )
    assert "hv_path_in_scan_dirs()" in source, "the shared directory-scope predicate is gone"


def test_the_scan_reads_the_shared_list_rather_than_its_own():
    """A second literal list is how the two sides drifted apart in the first place."""
    body = _code(SCAN)
    assert 'SCAN_DIRS=("${HV_SCAN_DIRS[@]}")' in body, (
        "detect-hardcoded-values.sh must take its directories from HV_SCAN_DIRS; a literal "
        "list here is invisible to the hook, which is exactly the #17329 gap"
    )


def test_the_hook_applies_the_same_directory_scope():
    """Without this the hook blocks files the scan never visits."""
    body = _code(HOOK)
    assert "hv_path_in_scan_dirs" in body, (
        "the pre-commit hook does not apply the directory scope, so a staged file outside "
        "HV_SCAN_DIRS is blocked on commit while the scan cannot see it and the baseline "
        "cannot absorb it (#17329)"
    )


@pytest.mark.parametrize(
    ("path", "expected_in_scope"),
    [
        ("autobot-backend/api/x.py", True),
        ("autobot-frontend/src/main.ts", True),
        ("autobot-slm-frontend/src/App.vue", True),
        ("autobot_shared/redis_client.py", True),
        ("autobot-infrastructure/deploy.sh", True),
        # #17329 option 2, now measured and taken: each frontend's project
        # root and scripts/ are scanned, so the configs that could previously
        # be neither committed nor baselined are in scope for BOTH sides.
        ("autobot-frontend/vitest.config.ts", True),
        ("autobot-frontend/vite.config.ts", True),
        ("autobot-slm-frontend/vitest.config.ts", True),
        ("scripts/whatever.sh", True),
        # A repo-root file still belongs to no scanned tree.
        ("vite.config.ts", False),
        ("docs/whatever.md", False),
    ],
)
def test_the_predicate_agrees_with_the_declared_directories(path: str, expected_in_scope: bool):
    result = _bash(f'source "{RULES}"; hv_path_in_scan_dirs "{path}"')
    assert result.returncode == (0 if expected_in_scope else 1), (
        f"hv_path_in_scan_dirs({path!r}) returned {result.returncode}, "
        f"expected {'in scope' if expected_in_scope else 'out of scope'}"
    )


def test_the_scan_resolves_exactly_the_declared_directories():
    """The set is asserted so it can only change deliberately.

    #17329 widened it once, on purpose: `autobot-frontend/src` became
    `autobot-frontend` (and the same for the SLM app), and `scripts/` was
    added, because a file in those trees could be neither committed through
    the hook nor absorbed by the baseline. Every finding that widening
    surfaced is fixed or carries a reviewed baseline entry in the same change.
    """
    result = _bash(f'source "{RULES}"; printf "%s\\n" "${{HV_SCAN_DIRS[@]}}"')
    assert result.returncode == 0, result.stderr
    dirs = [line for line in result.stdout.splitlines() if line]
    assert dirs == [
        "autobot-backend",
        "autobot-frontend",
        "autobot_shared",
        "autobot-slm-backend",
        "autobot-slm-frontend",
        "autobot-infrastructure",
        "scripts",
    ], f"the scanned directory set changed: {dirs}"
