# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Research-quarantine KB search filter (#12622, #12623, #13009).

``ResearchOrchestrator`` (#12622) lands web-research findings as KB facts
tagged ``metadata.collection == config.research_quarantine_collection``.
Those facts are quarantined -- invisible to every general-purpose chat/RAG
read -- until the corroboration + promotion gate (#12623) reviews them and
flips that metadata field.

``async_chat_workflow.py::_execute_kb_search`` was the first call site fixed
(#12622). #13009 audited every other ``kb.search()`` call site reachable
from a general-purpose surface and found several more with the same gap;
this module is the single shared filter so the exclusion is defined once
instead of copy-pasted at each call site.

The ``$ne`` operator also matches facts that predate the ``collection``
field entirely (no key at all) -- verified against the installed ChromaDB
(#12622) and against ``knowledge.backends.memory_adapter.InMemoryCollection``
(#12623), so pre-existing facts stay visible.

Research-internal readers (the corroboration/promotion gate itself --
``services/claim_verifier.py``, ``services/research/orchestrator.py``,
``services/research/planner.py``) must NOT use this filter: they exist to
read the quarantine collection.

The same filter carries the store-side half of the serving predicate
(#18820): ``knowledge.serving.SERVING_TRUST_WHERE`` is AND-ed in, so every
call site that already excludes quarantined facts also excludes rejected ones.
``KB.search`` applies ``knowledge.serving.is_servable`` to every result whatever the
``where`` (a reader that must see withheld facts passes ``include_unservable=True``).
"""

import copy
from typing import Any, Dict, Iterable

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge.serving import (
    SERVING_TRUST_WHERE,
    _fact_field,
    is_servable,
    is_servable_unquarantined,
    servable_response,
)
from knowledge.where_combine import and_where

logger = get_logger(__name__)


class QuarantineAuditFailed(HTTPException):
    """The audit entry an opt-out read owes was not written, so the read is refused (#19163).

    Fail closed: a privileged read nobody can account for is not served. It is an ``HTTPException``
    (503) so every route, and ``with_error_handling``, passes it through as the answer.
    """

    def __init__(self, surface: str) -> None:
        super().__init__(status_code=503, detail=f"Quarantine read audit unavailable on {surface}; nothing served")


#: Actors recorded by the backup and export paths, which must carry every fact (#19163).
BACKUP_AUDIT_ACTOR = "system:backup"
EXPORT_AUDIT_ACTOR = "system:export"

# Module-level constant (not a function): the filter is a static dict, cheap
# to import and share; no per-call construction needed.
_NOT_QUARANTINED_WHERE: dict = {"collection": {"$ne": config.research_quarantine_collection}}

RESEARCH_QUARANTINE_FILTER: dict = {"$and": [_NOT_QUARANTINED_WHERE, SERVING_TRUST_WHERE]}


def without_quarantine(caller_where: dict | None = None) -> dict:
    """Only the collection half of the filter, *caller_where* AND-ed in (a fresh copy).

    For ``KB.search`` when the caller opted out of the serving predicate but not of the quarantine.
    """
    return and_where(copy.deepcopy(_NOT_QUARANTINED_WHERE), caller_where)  # type: ignore[return-value]


def with_quarantine(caller_where: dict | None = None) -> dict:
    """The quarantine filter, with the caller's own ``where`` AND-ed in (#18946).

    A caller filter can only narrow what is served; it never replaces the quarantine
    (and serving-trust) predicate. ``None`` or ``{}`` yields the bare quarantine filter.
    """
    # A deep copy: ``and_where`` flattens into a new list but shares the inner clauses, so a caller
    # mutating the returned filter would otherwise rewrite the constant for every later read (#19163).
    return and_where(copy.deepcopy(RESEARCH_QUARANTINE_FILTER), caller_where)  # type: ignore[return-value]


def is_quarantined(fact_like: Any) -> bool:
    """Whether *fact_like* (any fact shape ``knowledge.serving`` reads) is a research-quarantined fact."""
    return _fact_field(fact_like, "collection") == config.research_quarantine_collection


def not_quarantined(fact_like: Any) -> bool:
    """The per-hit keep predicate of the default read: everything but quarantined facts."""
    return not is_quarantined(fact_like)


def quarantined_ids(facts: Iterable[Any]) -> list[str]:
    """The ids of the quarantined facts in *facts* (search hits or ``get_all_facts`` rows)."""
    return [_hit_id(f) for f in facts if is_quarantined(f)]


def _hit_id(fact_like: Any) -> str:
    """A fact's id from whichever key its shape carries."""
    for key in ("fact_id", "node_id", "id"):
        value = _fact_field(fact_like, key)
        if value:
            return str(value)
    return ""


async def audit_quarantine_read(actor: str | None, surface: str, ids: Iterable[str]) -> bool:
    """Write the one audit entry an opt-out read owes: who, which surface, how many, which ids (#19163).

    Goes through the canonical ``services.audit_logger.audit_log``; there is no second audit path.
    Raises :class:`QuarantineAuditFailed` when the entry is not written -- the caller then serves nothing.
    """
    from services.audit.taxonomy import AuditAction
    from services.audit_logger import audit_log

    id_list = list(ids)
    try:
        written = await audit_log(
            AuditAction.KNOWLEDGE_QUARANTINE_READ.value,
            user_id=actor,
            resource=surface,
            details={"surface": surface, "count": len(id_list), "ids": id_list},
        )
    except Exception as exc:
        raise QuarantineAuditFailed(surface) from exc
    if not written:
        raise QuarantineAuditFailed(surface)
    return True


async def apply_quarantine(facts: list, include_quarantined: bool, audit_actor: str | None) -> list:
    """``get_all_facts``' last step: drop quarantined facts, or audit the read that keeps them (#19163).

    The audit comes first; if it cannot be written :class:`QuarantineAuditFailed` propagates and no fact
    is returned.
    """
    if include_quarantined:
        await audit_quarantine_read(audit_actor, "kb.get_all_facts", quarantined_ids(facts))
        return facts
    return [f for f in facts if not_quarantined(f)]


def store_side_where(filters: Dict[str, Any] | None, include_unservable: bool, include_quarantined: bool):
    """The basic mode's ``where`` with the quarantine (and serving trust) clause AND-ed in (#19163)."""
    if include_quarantined:
        return filters
    return without_quarantine(filters) if include_unservable else with_quarantine(filters)


def keep_predicate(include_unservable: bool, include_quarantined: bool):
    """The per-hit check ``servable_response`` applies after the mode returned."""
    if include_unservable and include_quarantined:
        return lambda _hit: True
    if include_unservable:
        return not_quarantined
    if include_quarantined:
        return is_servable
    return is_servable_unquarantined


def response_hits(response: Any) -> list:
    """The hits of any mode's response: the list itself, or a response dict's ``results``."""
    if isinstance(response, list):
        return response
    results = response.get("results") if isinstance(response, dict) else None
    return results if isinstance(results, list) else []


def require_audit_actor(include_quarantined: bool, audit_actor: str | None) -> None:
    """An opt-out read is always audited, so it must say who is reading (#19163)."""
    if include_quarantined and not audit_actor:
        raise ValueError("include_quarantined=True needs audit_actor: an opt-out read is always audited")


async def gate_response(response: Any, include_unservable: bool, include_quarantined: bool, audit_actor: str | None):
    """The final check of ``KB.search``: audit an opt-out read, then drop what the caller did not opt into."""
    if include_quarantined:
        await audit_quarantine_read(audit_actor, "kb.search", quarantined_ids(response_hits(response)))
    return servable_response(response, keep_predicate(include_unservable, include_quarantined))


async def read_every_fact(kb: Any, actor: str, **kwargs: Any) -> list:
    """Every fact, quarantined ones included, through the audited opt-out (#19163).

    For backup and export, which must carry the ``collection`` marker of research facts so a
    restore puts them back quarantined; dropping them would lose the research data.
    """
    return await kb.get_all_facts(include_quarantined=True, audit_actor=actor, **kwargs)


def servable_unquarantined(results: Any) -> Any:
    """The serving check plus the quarantine check, for readers that bypass ``KB.search`` (#19163).

    The NPU search paths read the vector index or a FAISS/Chroma collection directly; they apply this
    in place of bare ``servable_response`` so a quarantined fact never reaches their callers either.
    """
    return servable_response(results, keep_predicate(False, False))
