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
before the ``@``. SHA-pinned actions are excluded from that comparison: a SHA
has no order, and resolving one to its release needs the network. For SHA pins
the guard asserts two narrower things instead:

* every SHA pin carries a trailing ``# vX.Y.Z``-shaped comment, so its version
  is at least *readable* -- the "low-cost improvement" #15332 asked for in
  place of resolving every SHA pin to its Node runtime;
* every pin of the SAME SHA carries labels that agree: the same version, or one
  a prefix of the other (``v4`` beside ``v4.37.9``) (#16303).

The second is what the first could not see. ``security.yml`` labelled its
``github/codeql-action`` pin ``# v3`` on the SHA ``codeql.yml`` labelled
``# v4``, and ``image-sign.yml`` labelled ``docker/login-action``,
``docker/build-push-action`` and ``sigstore/cosign-installer`` one major release
behind the very SHAs ``autoresearch-image.yml`` pins. An earlier version of this
docstring read those three as "genuinely pinned to different releases in
different workflows"; each was one commit carrying two labels. A wrong label on
a SHA pinned nowhere else still passes -- catching that needs the tag
resolution this guard does not do.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
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


def _label_parts(label: str) -> tuple[int, ...]:
    return tuple(int(part) for part in label.lstrip("v").split("."))


def _labels_agree(first: str, second: str) -> bool:
    """Same version, or one a prefix of the other: `v4` agrees with `v4.37.9`, not with `v3` or `v40`."""
    a, b = _label_parts(first), _label_parts(second)
    shorter = min(len(a), len(b))
    return a[:shorter] == b[:shorter]


def _label_disagreements(uses: list[ActionUse]) -> list[str]:
    """Every pair of pins on one SHA whose version labels disagree, reported together.

    Grouped by SHA alone, across actions and subpaths: `codeql-action/init` and
    `codeql-action/upload-sarif` pinned to one commit are one release.
    """
    by_sha: dict[str, list[tuple[ActionUse, str]]] = {}
    for use in uses:
        if SHA_PATTERN.match(use.ref) and use.comment_version:
            by_sha.setdefault(use.ref.lower(), []).append((use, use.comment_version))
    violations = []
    for sha, pins in by_sha.items():
        for (first, first_label), (second, second_label) in itertools.combinations(pins, 2):
            if not _labels_agree(first_label, second_label):
                violations.append(
                    f"{first.path}:{first.line_no} labels {first.action}@{sha} '# {first_label}', "
                    f"but {second.path}:{second.line_no} labels the same SHA '# {second_label}'"
                )
    return violations


def test_every_pin_of_one_sha_carries_agreeing_labels():
    """#16303: one commit is one release, so every label on its SHA must name that release.

    A label naming the wrong release passes the readability check above, and misleads
    every reader who trusts it. Resolve the SHA to its tag and correct the wrong label.
    """
    violations = _label_disagreements(_extract_uses(_workflow_files()))
    assert not violations, "Pins of one SHA name different releases:\n" + "\n".join(violations)


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


def _fake(action: str, ref: str, line_no: int = 1, comment_version: str | None = None) -> ActionUse:
    return ActionUse(
        path=Path(f"synthetic/{action.replace('/', '_')}.yml"),
        line_no=line_no,
        action=action,
        ref=ref,
        comment_version=comment_version,
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


_SHA_A = "a" * 40
_SHA_B = "b" * 40


def test_the_label_agreement_check_flags_a_planted_disagreement():
    """With #16303's labels fixed the repo has no disagreement, so the live check passes whatever it does.

    These fixtures pin what counts as agreement, and that grouping is by SHA.
    """
    planted = _label_disagreements([_fake("docker/login-action", _SHA_A, 1, "v4"), _fake("x/y", _SHA_A, 2, "v3")])
    assert len(planted) == 1 and "'# v4'" in planted[0] and "'# v3'" in planted[0], planted
    # A shorter label is a prefix of a longer one, not a disagreement -- and the
    # comparison is per component, so `v4` is no prefix of `v40`.
    assert _label_disagreements([_fake("a/b", _SHA_A, 1, "v4"), _fake("a/b", _SHA_A, 2, "v4.37.9")]) == []
    assert len(_label_disagreements([_fake("a/b", _SHA_A, 1, "v4"), _fake("a/b", _SHA_A, 2, "v40")])) == 1
    # Prefix agreement is not transitive: `v4` agrees with both, `v4.1` and `v4.2` not with each other.
    trio = [_fake("a/b", _SHA_A, 1, "v4"), _fake("a/b", _SHA_A, 2, "v4.1"), _fake("a/b", _SHA_A, 3, "v4.2")]
    assert len(_label_disagreements(trio)) == 1
    # Different SHAs are different commits; an unlabelled pin is the readability check's concern.
    assert _label_disagreements([_fake("a/b", _SHA_A, 1, "v3"), _fake("a/b", _SHA_B, 2, "v4")]) == []
    assert _label_disagreements([_fake("a/b", _SHA_A, 1, "v3"), _fake("a/b", _SHA_A, 2)]) == []
