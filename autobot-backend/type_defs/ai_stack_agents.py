# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one typed agent shape shared by AIStackClient, the agent routes and the schemas (#22141)."""

from typing import Any, Dict, List

from pydantic import BaseModel


class AIStackAgent(BaseModel):
    """One agent as listed by ``AIStackClient.list_available_agents``."""

    name: str
    type: str
    status: str = "ready"
    provider: str = ""
    parameters: str = ""

    @classmethod
    def coerce(cls, raw: Any, provider: str = "") -> "AIStackAgent":
        """Build an agent from a bare name or a partial dict (AI Stack ``/agents`` payloads)."""
        if isinstance(raw, str):
            return cls(name=raw, type=raw, provider=provider)
        name = str(raw.get("name") or raw.get("type") or raw.get("id") or "")
        fields = {k: str(v) for k, v in raw.items() if k in cls.model_fields and v is not None}
        fields.setdefault("provider", provider)
        return cls(**{**fields, "name": name, "type": str(raw.get("type") or name)})


def agent_dicts(raw_agents: List[Any], provider: str = "") -> List[Dict[str, str]]:
    """Normalise a raw agent list (names and/or dicts) to ``AIStackAgent`` dicts."""
    return [AIStackAgent.coerce(a, provider).model_dump() for a in raw_agents]


def agent_names(agents_info: Dict[str, Any]) -> List[str]:
    """Agent names from a ``list_available_agents`` result."""
    return [a["name"] for a in agents_info.get("agents", [])]
