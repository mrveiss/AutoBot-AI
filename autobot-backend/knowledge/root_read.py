# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The superadmin reads every knowledge fact: one audited bypass in the one visibility filter (#19860).

Owner decision (2026-10-28): "Superadmin is like a root user: it has access to every corner of the
system." It overrides, for the superadmin ONLY, the "no admin bypass" rule of #16654 T2 and of
``knowledge.search_filters.kb_principal``. An admin, an organisation owner and an organisation admin
are not superadmins and keep their visibility unchanged.

* The signal is the verified ``superadmin`` role claim (``Role.SUPERADMIN``), read from the
  authenticated user (:func:`is_superadmin_user`: a signed token or session), never from the development
  header, a request body, session metadata or a fact's metadata.
  ``TenantContext.is_platform_admin`` is NOT used: it is true for a plain admin as well.
* ``Principal.is_superadmin`` carries it; ``search_filters.filter_for_principal`` calls
  :func:`root_view`, so RAG, chat grounding and every scoped read share this one place.
* Every read the normal filter would have refused is audited as ``kb.admin_read`` with
  ``bypass="superadmin"``. If that entry cannot be written the bypassed facts are withheld and the
  caller gets exactly what the normal filter allowed (fail closed).
* The research quarantine is a separate store-side predicate (``knowledge.quarantine``) and is NOT
  lifted here: its only opt-out is the audited ``include_quarantined`` flag.
"""

from typing import Dict, List

from autobot_shared.auth.permissions import Role, role_value
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``details["bypass"]`` of the audit entry written for a root read.
ROOT_BYPASS_MARKER = "superadmin"


def is_superadmin_role(role: "Role | str | None") -> bool:
    """Whether a role claim is exactly ``superadmin`` (case-insensitive); admin is not."""
    return role_value(role).lower() == Role.SUPERADMIN.value


#: ``auth_method`` values whose role came out of a verified credential (a signed token or a server-side session).
#: ``development`` (the ``X-User-Role`` header, ``development.debug`` only), auth-disabled, run/device tokens and a
#: hand-built dict carry a role nobody verified (#19860).
_VERIFIED_AUTH_METHODS = frozenset({"jwt", "jwt_websocket", "session"})


def is_superadmin_user(user) -> bool:
    """Whether the authenticated *user* is a superadmin by a VERIFIED identity (#19860).

    A mapping must say how it authenticated (``auth_method``) and not be the auth-disabled identity;
    anything else reads as not a superadmin. An ORM user object comes from the user store itself.
    """
    getter = getattr(user, "get", None)
    if not callable(getter):
        return is_superadmin_role(getattr(user, "role", None))
    if getter("auth_method") not in _VERIFIED_AUTH_METHODS or getter("auth_disabled") or getter("service"):
        return False
    return is_superadmin_role(getter("role"))


async def audit_admin_read(user_id: str, details: Dict) -> bool:
    """Record an admin's explicit read (``kb.admin_read``), awaited; False when the row is not committed (#16665).

    ``durable``: ``audit_log`` otherwise only schedules the write and reports success, so the facts
    would be returned before any entry exists (#19860). A failure is logged and the caller withholds.
    """
    from services.audit.taxonomy import AuditAction  # noqa: PLC0415 -- keeps the audit stack off this import
    from services.audit_logger import audit_log  # noqa: PLC0415

    try:
        written = await audit_log(
            AuditAction.KNOWLEDGE_ADMIN_READ.value,
            user_id=user_id,
            resource="knowledge_base",
            details=details,
            durable=True,
        )
    except Exception:
        logger.error("kb.admin_read audit failed; withholding the admin read (#16665)", exc_info=True)
        return False
    if not written:
        logger.error("kb.admin_read audit was not committed; withholding the read (#19860)")
    return bool(written)


def _bypassed(everything: List[Dict], kept: List[Dict]) -> List[Dict]:
    """The facts in *everything* that the normal filter (*kept*) refused."""
    allowed = {id(r) for r in kept}
    return [r for r in everything if id(r) not in allowed]


async def root_view(results: List[Dict], principal, ownership_manager, kept: List[Dict]) -> List[Dict]:
    """What a superadmin *principal* reads of *results*; *kept* is the normal filter's answer (#19860).

    Reuses ``filter_search_results_by_permission`` with its explicit admin input and
    ``audit_admin_read``; there is no second filter. Returns *kept* unchanged when nothing was
    bypassed, or when the audit entry for the bypass cannot be written.
    """
    from knowledge.search_filters import (  # noqa: PLC0415 -- search_filters imports this module
        _fact_ids,
        filter_search_results_by_permission,
    )

    if not ownership_manager:
        logger.warning("superadmin root read without an ownership manager; returning the scoped view (#19860)")
        return kept

    everything = await filter_search_results_by_permission(
        results, principal.user_id, principal.company_id, [], ownership_manager=ownership_manager, is_admin=True
    )
    extra = _bypassed(everything, kept)
    if not extra:
        return kept
    details = {"fact_ids": _fact_ids(extra), "count": len(extra), "bypass": ROOT_BYPASS_MARKER}
    if await audit_admin_read(principal.user_id, details):
        return everything
    logger.error(
        "superadmin root read WITHHELD: audit not committed, %d bypassed fact(s) held back for user %s (#19860)",
        len(extra),
        principal.user_id,
    )
    return kept
