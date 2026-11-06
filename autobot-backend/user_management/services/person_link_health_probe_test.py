# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The first-admin link status is reported through the system health aggregator (#10200)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from api.system_health import _PROBES, KnownProbes  # noqa: E402
from services import first_admin_link_probe as probe  # noqa: E402
from user_management.services import person_link_service as link  # noqa: E402


@pytest.mark.parametrize(
    "status, expected",
    [
        (link.LINK_OK, "ok"),
        (link.LINK_KEY_MISSING, "down"),
        (link.LINK_REFUSED, "down"),
        (link.LINK_FAILED, "degraded"),
        (link.LINK_NO_HASH, "degraded"),
        (None, "idle"),
        ("something_new", "degraded"),
    ],
)
def test_status_maps_to_health(status, expected):
    assert probe._status_for(status)[0] == expected


def test_error_states_carry_a_message():
    for status in (link.LINK_KEY_MISSING, link.LINK_REFUSED, link.LINK_FAILED, link.LINK_NO_HASH):
        assert probe._status_for(status)[1]


def test_importing_the_service_registers_nothing():
    """No import side effect: a fresh interpreter importing the module leaves the registry empty."""
    code = (
        "from api.system_health import _PROBES, KnownProbes\n"
        "import user_management.services.person_link_service\n"
        "assert KnownProbes.FIRST_ADMIN_LINK not in _PROBES"
    )
    subprocess.run(
        [sys.executable, "-c", code], check=True, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    )


def test_probe_is_registered_once_the_module_is_imported():
    assert _PROBES[KnownProbes.FIRST_ADMIN_LINK] is probe.probe_first_admin_link


def test_lifespan_imports_the_probe_module():
    source = (Path(__file__).resolve().parents[2] / "initialization" / "lifespan.py").read_text(encoding="utf-8")
    assert "from services import first_admin_link_probe" in source
    assert "register_first_admin_link_probe" not in source


@pytest.mark.asyncio
async def test_probe_reads_last_link_status(monkeypatch):
    monkeypatch.setattr(link, "last_link_status", link.LINK_REFUSED)
    result = await probe.probe_first_admin_link(None)
    assert result.status == "down"
    assert result.data == {"link_status": link.LINK_REFUSED}
