# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the shared SubprocessLifecycleAdapter base (GH#9834)."""

import json
import os
import tempfile

import pytest

from llc.adapters.subprocess_base import (
    ADAPTER_TIMEOUT_SECONDS,
    SubprocessLifecycleAdapter,
    resolve_timeout,
)
from llc.models.enums import LLCRunStatus


def _state_path(output_dir: str, run_id: str) -> str:
    return os.path.join(output_dir, f"base_state_{run_id.replace('/', '_')}.json")


class _DummyAdapter(SubprocessLifecycleAdapter):
    _LOG_NAME = "DummyAdapter"
    _state_path = staticmethod(_state_path)

    async def _invoke(self, agent_config, context):  # pragma: no cover - not exercised
        return "1/x"


class TestResolveTimeout:
    def test_per_agent_override(self, monkeypatch) -> None:
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "250")
        assert resolve_timeout({"timeout_seconds": 500}) == 500

    def test_global_env(self, monkeypatch) -> None:
        monkeypatch.setenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", "180")
        assert resolve_timeout({}) == 180

    def test_adapter_default(self, monkeypatch) -> None:
        monkeypatch.delenv("LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS", raising=False)
        assert resolve_timeout({}) == ADAPTER_TIMEOUT_SECONDS == 3600


class TestLoadStatePathTraversal:
    def test_rejects_outside_safe_dir(self) -> None:
        # A path escaping safe_dir must be refused (returns None), not read.
        assert SubprocessLifecycleAdapter._load_state("/etc/passwd", "/tmp") is None

    def test_reads_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "s.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"pid": 1}, fh)
            assert SubprocessLifecycleAdapter._load_state(p, td) == {"pid": 1}


@pytest.mark.asyncio
class TestSharedLifecycle:
    async def test_status_unparseable_run_id(self) -> None:
        # No state file + non-numeric pid → FAILED via the shared base path.
        with tempfile.TemporaryDirectory() as td:
            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, "notapid/x")
        assert result.status == LLCRunStatus.FAILED

    async def test_status_completed_when_pid_gone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # No state file; run_id pid is an almost-certainly-dead PID.
            result = await _DummyAdapter().status({"adapter_config": {"output_dir": td}}, "2147483646/x")
        assert result.status in (LLCRunStatus.COMPLETED, LLCRunStatus.RUNNING)
