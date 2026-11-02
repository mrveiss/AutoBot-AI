# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""THE enforcement point for the three AI lines (#18430, folds #17463).

Owner rule 2026-10-12: for every ACTION of every tool, AI has one of three lines --
autonomous (run, then report), AI drafts and a person sends (waits in Approvals), or AI never
touches. An unset line counts as line 2. Agents never change a line.

Every surface where an agent acts resolves its line HERE, and only here:

* the chat tool seam      -- ``chat_workflow.tool_dispatch_guards.enforce_ai_line``
* the agent terminal      -- ``services.agent_terminal.service.AgentTerminalService.execute_command``

and nothing else decides whether an agent may act without a person. The pieces that used to
decide on their own are INPUTS here, and can only tighten:

* the approval baseline (#18294) -- a category in the baseline can never be line 1, except that a
  shell command which only reads never gets a baseline category (#19950);
* the role policy ``CommandApprovalManager.needs_approval`` (#17463) -- a role that needs
  approval for a risk can never be line 1;
* the work item's declared ``requires_approval_before`` -- the same floor, add-only.

Failure fails closed: an unreadable line store refuses, an unreadable baseline gates every
category, and an approval that cannot be recorded still leaves the action un-run.

``repo_tests/ai_line_single_policy_18430_test.py`` fails if a second approval decision appears.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

from autobot_shared.ai_lines import (
    SCOPE_COMPANY,
    VERIFIED_COMPANY_KEY,
    VERIFIED_USER_KEY,
    AiLine,
    LineResolution,
    LineScope,
    action_key,
    is_mutating,
    resolve_line,
    resolve_scope,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import redact_nested
from autobot_shared.ssot_config import config as ssot_config
from autobot_shared.status_enums import CommandRisk
from autobot_shared.tool_catalogue import approval_category_for, valid_approval_categories
from llc.services.ai_lines import stored_line
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.audit_logger import audit_log
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

#: Kind markers in ``Approval.context`` -- NOT ``action``, which would dispatch a post-approval
#: handler; a held tool call has nothing to execute on approval (HOOK for #18404 is in ``_file_hold``).
KIND_HOLD = "ai_line_hold"
REQUESTER_PREFIX = "ai-line"

#: The tool name a shell command carries in the tool-effect catalogue.
TERMINAL_TOOL = "execute_command"


class Outcome(str, Enum):
    RUN = "run"
    HOLD = "hold"
    REFUSE = "refuse"


@dataclass(frozen=True)
class LineVerdict:
    """What the enforcement point decided for one action."""

    outcome: Outcome
    resolution: LineResolution
    approval_id: Optional[str] = None
    approval_recorded: bool = False

    @property
    def message(self) -> str:
        key, why = self.resolution.key, self.resolution.reason
        if self.outcome is Outcome.RUN:
            return f"'{key}' ran on line 1 (autonomous) and was reported"
        if self.outcome is Outcome.REFUSE:
            return f"'{key}' is refused: AI never touches this action ({why})"
        return f"Action '{key}' requires approval before proceeding: AI drafts, a person sends ({why})"


async def gated_categories(declared: Iterable[str]) -> list[str]:
    """Baseline categories plus the declared ones. An unreadable baseline gates EVERY category."""
    try:
        from chat_workflow.approval_baseline import baseline_approval_categories

        baseline = await baseline_approval_categories()
    except Exception as exc:  # noqa: BLE001 - fail closed on any read failure
        logger.error("Approval baseline unreadable (%s); every category stays gated", exc)
        baseline = sorted(valid_approval_categories())
    return sorted(set(baseline) | {c for c in declared if isinstance(c, str)})


async def _stored(scope: Optional[LineScope], key: str) -> tuple[Optional[AiLine], bool]:
    """``(stored line, store unavailable)``. No scope means nothing to read a line from: unset."""
    if scope is None:
        return None, False
    try:
        async with get_async_session_factory()() as session:
            return await stored_line(session, scope.id, key, scope.kind), False
    except Exception as exc:  # noqa: BLE001 - fail closed
        logger.error("AI line store unreadable for %s (%s); failing closed", key, exc)
        return None, True


def _is_read_only_command(tool_name: str, params: Optional[Mapping[str, Any]]) -> bool:
    """Whether this call is a shell command rated SAFE that also only reads (#19950).

    The tool name says only "runs a command", so the command decides. SAFE alone is not enough: it covers
    ``git push`` and ``curl -X POST``. No command, or a classifier that cannot answer, is not read-only:
    the call keeps the tool's own line.
    """
    command = (params or {}).get("command") if tool_name == TERMINAL_TOOL else None
    if not command or not isinstance(command, str):
        return False
    try:
        from secure_command_executor import SecureCommandExecutor
        from security.read_only_commands import is_read_only_command

        risk, _reasons = SecureCommandExecutor(use_docker_sandbox=False).assess_command_risk(command)
        return risk is CommandRisk.SAFE and is_read_only_command(command)
    except Exception as exc:  # noqa: BLE001 - fail closed on an unreadable verdict
        logger.error("Command risk unreadable (%s); the command keeps its tool's line", exc)
        return False


async def resolve_action_line(
    tool_name: str,
    params: Optional[Mapping[str, Any]],
    company_id: Any,
    *,
    user_id: Any = None,
    declared_categories: Iterable[str] = (),
    role_requires_approval: bool = False,
) -> LineResolution:
    """Resolve the effective line for one action. Read-only: creates nothing, runs nothing.

    LineScope: the verified company; with none, the verified user's personal scope (#18430). A shell command that
    only reads gets no baseline category, so the baseline floor does not apply to it, and counts as not mutating
    (#19950); a work item's declared category still does. A company that is
    present but malformed is not a missing one and is never replaced by the user's scope.
    """
    key = action_key(tool_name, params)
    scope = resolve_scope(company_id, user_id)
    stored, unavailable = await _stored(scope, key)
    read_only = _is_read_only_command(tool_name, params)
    # A work item's own declared gate still applies to a read; the baseline's "destructive" one cannot.
    gated = list(declared_categories) if read_only else await gated_categories(declared_categories)
    category = approval_category_for(tool_name, gated)
    return resolve_line(
        key,
        stored=stored,
        mutating=not read_only and is_mutating(tool_name),
        baseline_category=category,
        role_requires_approval=role_requires_approval,
        store_unavailable=unavailable,
        scope_missing=scope is None,
    )


async def call_needs_approval(tool_call: Mapping[str, Any], ctx: Any) -> bool:
    """Plan-time projection for the chat graph's interrupt: any line stricter than line 1 (GH#11202).

    Asks the same resolver ``enforce_line`` applies, so the interrupt and the dispatch seam cannot disagree.
    """
    params = tool_call.get("params") or tool_call.get("arguments") or {}
    resolution = await resolve_action_line(
        tool_call.get("name", ""),
        params if isinstance(params, dict) else {},
        (getattr(ctx, "context", None) or {}).get(VERIFIED_COMPANY_KEY),
        user_id=(getattr(ctx, "context", None) or {}).get(VERIFIED_USER_KEY),
        declared_categories=getattr(ctx, "requires_approval_before", None) or (),
    )
    return resolution.line is not AiLine.AUTONOMOUS


def _fingerprint_key() -> bytes:
    """HMAC key derived from the platform session-signing secret, the way the auth middleware resolves it.

    ``ssot_config.jwt_secret``, else ``ssot_config.secret_key`` (``auth_middleware._get_jwt_secret``); the digest
    is domain-separated so the signing secret itself is never the HMAC key. With neither set it is random for
    this process: a fingerprint then cannot be matched after a restart, so an approval bound to it has to be
    given again, which is the safe direction. That choice is logged once, naming the setting and never a value.
    """
    secret = ssot_config.jwt_secret or ssot_config.secret_key
    if secret:
        return hashlib.sha256(b"ai-line-fingerprint:" + secret.encode()).digest()
    _warn_random_key_once()
    return _PROCESS_KEY


@functools.lru_cache(maxsize=1)
def _warn_random_key_once() -> None:
    logger.error(
        "AUTOBOT_JWT_SECRET (and SECRET_KEY) are unset: AI-line approvals are bound with a random per-process key "
        "and must be given again after a restart"
    )


_PROCESS_KEY = secrets.token_bytes(32)


def shown_call_fingerprint(tool_name: str, params: Optional[Mapping[str, Any]]) -> str:
    """HMAC of the RAW call (tool + params), so a person's yes is bound to exactly what they were shown.

    Raw, not redacted: two calls that differ only in a masked credential are different calls (#18430). The
    digest does not reveal the params.
    """
    body = json.dumps({"k": action_key(tool_name, params), "p": dict(params or {})}, sort_keys=True, default=str)
    return hmac.new(_fingerprint_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()


async def _existing_hold(session, company_id: Optional[uuid.UUID], requester: str, fingerprint: str) -> Approval | None:
    scope = Approval.company_id == company_id if company_id else Approval.company_id.is_(None)
    rows = await session.execute(
        select(Approval).where(
            scope,
            Approval.status == ApprovalStatus.PENDING.value,
            Approval.requested_by_agent == requester,
            Approval.context["fingerprint"].as_string() == fingerprint,
        )
    )
    return rows.scalars().first()


async def _file_hold(
    resolution: LineResolution,
    params: Mapping[str, Any],
    scope: LineScope,
    requested_by: str,
    surface: str,
) -> Approval:
    """File (or reuse) the pending approval for a line-2 action.

    HOOK: #18404's source/risk_tier go in ``context`` until that record lands, then into its columns.
    """
    requester = f"{REQUESTER_PREFIX}:{requested_by}"
    safe_params = redact_nested(dict(params))
    fingerprint = shown_call_fingerprint(resolution.key.split(":", 1)[0], params)
    company_id = scope.id if scope.kind == SCOPE_COMPANY else None  # a personal hold is an unscoped approval
    async with get_async_session_factory()() as session:
        existing = await _existing_hold(session, company_id, requester, fingerprint)
        if existing is not None:
            return existing
        return await ApprovalGateService(session).create_approval(
            title=f"AI drafted '{resolution.key}'; a person sends",
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent=requester,
            description=f"Line 2 for '{resolution.key}': {resolution.reason}. Nothing ran.",
            context={
                "kind": KIND_HOLD,
                "action_key": resolution.key,
                "surface": surface,
                "line_source": resolution.source,
                "params": safe_params,
                "fingerprint": fingerprint,
                "scope_kind": scope.kind,
                "scope_id": str(scope.id),
            },
            company_id=company_id,
        )


async def _report(verdict: LineVerdict, requested_by: str, surface: str) -> None:
    """Line 1 'then report', and the trail for refusals and holds. Best effort; never blocks the action."""
    try:
        await audit_log(
            f"ai_line.{verdict.outcome.value}",
            result="success",
            user_id=requested_by,
            resource=verdict.resolution.key,
            details={"surface": surface, "source": verdict.resolution.source, "approval_id": verdict.approval_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI line report for %s was not recorded: %s", verdict.resolution.key, exc)


async def enforce_line(
    *,
    tool_name: str,
    params: Optional[Mapping[str, Any]],
    company_id: Any,
    requested_by: str,
    surface: str,
    user_id: Any = None,
    declared_categories: Iterable[str] = (),
    role_requires_approval: bool = False,
    hold_in_approvals: bool = True,
    approved_fingerprints: frozenset[str] = frozenset(),
) -> LineVerdict:
    """Decide and apply the line for one agent action: line 1 RUN (reported), 2 HOLD, 3 REFUSE.

    ``hold_in_approvals=False`` is for a surface that holds the action in its own live queue (the terminal):
    the decision is still made here, the hold is not duplicated. ``approved_fingerprints`` are the
    calls a person was SHOWN and said yes to in the surface's own interrupt: a call whose :func:`shown_call_fingerprint`
    is in the set satisfies line 2; nothing satisfies line 3.
    """
    resolution = await resolve_action_line(
        tool_name,
        params,
        company_id,
        user_id=user_id,
        declared_categories=declared_categories,
        role_requires_approval=role_requires_approval,
    )
    if resolution.line is AiLine.NEVER:
        verdict = LineVerdict(Outcome.REFUSE, resolution)
    elif resolution.line is AiLine.AUTONOMOUS or shown_call_fingerprint(tool_name, params) in approved_fingerprints:
        verdict = LineVerdict(Outcome.RUN, resolution)
    else:
        verdict = await _hold(
            resolution, params or {}, resolve_scope(company_id, user_id), requested_by, surface, hold_in_approvals
        )
    await _report(verdict, requested_by, surface)
    return verdict


async def _hold(
    resolution: LineResolution,
    params: Mapping[str, Any],
    scope: Optional[LineScope],
    requested_by: str,
    surface: str,
    hold_in_approvals: bool,
) -> LineVerdict:
    if not hold_in_approvals or scope is None:
        return LineVerdict(Outcome.HOLD, resolution)
    try:
        approval = await _file_hold(resolution, params, scope, requested_by, surface)
    except Exception as exc:  # noqa: BLE001 - not recorded is still not run
        logger.error("Could not record the approval for held action %s: %s", resolution.key, exc)
        return LineVerdict(Outcome.HOLD, resolution)
    return LineVerdict(Outcome.HOLD, resolution, approval_id=str(approval.id), approval_recorded=True)
