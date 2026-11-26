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
        "fields": {"when": datetime.date(2026, 1, 1)},
    }
    obs = _from_record(record)
    assert (obs["status"], obs["parent"]) == ("declared", {"kind": "service", "name": "backend"})
    assert obs["attrs"] == {"when": "2026-01-01"}
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
