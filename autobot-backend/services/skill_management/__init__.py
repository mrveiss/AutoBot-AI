# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Management Module

Issue #4337: Skill relevance ranking and caching for agent prompts.
Issue #4338: Autonomous skill extraction from conversations.
"""

from services.skill_management.skill_extractor import ExtractedSkill, SkillExtractor
from services.skill_management.skill_feedback import SkillFeedbackAnalyzer
from services.skill_management.skill_health_scheduler import (
    SkillHealthScheduler,
    get_skill_health_scheduler,
)
from services.skill_management.skill_metrics import SkillMetrics
from services.skill_management.skill_proposer import SkillProposer
from services.skill_management.skill_ranker import SkillRanker, get_skill_ranker

__all__ = [
    "SkillRanker",
    "get_skill_ranker",
    "SkillMetrics",
    "SkillHealthScheduler",
    "get_skill_health_scheduler",
    "SkillFeedbackAnalyzer",
    "ExtractedSkill",
    "SkillExtractor",
    "SkillProposer",
]
