# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who a knowledge-base write is for -- the guard on caller-supplied ownership (#19517).

Any metadata an agent, an MCP client or a task payload hands to a KB write is the caller's
text: ``visibility: system`` made a fact readable by every signed-in user, ``owner_id``
filed it under someone else. :func:`guard_caller_metadata` is the one rule, applied in
``KnowledgeBase.store_fact`` / ``update_fact`` (every ``add_document`` / ``add_file`` /
``add_content`` write ends in ``store_fact``).

A write is a *caller* write only when the code that took it from a caller entered a
:func:`caller_write_scope`. That scope is a ``ContextVar`` set by Python code at the
boundary -- never read out of the metadata, so a caller's claim to be internal (an
``ingest_route`` or ``source_type`` of its choosing) changes nothing. A write made with
no scope is system-internal ingest (sync, connectors, diaries, imports) and keeps the
ownership its own code set.

Inside a scope an admin sets ownership as asked; anyone else's ownership fields are
dropped (:func:`knowledge.ownership_index.drop_ownership_unless_admin`) and their own
id and organisation are stamped from the verified principal. A non-admin scope with no
principal id refuses the write: an ownerless fact is not private, it is up for
reclassification (``knowledge.ingestion_visibility``).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_principal_id
from knowledge.ownership_index import drop_ownership_unless_admin
from llm_shared.run_credentials import get_llm_principal

logger = get_logger(__name__)


class KbWriteDenied(PermissionError):
    """A caller-controlled write with no verified principal to own it."""


@dataclass(frozen=True)
class CallerWrite:
    """The verified principal a caller-controlled write is made for."""

    user_id: Optional[str] = None
    org_id: Optional[str] = None
    role: Optional[str] = None


_CALLER_WRITE: ContextVar[Optional[CallerWrite]] = ContextVar("kb_caller_write", default=None)


@contextmanager
def caller_write_scope(user_id: Any = None, org_id: Any = None, role: Any = None) -> Iterator[CallerWrite]:
    """Mark the KB writes in this ``with`` block as made on behalf of a caller; reset on exit."""
    principal = CallerWrite(str(user_id) if user_id else None, str(org_id) if org_id else None, role)
    token = _CALLER_WRITE.set(principal)
    try:
        yield principal
    finally:
        _CALLER_WRITE.reset(token)


def caller_write_scope_for(user: Optional[Dict[str, Any]]) -> Any:
    """:func:`caller_write_scope` for an authenticated user dict: its id, organisation and role."""
    user = user or {}
    return caller_write_scope(resolve_principal_id(user), user.get("org_id"), user.get("role"))


async def add_document_as(kb: Any, user: Optional[Dict[str, Any]], **document: Any) -> Any:
    """``kb.add_document(**document)`` as the authenticated *user*: their ownership, never the payload's."""
    with caller_write_scope_for(user):
        return await kb.add_document(**document)


def agent_write_scope() -> Any:
    """:func:`caller_write_scope` for an agent's tool call: the turn's signed-in user, never an admin."""
    user_id, org_id = get_llm_principal() or (None, None)
    return caller_write_scope(user_id, org_id)


def current_caller_write() -> Optional[CallerWrite]:
    """The principal of the enclosing :func:`caller_write_scope`, or None for a system-internal write."""
    return _CALLER_WRITE.get()


def guard_caller_metadata(metadata: Optional[Dict[str, Any]], *, stamp: bool = True) -> Optional[Dict[str, Any]]:
    """*metadata* as the enclosing caller may write it; unchanged outside a :func:`caller_write_scope`.

    ``stamp=False`` is for an update, which edits fields and must not re-own the fact.
    """
    caller = _CALLER_WRITE.get()
    if caller is None:
        return metadata
    if is_admin_role(caller.role):
        return metadata
    if stamp and not caller.user_id:
        logger.warning("Refused a KB write from a caller scope with no verified principal")
        raise KbWriteDenied("A knowledge-base write needs a verified principal to own it")
    guarded = drop_ownership_unless_admin(metadata, caller.role)
    if stamp:
        guarded["owner_id"] = caller.user_id
        if caller.org_id:
            guarded["organization_id"] = caller.org_id
    return guarded
