# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orphan-storage detector framework (#17038, #17039).

Detection lives with the owner of the data: each data-owning module builds
its own detector (read-only) and registers it here at import time, the same
way ``register_env_var`` calls register into ``autobot_shared.env_registry``
as a side effect. This module only aggregates and dispatches -- it holds no
storage knowledge of its own, matching #17038's design ("the SLM does not
guess from outside").

Deletion never happens through this module directly either: a caller runs
one detector's ``delete`` through ``delete_candidate()``, which re-checks
orphan status and the grace period at delete time (never trusting a stale
``list_candidates()`` result), and the detector deletes through its own
owning service. Wiring that call behind a human-approved request is the
caller's job (#17043) -- this framework has no concept of who approved
anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

GRACE_PERIOD_ENV = "AUTOBOT_ORPHAN_GRACE_HOURS"
DEFAULT_GRACE_PERIOD_HOURS = 24


def orphan_grace_period_hours() -> int:
    """Hours below which a candidate is excluded -- work in flight is never offered."""
    return env_int_clamped(GRACE_PERIOD_ENV, DEFAULT_GRACE_PERIOD_HOURS, min_v=1, max_v=720)


@dataclass(frozen=True)
class OrphanCandidate:
    """One orphan-storage candidate, as a detector reports it (#17039).

    ``location`` is a logical reference (e.g. ``"code-sources/<id>"``), never
    a host filesystem path -- no detector may put one in the API output.
    """

    provider: str
    id: str
    location: str
    size_bytes: int
    modified_at: str
    reason: str
    deletable: bool = True


@dataclass(frozen=True)
class DeleteResult:
    """The outcome of one delete attempt. ``deleted=False`` always carries why."""

    deleted: bool
    reason: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    """Whether one detector's listing actually ran (#17039 review, #17050).

    An outage that makes a detector raise must never be read as "this
    provider has no orphans" -- ``list_all_candidates()`` reports it here
    instead of swallowing it, so a caller can tell "nothing found" apart
    from "could not look" (MEASUREMENT_DISCIPLINE).
    """

    provider: str
    available: bool
    error: str | None = None


@dataclass(frozen=True)
class OrphanListing:
    """Every candidate found, plus which detectors actually ran."""

    candidates: list[OrphanCandidate]
    statuses: list[ProviderStatus]


@dataclass(frozen=True)
class OrphanDetector:
    """One data-owning module's read-only listing plus its own delete path."""

    provider: str
    list_candidates: Callable[[], Awaitable[list[OrphanCandidate]]]
    delete: Callable[[str], Awaitable[DeleteResult]]


_REGISTRY: dict[str, OrphanDetector] = {}


def register_detector(detector: OrphanDetector) -> None:
    _REGISTRY[detector.provider] = detector


def registered_providers() -> list[str]:
    return sorted(_REGISTRY)


async def list_all_candidates() -> OrphanListing:
    """Every registered detector's candidates, plus which ones actually ran.

    One detector's failure never hides the rest, and never reads as that
    detector reporting zero orphans either -- it shows up in ``statuses``
    as unavailable, with why.
    """
    candidates: list[OrphanCandidate] = []
    statuses: list[ProviderStatus] = []
    for provider, detector in _REGISTRY.items():
        try:
            candidates.extend(await detector.list_candidates())
            statuses.append(ProviderStatus(provider=provider, available=True))
        except Exception as exc:
            logger.error("Orphan detector %r failed to list candidates: %s", provider, exc)
            statuses.append(ProviderStatus(provider=provider, available=False, error=str(exc)))
    return OrphanListing(candidates=candidates, statuses=statuses)


async def delete_candidate(provider: str, candidate_id: str) -> DeleteResult:
    """Delete through the owning detector. Refused for an unregistered provider.

    An unexpected exception from the detector's own delete (not just a
    registry outage it already turns into a refusal) is caught here too --
    the safe outcome either way is "nothing was deleted", never an
    unhandled exception surfacing past this boundary.
    """
    detector = _REGISTRY.get(provider)
    if detector is None:
        return DeleteResult(deleted=False, reason=f"unknown provider {provider!r}")
    try:
        return await detector.delete(candidate_id)
    except Exception as exc:
        logger.error("Orphan detector %r failed to delete %r: %s", provider, candidate_id, exc)
        return DeleteResult(deleted=False, reason=f"delete failed: {exc}")
