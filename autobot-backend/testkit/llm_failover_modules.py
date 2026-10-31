# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Real-load the fallback coordinator with the modules it imports for failover (#19753).

``conftest`` stubs ``llm_shared`` with an empty ``__path__``, so a module's relative imports resolve
only if the imported module was real-loaded first -- and ``real_load_and_bind`` answers a load that
raises with a silent package stub. The coordinator therefore becomes a ``MagicMock`` the moment one
of its dependencies is missing from this list. Dependency order matters.
"""

from __future__ import annotations

from pathlib import Path

from testkit.module_stubs import real_load_and_bind

#: (module name under ``llm_shared``, path relative to it), dependencies first.
_COORDINATOR_AND_DEPS = (
    ("rate_limit_backoff", "rate_limit_backoff.py"),
    ("optimization.router", "optimization/router.py"),
    ("provider_error_category", "provider_error_category.py"),
    ("failover_policy", "failover_policy.py"),
    ("model_fallback_coordinator", "model_fallback_coordinator.py"),
)


def load_coordinator(llm_root: Path) -> None:
    """Real-load ``llm_shared.model_fallback_coordinator`` and everything failover adds under it."""
    for name, relative_path in _COORDINATOR_AND_DEPS:
        real_load_and_bind(f"llm_shared.{name}", llm_root / relative_path)
