# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pytest configuration for autobot-npu-worker tests.

Sets up path imports and fixtures for NPU worker testing (Issue #4311).
"""

import sys
from pathlib import Path

__all__: list = []

# Add npu-worker core module to path for test imports
_npu_worker_root = Path(__file__).parent
_core_path = _npu_worker_root / "core"
if str(_core_path) not in sys.path:
    sys.path.insert(0, str(_core_path))

# Add backend path for fallback imports
_project_root = _npu_worker_root.parent
_backend_path = _project_root / "autobot-backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))
