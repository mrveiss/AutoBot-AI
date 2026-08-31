# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TelemetryPromptMiddleware actually loads AND actually fires (#14280).

Before this fix, `telemetry-prompt-middleware` shipped a `plugin.json` next
to a class that subclassed `middleware.base.Extension`, not
`autobot_shared.plugin_sdk.base.BasePlugin`. `PluginLoader` discovered the
manifest and logged "No plugin class found in module" on every startup — the
middleware never ran, and nothing in the test suite exercised the real
registration path against the real class.

There was a SECOND, deeper defect once the class question is fixed:
`_init_builtin_extensions` registered every built-in extension (including
PermissionEnforcement and SecretMasking) onto a brand-new `ExtensionManager()`
stored only on `app.state.extension_manager` — an object no hook-invocation
call site (`chat_workflow.llm_handler`, `chat_workflow.session_handler`)
ever reads; every real call site uses the module-level
`middleware.manager.get_extension_manager()` singleton instead. Registering a
now-correctly-classified `TelemetryPromptMiddleware` onto the wrong manager
would have reproduced the exact "full surface, no sink" bug one layer down.

These tests exercise the REAL registration function
(`initialization.lifespan._init_builtin_extensions`) and the REAL sink
(`chat_workflow.llm_handler._emit_full_prompt_ready`, which fires on
`HookPoint.FULL_PROMPT_READY`) end to end — no hand-built extension manager
stub.

PR #14414 review: fixing the sink means `SecretMaskingExtension` and
`LoggingExtension` — previously registered onto the same orphaned manager —
now ALSO actually fire for the first time. `SecretMaskingExtension` has no
raise-based path (unlike `PermissionEnforcementExtension`, see #14420) —
`invoke_with_transform` applies its return value directly — so this is
genuinely new, user-visible behaviour: any LLM response or tool result
matching one of its ~12 regexes gets rewritten with `****`.
`test_after_llm_response_sink_masks_a_secret_through_the_real_dispatch_path`
below is the regression test for that, driven through the real
`get_extension_manager()` and `_emit_after_llm_response` — not by calling
`SecretMaskingExtension.mask_secrets()` directly, since the bug this PR fixes
was entirely in dispatch, not in the extension.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from middleware.builtin.telemetry_prompt_middleware import TelemetryPromptMiddleware
from middleware.manager import get_extension_manager, reset_extension_manager


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_extension_manager()
    yield
    reset_extension_manager()


@pytest.fixture
def app():
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.asyncio
async def test_init_builtin_extensions_registers_telemetry_on_the_live_singleton(app):
    """The real registration function must put the extension where the real
    hook call sites actually look — the process-wide singleton, not a
    throwaway instance parked on app.state."""
    from initialization.lifespan import _init_builtin_extensions

    await _init_builtin_extensions(app)

    registered = get_extension_manager().get_extension("telemetry_prompt_middleware")
    assert isinstance(registered, TelemetryPromptMiddleware)
    # app.state.extension_manager must be an ALIAS for the same singleton —
    # the original defect was exactly that these two were different objects.
    assert app.state.extension_manager is get_extension_manager()


@pytest.mark.asyncio
async def test_init_builtin_extensions_also_wires_the_other_builtins_to_the_same_manager(app):
    """Guards the regression this fix also closes: PermissionEnforcement and
    SecretMasking were registered onto the same orphaned manager as
    telemetry — fixing telemetry's sink without fixing theirs would just move
    the bug, not close it."""
    from initialization.lifespan import _init_builtin_extensions

    await _init_builtin_extensions(app)

    manager = get_extension_manager()
    assert manager.get_extension("permission_enforcement") is not None
    assert manager.get_extension("secret_masking") is not None
    assert manager.get_extension("logging") is not None


@pytest.mark.asyncio
async def test_full_prompt_ready_sink_appends_the_hint_under_high_cpu(app, monkeypatch):
    """End-to-end through the REAL sink: registration -> ExtensionManager ->
    HookPoint.FULL_PROMPT_READY -> _emit_full_prompt_ready."""
    from chat_workflow.llm_handler import _emit_full_prompt_ready
    from initialization.lifespan import _init_builtin_extensions

    monkeypatch.setattr(
        TelemetryPromptMiddleware,
        "_fetch_cpu_percent",
        AsyncMock(return_value=95.0),
    )

    await _init_builtin_extensions(app)

    prompt = "Summarise the incident."
    result = await _emit_full_prompt_ready(prompt, llm_params={}, context={"session_id": "s1"})

    assert result != prompt
    assert "keep your response concise" in result


@pytest.mark.asyncio
async def test_full_prompt_ready_sink_is_a_no_op_under_low_cpu(app, monkeypatch):
    from chat_workflow.llm_handler import _emit_full_prompt_ready
    from initialization.lifespan import _init_builtin_extensions

    monkeypatch.setattr(
        TelemetryPromptMiddleware,
        "_fetch_cpu_percent",
        AsyncMock(return_value=5.0),
    )

    await _init_builtin_extensions(app)

    prompt = "Summarise the incident."
    result = await _emit_full_prompt_ready(prompt, llm_params={}, context={"session_id": "s1"})

    assert result == prompt


@pytest.mark.asyncio
async def test_after_llm_response_sink_masks_a_secret_through_the_real_dispatch_path(app):
    """SecretMaskingExtension now actually fires (PR #14414 review finding).

    Driven end to end through the real registration function and the real
    `AFTER_LLM_RESPONSE` sink (`chat_workflow.llm_handler._emit_after_llm_response`
    -> `get_extension_manager().invoke_with_transform`) — never by calling
    `SecretMaskingExtension.mask_secrets()` directly. The bug #14414 fixes was
    entirely in dispatch (registration onto a manager nothing read), so the
    regression test has to exercise dispatch, not the extension in isolation.
    """
    from chat_workflow.llm_handler import _emit_after_llm_response
    from initialization.lifespan import _init_builtin_extensions

    await _init_builtin_extensions(app)

    response = "Sure — your token: abcdefghij1234567890 should work for that request."
    result = await _emit_after_llm_response(response, llm_params={}, session_id="s1")

    assert result != response
    assert "abcdefghij1234567890" not in result
    assert "****" in result


@pytest.mark.asyncio
async def test_after_llm_response_sink_is_a_no_op_without_a_secret(app):
    """Guards against a masking regression that rewrites everything, not just secrets."""
    from chat_workflow.llm_handler import _emit_after_llm_response
    from initialization.lifespan import _init_builtin_extensions

    await _init_builtin_extensions(app)

    response = "The deployment finished successfully with no errors."
    result = await _emit_after_llm_response(response, llm_params={}, session_id="s1")

    assert result == response
