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


@pytest.mark.asyncio
async def test_the_node_id_lookup_answers_with_the_stores_own_host_mapping_and_bounds_the_request():
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException

    from api import self_model

    with patch.object(self_model, "node_ids_by_host", AsyncMock(return_value={"10.0.0.5": "n1"})) as store:
        assert await self_model.node_ids(db=None, _={}, hosts="10.0.0.5, 10.0.0.9,") == {"10.0.0.5": "n1"}
        store.assert_awaited_once_with(None, {"10.0.0.5", "10.0.0.9"})
        too_many = ",".join(f"h{i}" for i in range(self_model.MAX_HOSTS + 1))
        with pytest.raises(HTTPException) as refused:
            await self_model.node_ids(db=None, _={}, hosts=too_many)
    assert refused.value.status_code == 422
