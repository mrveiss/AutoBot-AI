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

import sys
from pathlib import Path

from testkit.module_stubs import _is_real_module, real_load_and_bind

#: (module name under ``llm_shared``, path relative to it), dependencies first.
_COORDINATOR_AND_DEPS = (
    ("run_credentials", "run_credentials.py"),
    ("rate_limit_backoff", "rate_limit_backoff.py"),
    ("optimization.router", "optimization/router.py"),
    ("provider_error_category", "provider_error_category.py"),
    ("failover_policy", "failover_policy.py"),
    ("model_fallback_coordinator", "model_fallback_coordinator.py"),
)


def load_coordinator(llm_root: Path) -> None:
    """Real-load ``llm_shared.model_fallback_coordinator`` and everything failover adds under it.

    Raises when any of them is still a stub afterwards: a failover test run against a mocked
    classifier, policy or router would pass while asserting nothing about them.
    """
    for name, relative_path in _COORDINATOR_AND_DEPS:
        real_load_and_bind(f"llm_shared.{name}", llm_root / relative_path)
    stubbed = [n for n, _ in _COORDINATOR_AND_DEPS if not _is_real_module(sys.modules.get(f"llm_shared.{n}"))]
    if stubbed:
        raise RuntimeError(f"failover modules did not real-load (a stub would pass vacuously): {stubbed}")
