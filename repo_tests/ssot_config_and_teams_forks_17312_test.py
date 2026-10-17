# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fork-plan batch 11: one definition per concept for config and teams names (#17312).

Merged: TLSConfig (pki -> ssot_tls), match_intent_from_patterns (voice shim -> ssot_constants),
get_autobot_db (two SLM routers -> user_management.database), get_redis_url (backend registry
copy removed). Renamed apart (different concepts, evidence in the new names): see _RENAMED.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root

_ROOT = repo_root()


def _module_defs(rel: str) -> set[str]:
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}


def _defines(source: str, name: str) -> bool:
    return name in {n.name for n in ast.parse(source).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}


#: file -> (names that must be gone, names that now live there)
_RENAMED = {
    "autobot-backend/api/schemas_agent.py": ({"GoalResponse"}, {"AgentGoalResponse"}),
    "autobot-slm-backend/services/service_orchestrator.py": ({"ServiceRegistry"}, {"ServiceDefinitionRegistry"}),
    "autobot-backend/llm_shared/optimization/attention_backend.py": (
        {"AttentionBackend", "ModelConfig"},
        {"ModelAttentionBackend", "AttentionModelConfig"},
    ),
    "autobot-backend/llm_shared/optimization/connection_pool.py": ({"PoolConfig"}, {"HttpPoolConfig"}),
    "autobot-backend/utils/advanced_cache_manager.py": ({"CacheConfig"}, {"CacheEntryPolicy"}),
    "autobot_shared/redis_management/config.py": ({"RedisConfig"}, {"RedisDbConfig"}),
    "autobot-backend/config/__init__.py": ({"reload_config"}, {"reload_config_files"}),
}


def test_homonyms_are_renamed_apart() -> None:
    for rel, (gone, present) in _RENAMED.items():
        defs = _module_defs(rel)
        assert not (gone & defs), f"{rel} still defines {sorted(gone & defs)}"
        assert present <= defs, f"{rel} lacks {sorted(present - defs)}"


def test_merged_names_have_one_definition() -> None:
    assert "TLSConfig" not in _module_defs("autobot-backend/pki/config.py")
    assert "TLSConfig" in _module_defs("autobot_shared/ssot_tls.py")
    assert "match_intent_from_patterns" not in _module_defs("autobot-backend/voice_processing/constants.py")
    assert "get_redis_url" not in _module_defs("autobot-backend/utils/service_registry.py")
    for rel in ("autobot-slm-backend/api/autobot_users.py", "autobot-slm-backend/api/autobot_teams.py"):
        assert "get_autobot_db" not in _module_defs(rel)
    assert "get_autobot_db" in _module_defs("autobot-slm-backend/user_management/database.py")


def test_contrast_pair_detector_sees_a_fork() -> None:
    assert _defines("class TLSConfig:\n    pass\n", "TLSConfig")
    assert not _defines("from x import TLSConfig\n", "TLSConfig")


def test_one_tls_config_serves_the_ssot_and_the_pki_tooling() -> None:
    from autobot_shared import ssot_config, ssot_tls

    assert ssot_config.TLSConfig is ssot_tls.TLSConfig
    assert ssot_config.TLSMode is ssot_tls.TLSMode
    cfg = ssot_tls.TLSConfig(_env_file=None)  # type: ignore[call-arg]
    # fields the SSOT model had
    assert (cfg.redis_tls_port, cfg.backend_tls_port, cfg.frontend_tls_port) == (6380, 8443, 443)
    # fields only the PKI copy had
    assert (cfg.ca_validity_days, cfg.cert_validity_days, cfg.renewal_threshold_days, cfg.key_size) == (
        3650,
        365,
        30,
        4096,
    )
    assert cfg.cert_dir_path == Path(ssot_tls.PROJECT_ROOT) / "certs"
    assert cfg.get_vm_cert_info("redis", "10.0.0.1").common_name == "autobot-redis"
    assert ssot_config.AutoBotConfig.model_fields["tls"].annotation in (ssot_tls.TLSConfig, "TLSConfig")
