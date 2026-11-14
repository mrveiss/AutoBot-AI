# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Drive the chat seam's AI-line guard without a database or an SLM (#18430)."""

import asyncio
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from autobot_shared.ai_lines import VERIFIED_COMPANY_KEY
from chat_workflow import approval_baseline as ab
from chat_workflow.tool_dispatch_guards import enforce_ai_line


@contextmanager
def ai_line_world(stored=None, slm_relaxed=None, store_unavailable=False):
    """Patch the outside reads: the line store (one line or ``{action_key: line}``), the SLM setting, approvals."""
    filed = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    async def _stored(_company, key):
        return (stored.get(key) if isinstance(stored, dict) else stored), store_unavailable

    with (
        patch.object(ab, "fetch_slm_policy_json", AsyncMock(return_value=slm_relaxed)),
        patch("services.ai_line_enforcement._stored", _stored),
        patch("services.ai_line_enforcement._file_hold", filed),
        patch("services.ai_line_enforcement.audit_log", AsyncMock(return_value=True)),
    ):
        yield filed


VERIFIED_COMPANY = str(uuid.UUID(int=18430))


async def arun_guard(tool_call, ctx, results, verified_company=True, **world):
    """``enforce_ai_line`` under :func:`ai_line_world`; returns ``(message, approvals_filed)``.

    The ctx gets a server-verified company unless ``verified_company=False``, because that is the one thing a
    mutating action needs to be decided at all (#18430). A client-claimed ``company_id`` never counts.
    """
    if verified_company:
        bag = dict(getattr(ctx, "context", None) or {})
        bag.setdefault(VERIFIED_COMPANY_KEY, VERIFIED_COMPANY)
        ctx.context = bag
    with ai_line_world(**world) as filed:
        message = await enforce_ai_line(tool_call, ctx, results)
    return message, filed.await_count


def run_guard(tool_call, ctx, results, **world):
    """Synchronous form of :func:`arun_guard` for tests that own no event loop."""
    return asyncio.run(arun_guard(tool_call, ctx, results, **world))
