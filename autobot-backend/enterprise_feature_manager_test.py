# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for enterprise_feature_manager config-attribute wiring (#9832).

`_get_vm_env_config` and `_get_fallback_endpoints` read several non-existent
top-level `config.*` attributes (e.g. `config.backend_host`), which raise
AttributeError via AutoBotConfig.__getattr__. The canonical paths live on the
sub-configs (`config.vm.*` / `config.port.*`). These tests build the dicts via a
no-__init__ instance so they fail loudly if any attribute regresses.
"""

import enterprise_feature_manager as efm
from autobot_shared.ssot_config import MiscConfig, PortConfig, config


def _instance() -> efm.EnterpriseFeatureManager:
    # Bypass __init__ (which itself calls _get_vm_env_config) to isolate the methods.
    return object.__new__(efm.EnterpriseFeatureManager)


def test_get_vm_env_config_uses_canonical_subconfig_attrs() -> None:
    cfg = _instance()._get_vm_env_config()
    assert cfg["backend_host"] == config.vm.main
    assert cfg["backend_port"] == config.port.backend
    assert cfg["vnc_port"] == config.port.vnc
    assert cfg["frontend_host"] == config.vm.frontend
    assert cfg["frontend_port"] == config.port.frontend
    assert cfg["ai_stack_host"] == config.vm.aistack
    assert cfg["ai_stack_port"] == config.port.aistack
    assert cfg["browser_host"] == config.vm.browser
    assert cfg["browser_port"] == config.port.browser


class TestRedisPortCanonicalAccessor:
    """Regression coverage for #12470.

    `config.redis_port` resolves (via AutoBotConfig.__getattr__ sub-config
    fallback) to the legacy `MiscConfig.redis_port` field (alias REDIS_PORT,
    default 0) rather than the canonical `PortConfig.redis` field (alias
    AUTOBOT_REDIS_PORT, default 6379). On any box that doesn't explicitly
    export REDIS_PORT -- every single-node/dev/local install -- the legacy
    field is falsy 0, which alone trips `_validate_vm_env_config`'s
    `all(cfg.values())` check even though every other topology value has a
    perfectly good default.
    """

    def test_misc_redis_port_is_legacy_trap_defaults_to_zero(self, monkeypatch: object) -> None:
        """Document the trap: MiscConfig.redis_port defaults to 0 when unset."""
        monkeypatch.delenv("REDIS_PORT", raising=False)
        misc = MiscConfig(_env_file=None)
        assert misc.redis_port == 0

    def test_port_config_redis_defaults_to_6379_when_unset(self, monkeypatch: object) -> None:
        """The canonical accessor keeps the correct default even with no env set."""
        monkeypatch.delenv("AUTOBOT_REDIS_PORT", raising=False)
        port = PortConfig(_env_file=None)
        assert port.redis == 6379

    def test_get_vm_env_config_reads_canonical_redis_port(self) -> None:
        """`_get_vm_env_config` must read `config.port.redis`, not `config.redis_port`."""
        cfg = _instance()._get_vm_env_config()
        assert cfg["redis_port"] == config.port.redis
        assert cfg["redis_port"] != 0

    def test_validate_vm_env_config_does_not_trip_on_default_single_node_config(self) -> None:
        """REDIS_PORT unset must not falsely fail topology validation (#12470)."""
        instance = _instance()
        cfg = instance._get_vm_env_config()
        instance._validate_vm_env_config(cfg)  # must not raise


def test_get_fallback_endpoints_builds_without_attribute_error() -> None:
    eps = _instance()._get_fallback_endpoints()
    assert eps["backend_api"] == f"http://{config.vm.main}:{config.port.backend}/health"
    assert eps["web_interface"] == (f"http://{config.vm.frontend}:{config.port.frontend}/health")
    assert eps["ai_processing"] == (f"http://{config.vm.aistack}:{config.port.aistack}/health")
