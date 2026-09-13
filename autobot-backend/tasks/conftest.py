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

import importlib
import sys
import types

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
# 3. ``autobot_shared.logging_manager`` / ``type_defs.common`` need no stub
#    here (#13224). Both used to go through a local ``_ensure_stub`` helper
#    that fell back to whatever was already in ``sys.modules`` for a name —
#    silently handing back the REAL module whenever an earlier import had
#    already pulled it in — and then rebound an attribute on it with no
#    restore, leaking into every test collected afterwards on that worker.
#    ``run_or_schedule`` on ``autobot_shared.async_compat`` was the third such
#    rebind and was already removed for exactly this reason in #13162.
#
#    - ``get_logger``: this is an ancestor conftest's job, not this one's.
#      ``autobot-backend/conftest.py`` (a parent directory, so pytest always
#      loads it before this file) already imports the REAL
#      ``autobot_shared.logging_manager`` and rebinds ``get_logger`` to a
#      stdlib-logger factory exactly once, guarded by
#      ``_get_logger_patched_for_tests`` (issue #7766). Redoing it here on the
#      same real module was pure duplication — no test relied on this copy's
#      slightly different default ``name="autobot"``; every caller under
#      ``tasks/`` passes ``__name__`` explicitly.
#
#    - ``type_defs.common.Metadata``: ``type_defs/common.py`` depends on
#      nothing but ``enum``/``typing``, and the rest of ``type_defs/__init__``
#      pulls in only ``pydantic``, already a hard dependency everywhere in
#      this backend. There was no import cost or cycle to avoid, so the real
#      module (``Metadata = Dict[str, Any]``) loads directly — forcing it to
#      plain ``dict`` bought nothing, and on a worker where some other test
#      had already imported the real module first would have rebound it
#      permanently for the rest of that worker's run.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4. Real-load services.knowledge.doc_indexer (#11606).
#    The root conftest replaces the ``services`` package with a stub whose
#    catch-all ``__getattr__`` returns a MagicMock.  ``mock.patch`` resolves
#    dotted targets via getattr() on the parent package, so
#    ``patch("services.knowledge.doc_indexer.get_doc_indexer_service")``
#    silently patched a MagicMock while the code under test imported (and
#    called) the real module.  Importing the real module here binds it as an
#    attribute on the parent stub, so patch() targets the real module.
# ---------------------------------------------------------------------------

importlib.import_module("services.knowledge.doc_indexer")
