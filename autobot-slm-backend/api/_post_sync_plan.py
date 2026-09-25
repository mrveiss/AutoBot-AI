# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Order post-sync actions and never restart a unit twice.

``roles.py`` builds a node's post-sync actions by walking its roles and
extending a list per role (``_classify_post_sync``). That is **role-major**, and
it produces a list nobody can execute top-to-bottom:

- a role's ``install`` can land after another role's ``restart``, so a service
  restarts before the dependency it needs is installed;
- the same systemd unit appears more than once, because a unit can be owned by
  more than one role (#16025 -- ``ollama`` backs both ``autobot-llm-cpu`` and
  ``autobot-llm-gpu``), so a node holding both roles restarts it twice.

Observed on a live node: ``ollama`` twice with identical labels, and
``autobot-celery`` twice -- once alone and once inside
``Restart autobot-backend autobot-celery``. The second pair is why deduplication
has to be at the **unit** level: the two labels differ, so comparing labels or
whole commands misses it.

This module is separate from ``roles.py`` because that file sits at its
600-line ratchet pin (691, shrink-only) and because the ordering policy is a
different concern from the route that serves it.

WHAT THIS DOES NOT DO. It does not say *why* an action is needed -- which
changed file or requirement triggered it -- because ``PostSyncAction`` carries
no field for that. A reader still sees "Install deps (AI Stack)" without
"because ``requirements-ai.txt`` changed". That is tracked separately; ordering
a list of unexplained actions is an improvement to the list, not an answer to
the question.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, TypeVar

#: Execution order. `install` first because everything else may need what it
#: installs; `restart` last because a restart is only correct once the code,
#: schema and assets it will load are in place. `schema` before `build` is
#: arbitrary between two independent steps -- they are ordered only so the
#: result is deterministic rather than dependent on role iteration order.
#:
#: A category absent from this mapping sorts last but before restarts, so a new
#: category added to `_classify_post_sync` degrades to "somewhere in the middle"
#: rather than silently landing after the restarts it should precede.
_CATEGORY_RANK = {"install": 0, "schema": 1, "build": 2, "restart": 4}
_UNKNOWN_CATEGORY_RANK = 3

_ActionT = TypeVar("_ActionT")


def _units(action: _ActionT) -> List[str]:
    """The systemd units an action restarts, in declaration order."""
    return [unit for unit in (getattr(action, "systemd_service", None) or "").split() if unit]


def _rank(action: _ActionT) -> int:
    return _CATEGORY_RANK.get(getattr(action, "category", ""), _UNKNOWN_CATEGORY_RANK)


def _without_duplicate_units(restarts: Sequence[_ActionT]) -> List[_ActionT]:
    """Restart actions with every unit scheduled at most once.

    Larger groups are considered first, deliberately. A role declaring
    ``autobot-backend autobot-celery`` restarts them together because they are
    meant to come back together; a separate role declaring ``autobot-celery``
    alone is a subset of that. Taking the larger group first keeps the intended
    grouping whole and drops the subset, rather than shrinking the group and
    leaving the single unit to restart on its own.

    Ties keep their incoming order, so the result is deterministic.
    """
    scheduled: set[str] = set()
    kept: List[_ActionT] = []

    for action in sorted(restarts, key=lambda a: -len(_units(a))):
        units = _units(action)
        if not units:
            # A restart action with no unit cannot be deduplicated on units and
            # is kept as-is; dropping it would hide a misconfigured role.
            kept.append(action)
            continue
        fresh = [unit for unit in units if unit not in scheduled]
        if not fresh:
            continue
        scheduled.update(fresh)
        if len(fresh) == len(units):
            kept.append(action)
        else:
            kept.append(
                action.model_copy(
                    update={
                        "systemd_service": " ".join(fresh),
                        "label": f"Restart {' '.join(fresh)}",
                    }
                )
            )
    return kept


def ordered_post_sync_plan(actions: Iterable[_ActionT]) -> List[_ActionT]:
    """*actions* in an order a reader can execute top to bottom.

    Stable within a category: two roles' installs keep the order the caller
    produced them in, so the output changes only when the roles do.
    """
    incoming = list(actions)
    restarts = [a for a in incoming if _rank(a) == _CATEGORY_RANK["restart"]]
    others = [a for a in incoming if _rank(a) != _CATEGORY_RANK["restart"]]

    ordered = sorted(others, key=_rank)
    ordered.extend(_without_duplicate_units(restarts))
    return ordered


__all__ = ["ordered_post_sync_plan"]
