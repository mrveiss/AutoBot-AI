"""LLC RAG assembler interface (GH#8261).

GH#8236 (heartbeat context builder) and GH#8239 (handoff brief generator)
both construct multi-source RAG queries over company/project/agent KB
collections. This module provides a shared assembler with swappable query
profiles so neither issue needs to duplicate ChromaDB call patterns.

Concrete implementation lives in GH#8236. This file provides the interface
stub so dependent issues can import and type-check against it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AssemblerProfile(str, Enum):
    """Query profile for RAG context assembly.

    HEARTBEAT: full organisation context for agent heartbeat runs.
    HANDOFF:   transition brief for agent-to-agent handoff.
    SUGGESTION: acceptance-criteria hints during work item creation.
    """

    HEARTBEAT = "heartbeat"
    HANDOFF = "handoff"
    SUGGESTION = "suggestion"


@dataclass
class LLCContext:
    """Assembled RAG context returned by LLCRAGAssembler.assemble()."""

    company_id: str
    profile: AssemblerProfile
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLCRAGAssembler:
    """Assembles multi-source RAG context for LLC operations.

    Both GH#8236 and GH#8239 use this rather than calling ChromaDB directly,
    ensuring consistent collection names, query parameters, and result merging.
    """

    async def assemble(
        self,
        company_id: str,
        profile: AssemblerProfile,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        work_item_id: Optional[str] = None,
    ) -> LLCContext:
        """Run parallel ChromaDB queries and return merged context.

        Args:
            company_id: Tenant company identifier.
            profile: Which query profile to use (HEARTBEAT, HANDOFF, SUGGESTION).
            project_id: Optional project scope filter.
            agent_id: Optional agent scope filter.
            work_item_id: Optional work item context.

        Returns:
            LLCContext with merged chunks from all relevant collections.
        """
        raise NotImplementedError("LLCRAGAssembler.assemble() — concrete impl in GH#8236")
