# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot_shared/llm_provider_candidates.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which providers a request may be served by, in what order (#15500).

Split out of ``llm_shared/provider_registry.py`` so the priority rules can be
read and tested on their own, and so the registry keeps room under MAX_LINES.
It sits beside ``llm_provider_order`` rather than under ``llm_shared/`` for the
same reason that module does: ``autobot-backend/conftest.py`` replaces the whole
``llm_shared`` package with a stub that has no real ``__path__`` and real-loads
only the submodules it names, so a new module there is a module the backend test
suite cannot import (#15500).

The asymmetry here is the point. An explicit provider, a conversation override
and an org preference each NAME a provider, and a caller who names one reaches
it whatever the configured order says. The step after them names nobody -- it is
"every other registered provider" -- so an order that lists its providers
exhaustively has to hold the unnamed ones out of that step, or the setting is a
preference that reorders and never an exclusion that excludes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from autobot_shared.llm_provider_order import ORDER_ENV_VAR, provider_is_permitted


@dataclass(frozen=True)
class CandidateSelection:
    """The candidates for one request, plus what the configured order held out.

    ``excluded`` is carried rather than discarded so an empty ``candidates`` can
    say *why* it is empty: nothing unreachable, nothing misconfigured, the order
    simply permitted none of what is registered. Reported as unreachability it
    would send an operator to look at credentials and network for a setting they
    chose themselves.
    """

    candidates: tuple[str, ...]
    excluded: tuple[str, ...]


def build_candidate_selection(
    *,
    explicit: str | None,
    conversation_preference: str | None,
    org_preference: str | None,
    chain: Sequence[str],
    registered: Iterable[str],
) -> CandidateSelection:
    """Order the candidates for one request.

    Priority: explicit provider, conversation override, org preference (#4451),
    the configured fallback chain, then every remaining *permitted* provider.
    """
    candidates: List[str] = []

    for named in (explicit, conversation_preference, org_preference):
        if named and named not in candidates:
            candidates.append(named)

    for name in chain:
        if name not in candidates:
            candidates.append(name)

    excluded: List[str] = []
    for name in registered:
        if name in candidates:
            continue
        if provider_is_permitted(name):
            candidates.append(name)
        else:
            excluded.append(name)

    return CandidateSelection(candidates=tuple(candidates), excluded=tuple(excluded))


def describe_exclusions(selection: CandidateSelection) -> str | None:
    """What the configured order held out of this request, or None if nothing was."""
    if not selection.excluded:
        return None
    return f"{ORDER_ENV_VAR} excludes {', '.join(sorted(selection.excluded))} from request selection"


def describe_exhaustion(selection: CandidateSelection) -> str:
    """Why no provider was returned, in terms the operator can act on.

    Three different situations reached one message before this existed, and only
    one of them was an availability problem. Telling an operator that every
    provider is unavailable, when what happened is that their own order held the
    one healthy provider out of selection, sends them to check credentials and
    networking for a setting they chose. So the exclusion is named whenever there
    is one, whether or not anything was left to try.
    """
    excluded = ", ".join(sorted(selection.excluded))
    if not selection.candidates:
        if selection.excluded:
            return (
                f"No provider permitted for this request: {excluded} "
                f"excluded by {ORDER_ENV_VAR}, and nothing else is registered"
            )
        return "No provider registered for this request"
    if selection.excluded:
        return (
            f"Every permitted provider is unavailable: tried {', '.join(selection.candidates)}; "
            f"{excluded} held out by {ORDER_ENV_VAR}"
        )
    return "All providers unavailable or not configured"
