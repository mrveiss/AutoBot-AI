# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A per-play "no hosts matched" skip is not a failed fleet update (#19762).

``update-all-nodes.yml`` is multi-play; with ``limit=["localhost", node_id]`` every play for a
group the node is not in prints ``skipping: no hosts matched`` while the node's own plays run.
#19475 matched that line over the whole output and turned a clean run (``failed=0``) into a halted
stage. The inventory-level markers still fail the run, and ``execute_playbook`` now requires a
host the limit names to have run -- ``localhost`` is always in the recap, so "some host ran"
proves nothing about the node.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_NODE = "b9a29e04"


def _load_ansible_utils():
    """The shared parser, loaded standalone — it imports only stdlib + env_utils."""
    spec = importlib.util.spec_from_file_location("_au_19762", _BACKEND_ROOT / "services" / "ansible_utils.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_au_19762"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_au_19762", None)
    return module


_au = _load_ansible_utils()


def _recap(node_ok: int = 100, node_failed: int = 0, with_node: bool = True) -> str:
    node = f"{_NODE}  : ok={node_ok}  changed=9  unreachable=0  failed={node_failed}  skipped=114\n"
    return (
        "PLAY RECAP ****\n" + (node if with_node else "") + "localhost  : ok=25  changed=4  unreachable=0  failed=0\n"
    )


# The shape of the 2026-10-27 run: the node's plays ran, three other-group plays skipped.
_SKIPS = "PLAY [Play 2b - Update Database Nodes] ****\nskipping: no hosts matched\n" * 3


def test_skips_from_other_groups_do_not_fail_a_run_the_node_completed() -> None:
    assert _au.ansible_run_failure(_SKIPS + _recap(), None, 0) is None
    assert _au.ansible_run_failure(_SKIPS + _recap(), _NODE, 0) is None
    assert _au.ansible_exit_code(_SKIPS + _recap(), None, 0) == 0


def test_the_inventory_level_markers_still_fail_the_whole_run() -> None:
    for marker in ("[WARNING]: No inventory was parsed\n", "[WARNING]: Could not match supplied host pattern, x\n"):
        assert _au.ansible_run_failure(marker + _recap(), None, 0)


def test_a_real_failure_in_the_recap_still_fails() -> None:
    assert _au.ansible_run_failure(_SKIPS + _recap(node_failed=1), _NODE, 0)


def test_a_run_that_skipped_the_node_entirely_is_not_proof_though_localhost_ran() -> None:
    absent = _SKIPS + _recap(with_node=False)
    assert _au.ansible_run_failure(absent, None, 0) is None  # localhost alone satisfies "some host ran"
    assert _au.limit_run_failure(absent, ["localhost", _NODE])  # which is why the limit is checked too
    assert _au.limit_run_failure(_SKIPS + _recap(node_ok=0), ["localhost", _NODE])


def test_the_limit_proof_passes_when_a_named_host_ran() -> None:
    assert _au.limit_run_failure(_SKIPS + _recap(), ["localhost", _NODE]) is None


def test_a_group_name_in_the_limit_is_satisfied_by_any_member_that_ran() -> None:
    # Limit entries may be groups; the recap lists hosts, so a group is never "absent".
    assert _au.limit_run_failure(_SKIPS + _recap(), ["fleet_nodes"]) is None


def test_a_localhost_only_or_empty_limit_asks_nothing_extra() -> None:
    localhost_only = "PLAY RECAP ****\nlocalhost  : ok=11  changed=1  unreachable=0  failed=0\n"
    assert _au.limit_run_failure(localhost_only, ["localhost"]) is None
    assert _au.limit_run_failure(localhost_only, None) is None


def test_the_executor_result_carries_the_reason_as_a_fatal_line() -> None:
    absent = {"output": _SKIPS + _recap(with_node=False), "returncode": 0, "timed_out": False}
    proved = _au.with_limit_proof(absent, ["localhost", _NODE])
    assert proved["returncode"] == 1
    assert proved["output"].splitlines()[0].startswith("ERROR! no host named by the limit")
    ran = {"output": _SKIPS + _recap(), "returncode": 0}
    assert _au.with_limit_proof(ran, ["localhost", _NODE]) is ran
    failed = {"output": "x", "returncode": 2}
    assert _au.with_limit_proof(failed, ["localhost", _NODE]) is failed
