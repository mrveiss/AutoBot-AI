# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim onto the canonical configuration surface (#12750).

This module used to be a second, parallel pydantic-settings configuration
system: ten ``BaseSettings`` subclasses, a ``settings`` singleton and a set of
convenience exports, with zero importers anywhere in the tree.  Because nothing
exercised it, it rotted -- it imported a symbol that existed nowhere (fixed in
PR #15561), its ``cors_origins`` default shipped an uninterpolated ``{...}``
literal because the ``f`` prefix was missing, its ``yaml_config_settings_source``
was never registered with pydantic so no YAML was ever read, and half its
classes silently dropped ``RedactedReprMixin`` so secrets would have printed in
the clear.

The consolidation keeps ONE definition of every setting.  The canonical surface
is:

* ``autobot_shared.ssot_config``       -- env-derived settings (pydantic), the
  surface the deployment contract (.env.example, ansible group_vars) is written
  against;
* ``config.defaults``                  -- the runtime ConfigManager tree, which
  derives its values from ssot_config;
* ``config.validation``                -- startup validation of that tree,
  reached from ``initialization.lifespan``.

Nothing here defines a field, a default, a validator or a method.  The legacy
names below are aliases onto the canonical objects so that any future importer
keeps resolving, and ``CONSOLIDATED_INTO`` records, for every setting this
module used to define, the single place that now owns it.
"""

from autobot_shared.ssot_config import (
    AuthConfig,
    AutoBotConfig,
    LLMConfig,
    PathConfig,
    PortConfig,
    RedisConfig,
    TelemetryConfig,
    VMConfig,
    config,
)

# --------------------------------------------------------------------------
# Legacy class names -> canonical classes.
# --------------------------------------------------------------------------
AutoBotSettings = AutoBotConfig
LLMSettings = LLMConfig
RedisSettings = RedisConfig
DataSettings = PathConfig
BackendSettings = PortConfig
SecuritySettings = AuthConfig
TelemetrySettings = TelemetryConfig

# --------------------------------------------------------------------------
# Legacy singletons -> the canonical lazy singleton and its sections.
# ``settings`` is the reload-aware proxy; prefer ``settings.redis`` over the
# section aliases, which are bound once at import.
# --------------------------------------------------------------------------
settings = config
llm_settings = config.llm
redis_settings = config.redis
data_settings = config.path
backend_settings = config.port
security_settings = config.auth
telemetry_settings = config.telemetry

# --------------------------------------------------------------------------
# Every setting this module used to define, and the single canonical owner it
# was consolidated into.  Strings only -- this is documentation the test suite
# asserts against, not behaviour.  An empty owner means the setting had no
# consumer and no canonical home; those are reported, not silently dropped.
# --------------------------------------------------------------------------
CONSOLIDATED_INTO = {
    "llm.default_llm": "autobot_shared.ssot_config.LLMConfig.provider",
    "llm.orchestrator_llm": "autobot_shared.ssot_config.LLMConfig.orchestrator_model",
    "llm.task_llm": "autobot_shared.ssot_config.LLMConfig.provider",
    "llm.ollama_host": "autobot_shared.ssot_config.VMConfig.ollama",
    "llm.ollama_port": "autobot_shared.ssot_config.PortConfig.ollama",
    "llm.ollama_model": "autobot_shared.ssot_config.LLMConfig.default_model",
    "llm.ollama_base_url": "autobot_shared.ssot_config.AutoBotConfig.ollama_url",
    "llm.openai_api_key": "autobot_shared.ssot_config.LLMConfig.openai_api_key",
    "llm.openai_model": "autobot_shared.ssot_config.LLMConfig.default_model",
    "llm.huggingface_api_key": "autobot_shared.ssot_config.MiscConfig.huggingface_api_token",
    "llm.huggingface_model": "",
    "redis.enabled": "autobot_shared.ssot_config.RedisConfig.enabled",
    "redis.host": "autobot_shared.ssot_config.VMConfig.redis",
    "redis.port": "autobot_shared.ssot_config.PortConfig.redis",
    "redis.db": "autobot_shared.ssot_config.RedisConfig.db_main",
    "redis.password": "autobot_shared.ssot_config.RedisConfig.password",
    "data.base_directory": "autobot_shared.ssot_config.PathConfig.data_dir",
    "data.chat_history_file": "autobot_shared.ssot_config.MiscConfig.chat_history_file",
    "data.chats_directory": "autobot_shared.ssot_config.MiscConfig.chats_directory",
    "data.long_term_db_path": "config.defaults data.long_term_db_path",
    "data.reliability_stats_file": "config.defaults data.reliability_stats_file",
    "data.knowledge_base_db": "services.config_service backend.knowledge_base_db",
    "data.chromadb_path": "autobot_shared.ssot_config.MiscConfig.chromadb_path",
    "backend.server_host": "config.defaults backend.server_host",
    "backend.server_port": "autobot_shared.ssot_config.PortConfig.backend",
    "backend.api_endpoint": "autobot_shared.ssot_config.AutoBotConfig.backend_url",
    "backend.cors_origins": "config.service_config.ServiceConfigMixin.get_cors_origins",
    "backend.reload": "autobot_shared.ssot_config.FeatureConfig.hot_reload",
    "backend.log_level": "autobot_shared.ssot_config.AutoBotConfig.log_level",
    "security.enable_auth": "",
    "security.audit_log_file": "autobot_shared.ssot_config.MiscConfig.audit_log_file",
    "security.allowed_users": "",
    "security.roles": "autobot_shared.ssot_config.PermissionConfig",
    "diagnostics.enabled": "",
    "diagnostics.use_llm_for_analysis": "",
    "diagnostics.use_web_search_for_analysis": "",
    "diagnostics.auto_apply_fixes": "",
    "memory.retention_days": "autobot_shared.ssot_config.AutoBotConfig.chat_retention_days",
    "memory.max_entries_per_category": "",
    "orchestrator.use_langchain": "",
    "orchestrator.task_transport": "config.defaults task_transport.type",
    "orchestrator.max_concurrent_tasks": "",
    "telemetry.enabled": "autobot_shared.ssot_config.TelemetryConfig.enabled",
    "telemetry.anonymous_usage_stats": "autobot_shared.ssot_config.TelemetryConfig.anonymous_usage_stats",
    "telemetry.first_run_prompt_shown": "autobot_shared.ssot_config.TelemetryConfig.first_run_prompt_shown",
    "environment": "autobot_shared.ssot_config.AutoBotConfig.environment",
    "debug": "autobot_shared.ssot_config.AutoBotConfig.debug",
    "yaml_config_settings_source": "autobot_shared.config_file_loading.load_config_file",
    "get_llm_config": "config.service_config.ServiceConfigMixin.get_llm_config",
    "get_redis_config": "config.service_config.ServiceConfigMixin.get_redis_config",
    "get_backend_config": "config.service_config.ServiceConfigMixin.get_backend_config",
    "to_dict": "config.manager.ConfigManager",
}

__all__ = [
    "AutoBotConfig",
    "AuthConfig",
    "LLMConfig",
    "PathConfig",
    "PortConfig",
    "RedisConfig",
    "TelemetryConfig",
    "VMConfig",
    "AutoBotSettings",
    "LLMSettings",
    "RedisSettings",
    "DataSettings",
    "BackendSettings",
    "SecuritySettings",
    "TelemetrySettings",
    "config",
    "settings",
    "llm_settings",
    "redis_settings",
    "data_settings",
    "backend_settings",
    "security_settings",
    "telemetry_settings",
    "CONSOLIDATED_INTO",
]
