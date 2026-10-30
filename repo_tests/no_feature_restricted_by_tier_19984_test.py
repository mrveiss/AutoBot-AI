# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No code path restricts a feature by tier or licence (#19984).

This repository has no paid versions or modules; paid functionality comes from another repository.
A branch on one of these names is how a tier would start restricting something. Only the conditions
of branches are read: storing or returning a value restricts nothing.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_TIER_NAMES = frozenset(
    {"subscription_tier", "license_tier", "license_key", "plan_tier", "paid_plan", "is_premium", "is_pro", "is_paid"}
)
_ROOTS = ("autobot-backend/*.py", "autobot-slm-backend/*.py", "autobot_shared/*.py")
#: A branch that only records what changed, without deciding anything about the feature.
_EXEMPT = {"autobot_shared/user_management/organization_service.py": 1}


def _names_in(node: ast.AST) -> set[str]:
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value)
    return found


def _tier_branches(source: str) -> list[int]:
    """Lines of branches whose condition reads a tier or licence name."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)) and _names_in(node.test) & _TIER_NAMES:
            lines.append(node.lineno)
    return lines


def test_no_branch_reads_a_tier_or_licence() -> None:
    listed = [rel for rel in tracked_paths(_ROOT, *_ROOTS) if not rel.endswith("_test.py")]
    assert len(listed) > 500, f"read only {len(listed)} files; this test reads nothing"
    found = {}
    for rel in listed:
        try:
            lines = _tier_branches((_ROOT / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if len(lines) > _EXEMPT.get(rel, 0):
            found[rel] = lines
    assert not found, found


def test_contrast_a_planted_restriction_is_caught() -> None:
    assert _tier_branches('if org.subscription_tier == "pro":\n    enable()\n') == [1]
    assert _tier_branches("assert user.is_premium\n") == [1]
    assert _tier_branches("x = 1 if license_key else 2\n") == [1]
    assert _tier_branches('org.subscription_tier = "free"\nreturn_value = {"subscription_tier": tier}\n') == []
