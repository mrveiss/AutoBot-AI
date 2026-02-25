#!/usr/bin/env python3
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

from typing import Optional

# VM IP addresses (6-VM distributed architecture + SLM admin)
REGISTRY_DEFAULTS = {
    # VM IPs
    "vm.main": "172.16.168.20",
    "vm.frontend": "172.16.168.21",
    "vm.npu": "172.16.168.22",
    "vm.redis": "172.16.168.23",
    "vm.aistack": "172.16.168.24",
    "vm.browser": "172.16.168.25",
    "vm.slm": "172.16.168.19",  # Issue #768: SLM admin server
    "vm.ollama": "127.0.0.1",
    # Provider-agnostic LLM service — autobot-llm-gpu (.20) hosts Ollama for GPU (#1193)
    "vm.llm": "172.16.168.20",  # autobot-llm-gpu (Main Backend, RTX 4070)
    # Convenience aliases
    "redis.host": "172.16.168.23",
    "redis.port": "6379",
    "backend.host": "172.16.168.20",
    "backend.port": "8001",
    "frontend.host": "172.16.168.21",
    "frontend.port": "5173",
    "npu.host": "172.16.168.22",
    "npu.port": "8081",
    "aistack.host": "172.16.168.24",
    "aistack.port": "8080",
    "browser.host": "172.16.168.25",
    "browser.port": "3000",
    "slm.host": "172.16.168.19",  # Issue #768
    "slm.port": "8000",  # Issue #768
    # Ports (for port.X access pattern)
    "port.backend": "8001",
    "port.frontend": "5173",
    "port.redis": "6379",
    "port.ollama": "11434",
    "port.llm": "11434",  # Provider-agnostic LLM port (defaults to Ollama)
    "port.vnc": "6080",
    "port.browser": "3000",
    "port.aistack": "8080",
    "port.npu": "8081",
    "port.npu_windows": "8081",
    "port.slm": "8000",  # Issue #768: SLM admin server
    "port.prometheus": "9090",
    "port.grafana": "3000",
    # LLM defaults
    "llm.default_model": "mistral:7b-instruct",
    "llm.embedding_model": "nomic-embed-text:latest",
    # Timeouts
    "timeout.http": "30",
    "timeout.redis": "5",
    "timeout.llm": "120",
    # TLS Configuration (Issue #164)
    "tls.redis_enabled": "false",
    "tls.backend_enabled": "false",
    "tls.frontend_enabled": "false",
    "tls.slm_enabled": "false",
    "tls.frontend_port": "443",
    "tls.backend_port": "8443",
    "tls.slm_port": "443",
    "tls.cert_path": "/etc/ssl/autobot",
    "tls.ca_cert": "/etc/ssl/autobot/ca.crt",
}


def get_default(key: str) -> Optional[str]:
    """Get default value for a config key."""
    return REGISTRY_DEFAULTS.get(key)
