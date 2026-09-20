# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which orchestrated agents a request may reach, given its originator's authority (#16957, #16950).

An admitted A2A peer's task runs through the orchestrator, which routes it to
internal agents. Several of those read a knowledge or memory store, and nothing
asked whether the peer may: ``QUERY_MEMORY`` was granted by trust level and checked
nowhere. The routing decision is the one choke point every A2A task passes before
any agent runs, and the only place the originator's authority is in scope. So the
check happens here, for every agent the decision would run.

Every agent type the orchestrator can route to is classified below, either as
needing a capability or as needing none, with the reason. **An unclassified agent
is refused to an external originator (fail closed).** ``DistributedAgentManager``
accepts agent types at runtime, so a test over the known set cannot be the only
line: a plugin-registered agent that nobody classified must not reach a peer
unchecked. ``capability_requirements_test`` still fails on an unclassified built-in
agent, so the refusal is not the first anyone hears of it.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from a2a.trust_score import Capability
from security.authority import Authority

#: Agents whose work reads a knowledge or memory store, from reading each handler.
REQUIRED_CAPABILITY: Dict[str, Capability] = {
    # The RAG route asks the KB librarian for documents first (agent_execution._execute_rag_agent).
    "rag": Capability.QUERY_MEMORY,
    # The KB librarian searches the knowledge base.
    "knowledge_retrieval": Capability.QUERY_MEMORY,
    # librarian_assistant holds a KnowledgeBase, and can also add documents to it.
    "research": Capability.QUERY_MEMORY,
    # Reads and writes per-session working memory and the agent diary.
    "sentiment_analysis": Capability.QUERY_MEMORY,
    # Distributed: searches the indexed codebase, a knowledge store.
    "npu_code_search": Capability.QUERY_MEMORY,
}

#: Agents that read no knowledge or memory store, with the reason, so "needs nothing"
#: is a recorded decision rather than an omission.
NEEDS_NO_CAPABILITY: Dict[str, str] = {
    "chat": "answers from the model and the request's own history; reads no store",
    "system_commands": "generates and validates a command; does not execute it or read a store",
    "orchestrator": "the fallback returns a fixed response",
    "data_analysis": "analyses the data in the request",
    "code_generation": "generates from the request",
    "translation": "translates the request",
    "summarization": "summarises the request",
    "image_analysis": "analyses the image in the request",
    "audio_processing": "processes the audio in the request",
    # Distributed: classifies the request; its Redis use is its own cache.
    "classification": "classifies the request; its Redis use is a classification cache",
}


def _may_reach(authority: Authority, agent: str) -> bool:
    """Whether *authority* may reach *agent*: only a classified agent, and only with what it requires."""
    if agent in NEEDS_NO_CAPABILITY:
        return True
    required = REQUIRED_CAPABILITY.get(agent)
    return required is not None and authority.has_capability(required.value)


def refused_agents(authority: Authority | None, agent_types: Iterable[str]) -> List[str]:
    """The agents in *agent_types* that *authority* may not reach. None, an internal caller, reaches all."""
    if authority is None:
        return []
    return [agent for agent in agent_types if not _may_reach(authority, agent)]


def refusal(refused: List[str]) -> Dict[str, object]:
    """The orchestrator's answer when a request's originator may not reach the agents it routed to."""
    needed = sorted({REQUIRED_CAPABILITY[agent].value for agent in refused if agent in REQUIRED_CAPABILITY})
    unclassified = sorted(agent for agent in refused if agent not in REQUIRED_CAPABILITY)
    reasons = [f"capabilities its originator does not hold: {', '.join(needed)}"] if needed else []
    if unclassified:
        reasons.append(f"agents not classified for external originators: {', '.join(unclassified)}")
    return {
        "status": "refused",
        "response": "This request was refused -- " + "; ".join(reasons),
        "refused_agents": refused,
        "missing_capabilities": needed,
        "unclassified_agents": unclassified,
        "routing_strategy": "refused_by_capability",
    }
