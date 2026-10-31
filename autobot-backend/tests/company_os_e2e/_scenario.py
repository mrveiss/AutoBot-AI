# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scenario's HTTP client, shared state and step bookkeeping (#19253).

A failing step raises StepFailure, whose message names the step and the M2.x issue it maps to
(the issue's third acceptance criterion). A known open defect is recorded with pytest.xfail(reason)
at the ONE assertion that encodes it, after the step's preconditions (the control agent was
dispatched, the budget reads exhausted, ...) have been asserted for real, so a dead scheduler or a
broken setup is a red failure and never reads as the open bug. When the fix lands the assertion
passes, the xfail call is never reached, and the reason's "remove" instruction is moot.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from tests.company_os_e2e._stack import HTTP_TIMEOUT_SECONDS, LOGIN_PASSWORD, LOGIN_USERNAME, Stack

API = "/api/llc"
# The scheduler wakes an agent on a cron boundary (one minute is the finest), polls every few
# seconds, and a run takes one stubbed model call. Two windows is enough to see a wake or its absence.
WAKE_WINDOW_SECONDS = float(60 * 2 + 20)

# step number -> (name, where a failure maps to)
STEPS: dict[str, tuple[str, str]] = {
    "1": ("create a company", "M2.1 members and tenancy (phase:M2.1)"),
    "2": ("hire a CEO and two heartbeat-enabled agents", "M2.2 hiring and the CEO (#15907, phase:M2.2)"),
    "3": ("set a goal, create a project and work items", "M2.3 work item hierarchy (#18978, phase:M2.3)"),
    "4": ("assign a task", "M2.3 work item hierarchy and assignment (phase:M2.3)"),
    "5": ("a scheduled heartbeat run is dispatched for the assignee", "M2.5 heartbeat scheduling (#20117, #19189)"),
    "5b": (
        "the dispatched run can reach the Agent API and take the task",
        "M2.5 run dispatch and run-scoped key (#20149)",
    ),
    "6": ("an exhausted budget stops dispatch", "M2.6 dispatch gate (#19240, PR #19958)"),
    "7": (
        "pause and resume an agent through the API",
        "M2.7 controls (#14189, #14164, #20150)",
    ),
    "7b": ("a paused agent is not dispatched until resumed", "M2.6 dispatch gate (#19240, PR #19958)"),
    "8": ("a hire approval can be filed and decided", "M2.7 board approval gates (#8214)"),
    "8b": ("a hire waits for its approval", "M2.7 board approval gates (#8214)"),
    "9": ("the activity log holds every step with actor_type", "M2.8 audit (#20101, PR #20107)"),
}


class StepFailure(AssertionError):
    """A scenario step failed; the message says which and what it maps to."""


@contextmanager
def step(number: int | str) -> Iterator[None]:
    name, maps_to = STEPS[str(number)]
    try:
        yield
    except StepFailure:
        raise
    except Exception as exc:
        raise StepFailure(f"STEP {number} ({name}) FAILED, maps to {maps_to}: {exc}") from exc


class Api:
    """The signed-in public API client. Raises AssertionError on an unexpected status."""

    def __init__(self, stack: Stack) -> None:
        # No connection reuse: the server closes idle keep-alive sockets, and the scenario idles for
        # minutes at a time, so a pooled connection would be reset on its next use.
        limits = httpx.Limits(max_keepalive_connections=0)
        self.http = httpx.Client(base_url=stack.base_url, timeout=HTTP_TIMEOUT_SECONDS, limits=limits)
        self.stack = stack
        self.company_id: str | None = None
        login = self.http.post("/api/auth/login", json={"username": LOGIN_USERNAME, "password": LOGIN_PASSWORD})
        assert login.status_code == 200, f"login failed: {login.status_code} {login.text[:300]}"
        self.http.headers["Authorization"] = f"Bearer {login.json()['token']}"

    def call(self, method: str, path: str, ok: tuple[int, ...] = (200, 201, 202, 204), **kw: Any) -> Any:
        resp = self.http.request(method, f"{API}{path}", **kw)
        assert resp.status_code in ok, f"{method} {path} -> {resp.status_code} {resp.text[:400]}"
        return resp.json() if resp.content else None

    def refuse(self, method: str, path: str, **kw: Any) -> httpx.Response:
        """A request the server should answer with a 4xx; returns the response."""
        return self.http.request(method, f"{API}{path}", **kw)

    def select_company(self, company_id: str) -> None:
        """Act inside this company: routes without a company in the path read the header."""
        self.company_id = company_id
        self.http.headers["X-Organization-Id"] = company_id

    def company(self, path: str) -> str:
        return f"/companies/{self.company_id}{path}"


@dataclass
class Scenario:
    api: Api
    stack: Stack
    agents: dict[str, dict[str, str]] = field(default_factory=dict)  # role -> {agent_id, node_id}
    ids: dict[str, str] = field(default_factory=dict)
    done: set[int] = field(default_factory=set)

    def require(self, *steps: int) -> None:
        missing = [n for n in steps if n not in self.done]
        if missing:
            raise StepFailure(f"prerequisite step(s) {missing} did not complete, so this step cannot run")

    def need(self, key: str, step: int) -> str:
        """State another step records; a clear precondition failure naming that step when it is absent."""
        if key not in self.ids:
            raise StepFailure(f"precondition: '{key}' is recorded by step {step}, which did not complete")
        return self.ids[key]

    def agent(self, role: str) -> dict[str, str]:
        if role not in self.agents:
            raise StepFailure(f"precondition: agent '{role}' is hired by step 2, which did not complete")
        return self.agents[role]

    def stub_invocations(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        lines = Path(self.stack.stub_log).read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        return [r for r in rows if agent_id is None or r["agent_id"] == agent_id]

    def server_log_has(self, *needles: str) -> bool:
        """Whether the server log holds every needle: how a test tells a known cause from a new one."""
        text = Path(self.stack.server_log).read_text(encoding="utf-8", errors="replace")
        return all(n in text for n in needles)

    def runs(self, agent_id: str) -> list[dict[str, Any]]:
        return self.api.call("GET", f"/agents/{agent_id}/runs")


def wait_for(probe: Callable[[], Any], seconds: float, every: float = 3.0) -> Any:
    """Poll until probe() is truthy; return it, or None when the time is up."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(every)
    return None
