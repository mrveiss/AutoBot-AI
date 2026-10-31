# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PKI Configuration Models
========================

Pydantic models for TLS/PKI configuration, integrated with SSOT config system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from autobot_shared.paths import project_root
from autobot_shared.ssot_tls import (  # noqa: F401 — canonical TLS settings, re-exported
    TLSConfig,
    TLSMode,
    VMCertificateInfo,
)

# #13149: this module carried its own ``.env``-walk copy of the project-root
# search. It had no checkout step, so from a source tree with no ``.env`` it
# resolved to the deployed install and pointed PKI's certificate paths at
# production — the same failure #13646 fixed for ``ssot_config`` and #13092 for
# ``run_agent.sh``. It now shares the one implementation.
PROJECT_ROOT = project_root()

# #17434: the Redis config file the daemon actually reads, and the Python half of
# a value ansible declares as `redis_config_file` in
# autobot-slm-backend/ansible/inventory/group_vars/all.yml. One value cannot be
# one literal across a YAML tree and a Python package, so the two declarations
# are pinned equal by repo_tests/redis_config_path_is_canonical_17434_test.py --
# that guard, not a shared file, is what makes "named in one place" enforceable.
#
# It is NOT /etc/redis-stack/redis-stack.conf: that directory does not exist on a
# provisioned node, so every write to it landed in nothing.
REDIS_STACK_CONFIG_PATH = "/etc/redis-stack.conf"


class CertificateType(str, Enum):
    """Types of certificates managed."""

    CA = "ca"
    SERVER = "server"
    CLIENT = "client"


@dataclass
class CertificateStatus:
    """Status of a certificate."""

    exists: bool
    valid: bool
    expires_at: str | None = None
    days_until_expiry: int | None = None
    subject: str | None = None
    issuer: str | None = None
    needs_renewal: bool = False


# VM definitions for certificate generation - imported from SSOT
# Issue #694: Centralized config consolidation
def _get_vm_definitions() -> Dict[str, str]:
    """Get VM definitions from SSOT config with fallback."""
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().vm_definitions
    except Exception:
        # Fallback for standalone PKI tool usage - use SSOT defaults
        from autobot_shared.ssot_config import VMConfig

        vm = VMConfig()
        return {
            "main-host": vm.main,
            "frontend": vm.frontend,
            "npu-worker": vm.npu,
            "redis": vm.redis,
            "ai-stack": vm.aistack,
            "browser": vm.browser,
        }


VM_DEFINITIONS: Dict[str, str] = _get_vm_definitions()
