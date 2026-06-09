# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLC adapter protocol, ProcessAdapter, HttpAdapter, and registry (GH#8226)."""

import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters import AdapterRunStatus, get_adapter, register_adapter
from llc.adapters.base import LLCAdapter
from llc.adapters.http_adapter import HttpAdapter
from llc.adapters.process_adapter import ProcessAdapter
from llc.models.enums import LLCRunStatus

# ---------------------------------------------------------------------------
# Base / protocol
# ---------------------------------------------------------------------------


class TestLLCAdapterProtocol:
    def test_process_adapter_satisfies_protocol(self) -> None:
        assert isinstance(ProcessAdapter(), LLCAdapter)

    def test_http_adapter_satisfies_protocol(self) -> None:
        assert isinstance(HttpAdapter(), LLCAdapter)


# ---------------------------------------------------------------------------
# AdapterRunStatus
# ---------------------------------------------------------------------------


class TestAdapterRunStatus:
    def test_defaults(self) -> None:
        s = AdapterRunStatus(status=LLCRunStatus.RUNNING)
        assert s.exit_code is None
        assert s.error is None

    def test_with_exit_code(self) -> None:
        s = AdapterRunStatus(status=LLCRunStatus.COMPLETED, exit_code=0)
        assert s.exit_code == 0

    def test_with_error(self) -> None:
        s = AdapterRunStatus(status=LLCRunStatus.FAILED, error="OOM")
        assert s.error == "OOM"

    def test_all_status_values(self) -> None:
        for val in ("running", "completed", "failed", "timeout", "cancelled"):
            assert LLCRunStatus(val) is not None


# ---------------------------------------------------------------------------
# ProcessAdapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProcessAdapter:
    async def test_invoke_returns_pid_string(self) -> None:
        adapter = ProcessAdapter()
        fake_proc = MagicMock()
        fake_proc.pid = 12345

        with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=fake_proc):
            run_id = await adapter.invoke({"command": "echo hello"}, {"key": "value"})

        assert run_id == "12345"

    async def test_invoke_passes_context_as_env(self) -> None:
        adapter = ProcessAdapter()
        fake_proc = MagicMock()
        fake_proc.pid = 99

        captured_env: dict = {}

        async def mock_shell(cmd, *, env, cwd):
            captured_env.update(env)
            return fake_proc

        with patch("asyncio.create_subprocess_shell", side_effect=mock_shell):
            await adapter.invoke({"command": "x"}, {"task_id": "t1"})

        import json

        ctx = json.loads(captured_env["LLC_INVOKE_CONTEXT"])
        assert ctx["task_id"] == "t1"

    async def test_status_running_when_pid_alive(self) -> None:
        adapter = ProcessAdapter()
        with patch("os.kill", return_value=None):  # signal 0 succeeds → process alive
            result = await adapter.status({}, "12345")
        assert result.status is LLCRunStatus.RUNNING

    async def test_status_completed_when_pid_gone(self) -> None:
        adapter = ProcessAdapter()

        def _raise(*_):
            raise ProcessLookupError

        with patch("os.kill", side_effect=_raise):
            result = await adapter.status({}, "99999")
        assert result.status is LLCRunStatus.COMPLETED

    async def test_status_failed_on_oserror(self) -> None:
        adapter = ProcessAdapter()
        with patch("os.kill", side_effect=OSError("bad")):
            result = await adapter.status({}, "12345")
        assert result.status is LLCRunStatus.FAILED
        assert "bad" in (result.error or "")

    async def test_status_failed_on_invalid_pid(self) -> None:
        adapter = ProcessAdapter()
        result = await adapter.status({}, "abc")
        assert result.status is LLCRunStatus.FAILED
        assert result.error is not None

    async def test_cancel_sends_sigterm(self) -> None:
        adapter = ProcessAdapter()
        killed = []

        sent_sigterm = [False]

        def smart_kill(pid, sig):
            killed.append((pid, sig))
            if sig == signal.SIGTERM:
                sent_sigterm[0] = True
            elif sig == 0:
                if sent_sigterm[0]:
                    raise ProcessLookupError  # process gone after SIGTERM

        with patch("os.kill", side_effect=smart_kill):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await adapter.cancel({}, "12345")

        assert any(s == signal.SIGTERM for _, s in killed)

    async def test_cancel_noop_when_pid_gone(self) -> None:
        adapter = ProcessAdapter()

        def _raise(pid, sig):
            raise ProcessLookupError

        with patch("os.kill", side_effect=_raise):
            await adapter.cancel({}, "99999")  # should not raise


# ---------------------------------------------------------------------------
# HttpAdapter
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status = status_code
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(responses: list) -> MagicMock:
    """Build a mock aiohttp session that returns each response in sequence."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.request = MagicMock(side_effect=responses)
    session.get = MagicMock(side_effect=responses)
    session.post = MagicMock(side_effect=responses)
    return session


@pytest.mark.asyncio
class TestHttpAdapter:
    async def test_invoke_returns_run_id(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {"run_id": "abc-123"})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            run_id = await adapter.invoke({"url": "http://agent.local"}, {"task": "t1"})

        assert run_id == "abc-123"

    async def test_invoke_with_payload_template(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {"run_id": "x"})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            run_id = await adapter.invoke(
                {
                    "url": "http://agent.local",
                    "payload_template": '{{"task_id": "{task_id}"}}',
                },
                {"task_id": "t42"},
            )

        assert run_id == "x"

    async def test_status_maps_running(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {"status": "running"})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            result = await adapter.status({"url": "http://agent.local"}, "r1")

        assert result.status is LLCRunStatus.RUNNING

    async def test_status_maps_completed(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {"status": "completed", "exit_code": 0})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            result = await adapter.status({"url": "http://agent.local"}, "r1")

        assert result.status is LLCRunStatus.COMPLETED
        assert result.exit_code == 0

    async def test_status_maps_remote_succeeded_to_completed(self) -> None:
        # Remote may return "succeeded" (old vocab) — maps to COMPLETED.
        adapter = HttpAdapter()
        resp = _mock_response(200, {"status": "succeeded", "exit_code": 0})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            result = await adapter.status({"url": "http://agent.local"}, "r1")

        assert result.status is LLCRunStatus.COMPLETED

    async def test_status_404_returns_failed(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(404, {})
        resp.raise_for_status = MagicMock()

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            result = await adapter.status({"url": "http://agent.local"}, "gone")

        assert result.status is LLCRunStatus.FAILED
        assert "not found" in (result.error or "")

    async def test_status_unknown_value_maps_to_failed(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {"status": "weird_value"})

        with patch("aiohttp.ClientSession", return_value=_mock_session([resp])):
            result = await adapter.status({"url": "http://agent.local"}, "r2")

        assert result.status is LLCRunStatus.FAILED

    async def test_cancel_posts_to_cancel_endpoint(self) -> None:
        adapter = HttpAdapter()
        resp = _mock_response(200, {})

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        cancel_ctx = MagicMock()
        cancel_ctx.__aenter__ = AsyncMock(return_value=resp)
        cancel_ctx.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=cancel_ctx)

        with patch("aiohttp.ClientSession", return_value=session):
            await adapter.cancel({"url": "http://agent.local"}, "r3")

        session.post.assert_called_once()
        called_url = session.post.call_args[0][0]
        assert called_url.endswith("/cancel/r3")


# ---------------------------------------------------------------------------
# Registry (register_adapter / get_adapter)
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_unknown_type_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="no_such_adapter"):
            get_adapter("no_such_adapter")

    def test_register_and_retrieve_custom_adapter(self) -> None:
        class FakeAdapter:
            async def invoke(self, agent_config: dict, context: dict) -> str:
                return "fake-run"

            async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
                return AdapterRunStatus(status=LLCRunStatus.COMPLETED)

            async def cancel(self, agent_config: dict, run_id: str) -> None:
                pass

        register_adapter("fake_test", FakeAdapter())
        retrieved = get_adapter("fake_test")
        assert isinstance(retrieved, FakeAdapter)
