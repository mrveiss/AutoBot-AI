# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tiny ``celery`` shim for test environments where the package is not installed (#4455).

Modules that do ``@celery_app.task`` / ``@shared_task`` or subclass ``celery.Task`` import
cleanly against it. The real package is used on production nodes and wherever it is
installed; tests never rely on Beat.
"""

import sys
import types


def install_celery_stub() -> None:
    """Put a stub ``celery`` (and ``celery.schedules``) in ``sys.modules`` unless the real one imports."""
    try:
        import celery  # noqa: F401
    except ImportError:
        _celery_stub = types.ModuleType("celery")

        class _StubCelery:
            def __init__(self, *args, **kwargs) -> None:
                self.conf = types.SimpleNamespace(
                    update=lambda **_k: None,
                    beat_schedule={},
                )

            def task(self, *_args, **_kwargs):
                def decorator(fn):
                    fn.update_state = lambda *a, **k: None
                    return fn

                return decorator

            def autodiscover_tasks(self, *_args, **_kwargs) -> None:
                return None

        _celery_stub.Celery = _StubCelery

        class _StubTask:
            """Base class for `celery.Task` subclasses (`DeadLetterTask`)."""

        def _stub_shared_task(*args, **_kwargs):
            """`@shared_task` and `@shared_task(...)`: hand the function back, as `_StubCelery.task` does."""

            def decorator(fn):
                fn.update_state = lambda *a, **k: None
                return fn

            return decorator(args[0]) if args and callable(args[0]) else decorator

        _celery_stub.Task = _StubTask
        _celery_stub.shared_task = _stub_shared_task
        sys.modules["celery"] = _celery_stub

        _schedules_stub = types.ModuleType("celery.schedules")

        class _StubCrontab:
            def __init__(self, **fields) -> None:
                def _parse(v):
                    try:
                        return {int(v)}
                    except (TypeError, ValueError):
                        return set()

                self.minute = _parse(fields.get("minute", 0))
                self.hour = _parse(fields.get("hour", 0))

        _schedules_stub.crontab = _StubCrontab
        sys.modules["celery.schedules"] = _schedules_stub
