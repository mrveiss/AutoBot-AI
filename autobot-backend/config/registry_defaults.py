#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""

Registry Defaults - Hardcoded Fallback Values
==============================================

Default values used when config is not found in Redis or environment.
These match the values from the distributed VM architecture.

Issue: #751 - Consolidate Common Utilities
"""

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    TRIVIAL_MODEL,
    get_config,
)

# Populate defaults from the SSOT config (Issue #2671)
# All values sourced from autobot_shared.ssot_config → .env → pydantic defaults
_ssot = get_config()

# VM IP addresses (6-VM distributed architecture + SLM admin)
REGISTRY_DEFAULTS = {
    # VM IPs — sourced from SSOT VMConfig
    "vm.main": _ssot.vm.main,
    "vm.frontend": _ssot.vm.frontend,
    "vm.npu": _ssot.vm.npu,
    "vm.redis": _ssot.vm.redis,
    "vm.aistack": _ssot.vm.aistack,
    "vm.browser": _ssot.vm.browser,
    "vm.slm": _ssot.vm.slm,  # Issue #768: SLM admin server
    "vm.ollama": _ssot.vm.ollama,
    # Provider-agnostic LLM service — autobot-llm-gpu (.20) hosts Ollama for GPU (#1193)
    "vm.llm": _ssot.vm.main,  # autobot-llm-gpu (Main Backend, RTX 4070)
    # Convenience aliases — sourced from SSOT VMConfig + PortConfig
    "redis.host": _ssot.vm.redis,
    "redis.port": str(_ssot.port.redis),
    "backend.host": _ssot.vm.main,
    "backend.port": str(_ssot.port.backend),
    "frontend.host": _ssot.vm.frontend,
    "frontend.port": str(_ssot.port.frontend),
    "npu.host": _ssot.vm.npu,
    "npu.port": str(_ssot.port.npu),
    "aistack.host": _ssot.vm.aistack,
    "aistack.port": str(_ssot.port.aistack),
    "browser.host": _ssot.vm.browser,
    "browser.port": str(_ssot.port.browser),
    "slm.host": _ssot.vm.slm,  # Issue #768
    "slm.port": str(_ssot.port.slm),  # Issue #768
    # Ports (for port.X access pattern) — sourced from SSOT PortConfig
    "port.backend": str(_ssot.port.backend),
    "port.frontend": str(_ssot.port.frontend),
    "port.redis": str(_ssot.port.redis),
    "port.ollama": str(_ssot.port.ollama),
    "port.llm": str(_ssot.port.ollama),  # Provider-agnostic LLM port (defaults to Ollama)
    "port.vnc": str(_ssot.port.vnc),
    "port.browser": str(_ssot.port.browser),
    "port.aistack": str(_ssot.port.aistack),
    "port.npu": str(_ssot.port.npu),
    "port.npu_windows": str(_ssot.port.npu),
    "port.slm": str(_ssot.port.slm),  # Issue #768: SLM admin server
    "port.prometheus": str(_ssot.port.prometheus),
    "port.grafana": str(_ssot.port.grafana),
    # LLM defaults — sourced from SSOT model constants
    "llm.default_model": DEFAULT_LLM_MODEL,
    "llm.embedding_model": DEFAULT_EMBEDDING_MODEL,
    # Tiered routing configuration (GH#9050)
    "llm.tiered_routing.enabled": "true",
    "llm.tiered_routing.models.trivial": TRIVIAL_MODEL,
    "llm.tiered_routing.models.simple": CLASSIFICATION_MODEL,
    "llm.tiered_routing.models.complex": DEFAULT_LLM_MODEL,
    "llm.tiered_routing.models.long_context": DEFAULT_LLM_MODEL,
    # Timeouts
    "timeout.http": "30",
    "timeout.redis": "5",
    "timeout.llm": "120",
    # TLS Configuration (Issue #164) — sourced from SSOT TLSConfig
    "tls.redis_enabled": "false",
    "tls.backend_enabled": "false",
    "tls.frontend_enabled": "false",
    "tls.slm_enabled": "false",
    "tls.frontend_port": str(_ssot.tls.frontend_tls_port),
    "tls.backend_port": str(_ssot.tls.backend_tls_port),
    "tls.slm_port": str(_ssot.tls.slm_tls_port),
    "tls.cert_path": "/etc/ssl/autobot",
    "tls.ca_cert": "/etc/ssl/autobot/ca.crt",
}


def get_default(key: str) -> str | None:
    """Get default value for a config key."""
    return REGISTRY_DEFAULTS.get(key)
