# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which claimed run the current code belongs to, and when it last made progress (#15950).

A work claim renews for as long as its run is alive, and "alive" used to mean
only "the coroutine has not returned". A run hung on an await that never
completes therefore renewed its claims forever. The owner's ruling on #15950
ties renewal to *progress* instead: the renewer keeps a claim only while the run
keeps reporting that it is doing something. That needs two things, and this
module provides both:

* **A record of the run, reachable from anywhere inside it.** It is held in a
  ``ContextVar``, so an LLM provider or the tool SDK, several layers below the
  agent, can say "the run I belong to just did something" without being handed a
  reference. Tasks created inside a run copy the context, so work fanned out
  from it reports to it too.
* **The run's standing,** which a write site checks before writing. A claim that
  lapsed because its run stalled must not be written under (#15950 AC6).

It lives in ``autobot_shared`` rather than beside the claim logic in
``agents.scope_enforcement`` because the progress points are in layers below
the agents, which must not import from ``agents``.

Outside a claimed run, ``record_progress`` does nothing and ``current_run``
returns None. Reporting progress is never the reason a call fails.
"""

from __future__ import annotations

import contextlib
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator, Literal

#: ``held``: every declared scope is claimed and being renewed.
#: ``lapsed``: renewal stopped because the run stalled, or a renew found the
#: claim gone. Writes under it are refused.
#: ``degraded``: the claim registry was unavailable, so the run proceeds
#: unclaimed by design; writes are allowed and logged.
Standing = Literal["held", "lapsed", "degraded"]


@dataclass
class ClaimedRun:
    """One run holding its declared scopes, and when it last reported progress."""

    scopes: frozenset[str]
    standing: Standing = "held"
    last_progress: float = field(default_factory=time.monotonic)
    lapse_reason: str = ""
    parent: ClaimedRun | None = None

    def lapse(self, reason: str) -> None:
        """Mark the claim as no longer safe to write under, and say why."""
        self.standing = "lapsed"
        self.lapse_reason = reason

    def chain(self) -> Iterator[ClaimedRun]:
        """This run and every run it is nested inside, innermost first."""
        run: ClaimedRun | None = self
        while run is not None:
            yield run
            run = run.parent


_CURRENT: ContextVar[ClaimedRun | None] = ContextVar("autobot_claimed_run", default=None)


def current_run() -> ClaimedRun | None:
    """The claimed run the calling code belongs to, or None outside one."""
    return _CURRENT.get()


def record_progress() -> None:
    """Report that the run the caller belongs to just did something.

    Walks up through nested runs, because progress made inside an inner run is
    also progress of the run that contains it. Outside a run this does nothing.
    """
    run = _CURRENT.get()
    if run is None:
        return
    now = time.monotonic()
    for each in run.chain():
        each.last_progress = now


@contextlib.contextmanager
def bound(run: ClaimedRun) -> Iterator[ClaimedRun]:
    """Make *run* the current run for the body, nested under any enclosing one."""
    run.parent = _CURRENT.get()
    token = _CURRENT.set(run)
    try:
        yield run
    finally:
        _CURRENT.reset(token)
