# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Proposer Service

Proposes extracted skills to SLM for review and auto-validation.
Manages skill lifecycle: proposal → validation → activation.

Related Issue: #4338 - autonomous skill extraction from conversations
"""

import asyncio
from typing import Dict, List

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from services.skill_management.skill_extractor import ExtractedSkill
from services.slm_client import get_slm_client

logger = get_logger(__name__)


class SkillProposalError(Exception):
    """Error proposing skill to SLM."""


class SkillProposer:
    """Proposes extracted skills to SLM for validation and activation."""

    def __init__(self, slm_client=None) -> None:
        """Initialize skill proposer with SLM client."""
        self.slm_client = slm_client or get_slm_client()
        self.http_client = get_http_client()

    async def propose_skills(
        self,
        skills: List[ExtractedSkill],
        session_id: str,
        conversation_id: str | None = None,
    ) -> Dict[str, List[str]]:
        """
        Propose extracted skills to SLM.

        Args:
            skills: List of extracted skills to propose
            session_id: Session ID for tracking
            conversation_id: Optional conversation ID for reference

        Returns:
            Dict with "proposed" list of skill names
        """
        if not skills:
            logger.debug("No skills to propose")
            return {"proposed": []}

        logger.info("Proposing %d skills to SLM", len(skills))

        proposed = []
        for skill in skills:
            try:
                success = await self._propose_single_skill(skill, session_id, conversation_id)
                if success:
                    proposed.append(skill.name)
                    logger.info("Proposed skill: %s", skill.name)
                else:
                    logger.warning("Failed to propose skill: %s", skill.name)
            except SkillProposalError as e:
                logger.warning("Skill proposal error: %s", e)
                continue

        logger.info("Successfully proposed %d/%d skills", len(proposed), len(skills))
        return {"proposed": proposed}

    async def _propose_single_skill(
        self,
        skill: ExtractedSkill,
        session_id: str,
        conversation_id: str | None = None,
    ) -> bool:
        """Propose a single skill to SLM and auto-validate.

        Args:
            skill: Skill to propose
            session_id: Session ID
            conversation_id: Optional conversation ID

        Returns:
            True if proposal accepted, False otherwise
        """
        proposal_payload = {
            "skill": skill.to_dict(),
            "metadata": {
                "session_id": session_id,
                "conversation_id": conversation_id,
                "extracted_at": asyncio.get_running_loop().time(),
                "auto_validate": True,  # No manual approval needed
            },
        }

        try:
            response = await self._send_proposal_to_slm(proposal_payload)

            # Check if SLM accepted the proposal
            if response.get("status") == "accepted":
                logger.debug("SLM accepted skill proposal: %s", skill.name)
                return True
            elif response.get("status") == "pending_review":
                logger.info("Skill pending human review in SLM: %s", skill.name)
                return True  # Count as success even if pending
            else:
                logger.warning(
                    "SLM rejected skill proposal: %s (reason: %s)",
                    skill.name,
                    response.get("reason"),
                )
                return False

        except SkillProposalError as e:
            logger.error("Failed to propose skill %s: %s", skill.name, e)
            raise

    async def _send_proposal_to_slm(self, payload: Dict) -> Dict:
        """Send skill proposal to SLM API.

        Args:
            payload: Proposal payload with skill definition

        Returns:
            SLM response

        Raises:
            SkillProposalError: If request fails
        """
        if not self.slm_client or not hasattr(self.slm_client, "_ws_url"):
            # Fallback: use HTTP directly
            return await self._send_proposal_http(payload)

        try:
            # Call SLM endpoint: POST /api/skills/propose
            slm_url = self.slm_client._ws_url.replace("ws://", "http://").replace("wss://", "https://")
            proposal_url = f"{slm_url}/api/skills/propose"

            async with self.http_client.post(
                proposal_url,
                json=payload,
                timeout=config.timeout.llm_call,
                ssl=False,  # Self-signed certs in dev
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise SkillProposalError(f"SLM returned {response.status}: {text}")

                return await response.json()

        except asyncio.TimeoutError:
            raise SkillProposalError("SLM request timeout")
        except Exception as e:
            raise SkillProposalError(f"Failed to send proposal: {e}")

    async def _send_proposal_http(self, payload: Dict) -> Dict:
        """Send proposal via HTTP as fallback."""
        try:
            slm_url = "http://127.0.0.1:8000"  # Default co-located SLM

            async with self.http_client.post(
                f"{slm_url}/api/skills/propose",
                json=payload,
                timeout=config.timeout.llm_call,
                ssl=False,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise SkillProposalError(f"SLM returned {response.status}: {text}")

                return await response.json()

        except asyncio.TimeoutError:
            raise SkillProposalError("SLM request timeout")
        except Exception as e:
            raise SkillProposalError(f"HTTP proposal failed: {e}")

    async def validate_skill_syntax(self, skill: ExtractedSkill) -> bool:
        """Validate skill syntax and required fields.

        Args:
            skill: Skill to validate

        Returns:
            True if valid, False otherwise
        """
        # Check required fields
        if not skill.name or not skill.description:
            logger.warning("Skill missing name or description")
            return False

        if not skill.procedure:
            logger.warning("Skill missing procedure")
            return False

        # Name must be valid identifier
        if not skill.name.replace("_", "").isalnum():
            logger.warning("Skill name not a valid identifier: %s", skill.name)
            return False

        # Confidence must be in valid range
        if not (0.0 <= skill.confidence <= 1.0):
            logger.warning("Skill confidence out of range: %s", skill.confidence)
            return False

        # Validate inputs/outputs structure
        for inp in skill.inputs:
            if "name" not in inp or "type" not in inp:
                logger.warning("Invalid input specification: %s", inp)
                return False

        for out in skill.outputs:
            if "name" not in out or "type" not in out:
                logger.warning("Invalid output specification: %s", out)
                return False

        logger.debug("Skill validation passed: %s", skill.name)
        return True

    async def queue_skill_activation(self, skill_name: str) -> bool:
        """Queue skill for deployment to /slm/skills/active.

        Args:
            skill_name: Name of skill to activate

        Returns:
            True if queued successfully
        """
        try:
            response = await self._send_proposal_to_slm(
                {
                    "action": "activate",
                    "skill_name": skill_name,
                }
            )
            return response.get("status") == "queued"
        except SkillProposalError as e:
            logger.error("Failed to queue skill activation: %s", e)
            return False
