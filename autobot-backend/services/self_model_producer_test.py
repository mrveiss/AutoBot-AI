# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend producers of the self-model push declared and probed observations (#22277)."""

import datetime

from services.self_model_producer import _from_record, _service_observations, health_observations


def test_catalogue_records_are_declared_under_their_serving_service():
    record = {
        "kind": "tool",
        "name": "web_fetch",
        "serving_service": "backend",
        "node_id": "10.0.0.5",
        "fields": {"when": datetime.date(2026, 1, 1)},
    }
    obs = _from_record(record)
    assert (obs["status"], obs["parent"]) == ("declared", {"kind": "service", "name": "backend"})
    assert obs["attrs"] == {"when": "2026-01-01"}
    assert obs["node_id"] == "10.0.0.5"  # the serving service's SSOT host, which the SLM maps to its node id
    assert _service_observations([record, record]) == [{"kind": "service", "name": "backend", "status": "declared"}]


def test_health_snapshot_maps_to_probed_or_declared():
    snapshot = {
        "a": {"status": "healthy"},
        "b": {"status": "unhealthy"},
        "c": {"status": "unknown"},
    }
    assert {o["name"]: o["status"] for o in health_observations(snapshot)} == {
        "a": "probed_ok",
        "b": "probed_failed",
        "c": "declared",
    }


async def test_event_published_only_when_the_revision_moves(monkeypatch):
    from events.event_types import SELF_MODEL_CHANGED
    from services import self_model_producer as producer

    published = []

    async def fake_publish(channel, event_type, payload, *, persist):
        published.append((event_type, payload))

    monkeypatch.setattr(producer, "publish_event", fake_publish)
    monkeypatch.setattr(producer, "_last_revision", None)
    for revision in (3, 3, 5):
        await producer._announce_if_changed({"revision": revision})
    assert published == [(SELF_MODEL_CHANGED, {"revision": 5})]


def _agent_obs(name):
    return {"kind": "agent", "name": name, "status": "declared", "attrs": {}}


def test_audit_verdicts_feed_agent_observations_and_leave_the_rest_declared():
    """#22271: an error finding fails the agent, a clean audited agent is probed_ok, an unaudited one stays declared."""
    from services.self_model_producer import apply_audit

    error = {"agent_id": "bad", "severity": "error", "code": "manifest_overlap", "message": "x"}
    warning = {"agent_id": "warn", "severity": "warning", "code": "duplicate_entries", "message": "y"}
    report = {"audited_agents": ["bad", "good", "warn"], "findings": [error, warning]}
    tool = {"kind": "tool", "name": "bad", "status": "declared", "attrs": {}}
    out = apply_audit([_agent_obs(n) for n in ("bad", "good", "warn", "other")] + [tool], report)
    by_name = {(o["kind"], o["name"]): o for o in out}
    assert by_name[("agent", "bad")]["status"] == "probed_failed"
    assert by_name[("agent", "bad")]["attrs"]["audit"] == [error]
    assert by_name[("agent", "good")]["status"] == "probed_ok"
    assert by_name[("agent", "warn")]["status"] == "probed_ok"
    assert by_name[("agent", "warn")]["attrs"]["audit"] == [warning]
    assert by_name[("agent", "other")]["status"] == "declared"
    assert by_name[("tool", "bad")]["status"] == "declared"


def test_the_real_audit_report_names_the_agents_it_covered():
    from orchestration.capability_audit import build_audit_report

    report = build_audit_report()
    assert report["agent_count"] == len(report["audited_agents"]) >= 4


def test_tool_records_send_requires_in_the_attrs():
    record = {"kind": "tool", "name": "t", "serving_service": "backend", "fields": {"requires": ["xdotool"]}}
    assert _from_record(record)["attrs"]["requires"] == ["xdotool"]


class _Provider:
    def __init__(self, names):
        self.names = names

    async def list_models(self):
        if self.names is None:
            raise RuntimeError("down")
        return self.names


class _Registry:
    providers = {"up": _Provider(["m1", "m1", "m2"]), "down": _Provider(["m3"]), "broken": _Provider(None)}

    async def health_check_all(self):
        return {"up": True, "down": False, "broken": True}

    def get_provider_by_name(self, name):
        return self.providers[name]

    def get_provider_facts(self):
        return {}


async def test_models_are_probed_by_their_providers_availability(monkeypatch):
    from services import self_model_models as models

    monkeypatch.setattr(models, "get_provider_registry", lambda: _Registry())
    out = await models.model_observations()
    assert [(o["name"], o["status"], o["parent"]["name"]) for o in out] == [
        ("m3", "probed_failed", "down"),
        ("m1", "probed_ok", "up"),
        ("m2", "probed_ok", "up"),
    ]
    assert out[1]["attrs"]["probe"] == "provider_availability" and out[1]["attrs"]["probed_at"]
