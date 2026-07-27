# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Extraction Service

Autonomously extracts reusable skills from conversation history using LLM analysis.
Detects multi-step workflows and repeated logic patterns to propose new skills.

Related Issue: #4338 - autonomous skill extraction from conversations
"""

import json
from dataclasses import dataclass
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from services.ai_stack_client import AIStackClient, AIStackError

logger = get_logger(__name__)


@dataclass
class ExtractedSkill:
    """Extracted skill definition with validation metadata."""

    name: str
    description: str
    inputs: List[Dict[str, str]]  # [{"name": "param", "type": "string"}]
    outputs: List[Dict[str, str]]  # [{"name": "result", "type": "string"}]
    procedure: str  # Step-by-step workflow description
    preconditions: List[str]  # ["System must be initialized", ...]
    edge_cases: List[str]  # ["If X fails, do Y", ...]
    confidence: float  # 0.0-1.0 confidence score
    usage_count: int = 0  # How many times this pattern appeared

    def to_dict(self) -> Dict:
        """Serialize to dict for SLM proposal."""
        return {
            "name": self.name,
            "description": self.description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "procedure": self.procedure,
            "preconditions": self.preconditions,
            "edge_cases": self.edge_cases,
            "confidence": self.confidence,
        }


class SkillExtractor:
    """Extracts reusable skills from conversation using LLM analysis."""

    # Pattern keywords for detecting multi-step workflows
    WORKFLOW_KEYWORDS = {
        "create",
        "build",
        "setup",
        "configure",
        "deploy",
        "install",
        "execute",
        "run",
        "process",
        "analyze",
    }

    # Pattern keywords for detecting repeated patterns
    PATTERN_KEYWORDS = {
        "first",
        "then",
        "next",
        "after",
        "before",
        "finally",
        "simultaneously",
        "parallel",
        "sequence",
    }

    def __init__(self, ai_stack_client: AIStackClient | None = None) -> None:
        """Initialize skill extractor with AI Stack client."""
        self.ai_client = ai_stack_client or AIStackClient()

    async def extract_skills(
        self,
        conversation_history: List[Dict[str, str]],
        existing_skills: List[Dict[str, str]] | None = None,
    ) -> List[ExtractedSkill]:
        """
        Extract reusable skills from conversation history.

        Args:
            conversation_history: List of conversation messages
                Format: [{"role": "user"/"assistant", "content": "..."}]
            existing_skills: Skills already registered, as ``{"name", "description"}``
                records (Issue #12809). Shown to the model so it can recognise a
                conversation that merely re-treads a skill the system already has.
                Omitted means the model sees no prior art and can only propose new.

        Returns:
            List of extracted skills with high confidence (>0.6)
        """
        if not conversation_history or len(conversation_history) < 4:
            logger.debug(
                "Skipping skill extraction: insufficient conversation history (%d messages)",
                len(conversation_history),
            )
            return []

        # Check if conversation contains workflow indicators
        if not self._has_workflow_patterns(conversation_history):
            logger.debug("Conversation does not contain detectable workflow patterns")
            return []

        logger.info("Extracting skills from %d-message conversation", len(conversation_history))
        try:
            extracted = await self._call_extraction_llm(conversation_history, existing_skills)
            # Filter by confidence threshold
            high_confidence = [s for s in extracted if s.confidence >= 0.6]
            logger.info(
                "Extracted %d skills (confidence >= 0.6) from %d candidates",
                len(high_confidence),
                len(extracted),
            )
            return high_confidence
        except AIStackError as e:
            logger.error("Failed to extract skills: %s", e)
            return []
        except Exception as e:
            logger.error("Unexpected error during skill extraction: %s", e)
            return []

    def _has_workflow_patterns(self, conversation_history: List[Dict[str, str]]) -> bool:
        """Check if conversation contains workflow/multi-step patterns."""
        import re

        content_lower = " ".join(msg.get("content", "").lower() for msg in conversation_history)

        # Strip punctuation and split into words
        words = re.findall(r"\b\w+\b", content_lower)

        workflow_count = sum(1 for word in words if word in self.WORKFLOW_KEYWORDS)
        pattern_count = sum(1 for word in words if word in self.PATTERN_KEYWORDS)

        # Need at least one workflow keyword and one pattern keyword
        has_patterns = workflow_count >= 1 and pattern_count >= 1

        if has_patterns:
            logger.debug(
                "Detected workflow patterns: %d workflow keywords, %d pattern keywords",
                workflow_count,
                pattern_count,
            )
        return has_patterns

    async def _call_extraction_llm(
        self,
        conversation_history: List[Dict[str, str]],
        existing_skills: List[Dict[str, str]] | None = None,
    ) -> List[ExtractedSkill]:
        """Call LLM to extract skills from conversation.

        Args:
            conversation_history: Full conversation history
            existing_skills: Already-registered skills shown to the model as prior art

        Returns:
            List of extracted skills (including low-confidence ones for filtering)
        """
        # Truncate to last 20 messages to stay within token budget
        recent_history = conversation_history[-20:]

        prompt = self._build_extraction_prompt(recent_history, existing_skills)

        # Call AI Stack LLM endpoint
        try:
            response = await self.ai_client.call(
                method="POST",
                endpoint="/agents/skill-extractor/process",
                payload={
                    "prompt": prompt,
                    "conversation_history": recent_history,
                    "temperature": 0.3,  # Low temp for consistent extraction
                    "max_tokens": 2000,
                },
            )

            # Parse LLM response
            extracted_json = response.get("content", "{}")
            try:
                skill_data = json.loads(extracted_json)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON: %s", extracted_json)
                return []

            return self._parse_extraction_response(skill_data)

        except AIStackError as e:
            logger.error("AI Stack call failed: %s", e)
            raise

    @staticmethod
    def _format_existing_skills(existing_skills: List[Dict[str, str]] | None) -> str:
        """Render already-registered skills as prior art for the prompt (Issue #12809)."""
        if not existing_skills:
            return "SKILLS ALREADY REGISTERED:\n(none)"

        lines = [
            f"- {skill.get('name', 'unnamed')}: {skill.get('description', '')}".rstrip()
            for skill in existing_skills
        ]
        return "SKILLS ALREADY REGISTERED:\n" + "\n".join(lines)

    def _build_extraction_prompt(
        self,
        conversation_history: List[Dict[str, str]],
        existing_skills: List[Dict[str, str]] | None = None,
    ) -> str:
        """Build prompt for LLM skill extraction."""
        history_text = "\n".join(
            f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}" for msg in conversation_history
        )

        return f"""Analyze this conversation and extract reusable skills.

{self._format_existing_skills(existing_skills)}

Extract a skill ONLY if the conversation developed a workflow that none of the
skills above already covers. Returning an empty array is a correct and expected
outcome — most conversations teach nothing new, and a conversation that merely
followed an existing skill must produce no skill at all. Do not invent a skill,
and do not restate an existing one under a different name, to justify a result.

For each skill you identify:
1. Name: concise skill identifier (lowercase_with_underscores)
2. Description: one-line summary of what it does
3. Inputs: list of parameters with types
4. Outputs: list of return values with types
5. Procedure: step-by-step workflow
6. Preconditions: what must be true before using it
7. Edge cases: error conditions and handling
8. Confidence: 0.0-1.0 score (1.0 = certain, 0.0 = guess)

CONVERSATION:
{history_text}

Output JSON array of skills:
[
  {{
    "name": "skill_name",
    "description": "What the skill does",
    "inputs": [{{"name": "param", "type": "string"}}],
    "outputs": [{{"name": "result", "type": "string"}}],
    "procedure": "Step 1: ... Step 2: ...",
    "preconditions": ["Precondition 1"],
    "edge_cases": ["If X fails, do Y"],
    "confidence": 0.9
  }}
]

If nothing in this conversation qualifies, respond with exactly: []

Respond ONLY with valid JSON, no other text."""

    def _parse_extraction_response(self, skill_data: Dict) -> List[ExtractedSkill]:
        """Parse LLM response into ExtractedSkill objects."""
        skills = []

        # Handle both array and object responses
        if isinstance(skill_data, list):
            skill_list = skill_data
        elif isinstance(skill_data, dict) and "skills" in skill_data:
            skill_list = skill_data["skills"]
        else:
            logger.warning("Unexpected LLM response format: %s", type(skill_data))
            return []

        for skill_dict in skill_list:
            try:
                skill = ExtractedSkill(
                    name=skill_dict.get("name", ""),
                    description=skill_dict.get("description", ""),
                    inputs=skill_dict.get("inputs", []),
                    outputs=skill_dict.get("outputs", []),
                    procedure=skill_dict.get("procedure", ""),
                    preconditions=skill_dict.get("preconditions", []),
                    edge_cases=skill_dict.get("edge_cases", []),
                    confidence=float(skill_dict.get("confidence", 0.0)),
                )

                # Validate required fields
                if not skill.name or not skill.description:
                    logger.warning("Skipping skill with missing name/description: %s", skill)
                    continue

                skills.append(skill)
                logger.debug("Extracted skill: %s (confidence: %.2f)", skill.name, skill.confidence)

            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse skill: %s", e)
                continue

        return skills
