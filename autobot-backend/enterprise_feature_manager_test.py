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
from autobot_shared.ssot_config import config


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


def test_get_fallback_endpoints_builds_without_attribute_error() -> None:
    eps = _instance()._get_fallback_endpoints()
    assert eps["backend_api"] == f"http://{config.vm.main}:{config.port.backend}/health"
    assert eps["web_interface"] == (
        f"http://{config.vm.frontend}:{config.port.frontend}/health"
    )
    assert eps["ai_processing"] == (
        f"http://{config.vm.aistack}:{config.port.aistack}/health"
    )
