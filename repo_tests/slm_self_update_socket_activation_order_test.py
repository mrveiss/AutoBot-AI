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
_BIND = _ROLE / "tasks/bind_self_update_socket.yml"
_UPDATE_PLAY = _ROLE.parents[1] / "playbooks/update-all-nodes.yml"
_UNITS = _ROLE / "tasks/service_units.yml"
_HANDLERS = _ROLE / "handlers/main.yml"

_SOCKET = "slm_self_update_socket_service"
_BACKEND = "slm_backend_service"


#: The include DIRECTIVE, anchored to its own line.
#:
#: Matching the bare substring is not enough, and neither was matching
#: ``include_tasks: service_units.yml`` unanchored: a task *name* can contain
#: that complete text, so the real include could be deleted and a name left
#: behind, and the reachability check would still pass over a path that no
#: longer runs. The first version of this detector had negative fixtures
#: carrying only the filename, which is why they did not catch that.
#:
#: Anchoring to a line that *starts* with the module key is what separates a
#: directive from a scalar mentioning one.
_INCLUDE_SERVICE_UNITS = re.compile(
    r"^[ \t-]*(?:ansible\.builtin\.)?include_tasks:[ \t]*service_units\.yml[ \t]*$",
    re.M,
)


def _includes_service_units(text: str) -> bool:
    return bool(_INCLUDE_SERVICE_UNITS.search(text))


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
    # Any indentation: the bind tasks live inside a ``block:``/``rescue:`` so
    # they are nested, and an anchored ``^- name:`` would see only the outer
    # block — collapsing every offset onto it and comparing a task to itself.
    marks = [m.start() for m in re.finditer(r"^\s*- name:", text, re.M)] + [len(text)]
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
    text = _BIND.read_text(encoding="utf-8")

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


@pytest.mark.parametrize("path", [_MAIN, _UNITS, _HANDLERS, _BIND])
def test_the_files_this_reads_still_exist(path: Path) -> None:
    """Reach floor.

    Every assertion above is a search over file text. If a file is renamed or
    moved, those searches find nothing and the permissive assertions pass while
    having checked nothing at all — the shape that let #15823 ship behind a
    green guard in the first place.
    """
    assert path.is_file(), f"{path} is missing; the assertions in this file would silently pass"


def test_a_failed_bind_restores_the_backend_before_re_raising() -> None:
    """The stop/bind window must not be able to leave the service down.

    Raised in review, and it is a worse failure than the one this change fixes:
    the backend is stopped so the socket can bind, so a bind failure between the
    two aborts the play with the service **off** — on the update path, on a node
    that has already taken new code.

    So the bind lives in a ``block:`` whose ``rescue:`` starts the backend and
    only then re-raises. Both halves matter and are asserted separately:

    * without the restore, a failed bind leaves the service down;
    * without the re-raise, the deploy reports success having not bound the
      socket — the silent half, and the one that would look like a fix working.
    """
    text = _BIND.read_text(encoding="utf-8")

    block = re.search(
        r"- name: \"SLM \| Bind the self-update socket.*",
        text,
        re.S | re.M,
    )
    assert block, "the bind tasks must live in one block so a failure can be rescued"
    body = _directives(block.group(0))

    assert "rescue:" in body, (
        "the bind block has no rescue: a failed bind aborts the play between the stop and the "
        "start, leaving the backend down (#15823 review)"
    )

    rescue = body[body.index("rescue:") :]
    # The task must start the BACKEND, not merely something. Accepting any
    # `state: started` lets a mutation that starts the socket instead pass while
    # the backend stays stopped — the exact failure the rescue exists to
    # prevent, and one that would look correct in the diff.
    restore_task = next(
        (
            chunk
            for chunk in re.split(r"(?=^\s*- name:)", rescue, flags=re.M)
            if _BACKEND in chunk and "state: started" in chunk
        ),
        None,
    )
    assert restore_task is not None, (
        "the rescue must start the backend service itself — a `state: started` on anything else "
        "leaves the backend stopped, which is what the rescue is for"
    )
    assert "ansible.builtin.fail" in rescue, (
        "the rescue must re-raise. Restoring the backend and continuing would report a successful "
        "deploy with the socket unbound, which is the failure this fix exists to prevent."
    )

    restore = rescue.index(restore_task)
    reraise = rescue.index("ansible.builtin.fail")
    assert restore < reraise, "the backend must be restored BEFORE re-raising; failing first leaves the service down"


def test_both_entry_points_reach_the_bind() -> None:
    """The update path must reach the fix, not only a full provision.

    ``playbooks/update-all-nodes.yml`` Play 1 runs the role with
    ``tasks_from: service_units.yml`` and **never runs main.yml**. Raised in
    review: with the bind in ``main.yml`` the fix would miss the update path —
    which is the path #15823 was reported on, and the only one where a node is
    left carrying new code after the abort.

    So the bind lives in ``service_units.yml``, which both entry points run, and
    ``main.yml`` must not carry a second copy: two copies drift, and the copy
    that drifts is the one nobody is running when it breaks.
    """
    units = _directives(_UNITS.read_text(encoding="utf-8"))
    assert (
        "bind_self_update_socket.yml" in units
    ), "service_units.yml must include the bind; it is the only file both entry points run"

    main = _directives(_MAIN.read_text(encoding="utf-8"))
    assert "state: stopped" not in main, (
        "main.yml carries its own stop/bind sequence again — a second copy that the update path "
        "does not run (#15823 review)"
    )


def test_each_entry_point_still_reaches_service_units() -> None:
    """Both callers must still *include* the file the bind lives in.

    Raised in review, and the gap was real: asserting that `service_units.yml`
    includes the bind proves nothing about whether anything still runs
    `service_units.yml`. Either entry point could stop reaching it while that
    assertion stayed green — the bind would be present, correct, and dead.

    * the full role reaches it through `main.yml`
    * `playbooks/update-all-nodes.yml` Play 1 reaches it directly with
      `tasks_from: service_units.yml`, and never runs `main.yml` — which is why
      putting the bind in `main.yml` missed the update path in the first place
    """
    main = _directives(_MAIN.read_text(encoding="utf-8"))
    assert _includes_service_units(main), (
        "main.yml no longer includes service_units.yml, so the full-provision path does not reach "
        "the bind (#15823 review)"
    )

    assert _UPDATE_PLAY.is_file(), f"{_UPDATE_PLAY} is missing; the assertion below would pass having read nothing"
    play = _directives(_UPDATE_PLAY.read_text(encoding="utf-8"))
    assert re.search(r"tasks_from:\s*service_units\.yml", play), (
        "playbooks/update-all-nodes.yml no longer runs service_units.yml, so the UPDATE path — the "
        "one #15823 was reported on — does not reach the bind"
    )


@pytest.mark.parametrize(
    ("fixture", "should_trip"),
    [
        # Real directives, in the forms this repo writes them.
        ("  ansible.builtin.include_tasks: service_units.yml\n", True),
        ("  ansible.builtin.include_tasks:  service_units.yml\n", True),
        ("  include_tasks: service_units.yml\n", True),
        ("- ansible.builtin.include_tasks: service_units.yml\n", True),
        # Scalars carrying the COMPLETE directive text — the case the first
        # version of this detector missed, because its negatives contained only
        # the filename. The include can be deleted and one of these left behind.
        ('  - name: "runs ansible.builtin.include_tasks: service_units.yml"\n', False),
        ('  msg: "ansible.builtin.include_tasks: service_units.yml"\n', False),
        ("  # ansible.builtin.include_tasks: service_units.yml\n", False),
        # Mentions of the filename alone.
        ('- name: "SLM | Refresh units, see service_units.yml for detail"\n', False),
        ("  # the bind moved out of service_units.yml\n", False),
        ("  ansible.builtin.include_tasks: other.yml\n", False),
    ],
)
def test_the_include_detector_distinguishes_a_directive_from_a_mention(fixture: str, should_trip: bool) -> None:
    """Contrast pair for the reachability detector.

    Raised in review: the check accepted **any** occurrence of the filename, so
    a task name or a comment mentioning `service_units.yml` would keep it green
    after the include itself was deleted — the full-provision path silently no
    longer reaching the bind.

    A detector with no negative case cannot be told apart from one that returns
    True for everything, which is the same failure this whole file guards
    against one level down.
    """
    assert _includes_service_units(fixture) is should_trip
