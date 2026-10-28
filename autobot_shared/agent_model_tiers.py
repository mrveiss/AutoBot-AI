# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE per-agent model tier assignment (#19332).

The tier constants -- which model each tier runs -- live in ``autobot_shared/ssot_config.py``.
This table says which tier each agent belongs to. Every plane that names a per-agent model
(``docker/.env.docker``, the backend and ai-stack Ansible roles, ``agents.yaml``) must state the
model of the agent's tier here; ``repo_tests/agent_model_tiers_19332_test.py`` fails the moment
one does not. Change a tier's model in ``ssot_config.py``; move an agent between tiers here.

Keys are the agent ids that ``get_agent_model_explicit`` turns into ``AUTOBOT_<ID>_MODEL`` (and the
tier variables themselves, e.g. ``instruction`` for ``AUTOBOT_INSTRUCTION_MODEL``).
"""

from __future__ import annotations

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    INSTRUCTION_MODEL,
    LIGHT_PROCESSING_MODEL,
    QUALITY_MODEL,
    ROUTING_MODEL,
    SYSTEM_MODEL,
)

#: Tier name -> the ssot_config constant that holds its model.
TIER_MODELS: dict[str, str] = {
    "default_llm": DEFAULT_LLM_MODEL,
    "embedding": DEFAULT_EMBEDDING_MODEL,
    "routing": ROUTING_MODEL,
    "classification": CLASSIFICATION_MODEL,
    "light": LIGHT_PROCESSING_MODEL,
    "instruction": INSTRUCTION_MODEL,
    "system": SYSTEM_MODEL,
    "quality": QUALITY_MODEL,
}

_QUALITY = (
    "chat code_generation data_analysis image_analysis reasoning coding agent research analysis planning"
    " code_analysis web_research_assistant advanced_web_research development_speedup overseer"
    " containerized_librarian system_knowledge_manager machine_aware_knowledge_manager standardized"
    " web_research_integration"
)
_INSTRUCTION = (
    "instruction rag kb_librarian knowledge_extraction knowledge_retrieval librarian_assistant"
    " graph_entity_extractor man_page_knowledge_integrator step_executor network_discovery"
    " summarization translation audio_processing"
)
_SYSTEM = "system system_commands enhanced_system_commands interactive_terminal security_scanner llm_failsafe"

#: Agent id -> tier name. One row per agent; every plane derives from it.
AGENT_TIERS: dict[str, str] = {
    "default_llm": "default_llm",
    "embedding": "embedding",
    **{a: "routing" for a in ("routing", "orchestrator")},
    **{a: "classification" for a in ("classification", "gemma_classification", "sentiment_analysis")},
    **{a: "light" for a in ("light_processing", "json_formatter", "npu_code_search")},
    **{a: "instruction" for a in _INSTRUCTION.split()},
    **{a: "system" for a in _SYSTEM.split()},
    **{a: "quality" for a in _QUALITY.split()},
}

#: The backend role's Ansible tier variables (``backend_<tier>_model``) -> the tier each carries. The
#: backend env template names per-agent models through these, so they are the backend plane's tiers.
BACKEND_VAR_TIERS: dict[str, str] = {
    "backend_llm_model": "default_llm",  # same model as "quality" (QUALITY_MODEL = DEFAULT_LLM_MODEL)
    "backend_routing_model": "routing",
    "backend_classification_model": "classification",
    "backend_light_model": "light",
    "backend_instruction_model": "instruction",
    "backend_system_model": "system",
    "backend_embedding_model": "embedding",
}
