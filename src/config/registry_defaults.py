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

# VM IP addresses (6-VM distributed architecture)
REGISTRY_DEFAULTS = {
    # VM IPs
    "vm.main": "172.16.168.20",
    "vm.frontend": "172.16.168.21",
    "vm.npu": "172.16.168.22",
    "vm.redis": "172.16.168.23",
    "vm.aistack": "172.16.168.24",
    "vm.browser": "172.16.168.25",
    "vm.ollama": "127.0.0.1",
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
    # LLM defaults
    "llm.default_model": "mistral:7b-instruct",
    "llm.embedding_model": "nomic-embed-text:latest",
    # Timeouts
    "timeout.http": "30",
    "timeout.redis": "5",
    "timeout.llm": "120",
}


def get_default(key: str) -> Optional[str]:
    """Get default value for a config key."""
    return REGISTRY_DEFAULTS.get(key)
