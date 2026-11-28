# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which company a coordination record belongs to, stamped when it is WRITTEN (#18391, #18410).

A claim, a waiter and a ledger event carry the company of the authenticated
caller that wrote them. Reads scope by that stamp and never by the agent's name:
an agent slug is a string anyone can choose, so scoping by slug lets a user
squat an unowned one and read the claims behind it.

A record with no company -- written by an install-wide actor (a dev session, an
AI-stack role) or before this existed -- is visible only to the install-wide
(SLM, admin) view. That is the fail-closed default, not a gap to fill by guessing.

The authenticated request boundary calls :func:`set_company`; a writer that
knows its company without a request (a scheduled company run) passes it
explicitly. Nothing here reads a company from a request parameter.
"""

from __future__ import annotations

from contextvars import ContextVar

_COMPANY: ContextVar[str | None] = ContextVar("coordination_company", default=None)


def set_company(company_id: str | None) -> None:
    """Record the authenticated caller's company for writes made under this context."""
    _COMPANY.set(company_id)


def resolve_company(explicit: str | None = None) -> str | None:
    """The company to stamp: the writer's explicit one, else the authenticated context's, else none."""
    return explicit if explicit is not None else _COMPANY.get()
