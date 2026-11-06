# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The first-admin link status is reported through the system health aggregator (#10200)."""

import pytest

pytest.importorskip("fastapi")

from api.system_health import _PROBES, KnownProbes  # noqa: E402
from user_management.services import person_link_service as link  # noqa: E402
from user_management.services import person_link_service as probe


@pytest.mark.parametrize(
    "status, expected",
    [
        (link.LINK_OK, "ok"),
        (link.LINK_KEY_MISSING, "down"),
        (link.LINK_REFUSED, "down"),
        (link.LINK_FAILED, "degraded"),
        (None, "idle"),
        ("something_new", "degraded"),
    ],
)
def test_status_maps_to_health(status, expected):
    assert probe._status_for(status)[0] == expected


def test_error_states_carry_a_message():
    for status in (link.LINK_KEY_MISSING, link.LINK_REFUSED, link.LINK_FAILED):
        assert probe._status_for(status)[1]


def test_probe_is_registered_in_the_aggregator():
    assert _PROBES[KnownProbes.FIRST_ADMIN_LINK] is probe.probe_first_admin_link


@pytest.mark.asyncio
async def test_probe_reads_last_link_status(monkeypatch):
    monkeypatch.setattr(link, "last_link_status", link.LINK_REFUSED)
    result = await probe.probe_first_admin_link(None)
    assert result.status == "down"
    assert result.data == {"link_status": link.LINK_REFUSED}
