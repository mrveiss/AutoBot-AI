# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every SDK response model must agree with the route it parses (#15072).

Pydantic's default ``extra='ignore'`` is the whole problem. ``models.py`` sets no
``model_config`` anywhere, so ``Model.model_validate(raw)`` discards a key the model
does not declare **in silence** -- not as an error, not as ``None``, not as an
``extra`` dict. A field the SDK forgot is therefore indistinguishable, from the
consumer's side, from a field the backend never sent. ``AgentConfig`` dropped
``mcp_tools``, ``config_source`` and ``health_check`` that way, and the only reason
anyone noticed was a code review.

Silence is the defect this guard removes. Whichever way a field resolves -- carried
by the SDK, or genuinely not part of the route -- a *future* divergence has to fail
something rather than vanish.

Both trees are importable in this run (``pytest.ini`` puts ``autobot-backend`` and
``libs/autobot-sdk-python`` on ``pythonpath``), so the comparison uses the real
``model_fields`` rather than a static parse: that picks up inherited fields, aliases
and anything a plain source scan would miss.

This is a *test-time* coupling only. The SDK still ships to PyPI depending on
``httpx`` and ``pydantic`` alone -- nothing imported here is imported by the SDK at
runtime (cf. #15053's note on ``sdk_defaults_match_ssot_test.py``).

Pairs that do not agree today are listed with an explicit waiver naming the issue
that tracks them, rather than omitted -- an omitted pair is exactly the silence this
file exists to end. Those issues are #15114 (SDK models requiring a field the route
never emits, which raises), #15116 (SDK parsing a ``DataResponse`` envelope out of a
flat route, so ``data`` is always ``None``) and #15118 (SDK naming fields the route
never emits, so the attribute is permanently ``None``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest
from autobot_sdk import models as sdk
from pydantic import BaseModel

from api.schemas_agent import (
    AgentConfigDetailHealthCheck,
    AgentConfigDetailOptions,
    AgentConfigDetailResponse,
    AgentHealthResponse,
)
from api.schemas_analytics import AnalyticsPerformanceMetricsResponse, AnalyticsUsageStatisticsResponse
from api.schemas_chat import (
    SessionCreateData,
    SessionDeleteData,
    SessionListData,
    SessionMessagesData,
    SessionUpdateData,
)
from knowledge.schemas.entries import KnowledgeEntriesResponse
from knowledge.schemas.entries import KnowledgeEntry as BackendKnowledgeEntry
from knowledge.schemas.ingestion import AddTextResponse
from knowledge.schemas.operations import KnowledgeStatsResponse
from knowledge.schemas.search import KnowledgeSearchResponse


@dataclass(frozen=True)
class Pair:
    """One SDK model and the backend response model it is fed from.

    ``waiver`` is the issue tracking a known divergence. ``None`` means the two
    field sets must match exactly, in both directions.
    """

    sdk_model: type[BaseModel]
    backend_model: type[BaseModel]
    route: str
    waiver: str | None = None


#: Every SDK model built from a backend response body, and the model that describes
#: that body. Derived by following each ``model_validate`` call in
#: ``libs/autobot-sdk-python/autobot_sdk/resources/`` to the route it requests and
#: that route's ``response_model=``.
CONTRACT: tuple[Pair, ...] = (
    # --- agreed: guarded in both directions -----------------------------------
    Pair(sdk.AgentConfig, AgentConfigDetailResponse, "GET /agent_config/agents/{id}"),
    Pair(sdk.AgentConfigOptions, AgentConfigDetailOptions, "GET /agent_config/agents/{id}.configuration_options"),
    Pair(sdk.AgentConfigHealthCheck, AgentConfigDetailHealthCheck, "GET /agent_config/agents/{id}.health_check"),
    # --- known divergences, each tracked ---------------------------------------
    Pair(sdk.AgentHealth, AgentHealthResponse, "GET /agent/health/detailed", waiver="#15118"),
    Pair(sdk.SessionList, SessionListData, "GET /chat/sessions", waiver="#15118"),
    Pair(sdk.SessionMessages, SessionMessagesData, "GET /chat/sessions/{id}", waiver="#15118"),
    Pair(sdk.SessionCreate, SessionCreateData, "POST /chat/sessions", waiver="#15114"),
    Pair(sdk.SessionUpdate, SessionUpdateData, "PUT /chat/sessions/{id}", waiver="#15114"),
    Pair(sdk.SessionDelete, SessionDeleteData, "DELETE /chat/sessions/{id}", waiver="#15118"),
    Pair(sdk.KnowledgeStats, KnowledgeStatsResponse, "GET /knowledge_base/stats", waiver="#15116"),
    Pair(sdk.KnowledgeAddResult, AddTextResponse, "POST /knowledge_base/add_text", waiver="#15116"),
    Pair(sdk.KnowledgeSearchResult, KnowledgeSearchResponse, "POST /knowledge_base/search", waiver="#15116"),
    Pair(sdk.KnowledgeSearchResult, KnowledgeEntriesResponse, "GET /knowledge_base/entries", waiver="#15116"),
    Pair(sdk.KnowledgeEntry, BackendKnowledgeEntry, "GET /knowledge_base/entries[].entry", waiver="#15118"),
    Pair(sdk.AnalyticsUsage, AnalyticsUsageStatisticsResponse, "GET /analytics/usage/statistics", waiver="#15116"),
    Pair(
        sdk.AnalyticsPerformance,
        AnalyticsPerformanceMetricsResponse,
        "GET /analytics/performance/metrics",
        waiver="#15116",
    ),
)

GUARDED: tuple[Pair, ...] = tuple(pair for pair in CONTRACT if pair.waiver is None)
WAIVED: tuple[Pair, ...] = tuple(pair for pair in CONTRACT if pair.waiver is not None)


def field_names(model: type[BaseModel]) -> frozenset[str]:
    """Declared field names of *model*, refusing to return an empty set.

    An enumeration that comes back empty makes every ``issubset`` assertion below
    pass without comparing anything, which is how a guard rots into decoration
    (#15087). A pydantic model with no fields is either the wrong class or a
    contract that was never written down; both are failures, not passes.
    """
    names = frozenset(model.model_fields)
    if not names:
        raise AssertionError(
            f"{model.__module__}.{model.__name__} enumerated zero fields -- "
            "either the model moved or it declares no contract at all; "
            "an empty enumeration must fail here, never pass vacuously"
        )
    return names


def _pair_id(pair: Pair) -> str:
    return f"{pair.sdk_model.__name__}<-{pair.backend_model.__name__}"


def test_the_contract_table_enumerates_pairs_to_check():
    """The table itself is an enumeration, so it gets the same empty-set treatment."""
    assert CONTRACT, "no SDK/route pairs enumerated -- this file would assert nothing"
    assert GUARDED, "every pair is waived -- the guard has stopped guarding anything"


@pytest.mark.parametrize("pair", GUARDED, ids=_pair_id)
def test_the_sdk_carries_every_field_the_route_returns(pair: Pair):
    """The #15072 defect proper: a route field absent from the SDK model is dropped in silence."""
    dropped = field_names(pair.backend_model) - field_names(pair.sdk_model)
    assert not dropped, (
        f"{pair.route} returns {sorted(dropped)}, which {pair.sdk_model.__name__} does not declare. "
        "extra='ignore' discards them without an error, so an SDK consumer cannot see them at all. "
        "Add the fields, or -- if they genuinely do not belong on the client -- stop the route "
        "advertising them and record the decision here."
    )


@pytest.mark.parametrize("pair", GUARDED, ids=_pair_id)
def test_the_sdk_declares_no_field_the_route_never_sends(pair: Pair):
    """The mirror failure: a field the route never sends reads as a supported, permanently-None one."""
    phantom = field_names(pair.sdk_model) - field_names(pair.backend_model)
    assert not phantom, (
        f"{pair.sdk_model.__name__} declares {sorted(phantom)}, which {pair.route} never emits. "
        "Those attributes exist on the object and are always None, which is indistinguishable "
        "from the backend having omitted them."
    )


@pytest.mark.parametrize("pair", WAIVED, ids=_pair_id)
def test_every_waiver_names_the_issue_that_tracks_it(pair: Pair):
    """A waiver without a tracked issue is a silently-accepted defect wearing a comment."""
    assert pair.waiver is not None and re.fullmatch(
        r"#\d+", pair.waiver
    ), f"{_pair_id(pair)} is waived as {pair.waiver!r}, which is not an issue reference"


@pytest.mark.parametrize("pair", WAIVED, ids=_pair_id)
def test_a_waived_pair_still_diverges(pair: Pair):
    """A waiver that no longer applies must be dropped, not left to rot into noise."""
    sdk_fields = frozenset(pair.sdk_model.model_fields)
    backend_fields = frozenset(pair.backend_model.model_fields)
    assert sdk_fields != backend_fields, (
        f"{_pair_id(pair)} now agrees exactly; remove the {pair.waiver} waiver " "so the pair is guarded from here on"
    )


def test_an_empty_field_enumeration_fails_instead_of_passing_vacuously():
    """#15087 in miniature, proved rather than asserted: the helper is fed an empty model."""

    class NoFields(BaseModel):
        pass

    with pytest.raises(AssertionError, match="enumerated zero fields"):
        field_names(NoFields)


#: One agent-config document carrying every key the route emits, with a distinguishable
#: value per field so a dropped key is visible as a missing value rather than as a
#: coincidental default. Mirrors the literal built at ``api/agent_config.py:1024``.
FULL_AGENT_CONFIG_DOCUMENT = {
    "id": "research",
    "name": "Research Agent",
    "description": "Researches things",
    "current_model": "gpt-4o",
    "provider": "openai",
    "enabled": True,
    "priority": 3,
    "tasks": ["research", "summarize"],
    "mcp_tools": ["web_search", "fetch"],
    "default_model": "gpt-4o-mini",
    "status": "connected",
    "config_source": "slm",
    "configuration_options": {
        "available_models": ["gpt-4o", "gpt-4o-mini"],
        "available_providers": ["openai", "bedrock"],
        "configurable_settings": ["model", "provider", "enabled", "priority"],
    },
    "health_check": {"last_check": "2026-01-01T00:00:00+00:00", "response_time": 1.5, "status": "healthy"},
}


def test_the_fixture_covers_every_key_the_route_declares():
    """Guards the guard: a route field the fixture forgot would make the round-trip vacuous."""
    declared = field_names(AgentConfigDetailResponse)
    assert frozenset(FULL_AGENT_CONFIG_DOCUMENT) == declared, (
        "FULL_AGENT_CONFIG_DOCUMENT no longer matches AgentConfigDetailResponse: "
        f"missing {sorted(declared - frozenset(FULL_AGENT_CONFIG_DOCUMENT))}, "
        f"unknown {sorted(frozenset(FULL_AGENT_CONFIG_DOCUMENT) - declared)}"
    )
    AgentConfigDetailResponse.model_validate(FULL_AGENT_CONFIG_DOCUMENT)


def test_a_full_route_document_round_trips_through_the_sdk_model():
    """AC: get_config() round-trips every key the route returns, values included (#15072)."""
    parsed = sdk.AgentConfig.model_validate(FULL_AGENT_CONFIG_DOCUMENT)
    dumped = parsed.model_dump()

    assert frozenset(dumped) >= frozenset(
        FULL_AGENT_CONFIG_DOCUMENT
    ), f"dropped {sorted(frozenset(FULL_AGENT_CONFIG_DOCUMENT) - frozenset(dumped))}"
    for key, expected in FULL_AGENT_CONFIG_DOCUMENT.items():
        assert dumped[key] == expected, f"{key} did not survive the round trip: {dumped[key]!r} != {expected!r}"


def test_the_nested_blocks_are_typed_rather_than_bare_dicts():
    """AC: health_check and configuration_options are modelled, not untyped dicts (#15072)."""
    parsed = sdk.AgentConfig.model_validate(FULL_AGENT_CONFIG_DOCUMENT)

    assert isinstance(parsed.health_check, sdk.AgentConfigHealthCheck)
    assert parsed.health_check.status == "healthy"
    assert parsed.health_check.response_time == 1.5
    assert isinstance(parsed.configuration_options, sdk.AgentConfigOptions)
    assert parsed.configuration_options.available_models == ["gpt-4o", "gpt-4o-mini"]


def test_an_older_backend_omitting_the_new_fields_still_parses():
    """AC: every added field stays optional, so an older backend does not break consumers (#15072)."""
    legacy = {
        k: v for k, v in FULL_AGENT_CONFIG_DOCUMENT.items() if k not in ("mcp_tools", "config_source", "health_check")
    }
    assert legacy, "the legacy fixture is empty, so this test would assert nothing"

    parsed = sdk.AgentConfig.model_validate(legacy)

    assert parsed.mcp_tools is None
    assert parsed.config_source is None
    assert parsed.health_check is None
    assert parsed.id == "research"
