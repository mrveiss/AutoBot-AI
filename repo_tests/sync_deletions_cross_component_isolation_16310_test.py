# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 review round 13b (owner): on a single-node, co-located install
every component's target directory lives on the SAME filesystem -- so one
component's deletion PLAN must never be able to reach another component's
files. Today the playbook is safe: PLAY 1/PLAY 2 target sibling directories,
and the only repeated target, `autobot_shared`, always has the same source.
These two guards make sure a future edit cannot break that.

Sibling to repo_tests/sync_deletions_target_pinning_and_shell_safety_16310_test.py
rather than an addition there: that file would cross its own ~580-line
soft ceiling with this content folded in. Reuses both existing modules' own
YAML-parsing and site-pinning helpers by import rather than re-deriving
them, so all three files never quietly disagree about how a task list is
flattened, a deletion include is recognized, or a sync site is pinned.

Test 4: each include's own `sync_deletions_target_dir` must match where the
    sync task it follows actually lands files. Every one of update-all-
    nodes.yml's 12 sync sites uses `unarchive`; 11 of them unarchive into a
    bare parent `dest:` (`/opt/autobot/`), so the real landing subdirectory
    is decided by the archive's OWN internal top-level directory name --
    fixed by whatever builds `deploy_tmp/*.tar.gz`, which lives entirely
    outside this repo (`deploy_tmp` has no hit anywhere under
    autobot-slm-backend/ except this playbook itself) and so cannot be
    resolved statically. Those 11 are listed, by name, in
    _UNDETERMINABLE_SYNC_DEST_SITES rather than silently skipped. Only AI
    Stack's `unarchive` is statically resolvable: its `--strip-components`
    opt flattens the archive directly into `dest`, so `dest` itself IS the
    final landing directory, with no archive-internal name left to guess.
Test 5: no two includes with DIFFERENT `sync_deletions_source_dir` values
    may have equal or nested `sync_deletions_target_dir` values (segment-
    compared, so `/x/a` is never mistaken for a parent of `/x/ab`). Equal
    target + equal source stays allowed -- today's three `autobot_shared`
    passes, safe because the shared marker makes the later passes no-ops.
"""

from __future__ import annotations

import re

from repo_tests.sync_deletions_ansible_wiring_16310_test import (
    _ANSIBLE_ROOT,
    _UPDATE_ALL_PLAYBOOK,
    _flatten,
    _index_of,
    _load_tasks,
)
from repo_tests.sync_deletions_target_pinning_and_shell_safety_16310_test import (
    _SYNC_THEN_DELETE_SITES,
    _include_matches_site,
)

_UPDATE_ALL_SYNC_THEN_DELETE_SITES: tuple[tuple[str, str, str, str], ...] = tuple(
    site for site in _SYNC_THEN_DELETE_SITES if site[0] == _UPDATE_ALL_PLAYBOOK
)


def _normalize_dir(path: str) -> str:
    """{{ autobot.base_dir }} and /opt/autobot are the SAME real directory on
    a deployed host -- collapse both to one token, and drop a trailing
    slash, before any target/source directory comparison."""
    return path.replace("{{ autobot.base_dir }}", "/opt/autobot").rstrip("/")


def _path_segments(path: str) -> list[str]:
    return [seg for seg in path.split("/") if seg]


def test_the_ansible_root_and_site_table_still_resolve() -> None:
    """Guard the imports: a stale _ANSIBLE_ROOT or an empty filtered site
    table would fail every test below with a confusing error instead of
    this clear one."""
    assert _ANSIBLE_ROOT.is_dir(), f"{_ANSIBLE_ROOT} not found -- imported constant is stale"
    assert len(_UPDATE_ALL_SYNC_THEN_DELETE_SITES) == 12, (
        f"expected 12 update-all-nodes.yml sync sites in the imported pinning table, "
        f"found {len(_UPDATE_ALL_SYNC_THEN_DELETE_SITES)}"
    )


# --------------------------------------------------------------------------
# Test 4: the deletion target equals the sync destination.
# --------------------------------------------------------------------------

_UNDETERMINABLE_SYNC_DEST_SITES: frozenset[str] = frozenset(
    {
        "SLM Backend (self-update)",
        "SLM Frontend (self-update)",
        "SLM autobot_shared (self-update)",
        "SLM libs (self-update)",
        "SLM autobot-plugins (self-update)",
        "Backend (fleet update)",
        "Backend autobot_shared (fleet update)",
        "Frontend (fleet update)",
        "NPU worker (fleet update)",
        "Browser worker (fleet update)",
        "Shared autobot_shared (fleet update)",
    }
)


def _sync_module_args(task: dict) -> tuple[str, dict]:
    """(module name, its arg dict) for the sync task's own module -- explicit
    per module type, so an unhandled module type falls through to "unknown"
    (undeterminable) instead of silently reading whatever `dest` key exists."""
    for module in ("unarchive", "ansible.builtin.unarchive"):
        if module in task:
            return "unarchive", task[module]
    for module in ("ansible.posix.synchronize", "synchronize"):
        if module in task:
            return "synchronize", task[module]
    for module in ("ansible.builtin.copy", "copy"):
        if module in task:
            return "copy", task[module]
    return "unknown", {}


def _actual_sync_dest(task: dict) -> str | None:
    """The normalized directory the sync task actually populates, or None if
    that cannot be determined from this file alone."""
    module, args = _sync_module_args(task)
    dest = args.get("dest")
    if not dest:
        return None
    if module in ("synchronize", "copy"):
        return _normalize_dir(str(dest))
    if module == "unarchive":
        extra_opts = args.get("extra_opts") or []
        if any(re.match(r"--strip-components=\d+$", str(opt)) for opt in extra_opts):
            return _normalize_dir(str(dest))
    return None


def test_deletion_target_matches_where_its_sync_task_actually_lands_files() -> None:
    tasks = _flatten(_load_tasks(_UPDATE_ALL_PLAYBOOK))
    seen_undeterminable = set()
    for rel_path, sync_task_name, target_dir, label in _UPDATE_ALL_SYNC_THEN_DELETE_SITES:
        sync_index = _index_of(tasks, lambda t, n=sync_task_name: n in str(t.get("name", "")))
        assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"
        actual_dest = _actual_sync_dest(tasks[sync_index])
        if actual_dest is None:
            seen_undeterminable.add(label)
            assert label in _UNDETERMINABLE_SYNC_DEST_SITES, (
                f"{label}: sync task destination could not be determined statically and is not in the named "
                "undeterminable set -- add it there with a reason, do not drop it"
            )
            continue
        assert actual_dest == _normalize_dir(target_dir), (
            f"{label}: sync_deletions_target_dir {target_dir!r} does not match where {sync_task_name!r} "
            f"actually lands files ({actual_dest!r})"
        )
    assert seen_undeterminable == set(_UNDETERMINABLE_SYNC_DEST_SITES), (
        f"undeterminable site set drifted: computed {seen_undeterminable}, expected "
        f"{set(_UNDETERMINABLE_SYNC_DEST_SITES)}"
    )


# --------------------------------------------------------------------------
# Test 5: no shared or nested targets across different sources.
# --------------------------------------------------------------------------


def _update_all_include_for_site(tasks: list[dict], target_dir: str, label: str) -> dict:
    idx = _index_of(tasks, lambda t: _include_matches_site(t, target_dir, label))
    assert idx != -1, f"{_UPDATE_ALL_PLAYBOOK}: no include found for {label!r}"
    return tasks[idx]


def _update_all_source_target_table() -> tuple[tuple[str, str, str], ...]:
    """(label, normalized source, normalized target) for every
    sync_deletions.yml include in update-all-nodes.yml, read off each
    include's OWN `vars:` -- never derived from the sync task."""
    tasks = _flatten(_load_tasks(_UPDATE_ALL_PLAYBOOK))
    rows = []
    for _rel_path, _sync_task_name, target_dir, label in _UPDATE_ALL_SYNC_THEN_DELETE_SITES:
        include = _update_all_include_for_site(tasks, target_dir, label)
        source = (include.get("vars") or {}).get("sync_deletions_source_dir")
        assert source, f"{label}: include has no sync_deletions_source_dir"
        rows.append((label, _normalize_dir(str(source)), _normalize_dir(str(target_dir))))
    return tuple(rows)


def _shared_or_nested_target_offenders(
    entries: "list[tuple[str, str, str]] | tuple[tuple[str, str, str], ...]",
) -> list[tuple[str, str]]:
    """Pairs of labels from *entries* (each (label, source, target)) whose
    DIFFERENT sources still reach a shared or nested target directory --
    empty once every pass is isolated to its own subtree. Segment-compared,
    so /x/a is never mistaken for a parent of /x/ab."""
    offenders = []
    for i, (label_a, source_a, target_a) in enumerate(entries):
        segs_a = _path_segments(target_a)
        for label_b, source_b, target_b in entries[i + 1 :]:
            if source_a == source_b:
                continue
            segs_b = _path_segments(target_b)
            shorter, longer = (segs_a, segs_b) if len(segs_a) <= len(segs_b) else (segs_b, segs_a)
            if longer[: len(shorter)] == shorter:
                offenders.append((label_a, label_b))
    return offenders


def test_no_shared_or_nested_targets_across_different_sources() -> None:
    entries = _update_all_source_target_table()
    assert len(entries) == 12, f"expected 12 sync_deletions.yml includes, found {len(entries)}"
    offenders = _shared_or_nested_target_offenders(entries)
    assert offenders == [], (
        f"deletion targets from different sources overlap or nest: {offenders} -- on a single-node co-located "
        "install every component's target directory is on the SAME filesystem, so one component's deletion "
        "plan must never be able to reach another's files (#16310 review round 13b, owner)"
    )


def test_planted_regression_nested_and_shared_targets_across_different_sources_are_caught() -> None:
    nested = [
        ("Widget component", "widget-source", "/opt/autobot/widget"),
        ("Backend (planted, nested under widget)", "backend-source", "/opt/autobot/widget/backend"),
    ]
    assert _shared_or_nested_target_offenders(nested) == [
        ("Widget component", "Backend (planted, nested under widget)")
    ]

    equal_target_diff_source = [
        ("Component C", "source-c", "/opt/autobot/shared"),
        ("Component D", "source-d", "/opt/autobot/shared"),
    ]
    assert _shared_or_nested_target_offenders(equal_target_diff_source) == [("Component C", "Component D")]

    equal_target_same_source = [
        ("Component E", "source-shared", "/opt/autobot/shared"),
        ("Component F", "source-shared", "/opt/autobot/shared"),
    ]
    assert _shared_or_nested_target_offenders(equal_target_same_source) == []
