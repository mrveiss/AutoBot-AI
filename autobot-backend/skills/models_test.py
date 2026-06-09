# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for Skills System DB models."""

from skills.models import (
    GovernanceConfig,
    GovernanceMode,
    RepoType,
    SkillActivationLevel,
    SkillApproval,
    SkillPackage,
    SkillRepo,
    SkillState,
)


def test_skill_package_defaults():
    """SkillPackage sets nullable fields to None on construction."""
    pkg = SkillPackage(name="test-skill", skill_md="# Test", state=SkillState.DRAFT)
    assert pkg.state == SkillState.DRAFT
    assert pkg.skill_py is None
    assert pkg.repo_id is None


def test_skill_repo_types():
    """SkillRepo accepts all four RepoType variants without error."""
    for t in [RepoType.GIT, RepoType.LOCAL, RepoType.HTTP, RepoType.MCP]:
        repo = SkillRepo(name="r", url="x", repo_type=t)
        assert repo.repo_type == t


def test_governance_config_defaults():
    """GovernanceConfig initialises to SEMI_AUTO mode via __init__ defaults."""
    cfg = GovernanceConfig()
    assert cfg.mode == GovernanceMode.SEMI_AUTO


def test_skill_approval_pending():
    """SkillApproval defaults status to pending and restrictions to empty dict."""
    appr = SkillApproval(skill_id="abc", requested_by="autobot-self", reason="gap")
    assert appr.status == "pending"
    assert appr.restrictions == {}


def test_skill_states_all_defined():
    """SkillState enum has exactly 4 members covering full lifecycle."""
    assert len(SkillState) == 4
    assert SkillState.DRAFT == "draft"
    assert SkillState.BUILTIN == "builtin"


def test_skill_activation_levels():
    """SkillActivationLevel enum string values match expected security tier names."""
    assert SkillActivationLevel.MONITORED == "monitored"
    assert SkillActivationLevel.SANDBOXED == "sandboxed"
