# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Skills System DB models."""
from skills.models import (
    GovernanceConfig,
    GovernanceMode,
    RepoType,
    SkillApproval,
    SkillPackage,
    SkillRepo,
    SkillState,
    TrustLevel,
)


def test_skill_package_defaults():
    pkg = SkillPackage(name="test-skill", skill_md="# Test", state=SkillState.DRAFT)
    assert pkg.state == SkillState.DRAFT
    assert pkg.skill_py is None
    assert pkg.repo_id is None


def test_skill_repo_types():
    for t in [RepoType.GIT, RepoType.LOCAL, RepoType.HTTP, RepoType.MCP]:
        repo = SkillRepo(name="r", url="x", repo_type=t)
        assert repo.repo_type == t


def test_governance_config_defaults():
    cfg = GovernanceConfig()
    assert cfg.mode == GovernanceMode.SEMI_AUTO


def test_skill_approval_pending():
    appr = SkillApproval(skill_id="abc", requested_by="autobot-self", reason="gap")
    assert appr.status == "pending"


def test_skill_states_all_defined():
    assert len(SkillState) == 4
    assert SkillState.DRAFT == "draft"
    assert SkillState.BUILTIN == "builtin"


def test_trust_levels():
    assert TrustLevel.MONITORED == "monitored"
    assert TrustLevel.SANDBOXED == "sandboxed"
