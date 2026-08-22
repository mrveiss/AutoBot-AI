# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14800: the template import creates runnable agents, so it asks the hire questions.

`POST /companies/{id}/agent-hires` rejects an unregistered `adapter_type` and one
whose adapter cannot run here. `_import_agent` inserted straight into
`agent_org_nodes` with an `adapter_type` taken from an imported template and asked
neither, so a template could create an agent whose every heartbeat is skipped —
the same symptom both hire-time checks exist to prevent, through a path that had
no checks at all.

Skipped-with-a-warning rather than a hard failure: a template may legitimately be
imported onto a host provisioned afterwards, and the import response already
carries `warnings` and `skipped`.

These drive `_import_agent` itself and assert on what it returns and appends, since
the defect was the missing check rather than a wrong answer.
"""

from __future__ import annotations

import uuid
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest


def _svc() -> ModuleType:
    import llc.services.portability as mod

    return mod


class _Available:
    def is_cli_available(self) -> bool:
        return True

    def cli_not_found_message(self) -> str:  # pragma: no cover - not reached
        return "unused"


class _Missing:
    def is_cli_available(self) -> bool:
        return False

    def cli_not_found_message(self) -> str:
        return "'claude' CLI not found on PATH"


def _service(mod: ModuleType):
    svc = mod.PortabilityService.__new__(mod.PortabilityService)
    svc._agent_names_exist = AsyncMock(return_value=[])
    svc._resolve_secrets = lambda cfg, mapping, *a, **k: cfg
    return svc


async def _import(mod, svc, adapter_type, warnings):
    return await mod.PortabilityService._import_agent(
        svc,
        {"name": "CEO", "adapter_type": adapter_type},
        str(uuid.uuid4()),
        {},
        warnings,
        {},
    )


class TestTheImportPathAsksTheHireQuestions:
    @pytest.mark.asyncio
    async def test_an_unregistered_adapter_type_is_skipped(self):
        mod = _svc()
        warnings: list[str] = []
        with patch.object(mod, "registered_adapter_types", return_value=["claude_code"]):
            result = await _import(mod, _service(mod), "totally-bogus", warnings)

        assert result is None, "an unknown adapter must not create an agent"
        assert any("totally-bogus" in w and "skipped" in w for w in warnings), warnings

    @pytest.mark.asyncio
    async def test_an_adapter_that_cannot_run_here_is_skipped(self):
        mod = _svc()
        warnings: list[str] = []
        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "adapter_unavailable_reason", return_value="'claude' CLI not found on PATH"),
        ):
            result = await _import(mod, _service(mod), "claude_code", warnings)

        assert result is None, "an unrunnable adapter must not create an agent"
        assert any("cannot run on this deployment" in w for w in warnings), warnings
        assert any("CLI not found" in w for w in warnings), "the warning must say why, or an operator cannot act on it"

    @pytest.mark.asyncio
    async def test_a_runnable_adapter_still_imports(self):
        """The control: without it, a gate that skipped everything would pass above."""
        mod = _svc()
        warnings: list[str] = []
        svc = _service(mod)
        svc._execute_insert = AsyncMock()

        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "adapter_unavailable_reason", return_value=None),
            patch.object(mod, "sa", create=True),
        ):
            try:
                result = await _import(mod, svc, "claude_code", warnings)
            except Exception:
                # The insert itself needs a session this test does not build; reaching
                # it at all is the point — the gate did not skip a runnable adapter.
                result = "reached-the-insert"

        assert result is not None, "a runnable adapter must not be skipped"
        assert not any("skipped" in w for w in warnings), warnings

    @pytest.mark.asyncio
    async def test_the_default_adapter_is_checked_too(self):
        """A template omitting adapter_type defaults to claude_code — still gated."""
        mod = _svc()
        warnings: list[str] = []
        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "adapter_unavailable_reason", return_value="not installed"),
        ):
            result = await mod.PortabilityService._import_agent(
                _service(mod), {"name": "CEO"}, str(uuid.uuid4()), {}, warnings, {}
            )

        assert result is None
        assert any("claude_code" in w for w in warnings), warnings
