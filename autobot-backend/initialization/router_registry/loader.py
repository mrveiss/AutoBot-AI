# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One router loader for every registry group (#14207).

Seven registry modules each carried their own copy of the same
import-and-swallow block. Six of them recorded nothing: a router whose module
raised ``ImportError`` — a syntax error in a dependency, a package missing
after a partial deploy, a symbol removed from a shared module — was simply not
mounted. The process started, ``systemctl`` reported ``active``, ``/health``
passed, and every endpoint that router owned returned **404**, with one WARNING
among hundreds of startup lines as the only trace.

A 404 is the worst possible presentation, because it is indistinguishable from
"that endpoint was never built" and sends whoever investigates at the frontend
or the route table rather than at the import that failed.

``feature_routers`` already had the answer (#6797, #6808): a structured result
per entry, a summary escalated to ERROR when fewer loaded than were configured,
and a health surface reading the results instead of the logs. This module is
that mechanism, extracted so all seven groups reach it rather than a seventh
copy being written.

Declared-optional vs failed
---------------------------

Every entry here is "optional" in the sense that its absence does not stop the
boot. That is why the two cases looked alike. The distinction this restores is
that appearing in a registry config means the router is *expected in this
build*: absent-and-configured is a gap worth an ERROR, while a module genuinely
not shipped is not in the config to begin with.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Iterable, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# group name -> load results, one entry per configured router.
# Per uvicorn worker, like the #6797 registry it generalizes: each worker
# imports its own routers, so this is that worker's view. The feature group
# additionally publishes to Redis for a cross-worker read (#6808).
_LOAD_RESULTS: Dict[str, List[Dict[str, Any]]] = {}


def record_result(group: str, name: str, module_path: str, error: str | None) -> None:
    """Record one router's load outcome under *group*.

    Args:
        group: registry group name, e.g. ``"feature"``.
        name: human-readable router name.
        module_path: module that was imported.
        error: ``None`` when loaded, else the exception rendered for an operator.
    """
    _LOAD_RESULTS.setdefault(group, []).append(
        {
            "name": name,
            "module": module_path,
            "loaded": error is None,
            "error": error,
            "group": group,
        }
    )


def reset_group(group: str) -> None:
    """Drop *group*'s results before a reload.

    Test environments load a registry several times in one process, and a
    stale entry would make a router look loaded when the current pass did not
    load it.
    """
    _LOAD_RESULTS[group] = []


def get_load_results(group: str | None = None) -> List[Dict[str, Any]]:
    """Return load results — one group, or every group when *group* is None.

    Returns a copy, so callers may mutate freely.
    """
    if group is not None:
        return list(_LOAD_RESULTS.get(group, []))
    return [dict(entry) for entries in _LOAD_RESULTS.values() for entry in entries]


def load_single_router(
    group: str,
    module_path: str,
    prefix: str,
    tags: List[str],
    name: str,
    router_attr: str = "router",
) -> Tuple | None:
    """Import one router and record the outcome.

    Args:
        router_attr: attribute holding the router. The monitoring group
            names it per entry; every other group uses ``router``.

    Returns:
        ``(router, prefix, tags, name)``, or None when the module could not be
        imported or carries no ``router`` attribute.
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, router_attr)
        logger.info("✅ Optional router loaded: %s", name)
        record_result(group, name, module_path, None)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        record_result(group, name, module_path, f"ImportError: {e}")
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router not found in module %s: %s - %s", module_path, name, e)
        record_result(group, name, module_path, f"AttributeError: {e}")
        return None


def log_group_summary(group: str, loaded: int, expected: int) -> List[Dict[str, Any]]:
    """Emit the loaded/expected summary, at ERROR when any router is missing.

    Returns:
        The failed entries, so a caller wanting to escalate further (the
        feature group's strict mode) does not re-derive them.
    """
    failed = [r for r in get_load_results(group) if not r["loaded"]]
    if loaded < expected:
        logger.error(
            "📊 Loaded %s/%s %s routers — %s FAILED: %s",
            loaded,
            expected,
            group,
            len(failed),
            ", ".join(r["name"] for r in failed),
        )
    else:
        logger.info("📊 Loaded %s/%s %s routers", loaded, expected, group)
    return failed


def _unpack(config: Tuple) -> Tuple:
    """Normalise a config entry to ``(module, prefix, tags, name, router_attr)``.

    The monitoring group carries the router attribute second — a 5-tuple —
    while the rest are 4-tuples that mean ``router``. Normalising here is
    what lets one loader serve both instead of the shapes justifying two.
    """
    if len(config) == 5:
        module_path, router_attr, prefix, tags, name = config
        return (module_path, prefix, tags, name, router_attr)
    module_path, prefix, tags, name = config
    return (module_path, prefix, tags, name, "router")


def load_router_group(group: str, configs: Iterable[Tuple]) -> List[Tuple]:
    """Load every router in *configs*, recording results and summarising.

    Args:
        group: registry group name used in results and log lines.
        configs: ``(module_path, prefix, tags, name)`` tuples.

    Returns:
        The tuples for routers that imported successfully.
    """
    reset_group(group)
    configs = list(configs)

    routers = [result for config in configs if (result := load_single_router(group, *_unpack(config))) is not None]

    log_group_summary(group, len(routers), len(configs))
    return routers
