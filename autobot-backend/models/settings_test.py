# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Consolidation guards for models/settings.py (#12750).

models/settings.py used to be a second pydantic-settings implementation of
settings the SSOT already owned.  These tests hold the consolidated end state:
the module is a re-export shim whose names resolve to the canonical objects,
and it defines no configuration behaviour of its own.  Two files agreeing today
is a fork that disagrees tomorrow, so "defines nothing" is asserted structurally
rather than by comparing values.
"""

import ast
from pathlib import Path

import pytest

from autobot_shared import ssot_config
from models import settings as shim

# Every setting the pre-consolidation module defined, by section.dotted name.
# Frozen inventory: if a name is added back to the shim as a real field, the
# coverage test below is what notices.
HISTORICAL_SETTINGS = {
    "llm.default_llm",
    "llm.orchestrator_llm",
    "llm.task_llm",
    "llm.ollama_host",
    "llm.ollama_port",
    "llm.ollama_model",
    "llm.ollama_base_url",
    "llm.openai_api_key",
    "llm.openai_model",
    "llm.huggingface_api_key",
    "llm.huggingface_model",
    "redis.enabled",
    "redis.host",
    "redis.port",
    "redis.db",
    "redis.password",
    "data.base_directory",
    "data.chat_history_file",
    "data.chats_directory",
    "data.long_term_db_path",
    "data.reliability_stats_file",
    "data.knowledge_base_db",
    "data.chromadb_path",
    "backend.server_host",
    "backend.server_port",
    "backend.api_endpoint",
    "backend.cors_origins",
    "backend.reload",
    "backend.log_level",
    "security.enable_auth",
    "security.audit_log_file",
    "security.allowed_users",
    "security.roles",
    "diagnostics.enabled",
    "diagnostics.use_llm_for_analysis",
    "diagnostics.use_web_search_for_analysis",
    "diagnostics.auto_apply_fixes",
    "memory.retention_days",
    "memory.max_entries_per_category",
    "orchestrator.use_langchain",
    "orchestrator.task_transport",
    "orchestrator.max_concurrent_tasks",
    "telemetry.enabled",
    "telemetry.anonymous_usage_stats",
    "telemetry.first_run_prompt_shown",
    "environment",
    "debug",
    "yaml_config_settings_source",
    "get_llm_config",
    "get_redis_config",
    "get_backend_config",
    "to_dict",
}

# Legacy alias -> the single canonical object that now owns the concern.
# No "LLMSettings" entry (#15577): that name collides with the live,
# actively-imported `llm_shared.models.LLMSettings` (Ollama provider config).
# Nothing imports the shim's bare `LLMSettings`, so it was dropped rather than
# aliased -- see test_llm_settings_is_not_aliased_here below.
CANONICAL_ALIASES = {
    "AutoBotSettings": ssot_config.AutoBotConfig,
    "RedisSettings": ssot_config.RedisConfig,
    "DataSettings": ssot_config.PathConfig,
    "BackendSettings": ssot_config.PortConfig,
    "SecuritySettings": ssot_config.AuthConfig,
    "TelemetrySettings": ssot_config.TelemetryConfig,
}


def _shim_tree() -> ast.Module:
    """Parse the shim's own source so structure can be asserted, not behaviour."""
    return ast.parse(Path(shim.__file__).read_text(encoding="utf-8"))


def test_shim_defines_no_classes_or_functions():
    """A re-export shim that grows a class or a def is a second implementation."""
    defined = [
        node.name
        for node in _shim_tree().body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert defined == [], f"models/settings.py defines behaviour again: {defined}"


def test_shim_declares_no_pydantic_fields_or_validators():
    """No Field()/field_validator/SettingsConfigDict anywhere in the shim."""
    banned = {"Field", "field_validator", "model_validator", "SettingsConfigDict", "BaseSettings"}
    used = {node.id for node in ast.walk(_shim_tree()) if isinstance(node, ast.Name) and node.id in banned}

    assert used == set(), f"models/settings.py re-declares settings machinery: {sorted(used)}"


def test_shim_assigns_only_aliases_and_documentation():
    """Every module-level assignment is a bare name alias or a literal map."""
    offenders = []
    for node in _shim_tree().body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, (ast.Name, ast.Attribute, ast.Dict, ast.List)):
            offenders.append(ast.unparse(node.targets[0]))

    assert offenders == [], f"models/settings.py computes values instead of aliasing: {offenders}"


@pytest.mark.parametrize("legacy_name,canonical", sorted(CANONICAL_ALIASES.items(), key=lambda kv: kv[0]))
def test_legacy_class_name_resolves_to_canonical_object(legacy_name, canonical):
    """The old names still import, and are the canonical classes themselves."""
    assert getattr(shim, legacy_name) is canonical


def test_llm_settings_is_not_aliased_here():
    """#15577: this module must not re-export a bare `LLMSettings`.

    `llm_shared.models.LLMSettings` is a live, actively-imported class
    (Ollama provider config -- `llm_shared/__init__.py`,
    `llm_shared/providers/ollama.py`, `ollama_provider.py`). If this shim ever
    grows an `LLMSettings = LLMConfig` alias again, both names would resolve
    under `LLMSettings` for two unrelated concepts -- exactly the collision
    #15577 removed. `LLMConfig` remains the shim's name for this concept.
    """
    from llm_shared.models import LLMSettings as live_llm_settings

    assert not hasattr(shim, "LLMSettings"), "models/settings.py re-added the LLMSettings collision (#15577)"
    assert "LLMSettings" not in shim.__all__
    assert shim.LLMConfig is not live_llm_settings, "the two LLMSettings concepts must stay distinct classes"


def test_settings_singleton_is_the_ssot_singleton():
    """`settings` is the SSOT proxy, not a second instance of a second model."""
    assert shim.settings is ssot_config.config


@pytest.mark.parametrize(
    "alias,section",
    [
        ("llm_settings", "llm"),
        ("redis_settings", "redis"),
        ("data_settings", "path"),
        ("backend_settings", "port"),
        ("security_settings", "auth"),
        ("telemetry_settings", "telemetry"),
    ],
)
def test_section_alias_is_the_canonical_section_object(alias, section):
    """Each convenience export is the canonical config section, not a copy."""
    assert getattr(shim, alias) is getattr(ssot_config.config, section)


def test_consolidated_map_covers_every_historical_setting():
    """No setting the orphan defined may vanish without a recorded owner."""
    assert set(shim.CONSOLIDATED_INTO) == HISTORICAL_SETTINGS


def test_redis_db_is_owned_only_by_the_db_main_env_var():
    """#12748 divergence: the deployment env var wins, the generic one is gone."""
    aliases = {name: field.alias for name, field in ssot_config.RedisConfig.model_fields.items()}

    assert shim.CONSOLIDATED_INTO["redis.db"].endswith("RedisConfig.db_main")
    assert aliases["db_main"] == "AUTOBOT_REDIS_DB_MAIN"
    assert "AUTOBOT_REDIS_DB" not in set(aliases.values())
