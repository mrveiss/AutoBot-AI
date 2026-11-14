# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path ``secrets_baseline_legacy_keys.json`` names must exist in the tree (#20895).

The file is a frozen list of ``(filename, type, hashed_secret)`` triples for findings
audited in files that were in the repository when it was written. When one of those
files is deleted or retired, its entries stop describing anything: they cannot match a
finding, and a path that is not tracked is a reviewer's false lead. #18548 retired a
mirrored copy and nothing pruned it, which is how this was found.

The check compares each entry's path with ``git ls-files``, never with the working
directory: an untracked or ignored leftover on one machine would otherwise keep a dead
entry alive there and fail it on a clean CI checkout.

Removing an entry changes ``FROZEN_LEGACY_KEYS_SHA256`` too (see
``secrets_baseline_reasons.py``); that is the deliberate act it asks for.
"""

from __future__ import annotations

from repo_tests._paths import repo_root
from repo_tests.secrets_baseline_reasons import load_legacy_keys

from tools.lint._scan_helpers import tracked_paths

#: Anchors for the reach check, by name: the baseline this guard reads and this guard itself.
#: If the enumeration stops listing them it is not listing the tree, and "no missing path" is empty.
_REACH_ANCHORS = (
    "repo_tests/secrets_baseline_legacy_keys.json",
    "repo_tests/secrets_baseline_legacy_keys_paths_exist_20895_test.py",
)


def missing_paths(entry_paths: set[str], tracked: set[str]) -> list[str]:
    """The *entry_paths* that are not in the *tracked* set, sorted."""
    return sorted(entry_paths - tracked)


def _tracked() -> set[str]:
    return set(tracked_paths(repo_root(), "*"))


def _entry_paths() -> set[str]:
    return {key[0] for key in load_legacy_keys()}


def _examined() -> tuple[set[str], set[str]]:
    """``(entry paths, tracked paths)`` after proving both sides were really read.

    The tree side must list the anchors; the entry side must MATCH the tree for at least one path,
    so a broken enumeration (everything "missing") or an emptied file (nothing to miss) cannot read as a result.
    """
    tracked, paths = _tracked(), _entry_paths()
    reached = [anchor for anchor in _REACH_ANCHORS if anchor in tracked]
    assert len(reached) == len(
        _REACH_ANCHORS
    ), f"git ls-files lists {len(reached)} of {len(_REACH_ANCHORS)} anchors; a missing-path result would be vacuous"
    matched = paths & tracked
    assert len(matched) > 0, f"none of the {len(paths)} legacy-key paths is in the tree; the comparison read nothing"
    return paths, tracked


def test_the_enumeration_reaches_the_tree_it_compares_against() -> None:
    paths, tracked = _examined()
    assert set(_REACH_ANCHORS) <= tracked and paths


def test_every_legacy_key_path_exists_in_the_tree() -> None:
    paths, tracked = _examined()
    missing = missing_paths(paths, tracked)
    assert not missing, (
        f"{len(missing)} of {len(paths)} paths in secrets_baseline_legacy_keys.json are not tracked "
        "(#20895). Remove their entries, and update FROZEN_LEGACY_KEYS_SHA256 with them -- never add or "
        "re-pin an entry:\n  " + "\n  ".join(missing)
    )


def test_a_path_absent_from_the_tree_is_reported() -> None:
    """Control: on a synthetic tree the check says no to the dead path and yes to the live one."""
    tracked = {"live/file.py", "other/file.py"}
    assert missing_paths({"live/file.py", "retired/mirror/file.py"}, tracked) == ["retired/mirror/file.py"]
    assert missing_paths({"live/file.py"}, tracked) == []
