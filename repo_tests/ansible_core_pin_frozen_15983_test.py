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
    assert any(v.strip().startswith(">") for v in versions), (
        f"ansible-core's ignore range {versions!r} is not open-ended, so a version above "
        "it can still be proposed. The pin tracks a deployment fact; no automated bump "
        "of it is correct (#15824, #15822)."
    )


def test_the_pin_tells_the_reader_it_is_frozen() -> None:
    """A freeze nobody can find from the pin is a freeze someone will undo."""
    text = _PIN.read_text(encoding="utf-8")
    assert "#15983" in text, (
        "constraints/ansible-core.txt does not mention the dependabot freeze. A reader "
        "wondering why the pin never moves must find the answer at the pin (#15983)."
    )
    assert "dependabot" in text.lower(), "the pin's header does not name dependabot as the frozen actor"
