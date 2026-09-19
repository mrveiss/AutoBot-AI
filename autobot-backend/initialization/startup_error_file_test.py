# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed critical startup still leaves the startup error file, written off the loop (#16250).

``initialize_critical_services`` used to write the file (GH#8947) inline in its
except path -- blocking I/O inside ``async def`` (#7444). It now runs
``persist_startup_error`` through ``asyncio.to_thread`` before re-raising, and a
failed write is logged rather than silently passed. Neither may mask the
original startup error.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from initialization import lifespan as lifespan_module
from initialization import startup_error_file


@pytest.fixture
def error_file(tmp_path, monkeypatch):
    target = tmp_path / "run" / "startup-error.json"
    monkeypatch.setattr(startup_error_file, "STARTUP_ERROR_FILE", target)
    return target


@pytest.fixture
def failing_startup(monkeypatch):
    """Make the first critical step raise, as a real startup failure would."""
    monkeypatch.setattr(lifespan_module, "update_app_state_multi", AsyncMock())
    monkeypatch.setattr(lifespan_module, "_check_env_drift", AsyncMock(side_effect=RuntimeError("boom")))


def test_persist_startup_error_records_the_error_type(error_file):
    startup_error_file.persist_startup_error("ValueError")

    record = json.loads(error_file.read_text(encoding="utf-8"))
    assert record["error_type"] == "ValueError"
    assert record["timestamp"]


@pytest.mark.asyncio
async def test_a_failed_startup_writes_the_file_then_re_raises(error_file, failing_startup):
    with pytest.raises(RuntimeError, match="boom"):
        await lifespan_module.initialize_critical_services(SimpleNamespace(state=SimpleNamespace()))

    written = await asyncio.to_thread(error_file.read_text, encoding="utf-8")
    assert json.loads(written)["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_and_never_masks_the_startup_error(failing_startup, monkeypatch):
    monkeypatch.setattr(lifespan_module, "persist_startup_error", MagicMock(side_effect=OSError("read-only")))
    warning = MagicMock()
    monkeypatch.setattr(lifespan_module.logger, "warning", warning)

    with pytest.raises(RuntimeError, match="boom"):
        await lifespan_module.initialize_critical_services(SimpleNamespace(state=SimpleNamespace()))

    assert "Startup error file not written" in warning.call_args.args[0]
