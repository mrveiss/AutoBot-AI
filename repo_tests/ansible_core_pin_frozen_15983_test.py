# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`constraints/ansible-core.txt` must stay frozen against automated bumps (#15983).

That pin is not an upstream dependency. It records **what the fleet's control node
runs** (#15824), so it may only move after the hosts move -- a PR changing it in
isolation is wrong whatever version it names.

#15822 is the cost when CI and the fleet disagree: 2.17.14 applies `set_fact` bool
coercion and newer interpreters do not, so the guard read a decidable token where
every host read a bool, and wrong-node cleanup stayed dead for eleven days behind a
green check.

Dependabot proposed the bump **twice on 2026-09-07** -- #15975 (closed) and #15980
(reverted by hand) -- because nothing excluded it. This asserts the exclusion that
now does, and asserts the SHAPE that makes it hold rather than merely its presence:
`update-types` alone does not stop a grouped `all-dependencies` bump (#14431 for
openai, #14727 for protobuf), so an unbounded `versions` range is required.

What this CANNOT assert: that dependabot's next weekly run does not propose it.
That is observable only in the run, and is recorded on #15983 as the outstanding
half rather than claimed here -- a test that asserts config shape must not be read
as evidence about behaviour.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

from repo_tests._paths import repo_root  # noqa: E402

_CONFIG = repo_root() / ".github" / "dependabot.yml"
_PIN = repo_root() / "constraints" / "ansible-core.txt"


def _root_pip_block() -> dict:
    document = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    blocks = [
        u
        for u in document["updates"]
        if u.get("package-ecosystem") == "pip" and u.get("directory") == "/"
    ]
    assert len(blocks) == 1, f"expected exactly one root pip block, found {len(blocks)}"
    return blocks[0]


def test_the_root_pip_block_still_groups_everything() -> None:
    """Non-vacuity: the freeze below only matters while a `*` group exists.

    If the grouped bump were removed, this test would still pass while guarding
    nothing -- so assert the condition that makes the freeze load-bearing.
    """
    groups = _root_pip_block().get("groups", {})
    patterns = [p for g in groups.values() for p in g.get("patterns", [])]
    assert "*" in patterns, (
        "the root pip block no longer groups `*`; re-check whether the ansible-core "
        "freeze is still needed and why, rather than deleting this test"
    )


def _pinned_version() -> str:
    """The version `constraints/ansible-core.txt` pins, read from the pin itself.

    Read rather than restated. A literal here would be a third copy of the same
    fact, and the copy a test asserts against is the one that never gets updated
    -- the assertion would then pass by agreeing with itself.
    """
    for line in _PIN.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("ansible-core=="):
            return stripped.split("==", 1)[1].split()[0]
    raise AssertionError(f"{_PIN} pins no ansible-core version -- nothing to compare against")


def _range_matches_pin(versions: list[str], pinned: str) -> bool:
    """Whether the ignore range is the open-ended range this pin requires.

    Extracted so it can be exercised against a MISMATCHING pair as well as a
    matching one. Asserted only against the live configuration, this comparison
    is checked exclusively in the state where it happens to agree -- and a
    comparison that has never been shown to fail is indistinguishable from one
    that cannot.
    """
    return versions == [f">{pinned}"]


def test_ansible_core_is_frozen_not_merely_capped() -> None:
    entries = [i for i in _root_pip_block().get("ignore", []) if i.get("dependency-name") == "ansible-core"]
    assert entries, (
        "ansible-core has no `ignore:` entry in dependabot.yml's root pip block. "
        "It was proposed twice on 2026-09-07 (#15975, #15980) when this was absent (#15983)."
    )
    entry = entries[0]
    versions = entry.get("versions") or []
    assert versions, (
        "ansible-core is ignored by `update-types` alone. That does NOT stop a grouped "
        "all-dependencies bump -- #14431 recorded it for openai, #14727 for protobuf. "
        "An unbounded `versions` range is what holds (#15983)."
    )
    pinned = _pinned_version()
    assert _range_matches_pin(versions, pinned), (
        f"ansible-core's ignore range is {versions!r} but the pin is {pinned!r}. These two "
        "numbers are one fact written twice, and the release procedure in the pin's header "
        "moves them together -- fleet first, then the pin, then this lower bound. A range "
        "that merely STARTS with '>' passes while reading '>2.17.15' against a 2.17.14 pin, "
        "which re-opens exactly the gap that let #15975 and #15980 be proposed (#15983)."
    )


def test_the_pin_tells_the_reader_it_is_frozen() -> None:
    """A freeze nobody can find from the pin is a freeze someone will undo."""
    text = _PIN.read_text(encoding="utf-8")
    assert "#15983" in text, (
        "constraints/ansible-core.txt does not mention the dependabot freeze. A reader "
        "wondering why the pin never moves must find the answer at the pin (#15983)."
    )
    assert "dependabot" in text.lower(), "the pin's header does not name dependabot as the frozen actor"


def test_the_range_comparison_rejects_a_drifted_lower_bound() -> None:
    """The contrast pair. The live configuration only ever exercises the True branch.

    `>2.17.15` against a `2.17.14` pin is not hypothetical -- it is what the three
    step release produces if someone moves the ignore's lower bound before moving
    the pin, and it is the precise state the old `startswith(">")` check accepted.
    The two assertions are one test on purpose: a matching pair passing proves
    nothing on its own, because a function returning True unconditionally passes it.
    """
    assert _range_matches_pin([">2.17.14"], "2.17.14")
    assert not _range_matches_pin([">2.17.15"], "2.17.14"), (
        "the comparison accepted an ignore range above the pin -- the two numbers "
        "are one fact written twice and must move together (#15983)"
    )


def test_the_range_comparison_rejects_the_shapes_that_are_not_a_freeze() -> None:
    """A cap, a closed interval and an empty list are all `not a freeze`.

    `update-types` alone does not stop a grouped bump -- #14431 recorded it for
    openai, #14727 for protobuf -- so each of these reads as protection while
    leaving the dependency reachable by the `all-dependencies` group.
    """
    assert not _range_matches_pin([], "2.17.14")
    assert not _range_matches_pin(["<2.18"], "2.17.14")
    assert not _range_matches_pin([">2.17.14", "<2.18"], "2.17.14")
    assert not _range_matches_pin([">=2.17.14"], "2.17.14")
