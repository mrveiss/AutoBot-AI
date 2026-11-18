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


#: Restart precedence by systemd unit name (#17455, owner decision 2026-10-10).
#: ``autobot-chromadb`` must be running before ``autobot-ai-stack`` comes up and
#: connects to it. Names are the units the ai-stack role installs (code_sync's
#: ``_COMPONENT_SERVICES["autobot-ai-stack"]``; ``roles/ai-stack/handlers``
#: restarts chromadb first). A unit not listed keeps its incoming position.
_RESTART_PRECEDENCE = ("autobot-chromadb", "autobot-ai-stack")

#: Units that go LAST, after every other action (#17455, #11496). Restarting
#: the SLM backend kills the process running the sync, so anything scheduled
#: after it would never run. Mirrors ``code_sync._SELF_SERVICE_NAME``.
_RESTART_LAST_UNITS = ("autobot-slm-backend",)


def _precedence(action: _ActionT) -> int:
    ranks = [_RESTART_PRECEDENCE.index(u) for u in _units(action) if u in _RESTART_PRECEDENCE]
    return min(ranks) if ranks else 0


def _is_last(action: _ActionT) -> bool:
    return any(unit in _RESTART_LAST_UNITS for unit in _units(action))


def _split_last_units(action: _ActionT) -> List[_ActionT]:
    """A restart naming both ordinary and last units becomes two actions."""
    units = _units(action)
    tail = [u for u in units if u in _RESTART_LAST_UNITS]
    head = [u for u in units if u not in _RESTART_LAST_UNITS]
    if not tail or not head or _rank(action) != _CATEGORY_RANK["restart"]:
        return [action]
    return [_with_units(action, head), _with_units(action, tail)]


def _with_units(action: _ActionT, units: List[str]) -> _ActionT:
    return action.model_copy(update={"systemd_service": " ".join(units), "label": f"Restart {' '.join(units)}"})


def ordered_post_sync_plan(actions: Iterable[_ActionT]) -> List[_ActionT]:
    """*actions* in an order a reader can execute top to bottom.

    Stable within a category: two roles' installs keep the order the caller
    produced them in, so the output changes only when the roles do. Actions
    touching ``_RESTART_LAST_UNITS`` go after everything else whatever their
    category; chromadb restarts before ai-stack's (#17455).
    """
    incoming = [piece for a in actions for piece in _split_last_units(a)]
    last = [a for a in incoming if _is_last(a)]
    rest = [a for a in incoming if not _is_last(a)]
    restarts = [a for a in rest if _rank(a) == _CATEGORY_RANK["restart"]]
    others = [a for a in rest if _rank(a) != _CATEGORY_RANK["restart"]]

    ordered = sorted(others, key=_rank)
    ordered.extend(sorted(_without_duplicate_units(restarts), key=_precedence))
    ordered.extend(_last_group(last))
    return ordered


def _last_group(last: List[_ActionT]) -> List[_ActionT]:
    """The self-killing unit's actions: non-restarts first, its restart at the very end."""
    restart = _CATEGORY_RANK["restart"]
    before = sorted((a for a in last if _rank(a) != restart), key=_rank)
    return before + _without_duplicate_units([a for a in last if _rank(a) == restart])


__all__ = ["ordered_post_sync_plan"]
