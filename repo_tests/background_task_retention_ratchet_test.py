# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15522 — background-task launches whose handle is thrown away.

The event loop holds only a WEAK reference to a task, so a launch whose return
value is discarded can be garbage-collected before the coroutine runs. Observed
live on the SLM self-update path: one firing executed end to end, an identical
firing minutes later produced no executor call, no inventory file, no transient
unit and no log write — and the surface reported success either way, because
nothing awaits these tasks or attaches a done callback.

``autobot_shared.async_compat.fire_and_forget`` is the fix: it retains the task
until completion and logs a failure that would otherwise vanish. This file
ratchets the population that has NOT been converted yet. The census is exact
and may only SHRINK — a new discarded launch fails here, and every conversion
must lower the census in the same commit. #15522 converted the three
``_ansible_self_update`` firings in ``api/code_sync.py``; #15524 tracks the rest.

#15619 widened the sweep. It used to read one ``SCAN_ROOT`` string,
``autobot-slm-backend/`` — a tree holding under a tenth of the backend Python
in this repo. Both the census AND the vacuity floor that is supposed to prove
the sweep still reaches anything were therefore healthy inside that tenth while
the other backend accumulated sites nobody could see. The two
``llc/services/goal.py`` firings #15612 was filed for sat in the unscanned tree
the whole time.

Two consequences of that history are load-bearing here:

* the floors are asserted PER ROOT (``SCAN_ROOTS``), never on a union. A union
  floor is exactly what let one tree carry the other: the small tree's 44 sites
  would satisfy any total a collapsed sweep of the large one left behind.
  Per-root floors mean a sweep that stops reaching one backend fails by that
  backend's name.
* ``test_the_scan_covers_both_backends`` pins the root set itself and asserts
  the large tree by a count the small tree cannot supply, so re-narrowing the
  scan fails loudly instead of quietly shrinking coverage again.

The discard detector covers ``create_task`` AND ``ensure_future``,
attribute-style (``asyncio.create_task(...)``, ``loop.create_task(...)``) and
bare-name style (``from asyncio import create_task``). Only a launch that is an
expression STATEMENT counts: ``self._tasks.add(asyncio.create_task(...))``
retains its handle and is not a finding.

The FLOOR counts a wider set — ``REACH_MARKERS``, which adds the retained forms
``fire_and_forget`` and ``retain_until_done``. Counting only the unconverted
forms would make the floor fall every time this ratchet did its job, and a
guard whose health metric drops as the fix lands eventually fails for the best
possible reason. The reach count is invariant under conversion.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]


class RootBudget(NamedTuple):
    """Floors for one scan root, asserted on their own and never pooled.

    ``min_files`` is the tracked non-test Python files the sweep must parse
    under the root; ``min_reach_markers`` the task-launch call sites it must
    reach, retained and discarded forms alike. Both sit well under the measured
    value so ordinary churn does not trip them, and well over anything a
    collapsed or re-narrowed sweep could produce.
    """

    min_files: int
    min_reach_markers: int


# Measured 2026-09 on Dev_new_gui: autobot-backend/ 2,375 non-test files and
# 198 reach markers; autobot-slm-backend/ 225 and 44. The large root's file
# floor is an order of magnitude above the small root's entire tree, which is
# what makes a re-narrowing to a single root fail rather than pass.
SCAN_ROOTS: dict[str, RootBudget] = {
    "autobot-backend/": RootBudget(min_files=2000, min_reach_markers=150),
    "autobot-slm-backend/": RootBudget(min_files=200, min_reach_markers=30),
    # Added by #15637: launches outside both backends were in no scan root at
    # all, which is how a discarded task in `autobot_shared/` -- the tree the
    # other guards import their fix from -- survived every sweep.
    "autobot_shared/": RootBudget(min_files=150, min_reach_markers=6),
    "autobot-infrastructure/": RootBudget(min_files=180, min_reach_markers=8),
    "autobot-npu-worker/": RootBudget(min_files=25, min_reach_markers=1),
}

# Discarded when used as a bare expression statement.
LAUNCHERS = frozenset({"create_task", "ensure_future"})
# The retained forms. Not findings — but they ARE evidence the sweep arrived,
# so the floor counts them and stays flat as conversions land.
RETAINERS = frozenset({"fire_and_forget", "retain_until_done"})
REACH_MARKERS = LAUNCHERS | RETAINERS

# The census: every discarded launch still standing, with the reason it is
# still standing. THIS MAPPING ONLY SHRINKS. A conversion lowers its entry in
# the same commit; an entry that no longer matches the tree fails either way.
#
# The widened sweep found 71 discarded launches in autobot-backend/, a tree
# this file had never reached. #15619 read every one of them and converted 39
# to ``fire_and_forget``; the 32 below are what is left. They are not "the rest
# of the backlog" — each group states what blocks it, and two of the three
# groups are blocked by something other than effort.
#
# GROUP 1 — blocked by the python-file-size ratchet (19 files, 27 sites).
# Every file here is grandfathered at an EXACT line count in
# ``scripts/python_file_size_known_large.py``; that mapping only shrinks, and
# the ``from autobot_shared.async_compat import fire_and_forget`` line a
# conversion needs puts each of them one line over its frozen ceiling. Buying
# that line back by deleting unrelated code would satisfy the counter while
# degrading the file, so the standing decision (taken for the identical
# autobot-slm-backend/ cases in #15524) is to decompose the file below
# MAX_LINES first, in its own refactor, and convert the site as part of that
# work. Three grandfathered files did NOT need to wait — agent_communication.py,
# todowrite_optimizer.py and tool_pattern_analyzer.py already imported from
# ``async_compat``, so extending that one import line converted their four
# sites at zero line growth. #15635 is the umbrella for the rest.
#
# GROUP 2 — wrong thread, not a retention bug (3 files, 3 sites). Each of
# these fires from a watchdog ``Observer`` thread that has no running event
# loop, so ``asyncio.create_task`` raises RuntimeError there and
# ``fire_and_forget`` would raise the identical RuntimeError. Converting them
# would dress a thread-boundary defect as a retention fix and change nothing.
# They need a loop captured at start() plus ``run_coroutine_threadsafe``.
#
# GROUP 3 — owned by an in-flight PR (1 file, 2 sites). Recorded so this
# census matches the tree it is asserted against; PR #15618 converts both and
# must lower this entry in the same commit, exactly as the contract says.
KNOWN_DISCARDED_LAUNCHES: dict[str, int] = {
    "autobot-backend/agents/base_agent.py": 1,
    "autobot-backend/agents/llm_failsafe_agent.py": 1,
    "autobot-backend/agents/npu_code_search_agent.py": 1,
    "autobot-backend/ai_hardware_accelerator.py": 1,
    "autobot-backend/api/analytics.py": 1,
    "autobot-backend/api/analytics_bug_prediction.py": 1,
    "autobot-backend/api/knowledge_population.py": 4,
    "autobot-backend/api/long_running_operations.py": 1,
    "autobot-backend/chat_workflow/manager.py": 2,
    "autobot-backend/chat_workflow/tool_handler.py": 2,
    "autobot-backend/initialization/lifespan.py": 1,
    "autobot-backend/knowledge/facts.py": 1,
    "autobot-backend/llc/services/goal.py": 2,
    "autobot-backend/orchestrator.py": 1,
    "autobot-backend/secure_sandbox_executor.py": 1,
    "autobot-backend/security/enterprise/threat_detection/engine.py": 3,
    "autobot-backend/services/documentation_watcher.py": 1,
    "autobot-backend/services/kb_folder_watcher.py": 1,
    "autobot-backend/services/knowledge/doc_indexer.py": 1,
    "autobot-backend/services/tool_output_filter.py": 1,
    "autobot-backend/utils/hot_reload_manager.py": 1,
    "autobot-backend/utils/service_discovery.py": 1,
    "autobot-backend/workflow_scheduler.py": 2,
    "autobot-npu-worker/resources/windows-npu-worker/app/npu_worker.py": 1,
    "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/agent.py": 1,
    "autobot-slm-backend/api/infrastructure.py": 1,
    "autobot-slm-backend/api/setup_wizard.py": 1,
    "autobot-slm-backend/api/updates.py": 1,
    "autobot-slm-backend/slm/agent/agent.py": 1,
    "autobot_shared/http_client.py": 1,
    # Censused rather than converted: each sits in a file grandfathered at an
    # exact line count, so the one import a conversion needs puts it over the
    # ceiling. Decompose first -- #15641, #15642.
}


def _named_call(node: ast.AST, names: frozenset[str]) -> bool:
    """True for ``x.<name>(...)`` and bare ``<name>(...)`` calls."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in names
    return isinstance(func, ast.Name) and func.id in names


def _tracked_python_files(root: str) -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", f"{root}*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return tuple(line for line in out.stdout.splitlines() if line)


class RootCensus(NamedTuple):
    """One root's sweep result: what was found, and proof the sweep ran."""

    discarded: dict[str, int]
    reach_markers: int
    files_parsed: int


@lru_cache(maxsize=None)
def _census_for(root: str) -> RootCensus:
    """Sweep one root. Cached: the tests share one parse of ~2,600 files."""
    discarded: dict[str, int] = {}
    reach_markers = files_parsed = 0
    for rel in _tracked_python_files(root):
        if "/tests/" in rel or rel.endswith("_test.py"):
            continue
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        files_parsed += 1
        for node in ast.walk(tree):
            if _named_call(node, REACH_MARKERS):
                reach_markers += 1
            if isinstance(node, ast.Expr) and _named_call(node.value, LAUNCHERS):
                discarded[rel] = discarded.get(rel, 0) + 1
    return RootCensus(discarded, reach_markers, files_parsed)


def _assert_root_floors(root: str) -> RootCensus:
    """Per-root vacuity floor. Never pooled — that pooling was the #15619 bug."""
    budget = SCAN_ROOTS[root]
    census = _census_for(root)
    assert census.files_parsed >= budget.min_files, (
        f"FIX THE SWEEP: only {census.files_parsed} files parsed under {root} "
        f"(floor {budget.min_files}). The sweep no longer reaches this tree."
    )
    assert census.reach_markers >= budget.min_reach_markers, (
        f"FIX THE SWEEP: only {census.reach_markers} task-launch sites reached under "
        f"{root} (floor {budget.min_reach_markers})."
    )
    return census


def test_every_root_is_swept_to_its_own_floor():
    """Floor first, per root: a collapsed sweep fails by name, never green."""
    for root in SCAN_ROOTS:
        _assert_root_floors(root)


def test_the_scan_covers_both_backends():
    """#15619: re-narrowing the scan must fail here, by count, not go quiet.

    The old sweep read one ``SCAN_ROOT`` string. Deleting a root from the
    mapping, or pointing several entries at the same tree, would shrink coverage
    by an order of magnitude and every other assertion in this file would
    still pass — the census simply stops seeing what it no longer visits.

    The set is pinned by name rather than by size, because "both backends" was
    the whole defect: a count alone is satisfied by scanning the small tree
    twice. #15637 added the three trees outside either backend, where a
    discarded task in ``autobot_shared/`` -- the tree the other guards import
    their own fix from -- had survived every sweep.
    """
    assert set(SCAN_ROOTS) == {
        "autobot-backend/",
        "autobot-slm-backend/",
        "autobot_shared/",
        "autobot-infrastructure/",
        "autobot-npu-worker/",
    }, f"FIX THE SWEEP: the scan roots changed. Got {sorted(SCAN_ROOTS)}."
    parsed = {root: _census_for(root).files_parsed for root in SCAN_ROOTS}
    small, large = parsed["autobot-slm-backend/"], parsed["autobot-backend/"]
    assert large > 4 * small, (
        f"FIX THE SWEEP: autobot-backend/ contributed only {large} parsed files "
        f"against autobot-slm-backend/'s {small}. The large tree holds an order of "
        "magnitude more Python; a ratio this low means the scan is pointed at the "
        "small tree twice, or is no longer reaching the large one."
    )


def test_every_scan_root_carries_its_own_census_entries():
    """A census entry outside the swept roots can never be re-verified."""
    census_roots = {rel.split("/", 1)[0] + "/" for rel in KNOWN_DISCARDED_LAUNCHES}
    assert census_roots <= set(SCAN_ROOTS), (
        "census entries outside every scan root can never be re-verified: " f"{sorted(census_roots - set(SCAN_ROOTS))}"
    )
    assert census_roots == set(SCAN_ROOTS), (
        "a scan root with no census entry means the sweep found nothing there — "
        "delete the root or prove the zero deliberately; missing: "
        f"{sorted(set(SCAN_ROOTS) - census_roots)}"
    )


def test_the_census_is_pinned_and_may_only_shrink():
    discarded: dict[str, int] = {}
    for root in SCAN_ROOTS:
        discarded.update(_assert_root_floors(root).discarded)

    pinned = {rel: n for rel, n in KNOWN_DISCARDED_LAUNCHES.items() if n}
    grown = {rel: n for rel, n in discarded.items() if n > KNOWN_DISCARDED_LAUNCHES.get(rel, 0)}
    assert grown == {}, (
        "discarded background-task launches added or regrown (file: count): "
        f"{grown}. Use autobot_shared.async_compat.fire_and_forget — a discarded "
        "task can be garbage-collected before it runs (#15522)."
    )
    shrunk = {rel: n for rel, n in pinned.items() if discarded.get(rel, 0) < n}
    assert shrunk == {}, f"census not lowered after converting (file: old count): {shrunk}"


def test_the_self_update_firings_are_retained():
    """The three #15522 sites, asserted by name so a revert cannot go quiet."""
    src = (REPO_ROOT / "autobot-slm-backend/api/code_sync.py").read_text(encoding="utf-8")
    assert src.count("_ansible_self_update(") >= 5, "FIX THE SWEEP: the self-update firings moved or vanished"
    assert "asyncio.create_task(_ansible_self_update(" not in src
    assert src.count("fire_and_forget(_ansible_self_update(") == 3
