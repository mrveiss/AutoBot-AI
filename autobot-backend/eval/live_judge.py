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
from eval.store import GoldenTrajectory

#: ``(record, golden) -> True`` when the judge finds the answer unsupported.
Judge = Callable[[LiveRunRecord, GoldenTrajectory], Awaitable[bool]]


class PinnedLLM:
    """An ``LLMService`` view whose every ``chat`` names one model, so the judge cannot drift to another."""

    def __init__(self, service: Any, model: str):
        self._service = service
        self.current_model = model

    async def chat(self, messages: list, **kwargs: Any) -> Any:
        return await self._service.chat(messages, model_name=self.current_model, **kwargs)


def response_judge(model: str, service: Any = None) -> Judge:
    """A judge pinned to *model*: ``unsupported`` when its ACCURACY score is below the judge's quality threshold."""
    from judges import JudgmentDimension
    from judges.agent_response_judge import AgentResponseJudge

    if service is None:
        from services.llm_service import get_llm_service

        service = get_llm_service()
    judge = AgentResponseJudge(llm_interface=PinnedLLM(service, model))

    async def _judge(record: LiveRunRecord, golden: GoldenTrajectory) -> bool:
        result = await judge.evaluate_agent_response(
            {"prompt": golden.query},
            {"answer": record.final_text},
            "chat",
            {"grounded": record.used_knowledge, "citations": len(record.rag_citations)},
        )
        scores = [s.score for s in result.criterion_scores if s.dimension == JudgmentDimension.ACCURACY]
        return bool(scores) and min(scores) < judge.quality_threshold

    return _judge
