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
    sync task it follows actually lands files, derived from the playbook
    itself rather than hand-declared. `deploy_tmp/*.tar.gz` is NOT built
    outside this repo -- Play 0's own "[PRE-FLIGHT] Create component
    archives" task builds it, right here, with a `git archive {{ deploy_ref
    }} -- {{ item.path }}` loop (name -> repo-relative path) and no
    `--prefix`; `git archive -- <path>` with no `--prefix` stores every
    entry UNDER `<path>` itself, so unarchiving into a bare parent `dest:`
    (`/opt/autobot/`) lands files at `dest` joined with that loop item's
    `path`. Each unarchive task's own `src` basename (`{{ deploy_tmp
    }}/<name>.tar.gz`) names which loop item built it. AI Stack is the one
    site that loop does NOT build -- its own "[PRE-FLIGHT] Create AI Stack
    archive" task packs a different tree (also confirmed `--prefix`-free),
    and its `unarchive` uses `--strip-components=4` to flatten straight into
    `dest`, so `dest` alone IS the landing directory there; that branch is
    unchanged from before. All 12 sites resolve statically -- none are
    undeterminable.
Test 5: no two includes with DIFFERENT `sync_deletions_source_dir` values
    may have equal or nested `sync_deletions_target_dir` values (segment-
    compared, so `/x/a` is never mistaken for a parent of `/x/ab`). Equal
    target + equal source stays allowed -- today's three `autobot_shared`
    passes, safe because the shared marker makes the later passes no-ops.
"""

from __future__ import annotations

import re

import pytest
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
# Test 4: the deletion target equals the sync destination, derived from
# Play 0's own `git archive` loop -- never hand-declared, never skipped.
# --------------------------------------------------------------------------

_ARCHIVE_LOOP_TASK_NAME = "[PRE-FLIGHT] Create component archives"
_AI_STACK_ARCHIVE_TASK_NAME = "[PRE-FLIGHT] Create AI Stack archive"
_ARCHIVE_BASENAME_RE = re.compile(r"([^/{}]+)\.tar\.gz$")


def _assert_no_archive_prefix_rewrite(task: dict) -> None:
    """`git archive -- <path>` with no `--prefix` stores every entry UNDER
    `<path>` itself -- the whole landing-dir derivation below assumes that.
    A `--prefix` would rewrite the archive's top-level name, so catch it
    here instead of silently deriving the wrong directory (#16310 round
    13c)."""
    cmd = str(task.get("shell", ""))
    assert "--prefix" not in cmd, (
        f"{task.get('name')}: git archive command uses --prefix -- the landing-dir derivation below must be "
        "updated to account for the rewritten path, not assumed away"
    )


def _archive_name_to_source_path(tasks: list[dict]) -> dict[str, str]:
    """name -> repo-relative path for every entry in Play 0's `git archive`
    loop, read from the playbook itself: the archive an unarchive task's
    `src` basename names IS one of these loop items. Also confirms the AI
    Stack archive task (built outside the loop) is `--prefix`-free, since
    its landing dir is derived separately, via --strip-components."""
    idx = _index_of(tasks, lambda t: _ARCHIVE_LOOP_TASK_NAME in str(t.get("name", "")))
    assert idx != -1, f"{_ARCHIVE_LOOP_TASK_NAME!r} task not found"
    _assert_no_archive_prefix_rewrite(tasks[idx])
    mapping = {}
    for item in tasks[idx].get("loop") or []:
        assert (
            isinstance(item, dict) and "name" in item and "path" in item
        ), f"{_ARCHIVE_LOOP_TASK_NAME!r}: loop item {item!r} is not a {{name, path}} dict"
        mapping[str(item["name"])] = str(item["path"])

    ai_stack_idx = _index_of(tasks, lambda t: _AI_STACK_ARCHIVE_TASK_NAME in str(t.get("name", "")))
    assert ai_stack_idx != -1, f"{_AI_STACK_ARCHIVE_TASK_NAME!r} task not found"
    _assert_no_archive_prefix_rewrite(tasks[ai_stack_idx])
    return mapping


def _archive_name_from_src(src: str) -> str:
    """The archive's loop `name` from an unarchive task's `src` basename
    (`{{ deploy_tmp }}/<name>.tar.gz`)."""
    match = _ARCHIVE_BASENAME_RE.search(src)
    assert match, f"unarchive src {src!r} is not a {{deploy_tmp}}/<name>.tar.gz path"
    return match.group(1)


def _archive_relative_landing_dir(dest: str, archive_path: str) -> str:
    """Where `git archive -- <archive_path>` (no --prefix) lands once
    unarchived into a bare `dest`: entries sit under `archive_path` itself,
    so the landing directory is `dest` joined with `archive_path`, trailing
    slashes dropped on both sides."""
    return f"{_normalize_dir(dest)}/{archive_path.strip('/')}"


def _sync_module_args(task: dict) -> tuple[str, dict]:
    """(module name, its arg dict) for the sync task's own module -- explicit
    per module type, so an unhandled module type falls through to "unknown"
    instead of silently reading whatever `dest` key exists."""
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


def _actual_sync_dest(task: dict, archive_paths: dict[str, str]) -> str:
    """The normalized directory *task* actually populates, derived from the
    SAME archive Play 0 built for it. Fails loudly (never returns None, never
    skips) on any module, `dest`, or `src` shape this module does not
    recognize (#16310 round 13c)."""
    module, args = _sync_module_args(task)
    dest = args.get("dest")
    assert dest, f"{task.get('name')}: {module} task has no dest"
    if module in ("synchronize", "copy"):
        return _normalize_dir(str(dest))
    assert module == "unarchive", f"{task.get('name')}: unrecognized sync module {module!r}"
    extra_opts = args.get("extra_opts") or []
    if any(re.match(r"--strip-components=\d+$", str(opt)) for opt in extra_opts):
        # the archive is flattened directly into dest -- dest IS the landing dir (AI Stack).
        return _normalize_dir(str(dest))
    archive_name = _archive_name_from_src(str(args.get("src") or ""))
    assert archive_name in archive_paths, (
        f"{task.get('name')}: archive {archive_name!r} is not in Play 0's archive loop -- add it there, or this "
        "derivation cannot resolve where it lands"
    )
    return _archive_relative_landing_dir(str(dest), archive_paths[archive_name])


def _assert_site_lands_at_target(
    task: dict, archive_paths: dict[str, str], target_dir: str, label: str, sync_task_name: str
) -> None:
    actual_dest = _actual_sync_dest(task, archive_paths)
    assert actual_dest == _normalize_dir(target_dir), (
        f"{label}: sync_deletions_target_dir {target_dir!r} does not match where {sync_task_name!r} "
        f"actually lands files ({actual_dest!r})"
    )


def test_deletion_target_matches_where_its_sync_task_actually_lands_files() -> None:
    tasks = _flatten(_load_tasks(_UPDATE_ALL_PLAYBOOK))
    archive_paths = _archive_name_to_source_path(tasks)
    for rel_path, sync_task_name, target_dir, label in _UPDATE_ALL_SYNC_THEN_DELETE_SITES:
        sync_index = _index_of(tasks, lambda t, n=sync_task_name: n in str(t.get("name", "")))
        assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"
        _assert_site_lands_at_target(tasks[sync_index], archive_paths, target_dir, label, sync_task_name)


def test_unrecognized_archive_name_fails_loudly() -> None:
    """A sync task whose `src` archive name is not in Play 0's loop must
    raise, never silently resolve to None or get skipped (#16310 round
    13c)."""
    task = {
        "name": "Synthetic | Deploy mystery",
        "unarchive": {"src": "{{ deploy_tmp }}/mystery.tar.gz", "dest": "/opt/autobot/"},
    }
    with pytest.raises(AssertionError, match="not in Play 0's archive loop"):
        _actual_sync_dest(task, {"widget": "widget-src/"})


def test_archive_task_with_a_prefix_rewrite_fails_loudly() -> None:
    """A `git archive --prefix=...` would move the archive's own top-level
    name out from under `item.path` -- this derivation assumes there is
    none; a future one must be caught, not silently mis-derived."""
    task = {
        "name": _ARCHIVE_LOOP_TASK_NAME,
        "shell": "git archive HEAD --prefix=renamed/ -- widget/ | gzip > out.tar.gz",
    }
    with pytest.raises(AssertionError, match="--prefix"):
        _assert_no_archive_prefix_rewrite(task)


def test_planted_regression_mismatched_landing_dir_is_caught() -> None:
    """Synthetic archive loop {'widget': 'widget-src/'} plus a sync task
    landing at /opt/autobot/widget-src, checked against an include that
    claims /opt/autobot/widget -- the derivation must reject the mismatch,
    not silently accept it (#16310 round 13c)."""
    archive_paths = {"widget": "widget-src/"}
    task = {
        "name": "Synthetic | Deploy widget",
        "unarchive": {"src": "{{ deploy_tmp }}/widget.tar.gz", "dest": "/opt/autobot/"},
    }
    with pytest.raises(AssertionError, match="does not match"):
        _assert_site_lands_at_target(
            task, archive_paths, "/opt/autobot/widget", "Widget (planted)", "Synthetic | Deploy widget"
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
