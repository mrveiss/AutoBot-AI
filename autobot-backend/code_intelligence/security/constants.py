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
    PLACEHOLDER_PATTERNS,
    HTTP_METHODS,
    INSECURE_RANDOM_FUNCS,
    PICKLE_MODULES,
    YAML_LOADER_ARGS,
    DEBUG_MODE_VARS,
    LOAD_FUNCS,
    VALIDATION_FUNCS,
    VALIDATION_ATTRS,
    SecuritySeverity,
    VulnerabilityType,
    OWASP_MAPPING,
    WEAK_HASH_ALGORITHMS,
    WEAK_ENCRYPTION,
)
