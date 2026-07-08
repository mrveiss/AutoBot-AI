# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from skills.base_skill import SkillManifest
from skills.manager import SkillManager
from skills.registry import SkillRegistry


class _FakeInstalled:
    def __init__(self, name, version):
        self.id = name
        self.name = name
        self.version = version
        self.mcp_url = ""
        self.installed_at = ""


@pytest.mark.asyncio
async def test_load_custom_definitions_reregisters_hub_skills(monkeypatch):
    reg = SkillRegistry()
    mgr = SkillManager(registry=reg)

    async def fake_list_installed(self):
        return [_FakeInstalled("hub-alpha", "1.2.0")]

    monkeypatch.setattr("skills.hub.SkillHub.list_installed", fake_list_installed)

    count = await mgr._load_custom_definitions()

    assert count == 1
    assert reg.get("hub-alpha") is not None
    assert reg.get_skill_detail("hub-alpha")["version"] == "1.2.0"


@pytest.mark.asyncio
async def test_load_custom_definitions_skips_names_already_registered(monkeypatch):
    reg = SkillRegistry()
    reg.register_declarative(SkillManifest(name="hub-alpha", version="9.9.9", description="d"))
    mgr = SkillManager(registry=reg)

    async def fake_list_installed(self):
        return [_FakeInstalled("hub-alpha", "1.2.0")]

    monkeypatch.setattr("skills.hub.SkillHub.list_installed", fake_list_installed)

    count = await mgr._load_custom_definitions()

    assert count == 0  # already present, not overwritten
    assert reg.get_skill_detail("hub-alpha")["version"] == "9.9.9"
