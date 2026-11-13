# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Claude ID SSOT and the data homes that cannot import it agree (#20884).

The scan for a second definition lives in ``hosted_model_literal_guard_15501_test.py``; this checks
the other half: that every home carries every current ID.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

from autobot_shared.model_pricing import MODEL_PRICING_PER_1M_TOKENS
from autobot_shared.ssot_claude_models import (
    CLAUDE_CONTEXT_WINDOW,
    CLAUDE_MODEL_IDS,
    CLAUDE_TIER_MODELS,
    resolve_claude_model,
    resolve_claude_models,
)
from autobot_shared.ssot_hosted_models import hosted_default_model


def _yaml(rel: str) -> dict:
    return yaml.safe_load((repo_root() / rel).read_text(encoding="utf-8"))


def test_the_four_current_ids_are_the_ssot():
    assert CLAUDE_MODEL_IDS == ("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")


def test_context_windows_yaml_covers_every_current_id():
    models = _yaml("autobot-backend/config/context_windows.yaml")["models"]
    for model_id in CLAUDE_MODEL_IDS:
        assert models[model_id]["context_window_tokens"] == CLAUDE_CONTEXT_WINDOW


def test_llm_models_yaml_covers_every_current_id():
    registry = _yaml("autobot-backend/config/llm_models.yaml")
    names = {m["api_name"]["anthropic"] for m in registry["models"] if "anthropic" in m.get("api_name", {})}
    assert set(CLAUDE_MODEL_IDS) <= names
    assert set(CLAUDE_MODEL_IDS) <= set(registry["anthropic_thinking_enabled"])


def test_every_current_id_is_priced_in_both_tables_and_the_tables_agree():
    """The provider baseline reads the current rows from the canonical table: one definition, same price."""
    from llm_shared.pricing.anthropic_source import _BASELINE

    assert set(CLAUDE_MODEL_IDS) <= set(MODEL_PRICING_PER_1M_TOKENS)
    rows = {row[0]: row for row in _BASELINE}
    for model in CLAUDE_MODEL_IDS:
        assert (rows[model][1], rows[model][2]) == (
            MODEL_PRICING_PER_1M_TOKENS[model]["input"],
            MODEL_PRICING_PER_1M_TOKENS[model]["output"],
        ), model


def test_a_tier_alias_resolves_and_anything_else_passes_through():
    assert {a: resolve_claude_model(a) for a in CLAUDE_TIER_MODELS} == CLAUDE_TIER_MODELS
    assert resolve_claude_model(" Sonnet ") == CLAUDE_TIER_MODELS["sonnet"]
    assert resolve_claude_model("gpt-4o") == "gpt-4o"
    assert resolve_claude_model(None) is None


def test_the_hosted_anthropic_defaults_are_the_current_sonnet_and_haiku():
    assert hosted_default_model("anthropic", "light") == CLAUDE_TIER_MODELS["haiku"]


def test_built_in_templates_name_tier_aliases_that_resolve():
    import json

    seen = set()
    for name in ("content-team", "customer-ops", "research-team", "software-team"):
        path = repo_root() / "autobot-backend/llc/built_in_templates" / f"{name}.json"
        for agent in json.loads(path.read_text(encoding="utf-8")).get("agents", []):
            if "model" in agent:
                seen.add(agent["model"])
    assert seen and seen <= set(CLAUDE_TIER_MODELS), seen


def test_resolving_a_template_replaces_every_nested_model_alias_and_nothing_else():
    template = {"agents": [{"model": "opus", "name": "sonnet"}, {"model": "gpt-4o"}], "nested": {"model": "haiku"}}
    assert resolve_claude_models(template) == {
        "agents": [{"model": CLAUDE_TIER_MODELS["opus"], "name": "sonnet"}, {"model": "gpt-4o"}],
        "nested": {"model": CLAUDE_TIER_MODELS["haiku"]},
    }


def test_adaptive_thinking_covers_the_5x_ids_and_4_6_plus_and_not_older_models():
    from autobot_shared.ssot_claude_models import requires_adaptive_thinking

    assert all(requires_adaptive_thinking(m) for m in CLAUDE_MODEL_IDS)
    assert all(requires_adaptive_thinking(m) for m in ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6"))
    assert requires_adaptive_thinking("claude-sonnet-4-6")
    assert not requires_adaptive_thinking("claude-sonnet-4-20250514")
    assert not requires_adaptive_thinking("claude-3-5-sonnet-20241022")


def test_adaptive_is_the_default_for_any_claude_id_not_an_explicit_pre_4_6_family():
    from autobot_shared.ssot_claude_models import requires_adaptive_thinking

    for adaptive in (
        "claude-opus-9-9",  # a future ID
        "claude-sonnet-5-5-20261001",  # a dated current ID
        "anthropic.claude-sonnet-5-5-v1:0",  # Bedrock spelling
        "us.anthropic.claude-opus-5-5-20260101-v1:0",
        "claude-opus-5-5@20260101",  # Vertex spelling
        "sonnet",  # a bare tier alias
    ):
        assert requires_adaptive_thinking(adaptive), adaptive
    for budgeted in (
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
        "claude-3-5-sonnet",
        "claude-opus-4-1-20250805",
        "claude-opus-4-20250514",
        "claude-haiku-4-5",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "gpt-4o",
    ):
        assert not requires_adaptive_thinking(budgeted), budgeted


def test_current_claude_model_maps_earlier_generation_ids_to_their_tier_and_passes_the_rest():
    from autobot_shared.ssot_claude_models import CLAUDE_HAIKU, CLAUDE_SONNET, current_claude_model

    assert current_claude_model("claude-sonnet-4-6") == CLAUDE_SONNET
    assert current_claude_model("claude-haiku-4-5-20251001") == CLAUDE_HAIKU
    assert current_claude_model("claude-haiku-4") == CLAUDE_HAIKU
    assert current_claude_model("haiku") == CLAUDE_HAIKU
    assert current_claude_model(CLAUDE_SONNET) == CLAUDE_SONNET
    assert current_claude_model("gpt-4o") == "gpt-4o"
    assert current_claude_model(None) is None


def test_every_budget_tokens_sender_goes_through_the_one_predicate():
    """The only places a thinking ``budget_tokens`` request is built are the shared builder's fixed-budget branch."""
    root = repo_root() / "autobot-backend"
    for rel in ("llm_shared/providers/anthropic_request.py", "chat_workflow/reasoning_kwargs.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert '"enabled"' not in text or "requires_adaptive_thinking" in text, rel
    assert '"enabled"' not in (root / "chat_workflow/reasoning_kwargs.py").read_text(encoding="utf-8")
