# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The self-model write endpoint takes only the backend's service identity and a known source (#22277)."""

import pytest
from pydantic import ValidationError

from api.self_model import ObservationBatch, router
from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.self_model_constants import PRODUCER_SOURCES


def _batch(source: str) -> dict:
    return {"source": source, "scope_kinds": ["service"], "observations": []}


def test_the_observation_endpoint_requires_the_internal_service_key():
    route = next(r for r in router.routes if r.path.endswith("/observations"))
    assert any(dep.call is require_internal_api_key for dep in route.dependant.dependencies)


@pytest.mark.parametrize("source", PRODUCER_SOURCES)
def test_a_known_producer_source_is_accepted(source):
    assert ObservationBatch(**_batch(source)).source == source


@pytest.mark.parametrize("source", ["node_agent", "backend_catalogue ", "x"])
def test_an_unknown_source_is_refused(source):
    with pytest.raises(ValidationError):
        ObservationBatch(**_batch(source))


def test_a_version_the_column_cannot_hold_is_refused_before_any_write():
    item = {"kind": "tool", "name": "git", "status": "declared"}
    with pytest.raises(ValidationError):
        ObservationBatch(**{**_batch("backend_catalogue"), "observations": [{**item, "version": "v" * 129}]})
    ok = ObservationBatch(**{**_batch("backend_catalogue"), "observations": [{**item, "version": "v" * 128}]})
    assert len(ok.observations[0].version) == 128


@pytest.mark.parametrize(
    ("push_s", "stale_s", "expected"),
    [(40, 90.0, 40), (45, 90.0, 45), (60, 90.0, 45), (90, 90.0, 45), (3600, 30.0, 15)],
)
def test_the_push_interval_must_stay_within_half_the_stale_window(push_s, stale_s, expected):
    from autobot_shared.self_model_constants import coherent_push_interval

    assert coherent_push_interval(push_s, stale_s) == expected
