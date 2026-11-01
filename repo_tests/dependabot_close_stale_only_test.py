# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The stale-close workflow merges nothing and touches only Dependabot's own PRs."""

import yaml
from repo_tests._paths import repo_root

_WORKFLOW = repo_root() / ".github" / "workflows" / "dependabot-close-stale.yml"


def _script() -> str:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["close-stale"]["steps"]
    return "\n".join(step["with"]["script"] for step in steps if "script" in step.get("with", {}))


def test_it_merges_nothing() -> None:
    assert "pulls.update" in _script()
    assert "pulls.merge" not in _WORKFLOW.read_text(encoding="utf-8")


def test_it_filters_on_the_author_because_the_listing_cannot() -> None:
    script = _script()
    assert "creator:" not in script
    assert "pr.user.login === 'dependabot[bot]'" in script
    assert "for (const pr of prs)" in script
