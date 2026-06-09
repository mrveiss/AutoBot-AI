# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skills System (Issue #731)

Modular AI capabilities packaged as self-contained, discoverable modules.
"""

from skills.base_skill import BaseSkill, SkillManifest, SkillStatus
from skills.manager import SkillManager
from skills.registry import SkillRegistry

__all__ = [
    "BaseSkill",
    "SkillManifest",
    "SkillManager",
    "SkillRegistry",
    "SkillStatus",
]
