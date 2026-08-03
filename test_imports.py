#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Quick import smoke check for the MCP metrics implementation.

Standalone diagnostic: run ``python3 test_imports.py`` to confirm the MCP
metrics/runtime modules import cleanly without spinning up pytest.

Package roots are resolved from ``__file__`` (#13409) — this script previously
pointed at a developer worktree that no longer exists, so it could not run at
all. The module bodies are guarded behind ``main()`` so a stray ``pytest .``
collecting this ``test_*.py`` filename cannot trip its ``sys.exit``.
"""

import importlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent

for _package_root in ("autobot-backend", "autobot_shared"):
    sys.path.insert(0, str(_REPO_ROOT / _package_root))

# (module path, attribute) pairs the MCP metrics work depends on.
CHECKS = (
    ("monitoring.metrics.mcp_worker", "MCPWorkerMetricsRecorder"),
    ("monitoring.prometheus_metrics", "get_metrics_manager"),
    ("services.mcp_isolated_runtime", "IsolatedBridgeClient"),
)


def check_import(module_path: str, attribute: str) -> bool:
    """Import ``attribute`` from ``module_path``; report and return success."""
    try:
        module = importlib.import_module(module_path)
        getattr(module, attribute)
    except Exception as exc:  # noqa: BLE001 - diagnostic reports any failure
        print(f"✗ Failed to import {attribute}: {exc}")  # noqa: print
        return False
    print(f"✓ {attribute} imported successfully")  # noqa: print
    return True


def main() -> int:
    """Run every import check; return 0 when all succeed."""
    results = [check_import(module, attr) for module, attr in CHECKS]
    if not all(results):
        return 1
    print("\nAll imports successful!")  # noqa: print
    return 0


if __name__ == "__main__":
    sys.exit(main())
