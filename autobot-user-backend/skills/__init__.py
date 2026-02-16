# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skills System (Issue #731)

Modular AI capabilities packaged as self-contained, discoverable modules.
"""

from backend.skills.base_skill import BaseSkill, SkillManifest, SkillStatus
from backend.skills.manager import SkillManager
from backend.skills.registry import SkillRegistry

__all__ = [
    "BaseSkill",
    "SkillManifest",
    "SkillManager",
    "SkillRegistry",
    "SkillStatus",
]
