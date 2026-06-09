# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
tasks/ directory conftest — stubs heavy infrastructure so that task modules
can be imported in the dev/CI environment without a live Redis stack.

Issue #7766: Added to support the task-registration regression test.
Previously the tasks package could not be imported in tests at all because
``celery_app.py`` pulls in the full config/Redis dependency chain.

Approach
--------
Pytest loads directory-level conftest.py files before importing any test
modules in that directory.  By injecting stubs into ``sys.modules`` here we
prevent the real ``celery_app`` module (and its Redis/config chain) from being
executed, while still allowing the ``@celery_app.task`` decorators to run and
register tasks on a lightweight in-process Celery app.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import celery as _real_celery

# ---------------------------------------------------------------------------
# 1. Build a lightweight in-process Celery app for the test session.
#    All task decorators will register against this app.
# ---------------------------------------------------------------------------

_test_celery_app = _real_celery.Celery(
    "test_autobot",
    broker="memory://",
    backend="cache+memory://",
)

# ---------------------------------------------------------------------------
# 2. Inject it as the ``celery_app`` module so that
#    ``from celery_app import celery_app``  inside task files gets our instance.
# ---------------------------------------------------------------------------

_celery_app_mod = types.ModuleType("celery_app")
_celery_app_mod.celery_app = _test_celery_app  # type: ignore[attr-defined]
sys.modules.setdefault("celery_app", _celery_app_mod)

# ---------------------------------------------------------------------------
# 3. Stub autobot_shared sub-packages that are imported at module level in
#    knowledge_tasks.py / memory_tasks.py / system_tasks.py.
#    The top-level conftest.py already stubs the root ``autobot_shared``
#    package — here we only add the specific sub-modules.
# ---------------------------------------------------------------------------


def _ensure_stub(name: str) -> types.ModuleType:
    """Return existing module or create+register a MagicMock stub."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []  # mark as package
    mod.__package__ = name.rpartition(".")[0] or name
    _m = MagicMock()
    mod.__getattr__ = lambda attr: _m  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


_logging_stub = _ensure_stub("autobot_shared.logging_manager")
_logging_stub.get_logger = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

_async_compat_stub = _ensure_stub("autobot_shared.async_compat")
_async_compat_stub.run_or_schedule = MagicMock()  # type: ignore[attr-defined]

# type_defs.common is imported by knowledge_tasks.py
_type_defs = _ensure_stub("type_defs")
_type_defs_common = _ensure_stub("type_defs.common")
_type_defs_common.Metadata = dict  # type: ignore[attr-defined]
