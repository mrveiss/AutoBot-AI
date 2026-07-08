# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from skills.base_skill import SkillManifest
from skills.registry import SkillRegistry


def test_register_declarative_adds_skill():
    reg = SkillRegistry()
    m = SkillManifest(name="my-custom", version="2.0.0", description="d", tools=["do_x"])
    assert reg.register_declarative(m) is True
    assert reg.get("my-custom") is not None
    assert reg.get_skill_detail("my-custom")["tools"] == ["do_x"]


def test_register_declarative_is_idempotent_by_name():
    reg = SkillRegistry()
    m = SkillManifest(name="dup", version="1.0.0", description="d")
    assert reg.register_declarative(m) is True
    assert reg.register_declarative(m) is False  # already present
