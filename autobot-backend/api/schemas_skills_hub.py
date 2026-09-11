# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Community skill hub API schemas (Issue #4412).

Moved out of ``api/skills_hub.py`` by #16368. The no-local-schemas hook forbids
BaseModel classes in API modules, and the shared ``schemas_*`` files are all at
their size ceilings, so the hub's models have a schema module of their own.
"""

from typing import TYPE_CHECKING, List

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from skills.hub import InstalledSkill, SkillListing


class SkillListingOut(BaseModel):
    id: str
    name: str
    description: str
    mcp_url: str
    version: str
    tags: List[str] = Field(default_factory=list)

    @classmethod
    def from_listing(cls, s: "SkillListing") -> "SkillListingOut":
        return cls(
            id=s.id,
            name=s.name,
            description=s.description,
            mcp_url=s.mcp_url,
            version=s.version,
            tags=s.tags,
        )


class InstalledSkillOut(BaseModel):
    id: str
    name: str
    mcp_url: str
    version: str
    installed_at: str

    @classmethod
    def from_installed(cls, s: "InstalledSkill") -> "InstalledSkillOut":
        return cls(
            id=s.id,
            name=s.name,
            mcp_url=s.mcp_url,
            version=s.version,
            installed_at=s.installed_at,
        )


class SkillUpdateOut(BaseModel):
    id: str
    name: str
    current_version: str
    latest_version: str


class InstallRequest(BaseModel):
    skill_id: str = Field(..., description="Registry id or name of the skill to install")
