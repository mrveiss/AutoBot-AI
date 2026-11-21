# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The optional, pinned response judge behind the ``unsupported_claim`` category (#20843).

Off unless a judge model is named (``--judge-model`` / ``AUTOBOT_EVAL_JUDGE_MODEL``). It reuses
``AgentResponseJudge`` and the ``LLMService`` provider path; the only thing added is the model pin.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from eval.live_classify import LiveRunRecord
from eval.live_guard import RemoteProviderRefused, remote_allowed
from eval.runner import RecordingUnusable
from eval.store import GoldenTrajectory
from llm_shared.failover_policy import is_local_provider

#: ``(record, golden) -> True`` when the judge finds the answer unsupported.
Judge = Callable[[LiveRunRecord, GoldenTrajectory], Awaitable[bool]]


class PinnedLLM:
    """An ``LLMService`` view whose every ``chat`` names one model and the provider already checked as local.

    The reply's own provider is checked as well (a failover inside the service can change it), so a judge call
    that landed on a hosted provider is refused instead of used, unless the operator allowed remote providers.
    """

    def __init__(self, service: Any, model: str, provider: str | None = None, allow_remote: bool = False):
        self._service = service
        self.current_model = model
        self._provider = provider or None
        self._allow_remote = allow_remote

    async def chat(self, messages: list, **kwargs: Any) -> Any:
        if self._provider:
            kwargs.setdefault("provider_name", self._provider)
        response = await self._service.chat(messages, model_name=self.current_model, **kwargs)
        served = getattr(response, "provider", None)
        if served and not is_local_provider(served) and not (self._allow_remote or remote_allowed()):
            raise RemoteProviderRefused("the judge was served by a non-local provider; its verdict is discarded")
        return response


def response_judge(model: str, service: Any = None, provider: str | None = None, allow_remote: bool = False) -> Judge:
    """A judge pinned to *model*: ``unsupported`` when its ACCURACY score is below the judge's quality threshold.

    A judge that fails, or returns no ACCURACY score, raises ``RecordingUnusable``: the run is ``not_run``, never
    a pass on a judgment nobody made.
    """
    from judges import JudgmentDimension
    from judges.agent_response_judge import AgentResponseJudge

    if service is None:
        from services.llm_service import get_llm_service

        service = get_llm_service()
    judge = AgentResponseJudge(llm_interface=PinnedLLM(service, model, provider, allow_remote))

    async def _judge(record: LiveRunRecord, golden: GoldenTrajectory) -> bool:
        result = await judge.evaluate_agent_response(
            {"prompt": golden.query},
            {"answer": record.final_text},
            "chat",
            {"grounded": record.used_knowledge, "citations": len(record.rag_citations)},
        )
        scores = [s.score for s in result.criterion_scores if s.dimension == JudgmentDimension.ACCURACY]
        if not scores:
            raise RecordingUnusable("the judge returned no ACCURACY score")
        return min(scores) < judge.quality_threshold

    return _judge
