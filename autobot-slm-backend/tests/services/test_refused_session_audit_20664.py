# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20664: a refused non-admin session is audited once per person per window, and never changes the 403."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    """By path: the root conftest stubs ``services.*``."""
    path = _BACKEND / "services" / "refused_session_audit.py"
    spec = importlib.util.spec_from_file_location("_refused_session_audit_20664", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def audit():
    return _load()


@pytest.fixture
def writer():
    writer = AsyncMock()
    shared = ModuleType("autobot_shared.user_management.middleware.rbac_middleware")
    shared._emit_permission_denied_audit = writer
    wiring = ModuleType("user_management.middleware.rbac_middleware")
    package = ModuleType("user_management.middleware")
    package.rbac_middleware = wiring
    stubs = {shared.__name__: shared, package.__name__: package, wiring.__name__: wiring}
    with patch.dict(sys.modules, stubs):
        yield writer


@pytest.mark.asyncio
async def test_the_first_refusal_writes_a_denial_naming_the_person(audit, writer) -> None:
    await audit.note_refused_session("operator")
    writer.assert_awaited_once()
    assert writer.await_args.args[1] == "slm.admin_session"
    assert writer.await_args.kwargs["subject"].startswith("operator")


@pytest.mark.asyncio
async def test_repeats_in_the_window_write_nothing_and_the_next_record_counts_them(audit, writer) -> None:
    for _ in range(50):
        await audit.note_refused_session("operator")
    assert writer.await_count == 1
    subject, (at, repeats) = next(iter(audit._GROUPER._recent.items()))
    assert subject == "operator" and repeats == 49
    audit._GROUPER._recent["operator"] = (at - audit.WINDOW_S - 1, repeats)
    await audit.note_refused_session("operator")
    assert writer.await_count == 2 and "+49 refused" in writer.await_args.kwargs["subject"]


@pytest.mark.asyncio
async def test_each_person_gets_their_own_record(audit, writer) -> None:
    await audit.note_refused_session("a")
    await audit.note_refused_session("b")
    assert writer.await_count == 2


@pytest.mark.asyncio
async def test_a_failed_write_doesnt_raise(audit, writer) -> None:
    writer.side_effect = RuntimeError("db down")
    await audit.note_refused_session("operator")


def test_the_tracked_set_cant_grow_past_its_cap(audit) -> None:
    audit._GROUPER.max_tracked = 3
    for number in range(20):
        assert audit.repeats_to_record(f"person-{number}") == 0
    assert len(audit._GROUPER._recent) <= 3


def test_get_current_user_records_before_refusing() -> None:
    source = (_BACKEND / "services" / "auth.py").read_text(encoding="utf-8")
    body = source[source.index("async def get_current_user") :]
    refusal = body[body.index("if not is_admin_session(payload):") :]
    assert refusal.index("note_refused_session") < refusal.index("raise HTTPException")
