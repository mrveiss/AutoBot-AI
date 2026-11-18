# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The REAL ``autobot_shared.audit_actions`` for tests that stub ``autobot_shared`` (#18716).

Several SLM tests replace ``autobot_shared`` with a ``MagicMock`` that is not a package, so
``from autobot_shared.audit_actions import ...`` in ``api/auth.py`` / ``api/sso.py`` fails with
``'autobot_shared' is not a package``. The module is pure (``__future__``, ``enum``, ``typing``
only), so it is loaded by path and handed to the stub dict: the tests exercise the real mapping
rather than a MagicMock that would make ``spellings_of`` return a Mock.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "autobot_shared" / "audit_actions.py"
NAME = "autobot_shared.audit_actions"


def load_real_audit_actions() -> types.ModuleType:
    """Execute ``autobot_shared/audit_actions.py`` by path; does not touch ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(NAME, _PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module
