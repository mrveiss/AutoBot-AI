# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-call budget gate for chat LLM calls (#16845).

Budget policy used to act only after spend, and only on an agent: the cost
tracker evaluates policies when a record carries an ``agent_id``, and the
action pauses that agent. Chat traffic carries none, so a budget configured
for a user or a company never stopped a chat request.

This module refuses the request instead, before the LLM call. Identity is the
LLM principal (``llm_shared.run_credentials``), set once per chat turn and per
compat-gateway request; policies are looked up under ``user`` and ``tenant``
(the principal's org) scope and compared with that scope's spend:

* user   -> ``llm_cost:by_user:{id}:daily:{date}``, written by the cost tracker
* tenant -> ``llm_cost:by_tenant:{id}:daily:{date}``, written here by
  :func:`record_tenant_spend` (the tracker keeps no per-tenant figure)

Only ``pause`` and ``alert_then_pause`` policies refuse, as in
``budget_policy.evaluate_policies``; ``alert`` never does. No policy, no
principal, or no spend means no refusal.

If the budget store cannot be read the request is allowed and the failure is
logged with its traceback, exactly as ``trigger_budget_evaluation`` behaves:
an unreachable store must not turn every chat into an outage.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from fastapi import HTTPException

from autobot_shared.category_defaults import CategoryDefaults
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_async_redis_client
from autobot_shared.time_utils import now_utc
from constants.ttl_constants import TTL_90_DAYS
from llm_shared.models import LLMResponse
from llm_shared.run_credentials import get_llm_principal
from services.budget_policy import (
    ACTION_ALERT_THEN_PAUSE,
    ACTION_PAUSE,
    PERIOD_HOUR,
    SCOPE_TENANT,
    SCOPE_USER,
    BudgetPolicy,
    get_namespace_period_spend,
    list_policies_for_scope,
)
from services.llm_cost_tracker import LLMCostTracker

logger = get_logger(__name__)

CHAT_BUDGET_ERROR_CODE = "chat_budget_exhausted"
#: Frontend i18n key for the refusal text; the English ``message`` is the API fallback.
CHAT_BUDGET_I18N_KEY = "chat.errors.budgetExhausted"
CHAT_BUDGET_STATUS = 402

USER_SPEND_NS = LLMCostTracker.USER_TOTALS_KEY
TENANT_SPEND_NS = f"{LLMCostTracker.REDIS_KEY_PREFIX}by_tenant"
_REFUSING_ACTIONS = (ACTION_PAUSE, ACTION_ALERT_THEN_PAUSE)
_SCOPE_NAMESPACES = {SCOPE_USER: USER_SPEND_NS, SCOPE_TENANT: TENANT_SPEND_NS}


class ChatBudgetExceeded(HTTPException):
    """A chat request refused because a budget policy's hard stop is reached.

    An ``HTTPException`` so the API surfaces it as a 402 with a structured
    body wherever it propagates; non-HTTP callers get a typed exception.
    """

    def __init__(self, policy: BudgetPolicy, spend_usd: float) -> None:
        self.policy = policy
        self.spend_usd = spend_usd
        self.message = (
            f"Your {policy.period} spending limit for this {policy.scope} "
            f"(${policy.threshold_usd:.2f}) has been reached. Chat is unavailable until it resets "
            "or an administrator raises the limit."
        )
        super().__init__(
            status_code=CHAT_BUDGET_STATUS,
            detail={
                "error_code": CHAT_BUDGET_ERROR_CODE,
                "message": self.message,
                "i18n_key": CHAT_BUDGET_I18N_KEY,
                "i18n_params": {"scope": policy.scope, "period": policy.period, "limit": f"{policy.threshold_usd:.2f}"},
            },
        )

    def __str__(self) -> str:
        return self.message


def _scopes_for(user_id: str, org_id: str) -> List[Tuple[str, str]]:
    """The ``(scope, scope_id)`` pairs a principal's policies live under, narrowest first."""
    pairs = [(SCOPE_USER, user_id), (SCOPE_TENANT, org_id)]
    return [(scope, scope_id) for scope, scope_id in pairs if scope_id]


async def _first_hard_stop(scope: str, scope_id: str) -> ChatBudgetExceeded | None:
    for policy in await list_policies_for_scope(scope, scope_id):
        if policy.action not in _REFUSING_ACTIONS or policy.threshold_usd <= 0:
            continue
        if policy.period == PERIOD_HOUR:
            # No hourly counter exists: ``get_namespace_period_spend`` answers an hour policy with the DAY total,
            # which would refuse someone under their hourly budget. Skipped until an hourly counter is written.
            continue
        spend = await get_namespace_period_spend(_SCOPE_NAMESPACES[scope], scope_id, policy.period)
        if spend >= policy.threshold_usd:
            return ChatBudgetExceeded(policy, spend)
    return None


async def _find_hard_stop(user_id: str, org_id: str) -> ChatBudgetExceeded | None:
    for scope, scope_id in _scopes_for(user_id, org_id):
        hit = await _first_hard_stop(scope, scope_id)
        if hit is not None:
            return hit
    return None


async def _audit_refusal(exc: ChatBudgetExceeded, user_id: str, org_id: str) -> None:
    """Record the refusal in the unified audit log; a failure to audit is logged, never hides the refusal."""
    try:
        from services.audit.audit import AuditCategory, AuditEvent
        from services.audit.audit import record as record_unified_event

        await record_unified_event(
            AuditEvent(
                category=AuditCategory.GOVERNANCE,
                action="budget.chat_refused",
                actor_id=user_id or "unknown",
                resource_type="budget_policy",
                resource_id=exc.policy.id,
                outcome="denied",
                metadata={
                    "scope": exc.policy.scope,
                    "scope_id": exc.policy.scope_id,
                    "period": exc.policy.period,
                    "current_spend_usd": exc.spend_usd,
                    "threshold_usd": exc.policy.threshold_usd,
                    "org_id": org_id,
                },
            )
        )
    except Exception:
        logger.exception("Failed to audit chat budget refusal for policy=%s", exc.policy.id)


async def enforce_chat_budget(user_id: str | None = None, org_id: str | None = None) -> None:
    """Raise :class:`ChatBudgetExceeded` when the caller's user or tenant budget is exhausted.

    ``user_id`` / ``org_id`` default to the current LLM principal.
    """
    principal_user, principal_org = get_llm_principal() or ("", "")
    uid, org = user_id or principal_user, org_id or principal_org
    try:
        exceeded = await _find_hard_stop(uid, org)
    except Exception:
        logger.exception("Chat budget check failed for user=%s org=%s; allowing the request", uid, org)
        return
    if exceeded is not None:
        await _audit_refusal(exceeded, uid, org)
        raise exceeded


async def chat_budget_refusal(request: Any) -> LLMResponse | None:
    """An error ``LLMResponse`` marked as a budget refusal when the caller's budget is exhausted, else None.

    For callers whose contract is an error *response* rather than an exception
    (``LLMService.chat``). The marker is ``metadata["error_code"]``; recognise it
    with :func:`is_budget_refusal` / :func:`budget_refusal_reply`, never by the text.
    """
    try:
        await enforce_chat_budget()
    except ChatBudgetExceeded as exc:
        return LLMResponse(
            content="",
            model=request.model_name or "",
            provider="budget",
            request_id=request.request_id,
            error=exc.message,
            metadata={"error_code": CHAT_BUDGET_ERROR_CODE, **_refusal_detail(exc)},
        )
    return None


def _refusal_detail(exc: ChatBudgetExceeded) -> dict[str, Any]:
    return {"i18n_key": exc.detail["i18n_key"], "i18n_params": exc.detail["i18n_params"]}


def is_budget_refusal(response: Any) -> bool:
    """True for a response built by :func:`chat_budget_refusal`."""
    return (getattr(response, "metadata", None) or {}).get("error_code") == CHAT_BUDGET_ERROR_CODE


def budget_refusal_reply(response: Any) -> dict[str, Any] | None:
    """The assistant reply dict (with its i18n metadata) for a budget-refusal response, else None."""
    if not is_budget_refusal(response):
        return None
    meta = {k: response.metadata[k] for k in ("error_code", "i18n_key", "i18n_params")}
    return {"content": response.error, "role": CategoryDefaults.ROLE_ASSISTANT, "metadata": meta}


def attributed_user(user_id: str | None) -> str | None:
    """``user_id`` if the caller named one, else the current principal's user, else None."""
    return user_id or (get_llm_principal() or ("", ""))[0] or None


async def record_tenant_spend(record: Any) -> None:
    """Add ``record.cost_usd`` to the current principal's tenant daily total.

    The tracker keeps per-agent and per-user totals only; tenant budgets need
    their own. No-op without a principal org or a cost. A failure is logged and
    leaves the tenant total short, never failing the served call.
    """
    org = (get_llm_principal() or ("", ""))[1]
    cost = getattr(record, "cost_usd", 0) or 0
    if not org or cost <= 0:
        return
    try:
        redis = await get_async_redis_client(RedisDatabase.ANALYTICS)
        key = f"{TENANT_SPEND_NS}:{org}:daily:{now_utc().strftime('%Y-%m-%d')}"
        await redis.incrbyfloat(key, cost)
        await redis.expire(key, TTL_90_DAYS)
    except Exception:
        logger.exception("Tenant spend of $%.6f unrecorded for org=%s; its budget cannot see this call", cost, org)
