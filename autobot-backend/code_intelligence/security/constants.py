# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security constants, enums, and OWASP mappings.

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    DEBUG_MODE_VARS,
    HTTP_METHODS,
    INSECURE_RANDOM_FUNCS,
    LOAD_FUNCS,
    OWASP_MAPPING,
    PICKLE_MODULES,
    PLACEHOLDER_PATTERNS,
    VALIDATION_ATTRS,
    VALIDATION_FUNCS,
    WEAK_ENCRYPTION,
    WEAK_HASH_ALGORITHMS,
    YAML_LOADER_ARGS,
    SecuritySeverity,
    VulnerabilityType,
)
