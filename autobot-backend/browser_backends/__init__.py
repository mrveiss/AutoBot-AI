# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""This backend's browser stacks, registered behind the canonical interface (#12651).

`autobot_shared.browser` owns the contract and the dispatch; the three stacks
live here because they are this app's transports. Shared code must never import
them — that inverted dependency is what #13201 had to design around for
`organization_service`, and `autobot_shared/browser/registry_test.py` asserts
by AST that it has not crept back.

Registration order is preference order per capability set. `in_process` leads
because it owns interactive research sessions with MHTML and human handoff;
`worker` follows for element refs and real interaction; `container` last, as
the stateless render/screenshot fallback that survives a backend restart.

Nothing is repointed by importing this — ADR-009 phases 1–2 are additive.
Callers keep their existing paths until the migration steps land.
"""

from __future__ import annotations

import logging

from autobot_shared.browser.registry import register_backend
from browser_backends.container import ContainerBrowserBackend
from browser_backends.in_process import InProcessBrowserBackend
from browser_backends.worker import WorkerBrowserBackend

logger = logging.getLogger(__name__)

__all__ = [
    "ContainerBrowserBackend",
    "InProcessBrowserBackend",
    "WorkerBrowserBackend",
    "register_all",
]

_registered = False


def register_all(*, force: bool = False) -> None:
    """Register this app's browser backends. Idempotent.

    Safe to call from app startup more than once — `register_backend` replaces
    by name rather than stacking, and the module-level guard avoids the churn.
    """
    global _registered
    if _registered and not force:
        return

    register_backend(InProcessBrowserBackend())
    register_backend(WorkerBrowserBackend())
    register_backend(ContainerBrowserBackend())
    _registered = True
    logger.info("browser: registered in_process, worker, container backends")
