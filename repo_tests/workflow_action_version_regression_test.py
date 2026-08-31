# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No workflow or composite action may pin an action older than the version
already standard elsewhere in the repository (#15332).

Two of the three drifted call sites #15332 found were composite actions under
``.github/actions/`` — a sweep over ``.github/workflows/*.yml`` alone would
have missed them, which is why this guard walks both directories. The third
was a tag pinned against an older example instead of the repo's actual
standard, and no check caught the divergence before merge.

Scope, deliberately narrow: this compares **tag-pinned** refs only
(``@v7``, ``@v6``, ...), grouped by the exact ``owner/repo[/subpath]`` string
before the ``@``. SHA-pinned actions are excluded from the cross-version
comparison — several (``docker/login-action``, ``docker/build-push-action``,
``sigstore/cosign-installer``) are genuinely pinned to different releases in
different workflows today, pre-dating this guard, and asserting consistency
there requires a resolution this issue's fix does not include. What the
guard does assert for SHA-pinned actions is narrower and unconditionally
true today: every SHA pin carries a trailing ``# vX.Y.Z``-shaped comment, so
its version is at least *readable* even though it cannot be diffed against a
tag. That is the "low-cost improvement" #15332 asked for in place of
resolving all sixteen SHA pins to Node runtimes, which would be a much larger
mechanism for the same annotation this guard is meant to make a real gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONS_DIR = REPO_ROOT / ".github" / "actions"

# `uses: owner/repo[/path]@ref` or `- uses: owner/repo[/path]@ref`, optionally
# trailed by a `# vX.Y.Z`-shaped comment. Local (`./...`) actions are skipped —
# they carry no version to compare.
USES_PATTERN = re.compile(
    r"^\s*-?\s*uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w./-]+)?)@(?P<ref>[0-9a-zA-Z.]+)"
    r"(?:\s*#\s*(?P<comment_version>v?\d+(?:\.\d+){0,2}))?\s*$"
)
TAG_VERSION_PATTERN = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class ActionUse:
    path: Path
    line_no: int
    action: str
    ref: str
    comment_version: str | None


def _workflow_files() -> list[Path]:
    files = sorted(WORKFLOW_DIR.glob("*.yml"))
    files += sorted(ACTIONS_DIR.glob("*/action.yml"))
    return files


def _extract_uses(files: list[Path]) -> list[ActionUse]:
    uses: list[ActionUse] = []
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = USES_PATTERN.match(line)
            if not match or match.group("action").startswith("."):
                continue
            uses.append(
                ActionUse(path, line_no, match.group("action"), match.group("ref"), match.group("comment_version"))
            )
    return uses


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = TAG_VERSION_PATTERN.match(version)
    if not match:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor or 0), int(patch or 0))


def test_the_scan_actually_finds_action_pins():
    """A glob or regex that matched nothing would make both guards below vacuous."""
    uses = _extract_uses(_workflow_files())
    assert len(uses) >= 100, f"Only found {len(uses)} 'uses:' pins — the scan is broken, not the repository."
    # A raw total does not protect the coverage this guard was built for:
    # .github/workflows/*.yml alone clears 100 on its own, so dropping the
    # ACTIONS_DIR glob from _workflow_files() would keep this green while
    # silently removing composite actions -- where two of the three drifted
    # pins that motivated #15332 actually lived.
    from_actions = [use for use in uses if use.path.is_relative_to(ACTIONS_DIR)]
    assert from_actions, (
        "no 'uses:' pins found under .github/actions — composite actions have dropped out "
        "of the sweep. The total above stays green without them, which is why this is checked "
        "separately (#15332)."
    )


def test_every_sha_pinned_action_carries_a_readable_version_comment():
    """#15332: a SHA pin without a version comment cannot be checked against anything.

    All sixteen SHA-pinned actions in the repository already carry a trailing
    `# vX.Y.Z` comment; this guard is what keeps that true for the next one.
    """
    uses = _extract_uses(_workflow_files())
    violations = [
        f"{use.path.relative_to(REPO_ROOT)}:{use.line_no} pins {use.action}@{use.ref} "
        "(a 40-char SHA) with no trailing '# vX.Y.Z' comment"
        for use in uses
        if SHA_PATTERN.match(use.ref) and not use.comment_version
    ]
    assert not violations, "SHA-pinned action(s) with no readable version:\n" + "\n".join(violations)


def _version_regressions(uses: list[ActionUse]) -> list[str]:
    """Every tag pin older than the best version of the same action, reported together."""
    best_by_action: dict[str, tuple[int, int, int]] = {}
    for use in uses:
        version = _version_tuple(use.ref)
        if version is not None and version > best_by_action.get(use.action, (0, 0, 0)):
            best_by_action[use.action] = version
    violations = []
    for use in uses:
        version = _version_tuple(use.ref)
        if version is None or version >= best_by_action[use.action]:
            continue
        best = ".".join(map(str, best_by_action[use.action]))
        violations.append(
            f"{use.path}:{use.line_no} pins {use.action}@{use.ref}, "
            f"older than v{best} already used elsewhere in the repository"
        )
    return violations


def test_no_tag_pinned_action_is_older_than_the_repo_standard():
    """#15332 AC4: a new file cannot reintroduce a tag version older than one already in use.

    Restricted to tag-pinned refs (SHA pins are excluded — see module
    docstring) grouped by the exact action string, including any subpath.
    """
    uses = [use for use in _extract_uses(_workflow_files()) if not SHA_PATTERN.match(use.ref)]
    violations = _version_regressions(uses)
    assert not violations, "Action version(s) older than the repo standard:\n" + "\n".join(violations)


def _fake(action: str, ref: str, line_no: int = 1) -> ActionUse:
    return ActionUse(
        path=Path(f"synthetic/{action.replace('/', '_')}.yml"),
        line_no=line_no,
        action=action,
        ref=ref,
        comment_version=None,
    )


def test_the_comparison_flags_a_planted_regression():
    """The repo currently has zero tag drift, so the check above passes whatever it does.

    With one version per action, `version < best` is never true and an inverted
    operator would look identical. These fixtures are what actually pin the
    comparison's direction and its grouping by exact action string.
    """
    regressions = _version_regressions([_fake("actions/cache", "v6"), _fake("actions/cache", "v4", 2)])
    assert len(regressions) == 1, f"a v4 pin beside a v6 pin must be flagged, got: {regressions}"
    assert "actions/cache@v4" in regressions[0]

    assert _version_regressions([_fake("actions/cache", "v6"), _fake("actions/cache", "v6", 2)]) == []
    # Grouping is by the exact action string, subpath included -- two different
    # actions are not each other's standard.
    assert _version_regressions([_fake("actions/cache", "v6"), _fake("actions/checkout", "v4", 2)]) == []
    # Minor and patch components participate, not just the major.
    assert len(_version_regressions([_fake("a/b", "v1.2.3"), _fake("a/b", "v1.2.2", 2)])) == 1
