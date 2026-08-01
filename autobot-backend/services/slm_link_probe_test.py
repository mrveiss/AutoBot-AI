# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Control-link health probe (#12781).

The backend→SLM link fails closed and silently: after a few rejected handshakes
the client pins its reconnect backoff to the maximum and stops logging, so a
node that cannot reach the control plane looks identical to a healthy one. Both
of a node's reporting paths were down at once in #12781, which is why the
crash loop in #12777 never appeared in the GUI.

These tests pin that a broken link is now *reported* rather than merely logged,
and that the "given up" state is distinguished from "still retrying".
"""

import pytest

pytest.importorskip("fastapi")

from services.slm_link_probe import _PROBE_NAME, _status_for, probe_slm_link  # noqa: E402


def _state(**overrides) -> dict:
    base = {
        "initialized": True,
        "connected": False,
        "auth_failures": 0,
        "backoff_pinned": False,
        "slm_url": "http://control-plane:8000",
    }
    base.update(overrides)
    return base


class TestStatusMapping:
    def test_connected_link_is_healthy(self):
        assert _status_for(_state(connected=True))[0] == "ok"

    def test_pinned_backoff_is_down_not_degraded(self):
        """The state that persists until a restart — it must not read as transient."""
        status, detail = _status_for(_state(backoff_pinned=True, auth_failures=3))

        assert status == "down"
        assert "will not recover without a" in detail

    def test_retrying_link_is_degraded(self):
        """Still reconnecting is real but not yet terminal."""
        status, detail = _status_for(_state(auth_failures=1))

        assert status == "degraded"
        assert "reconnecting" in detail

    def test_uninitialized_client_is_down(self):
        """A node with no client at all cannot reach the control plane either."""
        status, detail = _status_for(_state(initialized=False))

        assert status == "down"
        assert "not initialized" in detail

    def test_down_detail_names_the_secret_mismatch(self):
        """The 403 cause in #12781 — surface the fix, not just the symptom."""
        _, detail = _status_for(_state(backoff_pinned=True))

        assert "AUTOBOT_JWT_SECRET" in detail
        assert "SLM_SECRET_KEY" in detail


class TestProbe:
    @pytest.mark.asyncio
    async def test_probe_reports_link_state(self, monkeypatch):
        monkeypatch.setattr(
            "services.slm_link_probe.slm_link_state",
            lambda: _state(backoff_pinned=True, auth_failures=3),
        )

        result = await probe_slm_link()

        assert result.name == _PROBE_NAME
        assert result.status == "down"
        assert result.data["auth_failures"] == 3

    @pytest.mark.asyncio
    async def test_healthy_path_validates_against_the_model(self, monkeypatch):
        """Every branch must build a real ComponentHealth, not just the failing one.

        HealthStatus is Literal["ok", "degraded", "down", ...] — there is no
        "healthy". Testing only the down path let an invalid literal through
        that would have raised a ValidationError on the first healthy node.
        """
        monkeypatch.setattr("services.slm_link_probe.slm_link_state", lambda: _state(connected=True))

        result = await probe_slm_link()

        assert result.status == "ok"
        assert result.detail is None

    @pytest.mark.asyncio
    async def test_degraded_path_validates_against_the_model(self, monkeypatch):
        monkeypatch.setattr("services.slm_link_probe.slm_link_state", lambda: _state(auth_failures=1))

        assert (await probe_slm_link()).status == "degraded"

    @pytest.mark.asyncio
    async def test_probe_never_raises(self, monkeypatch):
        """A probe that raises would take the whole health response with it."""

        def _boom():
            raise RuntimeError("client exploded")

        monkeypatch.setattr("services.slm_link_probe.slm_link_state", _boom)

        result = await probe_slm_link()

        assert result.status == "down"
        assert "RuntimeError" in result.detail

    def test_probe_is_registered_under_a_known_name(self):
        """A typo'd probe name silently drops the component from /health."""
        from api.system_health import _PROBES, KnownProbes

        assert KnownProbes.SLM_LINK in _PROBES


def test_probe_is_imported_during_slm_init():
    """The decorator only fires on import — an unimported probe is dead code.

    It must also be imported BEFORE the connect attempt: a node whose SLM init
    raises is exactly the node whose link state has to be reported.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "initialization" / "lifespan.py").read_text(encoding="utf-8")
    body = source.split("async def _init_slm_client()")[1]
    import_pos = body.index("from services import slm_link_probe")
    try_pos = body.index("    try:")

    assert import_pos < try_pos, "probe import must precede the try block, not sit inside it"
