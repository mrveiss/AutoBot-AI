# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The manage-service rescue must capture the cause AND still fail (#15879).

A service start that fails logs systemd's generic "See `systemctl status` and
`journalctl -xeu` for details" -- a message that names its own evidence and
withholds it, because that journal is on the managed node and the operator is
reading the controller's aggregated log. The rescue added for #15879 fetches
those details from the node that failed.

The risk the rescue introduces is worse than the defect it fixes. A rescue that
captures and returns cleanly turns a failed service start into a **green play**.
Today the failure is loud and uninformative; a non-re-raising rescue would be
silent and informative, and silence on a failed production service start is the
worse of the two. So this file pins the re-raise, not the capture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_PLAYBOOK = Path(__file__).resolve().parents[1] / "ansible" / "manage-service.yml"

_FAIL_MODULES = {"ansible.builtin.fail", "fail", "ansible.builtin.assert", "assert"}


def _service_block() -> dict:
    """The task that wraps the service call, or fail saying it is gone.

    Bound rather than searched-and-shrugged: if the block is renamed or
    unwrapped, every assertion below would pass vacuously over an empty
    rescue, so its absence has to be the failure.
    """
    assert _PLAYBOOK.is_file(), f"playbook under test is missing: {_PLAYBOOK}"
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    blocks = [
        task
        for play in plays
        for task in play.get("tasks", [])
        if isinstance(task, dict) and "block" in task and "rescue" in task
    ]
    assert len(blocks) == 1, (
        f"expected exactly one block/rescue in {_PLAYBOOK.name}, found {len(blocks)}. "
        "The service call must stay wrapped or the capture never runs (#15879)."
    )
    return blocks[0]


def test_the_rescue_re_raises_so_a_failed_start_is_still_a_failed_play() -> None:
    """The whole point. A capturing rescue that returns cleanly is broken-open."""
    rescue = _service_block()["rescue"]
    assert rescue, "the rescue is empty -- a failed service start would pass silently"

    terminal = rescue[-1]
    module = next((k for k in terminal if k in _FAIL_MODULES), None)
    assert module is not None, (
        "the rescue's LAST task does not fail. A rescue that captures the cause and "
        f"returns cleanly converts a failed service start into a green play. Got: "
        f"{sorted(k for k in terminal if not k.startswith('_'))}"
    )


def _capture_task(rescue: list) -> dict:
    """The rescue task that runs the probes, identified by what it runs.

    Bound to the task rather than to "some task in the rescue": a check that
    only asks whether `failed_when: false` appears *somewhere* passes when the
    exemption migrates onto the `debug` or the `fail` task -- which would make
    the re-raise unable to fail. Review caught exactly that (#15879).
    """
    matches = [
        task
        for task in rescue
        if any("systemctl" in str(item) for item in (task.get("loop") or []))
    ]
    assert len(matches) == 1, (
        f"expected exactly one task running the probes, found {len(matches)}. "
        "The assertions below identify the capture by what it runs, so it must be findable."
    )
    return matches[0]


def test_the_exemption_sits_on_the_capture_task_and_nowhere_else() -> None:
    """`failed_when: false` is required on the capture and forbidden everywhere else.

    `systemctl status` exits non-zero for a failed unit -- the case we are in --
    so the capture needs the exemption or it loses the diagnosis. On the service
    call it would silence the failure; on the `fail` task it would defeat the
    re-raise, turning a failed start into a green play.
    """
    block = _service_block()

    for task in block["block"]:
        assert task.get("failed_when") is not False, (
            f"the service task {task.get('name')!r} is marked `failed_when: false`, "
            "so it can no longer fail -- that silences the failure this exists to report"
        )

    capture = _capture_task(block["rescue"])
    assert capture.get("failed_when") is False, (
        "the capture task is not exempt; `systemctl status` returns non-zero for a "
        "failed unit, so it would abort before reporting the diagnosis"
    )

    for task in block["rescue"]:
        if task is capture:
            continue
        assert task.get("failed_when") is not False, (
            f"rescue task {task.get('name')!r} carries `failed_when: false`. On the "
            "re-raise that converts a failed service start into a green play (#15879)."
        )


def test_the_capture_reads_the_node_journal_not_just_the_unit_state() -> None:
    """Both halves of the message systemd tells the reader to consult."""
    commands = " ".join(str(item) for item in (_capture_task(_service_block()["rescue"]).get("loop") or []))
    for probe in ("systemctl", "journalctl"):
        assert probe in commands, (
            f"the rescue never runs {probe!r}. systemd's failure message names both, "
            "and fetching only one leaves the operator on the same hunt (#15879)."
        )


def test_the_probes_are_argv_so_a_service_name_cannot_inject_options() -> None:
    """CWE-88: `service_name` is caller-supplied and runs here under `become`.

    A `cmd:` string is split into arguments before execution, so a multi-token
    name could add options -- redirecting journalctl at another unit whose
    output then lands in the controller log. As argv the value stays one
    element. Asserted on the structure, because a string that merely *looks*
    safe today is one templating change from not being.
    """
    capture = _capture_task(_service_block()["rescue"])
    assert "argv" in capture.get("ansible.builtin.command", capture.get("command", {})), (
        "the diagnostic runs via `cmd:`, which splits a caller-supplied service_name "
        "into arguments under become (#15879 review, CWE-88)"
    )
    for probe in capture.get("loop") or []:
        assert isinstance(probe, list), f"probe is not an argv list: {probe!r}"
        assert sum("{{ service_name }}" in str(tok) for tok in probe) == 1, (
            f"service_name appears in more than one argv element: {probe!r}"
        )
