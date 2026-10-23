# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one serving predicate: may this fact reach chat grounding or LLM context? (#18820, #18829).

A fact's trust state (``verification_status``) and its validity window
(``valid_from`` / ``valid_to`` / ``valid_until`` / ``is_active``) are written by
the knowledge store and the memory graph, but no read path consulted them as one
rule: rejected facts were served, and the graph compared ``valid_to`` as a
string, so a malformed value counted as valid. Every retrieval path that feeds
chat or LLM context asks this module instead of deciding locally.

Two layers, one rule:

* :data:`SERVING_TRUST_WHERE` -- the store-side vector-store ``where`` clause,
  AND-ed into the shared grounding filter (``knowledge/quarantine.py``) so the
  store never even ranks a withheld fact.
* :func:`serving_verdict` / :func:`is_servable` -- the final check, applied once in
  ``SearchMixin.search`` (via :func:`servable_response`) to what any mode returned, so a
  store-side bug cannot serve a rejected or expired fact. Validity is only checkable here: the stores hold timestamps as
  strings, and a string comparison is exactly the fail-open defect of #18829.

Fact shapes differ by store -- a search-result dict with a ``metadata`` mapping,
a graph entity dict, a ``RankedResult`` dataclass, an ``AtomicFact`` dataclass,
an ORM row with ``metadata_json``. :func:`_fact_field` reads all of them, so the
predicate itself is never forked per shape.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso

logger = get_logger(__name__)


class ServingVerdict(str, Enum):
    """The per-hit verdict (#18829). Only :attr:`VALID` is served."""

    VALID = "valid"
    REJECTED = "rejected"
    WITHHELD = "withheld"
    INVALIDATED = "invalidated"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    UNPARSEABLE = "unparseable"


#: The trust state that never serves -- decided, needs no further ruling (#18820).
REJECTED_STATE = "rejected"

#: Trust states whose serving behaviour is the open #18077 decision.
UNDECIDED_TRUST_STATES = frozenset({"unverified", "pending_review"})

#: #18077 seam -- the ONE line that decision flips. ``True`` keeps today's behaviour
#: (unverified and pending_review facts are served); ``False`` withholds them from
#: grounding on every path at once, store-side and in the final check.
UNDECIDED_TRUST_STATES_SERVE: bool = True

#: Every trust state withheld from grounding, derived from the seam above.
WITHHELD_TRUST_STATES = frozenset({REJECTED_STATE}) | (
    frozenset() if UNDECIDED_TRUST_STATES_SERVE else UNDECIDED_TRUST_STATES
)

#: Fields that end a fact's validity window. ``valid_to`` is the memory graph's
#: name, ``valid_until`` the extraction pipeline's; both mean the same instant.
VALIDITY_END_FIELDS = ("valid_to", "valid_until")
VALIDITY_START_FIELD = "valid_from"

_METADATA_FIELDS = ("metadata", "metadata_json")
_FALSE_STRINGS = frozenset({"false", "0"})


def _trust_where(states: frozenset[str]) -> dict:
    """The vector-store clause excluding *states*; a fact with no status at all still passes."""
    ordered = sorted(states)
    if len(ordered) == 1:
        return {"verification_status": {"$ne": ordered[0]}}
    return {"verification_status": {"$nin": ordered}}


#: Store-side half of the predicate, AND-ed into the shared grounding filter.
SERVING_TRUST_WHERE: dict = _trust_where(WITHHELD_TRUST_STATES)


def _attr_or_key(obj: Any, name: str) -> Any:
    """*name* from a mapping key or an attribute, else ``None``."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _fact_field(fact_like: Any, name: str) -> Any:
    """Read *name* from any fact shape: its metadata mapping first, then the object itself."""
    for container in _METADATA_FIELDS:
        metadata = _attr_or_key(fact_like, container)
        if isinstance(metadata, Mapping) and name in metadata:
            return metadata[name]
    return _attr_or_key(fact_like, name)


def _instant(value: Any) -> datetime | None:
    """A timestamp field as an aware datetime; ``None`` when unset. Raises ``ValueError`` on garbage."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return parse_utc_iso(value)


def _as_of_instant(as_of: datetime | str | None) -> datetime:
    """The instant validity is judged at -- now when unset. Raises ``ValueError`` on garbage."""
    if as_of is None:
        return datetime.now(tz=timezone.utc)
    instant = _instant(as_of)
    if instant is None:
        raise ValueError("serving_verdict: as_of is empty")
    return instant


def _is_inactive(value: Any) -> bool:
    """``is_active`` explicitly false -- a Redis hash stores it as the string ``"False"``."""
    if isinstance(value, str):
        return value.strip().lower() in _FALSE_STRINGS
    return value is False


def _trust_status(fact_like: Any) -> ServingVerdict | None:
    """The trust verdict, or ``None`` when the trust state does not withhold the fact.

    The state is compared case- and whitespace-insensitively (``" REJECTED "`` is rejected). An
    absent state (``None`` or empty) is a fact that predates the field and is served; a state
    that is present but not text cannot be read as a trust state, so it fails closed like an
    unparseable validity bound. Any other text is an open vocabulary and is served.
    """
    state = _fact_field(fact_like, "verification_status")
    if state is None:
        return None
    if not isinstance(state, str):
        return ServingVerdict.UNPARSEABLE
    state = state.strip().lower()
    if state == REJECTED_STATE:
        return ServingVerdict.REJECTED
    if state in WITHHELD_TRUST_STATES:
        return ServingVerdict.WITHHELD
    return None


def _validity_status(fact_like: Any, at: datetime) -> ServingVerdict:
    """The validity verdict at *at*. An unparseable bound fails closed (#18829)."""
    if _is_inactive(_fact_field(fact_like, "is_active")):
        return ServingVerdict.INVALIDATED
    try:
        start = _instant(_fact_field(fact_like, VALIDITY_START_FIELD))
        ends = [_instant(_fact_field(fact_like, name)) for name in VALIDITY_END_FIELDS]
    except ValueError:
        return ServingVerdict.UNPARSEABLE
    if start is not None and start > at:
        return ServingVerdict.NOT_YET_VALID
    if any(end is not None and end < at for end in ends):
        return ServingVerdict.EXPIRED
    return ServingVerdict.VALID


def serving_verdict(fact_like: Any, as_of: datetime | str | None = None) -> ServingVerdict:
    """The verdict for one fact at *as_of* (default: now). Trust is judged before validity.

    Raises ``ValueError`` when *as_of* itself is unparseable -- that is the caller's input,
    not the fact's, and guessing an instant would answer a different question.
    """
    trust = _trust_status(fact_like)
    if trust is not None:
        return trust
    return _validity_status(fact_like, _as_of_instant(as_of))


def is_servable(fact_like: Any, as_of: datetime | str | None = None) -> bool:
    """Whether *fact_like* may reach chat grounding or LLM context at *as_of* (default: now)."""
    return serving_verdict(fact_like, as_of) is ServingVerdict.VALID


def servable(items: Iterable[Any] | None) -> List[Any]:
    """*items* without any fact that may not be served now, order preserved."""
    pool = list(items or ())
    kept = [item for item in pool if is_servable(item)]
    if len(kept) != len(pool):
        logger.debug("Serving predicate withheld %d of %d hit(s)", len(pool) - len(kept), len(pool))
    return kept


def _fewer(items: Any, kept: list) -> int:
    """How many entries *servable* dropped from *items*."""
    return len(items) - len(kept)


def _servable_cluster(cluster: Any) -> Any:
    """A response cluster without the hits that may not be served; counts follow."""
    if not isinstance(cluster, dict) or not isinstance(cluster.get("results"), list):
        return cluster
    kept = servable(cluster["results"])
    dropped = _fewer(cluster["results"], kept)
    out = {**cluster, "results": kept}
    if dropped and isinstance(out.get("result_count"), int):
        out["result_count"] = max(0, out["result_count"] - dropped)
    return out


def _reduced(response: dict, key: str, dropped: int) -> None:
    """Lower the integer count *key* of *response* by *dropped*, never below zero."""
    if dropped and isinstance(response.get(key), int):
        response[key] = max(0, response[key] - dropped)


def servable_response(response: Any) -> Any:
    """A KB search response without the facts that may not be served now.

    The single place the predicate meets a search result, whatever the mode returned: a list of
    hits (basic) or a response dict whose ``results`` and ``clusters`` carry hits (enhanced and
    advanced). Anything else -- an error dict without ``results`` -- is returned untouched.
    """
    if isinstance(response, list):
        return servable(response)
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return response
    kept = servable(response["results"])
    out = {**response, "results": kept}
    dropped = _fewer(response["results"], kept)
    _reduced(out, "total_count", dropped)
    _reduced(out, "unclustered_count", dropped)
    if isinstance(out.get("clusters"), list):
        out["clusters"] = [_servable_cluster(c) for c in out["clusters"]]
    return out
