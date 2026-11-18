# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared rules and paths for the schema-split tools.

Holds the schema-class -> domain classification and the repo paths that
split_schemas.py and update_imports.py both use, so the two cannot drift.
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_DIR = os.path.join(REPO_ROOT, "autobot-backend", "api")

# ---------------------------------------------------------------------------
# Classification rules — longest-match prefix wins
# ---------------------------------------------------------------------------
DOMAIN_RULES = [
    # Longest prefixes first to avoid shorter-prefix false matches
    (r"^(AgentTerminal)", "terminal"),
    (r"^(AgentMessage|AgentCommand|AgentHealth|AgentConfig|AgentCommandApproval|AgentCommandExecute)", "agent"),
    (r"^(Terminal|SSH|CommandAssess|AdminExecute|PackageManagers)", "terminal"),
    (r"^(Analytics|Cost|Budget|UsageSummary|UsageBy|RecentUsage|ModelPricing|AllAgent|Metrics)", "analytics"),
    (r"^Knowledge", "knowledge"),
    (r"^(LLM|Memory)", "agent"),
    (r"^(System|NPU|WakeWord|FeatureFlag|AdminFile)", "system"),
    (
        r"^(ValidationDashboard|ValidationJudge|ValidationJudgment|Workflow|Registry|RUM|Elevation|AdvancedControl|StateTracking|StructuredThinking)",  # noqa: E501
        "workflows",
    ),
    (
        r"^(CodeReview|Git|Skills|SkillsDraft|SkillsApproval|SkillsGovernance|SkillsGap|Database|Template|Templates|Log|Voice|AccessControl|FileSandbox|MCP|HTTP)",  # noqa: E501
        "code",
    ),
    (r"^(Success|Data|UsageRecord)", "common"),
]


def classify_class(cls: str) -> str:
    for pattern, domain in DOMAIN_RULES:
        if re.match(pattern, cls):
            return domain
    return "common"  # fallback — stays in schemas_common
