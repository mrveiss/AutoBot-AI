# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for vnc_mcp async correctness (#10785).

Verifies that desktop_screenshot_mcp and desktop_observe_state_mcp are async
functions, and that subprocess.run is dispatched via asyncio.to_thread (not
called directly in the event loop), preventing event-loop blocking.

Note: scrot/import/xdpyinfo/xdotool are not available in CI (no X display),
so these tests mock subprocess.run via asyncio.to_thread and verify the
dispatch path rather than end-to-end screenshot behaviour.

Import strategy: use importlib.util.spec_from_file_location to load
api/vnc_mcp.py directly by file path, which avoids triggering the real
`services/__init__.py` chain and its deep dependency tree. All third-party
and internal modules are stubbed in sys.modules before the load.
"""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path to the module under test
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent
_VNC_MCP_PATH = _BACKEND_ROOT / "api" / "vnc_mcp.py"


# ---------------------------------------------------------------------------
# sys.modules surgery: stub every import that vnc_mcp.py pulls in at
# module-load time so we can load the file in isolation.
# ---------------------------------------------------------------------------


def _make_mod(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _install_stubs() -> dict:
    """Install stubs and return original values for teardown."""
    saved = {}

    def _stub(name: str, **attrs):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = _make_mod(name, **attrs)

    # aiohttp
    _stub("aiohttp", ClientSession=MagicMock, ClientTimeout=MagicMock)

    # fastapi — APIRouter.post/get/... must be identity decorators so that
    # @router.post(...) preserves the original async function rather than
    # replacing it with a MagicMock return value.
    class _IdentityRouter:
        def __init__(self, **kw):
            pass

        def _identity_decorator(self, *a, **kw):
            def decorator(fn):
                return fn

            return decorator

        post = get = put = delete = patch = _identity_decorator

    _stub("fastapi", APIRouter=_IdentityRouter, Depends=MagicMock, HTTPException=Exception)

    # services (top-level package only — prevent __init__ from running)
    _stub("services")

    # services.mcp_bridge_manifest
    class _FakeManifest:  # noqa: D101
        def __init__(self, **kw):
            pass

    _stub("services.mcp_bridge_manifest", MCPBridgeManifest=_FakeManifest)

    # api (top-level) — we load vnc_mcp.py directly via spec_from_file_location
    # so it does NOT require api to be a real importable package.
    _stub("api")

    # api.vnc_manager — stub _run_xdotool_cmd so that the lazy imports inside
    # desktop_mouse_click_mcp / desktop_keyboard_type_mcp / desktop_special_key_mcp
    # resolve without needing the real module (which has its own heavy deps).
    def _run_xdotool_cmd(args, timeout=5):  # pragma: no cover
        return {"status": "success", "message": "Action completed"}

    _stub("api.vnc_manager", _run_xdotool_cmd=_run_xdotool_cmd)

    # api.schemas_system — exact names imported by vnc_mcp.py lines 28-45
    _schema_attrs = {
        n: MagicMock
        for n in (
            "BrowserVncContextResponse",
            "DesktopClickMcpResponse",
            "DesktopKeyboardTypeMcpResponse",
            "DesktopKeyboardTypeRequest",
            "DesktopMouseClickRequest",
            "DesktopObserveStateMcpResponse",
            "DesktopObserveStateRequest",
            "DesktopScreenshotMcpResponse",
            "DesktopSpecialKeyMcpResponse",
            "DesktopSpecialKeyRequest",
            "VncMCPTool",
            "VncObservationMcpResponse",
            "VNCObservationRequest",
            "VncRecordObservationResponse",
            "VncStatusMcpResponse",
            "VNCStatusRequest",
        )
    }
    _stub("api.schemas_system", **_schema_attrs)

    # auth_middleware
    _stub("auth_middleware", check_admin_permission=MagicMock())

    # autobot_shared and sub-modules
    _stub("autobot_shared")

    def _with_error_handling(**kw):
        def decorator(fn):
            return fn

        return decorator

    _err_cat = MagicMock()
    _err_cat.SERVER_ERROR = "SERVER_ERROR"
    _stub(
        "autobot_shared.error_boundaries",
        ErrorCategory=_err_cat,
        with_error_handling=_with_error_handling,
    )
    _stub("autobot_shared.http_client", get_http_client=MagicMock())
    _stub("autobot_shared.logging_manager", get_logger=lambda name: MagicMock())
    _stub("autobot_shared.time_utils", parse_utc_iso=MagicMock())
    _stub("autobot_shared.ssot_config", config=MagicMock())

    # constants and type_defs
    _stub("constants")
    nc = MagicMock()
    nc.VNC_HOST = "localhost"
    nc.VNC_PORT = 5900
    _stub("constants.network_constants", NetworkConstants=nc)
    _stub("type_defs")
    _stub("type_defs.common", Metadata=dict)

    return saved


def _restore_stubs(saved: dict) -> None:
    for name, orig in saved.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig


# ---------------------------------------------------------------------------
# Module-scoped fixture: load vnc_mcp once for the whole test session.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vnc_mcp_module():
    saved = _install_stubs()
    try:
        # Remove any cached copy so stubs take effect
        sys.modules.pop("api.vnc_mcp", None)

        spec = importlib.util.spec_from_file_location("api.vnc_mcp", str(_VNC_MCP_PATH))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["api.vnc_mcp"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("api.vnc_mcp", None)
        _restore_stubs(saved)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVncMcpAsyncFunctions:
    """Verify async-function signatures are preserved after the fix."""

    def test_desktop_screenshot_mcp_is_async(self, vnc_mcp_module):
        fn = vnc_mcp_module.desktop_screenshot_mcp
        assert inspect.iscoroutinefunction(
            fn
        ), "desktop_screenshot_mcp must be an async def (event-loop blocking fix #10785)"

    def test_desktop_observe_state_mcp_is_async(self, vnc_mcp_module):
        fn = vnc_mcp_module.desktop_observe_state_mcp
        assert inspect.iscoroutinefunction(
            fn
        ), "desktop_observe_state_mcp must be an async def (event-loop blocking fix #10785)"


class TestSubprocessDispatchedViaToThread:
    """
    Verify subprocess.run is dispatched through asyncio.to_thread, not called
    directly on the event loop.

    Strategy: patch asyncio.to_thread with an AsyncMock that returns a fake
    CompletedProcess, then invoke the async function and assert to_thread was
    called with subprocess.run as its first argument.

    Limitation: scrot/xdpyinfo/xdotool are unavailable in CI (no X display);
    the mocks prevent any real subprocess execution.
    """

    @pytest.mark.asyncio
    async def test_screenshot_scrot_uses_to_thread(self, vnc_mcp_module):
        """scrot invocation goes through asyncio.to_thread."""
        fake_fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_fail) as mock_tt:
            await vnc_mcp_module.desktop_screenshot_mcp()

        calls = mock_tt.call_args_list
        assert len(calls) >= 1, "asyncio.to_thread was never called"
        first_arg = calls[0].args[0]
        assert (
            first_arg is subprocess.run
        ), f"Expected asyncio.to_thread(subprocess.run, ...) but first arg was {first_arg!r}"
        argv = calls[0].args[1]
        assert argv[0] == "scrot", f"Expected 'scrot' as argv[0], got {argv[0]!r}"
        kw = calls[0].kwargs
        assert kw.get("capture_output") is True
        assert kw.get("text") is True
        assert kw.get("timeout") == 10
        assert kw.get("env") == {"DISPLAY": ":1"}

    @pytest.mark.asyncio
    async def test_screenshot_fallback_import_uses_to_thread(self, vnc_mcp_module):
        """When scrot returns rc=1, the 'import' fallback also uses to_thread."""
        fake_fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_fail) as mock_tt:
            await vnc_mcp_module.desktop_screenshot_mcp()

        calls = mock_tt.call_args_list
        assert len(calls) >= 2, f"Expected >= 2 asyncio.to_thread calls (scrot + import fallback), got {len(calls)}"
        fallback_argv = calls[1].args[1]
        assert fallback_argv[0] == "import", f"Expected 'import' as fallback argv[0], got {fallback_argv[0]!r}"
        kw = calls[1].kwargs
        assert kw.get("capture_output") is True
        assert kw.get("text") is True
        assert kw.get("timeout") == 10
        assert kw.get("env") == {"DISPLAY": ":1"}

    @pytest.mark.asyncio
    async def test_observe_state_xdpyinfo_uses_to_thread(self, vnc_mcp_module):
        """xdpyinfo call goes through asyncio.to_thread."""
        fake_ok = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="dimensions:  1920x1080 pixels\n", stderr=""
        )
        request_mock = MagicMock()
        request_mock.include_screenshot = False

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_ok) as mock_tt:
            await vnc_mcp_module.desktop_observe_state_mcp(request_mock)

        calls = mock_tt.call_args_list
        assert len(calls) >= 1, "asyncio.to_thread was never called"
        argv = calls[0].args[1]
        assert argv[0] == "xdpyinfo", f"Expected 'xdpyinfo', got {argv[0]!r}"
        kw = calls[0].kwargs
        assert kw.get("env") == {"DISPLAY": ":1"}
        assert kw.get("timeout") == 5

    @pytest.mark.asyncio
    async def test_observe_state_xdotool_uses_to_thread(self, vnc_mcp_module):
        """xdotool call goes through asyncio.to_thread."""
        fake_ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="My Window\n", stderr="")
        request_mock = MagicMock()
        request_mock.include_screenshot = False

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_ok) as mock_tt:
            await vnc_mcp_module.desktop_observe_state_mcp(request_mock)

        calls = mock_tt.call_args_list
        assert len(calls) >= 2, f"Expected >= 2 asyncio.to_thread calls (xdpyinfo + xdotool), got {len(calls)}"
        argv = calls[1].args[1]
        assert argv[0] == "xdotool", f"Expected 'xdotool', got {argv[0]!r}"
        kw = calls[1].kwargs
        assert kw.get("env") == {"DISPLAY": ":1"}
        assert kw.get("timeout") == 5


class TestXdotoolMcpDispatchedViaToThread:
    """
    Verify desktop_mouse_click_mcp, desktop_keyboard_type_mcp, and
    desktop_special_key_mcp dispatch _run_xdotool_cmd via asyncio.to_thread
    (#10783 Category B fix).
    """

    @pytest.mark.asyncio
    async def test_mouse_click_dispatches_via_to_thread(self, vnc_mcp_module):
        """desktop_mouse_click_mcp wraps _run_xdotool_cmd in asyncio.to_thread."""
        fake_result = {"status": "success", "message": "Action completed"}
        request_mock = MagicMock()
        request_mock.x = 100
        request_mock.y = 200
        request_mock.button = "left"

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt:
            result = await vnc_mcp_module.desktop_mouse_click_mcp(request_mock)

        assert mock_tt.called, "asyncio.to_thread was never called in desktop_mouse_click_mcp"
        assert result["success"] is True
        first_positional = mock_tt.call_args_list[0].args
        # First arg to to_thread must be the sync _run_xdotool_cmd function
        assert callable(first_positional[0]), "First arg to asyncio.to_thread must be callable (_run_xdotool_cmd)"
        assert first_positional[0].__name__ == "_run_xdotool_cmd"

    @pytest.mark.asyncio
    async def test_keyboard_type_dispatches_via_to_thread(self, vnc_mcp_module):
        """desktop_keyboard_type_mcp wraps _run_xdotool_cmd in asyncio.to_thread."""
        fake_result = {"status": "success", "message": "Action completed"}
        request_mock = MagicMock()
        request_mock.text = "hello world"

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt:
            result = await vnc_mcp_module.desktop_keyboard_type_mcp(request_mock)

        assert mock_tt.called, "asyncio.to_thread was never called in desktop_keyboard_type_mcp"
        assert result["success"] is True
        first_positional = mock_tt.call_args_list[0].args
        assert callable(first_positional[0]), "First arg to asyncio.to_thread must be callable (_run_xdotool_cmd)"
        assert first_positional[0].__name__ == "_run_xdotool_cmd"

    @pytest.mark.asyncio
    async def test_special_key_dispatches_via_to_thread(self, vnc_mcp_module):
        """desktop_special_key_mcp wraps _run_xdotool_cmd in asyncio.to_thread."""
        fake_result = {"status": "success", "message": "Action completed"}
        request_mock = MagicMock()
        request_mock.key = "Return"

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt:
            result = await vnc_mcp_module.desktop_special_key_mcp(request_mock)

        assert mock_tt.called, "asyncio.to_thread was never called in desktop_special_key_mcp"
        assert result["success"] is True
        first_positional = mock_tt.call_args_list[0].args
        assert callable(first_positional[0]), "First arg to asyncio.to_thread must be callable (_run_xdotool_cmd)"
        assert first_positional[0].__name__ == "_run_xdotool_cmd"
