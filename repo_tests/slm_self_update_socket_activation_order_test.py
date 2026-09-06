# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The self-update socket must bind before the service it activates (#15823).

systemd refuses to start a socket whose ``Service=`` is already running:

    autobot-slm-self-update.socket: Socket service autobot-slm-backend.service
    already active, refusing.

The role used to run ``state: started`` on the socket in ``service_units.yml``
(main.yml:673), while the backend is only restarted much later (:1023). On any
node already serving, the backend was still up from before the deploy, so that
task failed every run — and it failed **after the code archives had landed**,
leaving a node with new code and an incomplete activation.

**What the existing guard could not see.**
``slm_self_update_socket_permissions_test.py`` parses the unit file's *text* —
mode, user, group, ``RemoveOnStop``. Every one of those assertions passed
throughout: the defect was never in the unit file. It was in the order two
tasks run in, in a different file. A text-parse test cannot fail on an
ordering defect, which is why this issue reached production behind a green
guard.

**What this test can and cannot prove.**
It cannot start systemd, so it cannot observe the refusal. What it asserts is
the ordering property the fix turns on, read from the task files: the socket is
started only after a task that stops the backend, and before the task that
starts it. That is weaker than an activation test and stronger than parsing the
unit — it fails if someone restores ``state: started`` to the early task, or
moves the socket start back after the service start, which are the two ways
this regresses.

An end-to-end check would need a systemd-capable container; none exists in this
suite, and asserting that here rather than pretending otherwise is the point of
this docstring.
"""

import re
from pathlib import Path

import pytest

_ROLE = Path(__file__).resolve().parents[1] / "autobot-slm-backend/ansible/roles/slm_manager"
_MAIN = _ROLE / "tasks/main.yml"
_UNITS = _ROLE / "tasks/service_units.yml"
_HANDLERS = _ROLE / "handlers/main.yml"

_SOCKET = "slm_self_update_socket_service"
_BACKEND = "slm_backend_service"


def _directives(block: str) -> str:
    """The block with comment lines removed.

    Every predicate below searches task text for things like ``state: started``.
    A prose comment explaining *why* a directive was removed contains that exact
    string, so an un-stripped search matches the explanation and reports the
    defect it was written to describe. That is not hypothetical — the first run
    of this file failed on its own comment, which is the same trap the frontend
    contract ratchet hit earlier: **a text scan cannot tell code from prose
    about code.**
    """
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))


def _offset_of(text: str, predicate) -> int | None:
    """Offset of the first task block whose body satisfies ``predicate``."""
    marks = [m.start() for m in re.finditer(r"^- name:", text, re.M)] + [len(text)]
    for start, end in zip(marks, marks[1:]):
        if predicate(_directives(text[start:end])):
            return start
    return None


def test_the_socket_is_not_started_in_service_units() -> None:
    """The early task enables the socket and must not start it.

    This is the exact regression: ``state: started`` here runs while the backend
    is still up from before the deploy, and systemd refuses.
    """
    text = _UNITS.read_text(encoding="utf-8")
    start = _offset_of(text, lambda b: _SOCKET in b and "state: started" in b)
    assert start is None, (
        "service_units.yml starts the self-update socket. That task runs long before the "
        "backend is restarted, so systemd refuses it whenever the node was already serving "
        "(#15823). Enable it here; start it in main.yml where the backend is down."
    )
    enable = _offset_of(text, lambda b: _SOCKET in b and "enabled: true" in b)
    assert enable is not None, "the socket must still be enabled in service_units.yml"


def test_the_socket_binds_between_stopping_and_starting_the_backend() -> None:
    """Bind order, which is the whole fix.

    Started before the stop, systemd refuses. Started after the service start,
    it is refused again and the self-update path has no listener despite the
    unit being enabled.
    """
    text = _MAIN.read_text(encoding="utf-8")

    stop = _offset_of(text, lambda b: _BACKEND in b and "state: stopped" in b)
    socket = _offset_of(text, lambda b: _SOCKET in b and re.search(r"state: (started|restarted)", b))
    start = _offset_of(text, lambda b: _BACKEND in b and "state: started" in b)

    assert stop is not None, "main.yml must stop the backend to open a window for the socket bind"
    assert socket is not None, "main.yml must start the self-update socket"
    assert start is not None, "main.yml must start the backend"

    assert stop < socket < start, (
        "the socket must bind between stopping and starting the backend "
        f"(stop@{stop}, socket@{socket}, backend start@{start}). Outside that window systemd "
        "refuses the socket because its Service= is active."
    )


def test_no_handler_restarts_the_socket_after_the_backend_is_up() -> None:
    """A handler for this can only ever fire in the state that fails.

    Handlers flush after the backend has been started, so a
    ``restart slm self-update socket`` notification is guaranteed to hit the
    refusal. The handler may exist; nothing may notify it.
    """
    notifiers = [
        p.name
        for p in (_UNITS, _MAIN)
        if re.search(r"^\s*- restart slm self-update socket\s*$", _directives(p.read_text(encoding="utf-8")), re.M)
    ]
    assert not notifiers, (
        f"{notifiers} notify the self-update socket restart handler. Handlers flush after the "
        "backend is running, where systemd refuses the restart (#15823). The ordered restart in "
        "main.yml applies template changes instead."
    )


@pytest.mark.parametrize("path", [_MAIN, _UNITS, _HANDLERS])
def test_the_files_this_reads_still_exist(path: Path) -> None:
    """Reach floor.

    Every assertion above is a search over file text. If a file is renamed or
    moved, those searches find nothing and the permissive assertions pass while
    having checked nothing at all — the shape that let #15823 ship behind a
    green guard in the first place.
    """
    assert path.is_file(), f"{path} is missing; the assertions in this file would silently pass"
