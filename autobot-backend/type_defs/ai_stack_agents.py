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
    status: str | None = None  # None = the source did not report one
    provider: str = ""
    parameters: str = ""

    @classmethod
    def coerce(cls, raw: Any, provider: str = "") -> "AIStackAgent":
        """Build an agent from a bare name or a partial dict (AI Stack ``/agents`` payloads)."""
        if isinstance(raw, str):
            return cls(name=raw, type=raw, provider=provider)
        name = _raw_name(raw)
        fields = {k: str(v) for k, v in raw.items() if k in cls.model_fields and v is not None}
        fields.setdefault("provider", provider)
        return cls(**{**fields, "name": name, "type": str(raw.get("type") or name)})


def _raw_name(raw: Any) -> str:
    """The name of a raw agent entry (bare string or dict); empty when it has none."""
    if isinstance(raw, str):
        return raw
    return str(raw.get("name") or raw.get("type") or raw.get("id") or "")


def agent_dicts(raw_agents: List[Any], provider: str = "") -> List[Dict[str, str | None]]:
    """Normalise a raw agent list (names and/or dicts) to ``AIStackAgent`` dicts, skipping nameless entries."""
    return [AIStackAgent.coerce(a, provider).model_dump() for a in raw_agents if _raw_name(a)]


def agent_names(agents_info: Dict[str, Any]) -> List[str]:
    """Agent names from a ``list_available_agents`` result."""
    return [a["name"] for a in agents_info.get("agents", [])]
