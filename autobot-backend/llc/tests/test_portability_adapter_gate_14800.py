# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14800: the template import creates runnable agents, so it asks the hire questions.

`POST /companies/{id}/agent-hires` rejects an unregistered `adapter_type` and one
whose adapter cannot run here. `_import_agent` inserted straight into
`agent_org_nodes` with an `adapter_type` from a template and asked neither, so an
import could create an agent whose every heartbeat is skipped — the symptom both
hire-time checks exist to prevent, through a path with no checks at all.

The subtlety these pin: **only a declared `adapter_type` is checked.** A missing
one is not a `claude_code` agent. `heartbeat_scheduler` reads a missing value as
`autobot_agent`, which runs in-process, is deliberately absent from the registry,
and needs no CLI. Gating the omitted case against `claude_code` would spuriously
skip every ordinary in-process agent in a template re-imported onto a host without
that CLI — a regression on a normal round trip rather than a fix.
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import patch


def _svc() -> ModuleType:
    import llc.services.portability as mod

    return mod


def _gate(mod, declared, warnings):
    return mod.PortabilityService._adapter_runnable_or_warn("CEO", declared, warnings)


class TestOnlyADeclaredAdapterIsChecked:
    def test_an_omitted_adapter_type_is_never_skipped(self):
        """The regression guard: omitted means in-process, not claude_code.

        `autobot_agent` is not in the registry by design, so gating the omitted
        case against `registered_adapter_types()` would reject exactly the
        ordinary agent this import exists to carry.
        """
        mod = _svc()
        warnings: list[str] = []
        with patch.object(mod, "adapter_unavailable_reason") as probe:
            assert _gate(mod, None, warnings) is True
            assert _gate(mod, "", warnings) is True
        assert warnings == []
        probe.assert_not_called(), "an omitted type must not even be probed"

    def test_an_unregistered_adapter_type_is_skipped(self):
        mod = _svc()
        warnings: list[str] = []
        with patch.object(mod, "registered_adapter_types", return_value=["claude_code"]):
            assert _gate(mod, "totally-bogus", warnings) is False
        assert any("totally-bogus" in w and "skipped" in w for w in warnings), warnings

    def test_an_adapter_that_cannot_run_here_is_skipped(self):
        mod = _svc()
        warnings: list[str] = []
        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "adapter_unavailable_reason", return_value="'claude' CLI not found on PATH"),
        ):
            assert _gate(mod, "claude_code", warnings) is False
        assert any("cannot run on this deployment" in w for w in warnings), warnings
        assert any("CLI not found" in w for w in warnings), "the warning must say why, or an operator cannot act on it"

    def test_a_runnable_declared_adapter_passes(self):
        """The control: without it, a gate that refused everything would satisfy the rest."""
        mod = _svc()
        warnings: list[str] = []
        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "adapter_unavailable_reason", return_value=None),
        ):
            assert _gate(mod, "claude_code", warnings) is True
        assert warnings == []


class TestTheGateAndTheInsertAgree:
    def test_the_checked_value_is_the_value_that_gets_persisted(self):
        """They must read the same expression, or the check guards a different agent.

        The gate previously resolved `agent.get("adapter_type") or "claude_code"`
        while the INSERT bound the raw field, so an omitted type was checked as
        claude_code and written as NULL — which the scheduler then runs as
        `autobot_agent`, an adapter that was never checked.
        """
        import inspect

        mod = _svc()
        src = inspect.getsource(mod.PortabilityService._import_agent)
        gate_line = next(ln for ln in src.splitlines() if "_adapter_runnable_or_warn" in ln)
        insert_line = next(ln for ln in src.splitlines() if "adapter_type=" in ln)

        assert 'agent.get("adapter_type")' in gate_line, gate_line
        assert 'agent.get("adapter_type")' in insert_line, insert_line
        assert '"claude_code"' not in gate_line, "the gate must not resolve a default the INSERT does not also apply"
