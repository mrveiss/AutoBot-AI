# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every per-agent model default derives from ONE tier assignment (#19332).

Maintainer decision 2026-10-26: per-agent models derive from the tier map. The tier models are
the constants in ``autobot_shared/ssot_config.py``; which tier each agent runs is
``autobot_shared/agent_model_tiers.AGENT_TIERS``. The four planes that name a per-agent model
cannot import Python, so each states the model and this guard holds it to the assignment:

* ``docker/.env.docker`` -- ``AUTOBOT_<AGENT>_MODEL=<model>``;
* the ai-stack role defaults -- ``ai_<agent>_model: "<model>"``;
* ``agents.yaml`` -- ``llm.models.<agent>``;
* the backend env template -- ``AUTOBOT_<AGENT>_MODEL={{ backend_<tier>_model ... }}``.

Before, the same agent ran a 3.8B model on a Docker host and a 7B one on a VM fleet, and the
failsafe differed between the backend and the ai-stack role of one fleet. An agent named in any
plane but missing from the assignment also fails here: a new agent picks its tier first.
"""

from __future__ import annotations

import re

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.agent_model_tiers import AGENT_TIERS, BACKEND_VAR_TIERS, TIER_MODELS

_ROOT = repo_root()
_DOCKER = "docker/.env.docker"
_AI_STACK = "autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml"
_AGENTS = "autobot-infrastructure/shared/config/agents.yaml"
_BACKEND = "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2"


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


#: An ai-stack value that names another of the file's own model variables, e.g. the failsafe
#: pointing at the system tier, so the model is written once.
_AI_STACK_SELF_REF = re.compile(r"\{\{\s*ai_(\w+)_model\s*\}\}")


def ai_stack_models(text: str) -> dict[str, str]:
    """``{agent: model}`` from the ai-stack defaults, with references to its own variables resolved."""
    stated = dict(re.findall(r"^ai_(\w+)_model:\s*\"([^\"]+)\"", text, re.M))
    resolved = {}
    for agent, value in stated.items():
        ref = _AI_STACK_SELF_REF.fullmatch(value)
        resolved[agent] = stated.get(ref.group(1), value) if ref else value
    return resolved


def stated_models() -> dict[str, dict[str, str]]:
    """Plane -> {agent id: model it states}."""
    backend = {}
    for agent, var in re.findall(r"^AUTOBOT_(\w+)_MODEL=\{\{\s*(backend_\w+_model)\b", _read(_BACKEND), re.M):
        assert var in BACKEND_VAR_TIERS, f"{_BACKEND}: {var} has no tier in agent_model_tiers.BACKEND_VAR_TIERS"
        backend[agent.lower()] = TIER_MODELS[BACKEND_VAR_TIERS[var]]
    return {
        _DOCKER: {a.lower(): m for a, m in re.findall(r"^AUTOBOT_(\w+)_MODEL=(\S+)", _read(_DOCKER), re.M)},
        _AI_STACK: ai_stack_models(_read(_AI_STACK)),
        _AGENTS: dict(yaml.safe_load(_read(_AGENTS))["llm"]["models"]),
        _BACKEND: backend,
    }


def mismatches(planes: dict[str, dict[str, str]]) -> list[str]:
    found = []
    for plane, models in planes.items():
        for agent, model in sorted(models.items()):
            tier = AGENT_TIERS.get(agent)
            if tier is None:
                found.append(f"{plane}: {agent} has no tier in agent_model_tiers.AGENT_TIERS")
            elif model != TIER_MODELS[tier]:
                found.append(f"{plane}: {agent} = {model}, its {tier} tier is {TIER_MODELS[tier]}")
    return found


#: Each text plane's model lines -- every one must be parsed, or a new shape would pass unread.
_MODEL_LINES = {
    _DOCKER: r"^AUTOBOT_\w+_MODEL=",
    _AI_STACK: r"^ai_\w+_model:",
    _BACKEND: r"^AUTOBOT_\w+_MODEL=",
}


def test_every_model_line_of_every_plane_is_read() -> None:
    planes = stated_models()
    for plane, pattern in _MODEL_LINES.items():
        lines = len(re.findall(pattern, _read(plane), re.M))
        assert lines and len(planes[plane]) == lines, f"{plane}: {lines} model lines, {len(planes[plane])} read"
    assert planes[_AGENTS], f"{_AGENTS}: llm.models parsed to nothing"


def test_every_plane_states_the_model_of_the_agents_tier() -> None:
    planes = stated_models()
    assert not mismatches(planes), "derive from autobot_shared/agent_model_tiers.py (#19332):\n" + "\n".join(
        mismatches(planes)
    )


def test_every_tier_is_an_ssot_constant() -> None:
    assert set(AGENT_TIERS.values()) <= set(TIER_MODELS), set(AGENT_TIERS.values()) - set(TIER_MODELS)


@pytest.mark.parametrize(
    "plane,agent,model",
    [
        (_DOCKER, "kb_librarian", "phi3:mini"),
        (_AI_STACK, "llm_failsafe", "phi3:mini"),
        (_DOCKER, "sentiment_analysis", "qwen3.5:9b"),
        (_AGENTS, "brand_new_agent", "qwen3.5:9b"),
    ],
)
def test_each_pre_fix_value_or_an_unassigned_agent_is_flagged(plane: str, agent: str, model: str) -> None:
    assert mismatches({plane: {agent: model}})


# --- the Docker plane's models are pulled (code review on #19692) ----------------------------
#: Docker has no automatic pull: Ollama starts empty and the quick-start docs pull. They read the
#: model list from docker/.env.docker itself, so every model an agent runs is pulled.
_DERIVED_PULL = "sed -n 's/^AUTOBOT_[A-Z_]*_MODEL=//p' docker/.env.docker | sort -u"
_PULL_DOCS = ("README.md", "INSTALL.md")
_LITERAL_PULL = re.compile(r"exec(?:\s+-T)?\s+autobot-ollama\s+ollama\s+pull\s+[\w.-]+:[\w.-]+")


def test_the_docker_quick_start_pulls_every_model_the_docker_env_names() -> None:
    for doc in _PULL_DOCS:
        assert _DERIVED_PULL in _read(doc), f"{doc}: pull the models with `{_DERIVED_PULL} | xargs ...` (#19332)"
    pulled = set(re.findall(r"^AUTOBOT_[A-Z_]*_MODEL=(.*)$", _read(_DOCKER), re.M))
    assert pulled == set(stated_models()[_DOCKER].values()), "the pull's sed reads other lines than the guard"


def test_no_doc_pulls_one_hand_picked_model_into_the_docker_ollama() -> None:
    docs = [*_PULL_DOCS, *(p.relative_to(_ROOT).as_posix() for p in sorted((_ROOT / "docs").rglob("*.md")))]
    found = [f"{d}: {m}" for d in docs for m in _LITERAL_PULL.findall(_read(d))]
    assert not found, f"a hand-picked pull drifts from docker/.env.docker -- use the derived pull: {found}"


def test_the_literal_pull_shape_is_flagged_and_the_derived_one_is_not() -> None:
    assert _LITERAL_PULL.findall("docker compose exec autobot-ollama ollama pull qwen3.5:9b")
    assert not _LITERAL_PULL.findall(f"{_DERIVED_PULL} | xargs -n1 docker compose exec -T autobot-ollama ollama pull")


def test_an_ai_stack_reference_to_its_own_model_variable_resolves() -> None:
    text = 'ai_system_commands_model: "dolphin-llama3:8b"\nai_llm_failsafe_model: "{{ ai_system_commands_model }}"\n'
    assert ai_stack_models(text)["llm_failsafe"] == "dolphin-llama3:8b"
    # A reference to a name the file does not define stays as written, so it reads as a mismatch.
    assert ai_stack_models('ai_x_model: "{{ ai_missing_model }}"\n')["x"] == "{{ ai_missing_model }}"
