# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Management Module

Issue #4337: Skill relevance ranking and caching for agent prompts.
"""

from services.skill_management.skill_ranker import SkillRanker, get_skill_ranker

__all__ = ["SkillRanker", "get_skill_ranker"]
