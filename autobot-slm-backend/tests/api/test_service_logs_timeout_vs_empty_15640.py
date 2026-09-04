# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``get_service_logs`` must answer differently for "cut short" and "logged nothing" (#15640).

#15620 fixed the chain that keeps those two apart, and left both of its
boundaries untested. The bug it replaced was not a crash: the fetch returned
``(bool, str)``, and on timeout the error text travelled in the same slot the
logs do, so the route answered 200 with something falsy and
``FleetToolsTab.vue`` rendered ``logs || 'No logs available'`` — a node that had
been cut off mid-answer told the operator, in words, that it had nothing to say.

Both boundaries are asserted here, and both are needed. A test that only pinned
the 504 would let a regression *move* the ambiguity rather than remove it: make
an empty journal answer 504 too and the timeout assertion still passes, while
the operator is back to one answer for two situations.

The route is driven directly rather than through a ``TestClient`` because the
subject is the mapping the route body performs; the transport underneath
``services/journal_fetch.py`` is faked at ``asyncio.create_subprocess_exec``, so
the real ceiling, the real ``asyncio.wait_for``, the real orphan kill and the
real ``except JournalFetchTimeout`` clause all execute.

Ordering note (#15620): this file could not have been written before
``services.journal_fetch`` joined the root conftest's ``_REAL_SERVICE_MODULES``.
Under the plain stub list ``JournalFetchTimeout`` is a MagicMock, and
``except <MagicMock>`` raises ``TypeError`` instead of catching — the timeout
would have crashed the route rather than mapping to 504. The last test below
pins that precondition so it cannot be quietly withdrawn.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException, status

# Shared real-ORM swap (#15640): api/services.py decorates its routes with
# `response_model=` Pydantic classes, and the root conftest stubs models.schemas
# as a MagicMock, which FastAPI rejects at decoration time. The empty-journal
# assertion also needs the REAL ServiceLogsResponse — a fieldless stand-in drops
# the `logs=""` it is handed, which is the very value under test.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import REAL_MODULES, SLM_ROOT, import_modules_with_real_orm  # noqa: E402

_restart, _services_api = import_modules_with_real_orm(
    import_names=("api.services",),
    path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"},
)
_journal_fetch = sys.modules["services.journal_fetch"]
Node = REAL_MODULES["models.database"].Node
ServiceLogsResponse = REAL_MODULES["models.schemas"].ServiceLogsResponse

_PRINCIPAL = {"admin": True, "role": "admin", "sub": "tester"}
_NODE_ID = "n-logs"
_SERVICE = "slm-backend"

# The ceiling the route is driven against. Small enough that the timeout test
# costs milliseconds, and printed into the 504 detail by the module under test,
# so the assertion below reads the value back out rather than restating 30.0.
_TEST_CEILING_SECONDS = 0.05

# What "the fetch never finishes" is made of. Any value far above the ceiling
# does; `wait_for` cancels this sleep rather than waiting it out.
_NEVER_SECONDS = 3600.0


class _FakeProcess:
    """A stand-in for the ssh child ``fetch_service_journal`` spawns."""

    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, hangs: bool = False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._hangs = hangs
        self.killed = False

    async def communicate(self):
        if self._hangs:
            await asyncio.sleep(_NEVER_SECONDS)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


class _NodeResult:
    def __init__(self, node):
        self._node = node

    def scalar_one_or_none(self):
        return self._node


class _NodeReturningSession:
    """The narrowest ``db`` ``_get_node_or_404`` accepts: one node, one query."""

    def __init__(self, node):
        self._node = node
        self.statements: list = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _NodeResult(self._node)


@pytest.fixture
def db_session():
    return _NodeReturningSession(
        Node(node_id=_NODE_ID, hostname="host-logs", ip_address="10.0.0.83", ssh_user="autobot", ssh_port=22)
    )


@pytest.fixture
def transport(monkeypatch):
    """Install *process* as the ssh child, recording the argv it was spawned with."""
    recorded: dict = {"argv": None}

    def _install(process: _FakeProcess) -> dict:
        async def _spawn(*argv, **_kwargs):
            recorded["argv"] = list(argv)
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
        monkeypatch.setattr(_journal_fetch, "JOURNAL_SSH_TIMEOUT_SECONDS", _TEST_CEILING_SECONDS)
        return recorded

    return _install


async def _call_logs(db_session, lines: int = 100):
    return await _services_api.get_service_logs(
        node_id=_NODE_ID,
        service_name=_SERVICE,
        db=db_session,
        _=_PRINCIPAL,
        lines=lines,
        since=None,
    )


class TestServiceLogsDistinguishesCutShortFromEmpty:
    """#15640 — the two boundaries of the timeout-vs-empty distinction."""

    async def test_a_fetch_that_runs_out_of_time_answers_504_and_names_the_ceiling(self, db_session, transport):
        """504, with enough in the detail for an operator to act on it.

        Not 500 and not an empty 200: the status code alone has to carry
        "incomplete, not absent". The detail names the ceiling that was hit and
        the environment variable that moves it, so the answer says what to
        change rather than only that something went wrong.

        Against the pre-#15620 shape — a timeout returning ``(False, "...")`` or
        ``(True, "")`` instead of raising — this fails on the status code: 500
        or no exception at all. Against a route that drops the
        ``except JournalFetchTimeout`` clause it fails with the bare
        ``JournalFetchTimeout`` escaping instead of an ``HTTPException``.
        """
        process = _FakeProcess(hangs=True)
        transport(process)

        with pytest.raises(HTTPException) as raised:
            await _call_logs(db_session)

        assert raised.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        detail = str(raised.value.detail)
        assert _SERVICE in detail
        assert f"{_TEST_CEILING_SECONDS:g}s" in detail, "the 504 must name the ceiling it hit"
        assert "AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS" in detail, "the 504 must name what to change"
        assert "incomplete" in detail, "the 504 must say the logs are incomplete, not absent"
        assert process.killed is True, "the cancelled fetch left its ssh child running"

    async def test_an_empty_journal_still_answers_200_with_empty_content(self, db_session, transport):
        """A unit that logged nothing is a success, and says so with empty logs.

        This is the half that keeps the fix from merely relocating the
        ambiguity. A regression that answered 504 for an empty journal would
        satisfy the timeout test above while leaving the operator with one
        answer for two different situations.
        """
        transport(_FakeProcess(stdout=b"", stderr=b"", returncode=0))

        response = await _call_logs(db_session)

        assert isinstance(response, ServiceLogsResponse)
        assert response.logs == ""
        assert response.node_id == _NODE_ID
        assert response.service_name == _SERVICE
        assert response.lines_returned == 1

        route = next(r for r in _services_api.router.routes if getattr(r, "name", None) == "get_service_logs")
        # FastAPI leaves `status_code` unset when the decorator names none, and
        # answers 200. Asserting it here pins that the success path is a plain
        # 200 rather than anything a caller would have to branch on.
        assert route.status_code in (None, status.HTTP_200_OK)
        assert route.response_model is ServiceLogsResponse

    async def test_the_journalctl_request_reaches_the_transport(self, db_session, transport):
        """The route's wiring, not only its error mapping.

        ``_run_ansible_get_logs`` builds the remote command through
        ``build_journal_command`` and the argv through the same
        ``build_service_ssh_cmd`` the restart path uses. A test that faked the
        fetch outright would assert the 504 mapping over a route that had
        stopped asking for logs at all.
        """
        recorded = transport(_FakeProcess(stdout=b"line one\nline two\n", returncode=0))

        response = await _call_logs(db_session, lines=25)

        assert response.logs == "line one\nline two\n"
        assert recorded["argv"][-1] == f"sudo -n journalctl -u {_SERVICE} -n 25 --no-pager"
        assert f"autobot@{db_session._node.ip_address}" in recorded["argv"]

    def test_the_timeout_type_the_route_catches_is_a_real_exception(self):
        """The precondition that made the 504 test writable at all (#15620).

        ``except <MagicMock>`` raises ``TypeError`` rather than catching, so if
        ``services.journal_fetch`` ever falls back to the root conftest's plain
        stub list the route stops mapping the timeout and starts crashing on it.
        That would break this file loudly, which is the point — but it would
        break it in a way that reads as unrelated, so the precondition is named.
        """
        timeout_type = _journal_fetch.JournalFetchTimeout
        assert isinstance(timeout_type, type)
        assert issubclass(timeout_type, Exception)
        assert _services_api.JournalFetchTimeout is timeout_type
