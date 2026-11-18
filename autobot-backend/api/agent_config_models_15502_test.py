# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pins each agent's recommended default model to its canonical tier (#15502).

The tier map is the tested recommended set, used as the default and the fallback. Nothing here
asserts an override is impossible: per-agent / per-user overrides (the `AUTOBOT_<AGENT>_MODEL`
env path today) stay open and are reworked by #18282.

`complete.yaml` no longer carries `agents.<id>.model`; `DEFAULT_AGENT_CONFIGS` resolves every
agent to a tier constant that is read from the source-of-truth tier map, never a model literal.
"""

import re
from pathlib import Path

import pytest
import yaml

import autobot_shared.ssot_config as ssot
from api.agent_config import DEFAULT_AGENT_CONFIGS

#: agent id -> the tier whose recommended model is that agent's default.
AGENT_TIER = {
    "orchestrator": "ROUTING_MODEL",
    "chat": "QUALITY_MODEL",
    "classification": "CLASSIFICATION_MODEL",
    # Owner decision (#15502): the KB agents run on the instruction tier.
    "kb_librarian": "INSTRUCTION_MODEL",
    "knowledge_extraction": "INSTRUCTION_MODEL",
    "knowledge_retrieval": "INSTRUCTION_MODEL",
    "research": "QUALITY_MODEL",
    "system_commands": "SYSTEM_MODEL",
    "security_scanner": "SYSTEM_MODEL",
    "code_analysis": "QUALITY_MODEL",
}


@pytest.mark.parametrize(("agent_id", "tier"), sorted(AGENT_TIER.items()))
def test_agent_recommended_default_resolves_to_its_tier(agent_id: str, tier: str) -> None:
    assert DEFAULT_AGENT_CONFIGS[agent_id]["default_model"] == getattr(ssot, tier)


def test_no_agent_recommended_default_is_outside_the_tier_map() -> None:
    tiers = {
        getattr(ssot, n)
        for n in (
            "ROUTING_MODEL",
            "CLASSIFICATION_MODEL",
            "LIGHT_PROCESSING_MODEL",
            "INSTRUCTION_MODEL",
            "SYSTEM_MODEL",
            "QUALITY_MODEL",
        )
    }
    stray = {a: c["default_model"] for a, c in DEFAULT_AGENT_CONFIGS.items() if c["default_model"] not in tiers}
    assert stray == {}, f"recommended defaults naming a model outside the tier map: {stray}"


_ROOT = Path(__file__).resolve().parents[2]
_TIER_NAMES = (
    "ROUTING_MODEL",
    "CLASSIFICATION_MODEL",
    "LIGHT_PROCESSING_MODEL",
    "INSTRUCTION_MODEL",
    "SYSTEM_MODEL",
    "QUALITY_MODEL",
)
_TEMPLATE_LINE = re.compile(r"^AUTOBOT_(\w+)_MODEL=\{\{ \w+ \| default\('([^']+)'\) \}\}$", re.M)


def _tier_of(model: str) -> str:
    """The tier whose canonical model this is (QUALITY wins ties with DEFAULT_LLM_MODEL)."""
    return next((n for n in _TIER_NAMES if getattr(ssot, n) == model), f"NOT_A_TIER:{model}")


def _divergences(agent_tiers: dict[str, str], other: dict[str, str]) -> dict[str, tuple[str, str]]:
    """agent -> (tier here, tier there) for every agent both sides name whose tiers differ."""
    return {a: (agent_tiers[a], other[a]) for a in agent_tiers.keys() & other.keys() if agent_tiers[a] != other[a]}


def _agent_config_tiers() -> dict[str, str]:
    return {a: _tier_of(c["default_model"]) for a, c in DEFAULT_AGENT_CONFIGS.items()}


def _agents_yaml_tiers() -> dict[str, str]:
    path = _ROOT / "autobot-infrastructure/shared/config/agents.yaml"
    models = yaml.safe_load(path.read_text(encoding="utf-8"))["llm"]["models"]
    return {a: _tier_of(m) for a, m in models.items()}


def _env_template_tiers() -> dict[str, str]:
    text = (_ROOT / "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2").read_text(encoding="utf-8")
    # The embedding alias is not a chat-tier model; every other defaulted *_MODEL line is.
    return {n.lower(): _tier_of(d) for n, d in _TEMPLATE_LINE.findall(text) if n != "EMBEDDING"}


def test_recommended_tiers_agree_across_agent_config_agents_yaml_and_env_template() -> None:
    mine = _agent_config_tiers()
    yaml_tiers, env_tiers = _agents_yaml_tiers(), _env_template_tiers()
    assert len(mine.keys() & yaml_tiers.keys()) >= 10, "the agents.yaml comparison went vacuous"
    assert len(mine.keys() & env_tiers.keys()) >= 4, "the env template comparison went vacuous"
    assert _divergences(mine, yaml_tiers) == {}
    assert _divergences(mine, env_tiers) == {}


def test_the_cross_file_comparison_reports_a_divergence_and_ignores_unshared_agents() -> None:
    """Contrast fixture: a tier moved in one file is reported; an agent only one side names is not."""
    here = {"kb_librarian": "INSTRUCTION_MODEL", "chat": "QUALITY_MODEL"}
    there = {"kb_librarian": "LIGHT_PROCESSING_MODEL", "chat": "QUALITY_MODEL", "other": "SYSTEM_MODEL"}
    assert _divergences(here, there) == {"kb_librarian": ("INSTRUCTION_MODEL", "LIGHT_PROCESSING_MODEL")}
