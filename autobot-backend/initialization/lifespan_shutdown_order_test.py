# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``cleanup_services`` runs every shutdown step once, in the pinned order (#16250).

The step bodies live in ``initialization/lifespan_shutdown.py``. ``cleanup_services``
and its three stage functions are the only statement of the order. Every step and
every inline leg is swapped for a recorder here, so this pins the whole sequence;
``lifespan_test.py`` checks pieces of it (background init first, executor drain
before Redis close) against the real steps.
"""

import inspect
from types import SimpleNamespace

import pytest

from initialization import lifespan as lifespan_module
from initialization import lifespan_shutdown

_ORDER = [
    "cancel_background_init_task",
    "shutdown_code_analysis_pool",
    "stop_state_services",
    "stop_connector_and_skill_schedulers",
    "stop_vector_store_workers",
    "stop_documentation_watchers",
    "stop_doc_sync_queue_worker",
    "shutdown_slm_client",
    "stop_gateway",
    "drain_llc_monitors_and_mesh_scheduler",
    "stop_llc_services",
    "stop_periodic_schedulers",
    "stop_background_loops",
    "shutdown_agent_runtime",
    "dispose_skills_engine",
    "stop_log_forwarder",
    "stop_redis_dependent_loops",
    "shutdown_io_executors",
    "shutdown_tracing",
    "shutdown_extensions",
    "flush_llm_observers",
    "dispose_database_engine",
    "drain_worker_executor",
    "close_redis_connections",
]
#: Legs that stay inline in ``lifespan.py``, where tests patch them.
_INLINE = {"shutdown_slm_client", "shutdown_io_executors", "shutdown_tracing", "drain_worker_executor"}


def _steps() -> set:
    """Every step the module defines -- a new one has to be placed in ``_ORDER``."""
    return {
        name
        for name, fn in inspect.getmembers(lifespan_shutdown, inspect.iscoroutinefunction)
        if fn.__module__ == lifespan_shutdown.__name__
    }


@pytest.fixture
def calls(monkeypatch) -> list:
    recorded: list = []

    def _async(name: str, result=None):
        async def _record(*_args, **_kwargs):
            recorded.append(name)
            return result

        return _record

    for name in _steps():
        monkeypatch.setattr(lifespan_shutdown, name, _async(name))
    monkeypatch.setattr(lifespan_module, "shutdown_slm_client", _async("shutdown_slm_client"))
    monkeypatch.setattr(lifespan_module, "shutdown_io_executors", lambda: recorded.append("shutdown_io_executors"))
    monkeypatch.setattr(lifespan_module, "shutdown_tracing", _async("shutdown_tracing"))
    monkeypatch.setattr(lifespan_module, "_executor", object())
    monkeypatch.setattr(lifespan_module, "_drain_worker_executor", _async("drain_worker_executor", True))
    return recorded


def test_every_step_the_module_defines_is_in_the_order():
    assert _steps() == set(_ORDER) - _INLINE


@pytest.mark.asyncio
async def test_cleanup_runs_every_step_once_in_the_pinned_order(calls):
    failed = await lifespan_module.cleanup_services(SimpleNamespace(state=SimpleNamespace()))

    assert calls == _ORDER
    assert failed == []
