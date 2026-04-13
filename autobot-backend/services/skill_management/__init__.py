# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
<<<<<<< HEAD
"""
Skill Management Service Module

Provides skill metrics tracking, health scoring, feedback analysis,
autonomous skill extraction, and skill relevance ranking.
"""

from .skill_feedback import SkillFeedbackAnalyzer
from .skill_health_scheduler import SkillHealthScheduler, get_skill_health_scheduler
from .skill_metrics import SkillMetrics
from .skill_extractor import SkillExtractor
from .skill_proposer import SkillProposer
from .skill_ranker import SkillRanker, get_skill_ranker

__all__ = [
    "SkillMetrics",
    "SkillHealthScheduler",
    "get_skill_health_scheduler",
    "SkillFeedbackAnalyzer",
    "SkillExtractor",
    "SkillProposer",
    "SkillRanker",
    "get_skill_ranker",
]
=======
"""Skill management services for autonomous skill extraction and proposal."""
>>>>>>> origin/issue-4338
