# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A role whose ``systemd_service`` is not a unit name fails removal cleanly, never as an unhandled error (#19005).

``_run_role_removal`` passes ``Role.systemd_service`` to ``remove-role.yml`` as an extra var. The
playbook executor refuses a non-unit-name (ValueError) before spawning; the function must turn that
into its own failed-removal shape, ``{"success": False, "output": ...}``, which the route already maps
to its handled "Role removal failed" answer, instead of letting the ValueError escape.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import SLM_ROOT, import_modules_with_real_orm  # noqa: E402

_codestatus, _nodes = import_modules_with_real_orm(
    import_names=("api.nodes",),
    path_loaded={"services.code_status": SLM_ROOT / "services" / "code_status.py"},
)

from services.unit_names import validate_unit_extra_vars  # noqa: E402


def _executor():
    """An executor whose ``execute_playbook`` applies the real sink validator, then 'runs'."""
    ran = AsyncMock(return_value={"success": True, "output": "ok"})

    async def _execute(playbook_name, limit=None, extra_vars=None, **_kw):
        validate_unit_extra_vars(extra_vars)
        return await ran(playbook_name, limit=limit, extra_vars=extra_vars)

    return type("Ex", (), {"execute_playbook": staticmethod(_execute), "ran": ran})()


def _remove(service_name: str, executor):
    with (
        patch("services.playbook_executor.get_playbook_executor", return_value=executor),
        patch.object(asyncio, "create_subprocess_exec", new=AsyncMock()) as spawn,
    ):
        result = asyncio.run(_nodes._run_role_removal("n1", "redis", service_name, False, "/opt/x/y"))
    return result, spawn


@pytest.mark.parametrize("name", ["{{ lookup('pipe', 'id') }}", "a b", "a;b", "../x", "rédis", "x" * 300])
def test_a_hostile_systemd_service_is_a_failed_removal_not_an_exception(name, caplog):
    executor = _executor()

    with caplog.at_level("WARNING"):
        result, spawn = _remove(name, executor)

    assert result["success"] is False
    assert "output" in result
    executor.ran.assert_not_awaited()
    spawn.assert_not_awaited()
    (record,) = [r for r in caplog.records if "Role removal refused" in r.getMessage()]
    assert "redis" in record.getMessage()
    assert len(record.getMessage()) < 200


def test_a_valid_systemd_service_still_runs_the_removal():
    executor = _executor()

    result, _spawn = _remove("redis-stack-server", executor)

    assert result["success"] is True
    executor.ran.assert_awaited_once()
