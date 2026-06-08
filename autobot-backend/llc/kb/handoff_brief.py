# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC HandoffBriefGenerator — AI→Human and Human→AI KB-powered briefs (GH#8239)."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

from .rag_assembler import AssemblerProfile, LLCRAGAssembler

logger = get_logger(__name__)


class HandoffBriefGenerator:
    """Generates KB-powered handoff briefs for work item transitions."""

    def __init__(self):
        self.rag = LLCRAGAssembler()

    async def generate_agent_to_human_brief(
        self,
        work_item_id: str,
        agent_id: str,
        company_id: str,
        project_id: Optional[str] = None,
        work_item_title: str = "",
        work_item_description: str = "",
    ) -> Dict[str, Any]:
        """Generate a brief when agent hands off completed work to human reviewer.

        Assembles KB context from:
        - work_item:{work_item_id} (comments, traces, artifacts)
        - agent:{agent_id} (diary entries for this work item)
        - project:{project_id} (similar completed items for reference)

        Args:
            work_item_id: Work item UUID.
            agent_id: Agent UUID handing off the work.
            company_id: Tenant company UUID.
            project_id: Optional project scope for similar-item queries.
            work_item_title: Work item title for RAG query.
            work_item_description: Work item description for RAG query.

        Returns:
            Dict with: completed, remaining, open_questions, next_steps, artifacts, generated_at.
        """
        try:
            query_text = f"{work_item_title} {work_item_description}".strip()

            context = await self.rag.assemble(
                company_id=company_id,
                profile=AssemblerProfile.HANDOFF,
                project_id=project_id,
                agent_id=agent_id,
                work_item_id=work_item_id,
                query_text=query_text,
            )

            formatted_context = self._format_context_for_llm(context.chunks, "agent_to_human")

            from services.llm_service import get_llm_service

            llm = get_llm_service()
            response = await llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a work item handoff brief generator. "
                        "Generate a structured human-readable summary of completed work. "
                        "Be concise but comprehensive. Format output as JSON.",
                    },
                    {
                        "role": "user",
                        "content": f"Generate a handoff brief from the following work context:\n\n{formatted_context}\n\n"  # noqa: E501
                        "Return a JSON object with: completed (list of completed tasks), "
                        "remaining (list of incomplete tasks), "
                        "open_questions (list of unresolved issues), "
                        "next_steps (list of recommended next actions), "
                        "artifacts (list of created/modified artifacts)",
                    },
                ],
                llm_type="extraction",
                temperature=0.1,
                max_tokens=1024,
            )

            if response.error:
                logger.error("LLM error generating agent_to_human brief: %s", response.error)
                return self._fallback_agent_to_human_brief()

            try:
                brief_content = json.loads(response.content)
            except json.JSONDecodeError:
                try:
                    brief_content = self._parse_llm_text_response(response.content)
                except (ValueError, json.JSONDecodeError):
                    logger.warning("Failed to parse LLM response as JSON, using fallback")
                    return self._fallback_agent_to_human_brief()

            return {
                "completed": brief_content.get("completed", []),
                "remaining": brief_content.get("remaining", []),
                "open_questions": brief_content.get("open_questions", []),
                "next_steps": brief_content.get("next_steps", []),
                "artifacts": brief_content.get("artifacts", []),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "handoff_brief_generator",
            }

        except Exception as e:
            logger.exception("Error generating agent_to_human brief: %s", e)
            return self._fallback_agent_to_human_brief()

    async def generate_human_to_agent_brief(
        self,
        work_item_id: str,
        human_notes: str,
        company_id: str,
        project_id: Optional[str] = None,
        work_item_title: str = "",
    ) -> Dict[str, Any]:
        """Generate a brief when human assigns work to agent.

        Assembles KB context from:
        - company:{company_id} (relevant policies/standards)
        - project:{project_id} (architecture decisions, prior work)
        - human_notes (verbatim context from human)

        Args:
            work_item_id: Work item UUID.
            human_notes: Human-provided context notes.
            company_id: Tenant company UUID.
            project_id: Optional project scope.
            work_item_title: Work item title for RAG query.

        Returns:
            Dict with: human_context, company_standards, project_context, suggested_approach, generated_at.
        """
        try:
            context = await self.rag.assemble(
                company_id=company_id,
                profile=AssemblerProfile.HANDOFF,
                project_id=project_id,
                work_item_id=work_item_id,
                query_text=work_item_title,
            )

            formatted_context = self._format_context_for_llm(context.chunks, "human_to_agent")

            from services.llm_service import get_llm_service

            llm = get_llm_service()
            response = await llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a work item handoff brief generator for agent assignment. "
                        "Synthesize company policies and project architecture to guide the agent. "
                        "Be actionable and concise. Format output as JSON.",
                    },
                    {
                        "role": "user",
                        "content": f"Human context:\n{human_notes}\n\n"
                        f"Company and project context:\n{formatted_context}\n\n"
                        "Return a JSON object with: "
                        "company_standards (list of relevant policies), "
                        "project_context (list of relevant architectural decisions), "
                        "suggested_approach (recommended strategy for this work)",
                    },
                ],
                llm_type="extraction",
                temperature=0.1,
                max_tokens=1024,
            )

            if response.error:
                logger.error("LLM error generating human_to_agent brief: %s", response.error)
                return self._fallback_human_to_agent_brief(human_notes)

            try:
                brief_content = json.loads(response.content)
            except json.JSONDecodeError:
                try:
                    brief_content = self._parse_llm_text_response(response.content)
                except (ValueError, json.JSONDecodeError):
                    logger.warning("Failed to parse LLM response as JSON, using fallback")
                    return self._fallback_human_to_agent_brief(human_notes)

            return {
                "human_context": human_notes,
                "company_standards": brief_content.get("company_standards", []),
                "project_context": brief_content.get("project_context", []),
                "suggested_approach": brief_content.get("suggested_approach", ""),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "handoff_brief_generator",
            }

        except Exception as e:
            logger.exception("Error generating human_to_agent brief: %s", e)
            return self._fallback_human_to_agent_brief(human_notes)

    def _format_context_for_llm(self, chunks: List[Dict[str, Any]], brief_type: str) -> str:
        """Format RAG chunks into human-readable context for LLM."""
        if not chunks:
            return "(No KB context available)"

        lines = []
        for chunk in chunks:
            content = chunk.get("content", "")
            source = chunk.get("source", "unknown")
            similarity = chunk.get("similarity_score", 0.0)

            lines.append(f"[{source} (relevance: {similarity:.2f})]")
            lines.append(content[:500])
            lines.append("")

        return "\n".join(lines)

    def _fallback_agent_to_human_brief(self) -> Dict[str, Any]:
        """Return a minimal valid brief when KB/LLM fails."""
        return {
            "completed": [],
            "remaining": [],
            "open_questions": [],
            "next_steps": [],
            "artifacts": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "fallback",
        }

    def _fallback_human_to_agent_brief(self, human_notes: str) -> Dict[str, Any]:
        """Return a minimal valid brief when KB/LLM fails."""
        return {
            "human_context": human_notes,
            "company_standards": [],
            "project_context": [],
            "suggested_approach": "Proceed with default best practices. Escalate if unclear.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "fallback",
        }

    def _parse_llm_text_response(self, text: str) -> Dict[str, Any]:
        """Attempt to extract JSON from LLM text when direct parse fails.

        Tries markdown code-fenced JSON (```json ... ```) and bare JSON
        objects/arrays embedded in prose. Raises ValueError if no JSON found,
        so the outer handler falls through to the appropriate fallback.
        """
        import re

        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return json.loads(fence_match.group(1))

        obj_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", text, re.DOTALL)
        if obj_match:
            return json.loads(obj_match.group(0))

        raise ValueError("No JSON object found in LLM text response")


__all__ = ["HandoffBriefGenerator"]
