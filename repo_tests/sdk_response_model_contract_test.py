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

The waiver mechanism stays, and the waiver *table* is now empty: #15114, #15116 and
#15118 closed every divergence this file was opened carrying. A pair that regresses
therefore fails outright rather than being annotated, and a future divergence that
genuinely cannot be fixed at once has a documented way to be recorded instead of
dropped.

Two SDK models are deliberately unpaired rather than silently absent, listed in
:data:`UNPAIRED` with the reason: ``SessionListData.sessions`` and
``SessionMessagesData.messages`` are both declared ``List[Any]`` by the backend, so
there is no server-side model of a row to compare against. That is tracked in
#15138 -- declaring those two row shapes changes what the chat routes serialise,
which is a different risk class from an SDK-only fix.
``test_every_sdk_response_model_is_paired_or_explicitly_unpaired`` fails when a new
SDK model appears in neither list, which is the omission this table would otherwise
be open to.
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
from api.schemas_analytics_collector import AnalyticsPerformanceMetricsResponse, AnalyticsUsageStatisticsResponse
from api.schemas_chat import (
    FileHandlingResult,
    KbCleanupResult,
    SessionCreateData,
    SessionDeleteData,
    SessionUpdateData,
    TerminalCleanupResult,
    TranscriptCleanupResult,
)
from api.schemas_chat_rows import SessionListData, SessionMessage, SessionMessagesData, SessionSummary
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
    Pair(sdk.AgentConfig, AgentConfigDetailResponse, "GET /agent_config/agents/{id}"),
    Pair(sdk.AgentConfigOptions, AgentConfigDetailOptions, "GET /agent_config/agents/{id}.configuration_options"),
    Pair(sdk.AgentConfigHealthCheck, AgentConfigDetailHealthCheck, "GET /agent_config/agents/{id}.health_check"),
    Pair(sdk.AgentHealth, AgentHealthResponse, "GET /agent/health/detailed"),
    Pair(sdk.SessionList, SessionListData, "GET /chat/sessions"),
    Pair(sdk.SessionMessages, SessionMessagesData, "GET /chat/sessions/{id}"),
    # #15138: both rows are now described by a model instead of List[Any], so
    # they move out of UNPAIRED and are compared like every other pair.
    Pair(sdk.Session, SessionSummary, "GET /chat/sessions[].sessions"),
    Pair(sdk.ChatMessage, SessionMessage, "GET /chat/sessions/{id}[].messages"),
    Pair(sdk.SessionCreate, SessionCreateData, "POST /chat/sessions"),
    Pair(sdk.SessionUpdate, SessionUpdateData, "PUT /chat/sessions/{id}"),
    Pair(sdk.SessionDelete, SessionDeleteData, "DELETE /chat/sessions/{id}"),
    Pair(sdk.SessionDeleteFileHandling, FileHandlingResult, "DELETE /chat/sessions/{id}.file_handling"),
    Pair(sdk.SessionDeleteTerminalCleanup, TerminalCleanupResult, "DELETE /chat/sessions/{id}.terminal_cleanup"),
    Pair(sdk.SessionDeleteKbCleanup, KbCleanupResult, "DELETE /chat/sessions/{id}.kb_cleanup"),
    Pair(
        sdk.SessionDeleteTranscriptCleanup,
        TranscriptCleanupResult,
        "DELETE /chat/sessions/{id}.transcript_cleanup",
    ),
    Pair(sdk.KnowledgeStats, KnowledgeStatsResponse, "GET /knowledge_base/stats"),
    Pair(sdk.KnowledgeAddResult, AddTextResponse, "POST /knowledge_base/add_text"),
    Pair(sdk.KnowledgeSearchResult, KnowledgeSearchResponse, "POST /knowledge_base/search"),
    Pair(sdk.KnowledgeEntries, KnowledgeEntriesResponse, "GET /knowledge_base/entries"),
    Pair(sdk.KnowledgeEntry, BackendKnowledgeEntry, "GET /knowledge_base/entries[].entry"),
    Pair(sdk.AnalyticsUsage, AnalyticsUsageStatisticsResponse, "GET /analytics/usage/statistics"),
    Pair(sdk.AnalyticsPerformance, AnalyticsPerformanceMetricsResponse, "GET /analytics/performance/metrics"),
)

#: SDK models with no backend counterpart to compare against, and why. Listed
#: rather than omitted: an omitted model is indistinguishable from a forgotten
#: one, which is the silence this file exists to end.
UNPAIRED: dict[type[BaseModel], str] = {
    sdk.DataResponse: "The envelope itself; it mirrors schemas_common.DataResponse, not one route.",
}


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


def test_every_waiver_names_the_issue_that_tracks_it():
    """A waiver without a tracked issue is a silently-accepted defect wearing a comment.

    Looped rather than parametrized: ``WAIVED`` is empty today and an empty
    parametrize would report as a skip, which reads like a broken test rather
    than like the goal state. An empty loop here asserts nothing *and asserts
    nothing is owed* -- unlike the enumerations in ``field_names`` and
    ``test_the_contract_table_enumerates_pairs_to_check``, where empty means the
    guard stopped guarding and must fail.
    """
    for pair in WAIVED:
        assert pair.waiver is not None and re.fullmatch(
            r"#\d+", pair.waiver
        ), f"{_pair_id(pair)} is waived as {pair.waiver!r}, which is not an issue reference"


def test_a_waived_pair_still_diverges():
    """A waiver that no longer applies must be dropped, not left to rot into noise."""
    for pair in WAIVED:
        sdk_fields = frozenset(pair.sdk_model.model_fields)
        backend_fields = frozenset(pair.backend_model.model_fields)
        assert sdk_fields != backend_fields, (
            f"{_pair_id(pair)} now agrees exactly; remove the {pair.waiver} waiver "
            "so the pair is guarded from here on"
        )


def test_every_sdk_response_model_is_paired_or_explicitly_unpaired():
    """A model in neither table is the omission the pair table is otherwise open to.

    ``AgentConfigOptions`` reached the SDK carried inside ``AgentConfig`` and no
    route of its own; a new model can arrive the same way and be compared with
    nothing. Either it names the backend model it is fed from, or it says in
    ``UNPAIRED`` why no such model exists.
    """
    declared = {
        obj
        for obj in vars(sdk).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == sdk.__name__
    }
    assert declared, "no SDK models found -- the introspection broke, not the SDK"

    accounted = {pair.sdk_model for pair in CONTRACT} | set(UNPAIRED)
    orphans = declared - accounted
    assert not orphans, (
        f"SDK models compared against nothing: {sorted(m.__name__ for m in orphans)}. "
        "Add a Pair naming the backend response model each is built from, or an UNPAIRED "
        "entry saying why the backend describes no such model."
    )


def test_no_unpaired_entry_is_stale():
    """An UNPAIRED entry for a model that no longer exists is a comment about nothing."""
    assert UNPAIRED, "the unpaired table is empty -- delete it rather than leaving a table nothing reads"
    for model, reason in UNPAIRED.items():
        assert getattr(sdk, model.__name__, None) is model, f"{model.__name__} is no longer an autobot_sdk model"
        assert reason.strip(), f"{model.__name__} is unpaired for no recorded reason"


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
