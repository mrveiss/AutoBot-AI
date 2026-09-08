# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two frontend gates run locally when they can, and say so when they cannot (#15933).

`scripts/pr-preflight.sh` skipped `verify-generated-types` and
`Unit & Integration Tests` outright, with the reason recorded at the skip:
each *appeared* to need an `npm ci` first, and a preflight that installs
packages is one that gets run once and then avoided.

That reasoning was right about one of them and wrong about the other.

**`verify:types` needs no `node_modules` at all.** It is
`git diff --exit-code src/types/generated/api.ts` -- a git command wearing an
npm script's clothes. Skipping it cost a gate for a dependency it never had,
and the assumption survived because "needs npm" was true of its neighbour.

`test:unit` is `vitest run` and genuinely needs the workspace, so it stays
conditional -- on a **check**, never an install, mirroring what this script
already does for Python with `setup-ci-parity-env.sh --check` at the top.

The freshness test is `node_modules/.package-lock.json` against
`package-lock.json`: npm writes the former on every install, so a lockfile
newer than it means the tree was installed from a different one. No npm
invocation, because asking npm whether npm needs to run is slow enough that
people stop running the preflight.

These tests **extract and execute the shipped predicate** rather than
restating it. A restatement agrees with itself and proves nothing -- the same
reason the pre-push split tests (#16069) run the hook's own grep expressions.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from repo_tests._paths import repo_root

_SCRIPT = repo_root() / "scripts" / "pr-preflight.sh"

#: The shipped function, lifted whole. Fails loudly if it is renamed or moved,
#: rather than silently testing nothing.
_PREDICATE = re.compile(
    r"^  frontend_deps_current\(\) \{\n(?:.*\n)*?  \}$",
    re.MULTILINE,
)


def _predicate_source() -> str:
    match = _PREDICATE.search(_SCRIPT.read_text(encoding="utf-8"))
    assert match, (
        "frontend_deps_current() is no longer where this test extracts it from. "
        "If the gate moved, move this test with it -- do not delete it."
    )
    return match.group(0)


def _run(ws_setup: str) -> bool:
    """True when the shipped predicate reports the workspace usable."""
    script = f"""
set -u
REPO_ROOT="$1"
{_predicate_source()}
mkdir -p "$REPO_ROOT/autobot-frontend"
{ws_setup}
frontend_deps_current && echo CURRENT || echo STALE
"""
    # `bash -c CMD a b` sets $0=a and $1=b, not $1=a. An earlier version passed
    # the temp directory as the first argument and it landed in $0, so REPO_ROOT
    # was empty and every case reported STALE -- three of the four tests below
    # passed for that reason rather than for the behaviour they name. The
    # positive control is what caught it, which is the whole reason it is here.
    completed = subprocess.run(
        ["bash", "-c", 'd=$(mktemp -d); bash -c "$0" _ "$d"; rm -rf "$d"', script],
        capture_output=True,
        text=True,
    )
    return "CURRENT" in completed.stdout


def test_a_missing_node_modules_is_stale() -> None:
    assert not _run('touch "$REPO_ROOT/autobot-frontend/package-lock.json"')


def test_node_modules_without_its_lock_marker_is_stale() -> None:
    """npm writes `.package-lock.json` on install; without it nothing was installed."""
    assert not _run(
        'mkdir -p "$REPO_ROOT/autobot-frontend/node_modules"; '
        'touch "$REPO_ROOT/autobot-frontend/package-lock.json"'
    )


def test_a_lockfile_newer_than_the_install_is_stale() -> None:
    """The case the gate exists for: someone pulled a lockfile change."""
    assert not _run(
        'mkdir -p "$REPO_ROOT/autobot-frontend/node_modules"; '
        'touch -t 202001010000 "$REPO_ROOT/autobot-frontend/node_modules/.package-lock.json"; '
        'touch "$REPO_ROOT/autobot-frontend/package-lock.json"'
    )


def test_an_install_at_or_after_the_lockfile_is_current() -> None:
    """The positive control. Without it, a predicate that always said STALE would pass every test above."""
    assert _run(
        'mkdir -p "$REPO_ROOT/autobot-frontend/node_modules"; '
        'touch -t 202001010000 "$REPO_ROOT/autobot-frontend/package-lock.json"; '
        'touch "$REPO_ROOT/autobot-frontend/node_modules/.package-lock.json"'
    )


@pytest.mark.parametrize(
    "context,must_be_conditional",
    [("verify-generated-types", False), ("Unit & Integration Tests", True)],
)
def test_each_gate_is_wired_to_what_it_actually_needs(context: str, must_be_conditional: bool) -> None:
    """Structural, because the behavioural tests above cannot see which gate got which treatment.

    `verify-generated-types` must NOT sit behind the freshness check -- it needs
    no node_modules, and gating it would re-lose the gate this change recovers.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    assert f'skip_check "{context}"' in source or f'require_check "{context}"' in source

    gate_block = source.split("frontend_deps_current; then", 1)
    assert len(gate_block) == 2, "the conditional gate is gone -- both would now run unguarded"
    before, after = gate_block

    if must_be_conditional:
        assert f'require_check "{context}"' in after, f"{context} must stay behind the freshness check"
    else:
        assert f'require_check "{context}"' in before, (
            f"{context} was moved behind the freshness check. `npm run verify:types` is "
            "`git diff --exit-code` and needs no node_modules -- gating it loses the gate."
        )
