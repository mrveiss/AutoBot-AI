# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request-body payloads for the endpoints in ``api/agent.py``.

Split out of ``schemas_agent.py`` (#15527). That module sits exactly on its
file-size ceiling, and the ratchet holding it (``scripts/python_file_size_
known_large.py`` with ``repo_tests/python_file_size_ratchet_baseline.py``)
only ever shrinks, so it could not take one more model. The five payloads
below moved here verbatim — they are the ones ``api/agent.py`` binds to a
request body — and ``CommandExecutePayload`` joins them as the sixth.

Response models for the same endpoints stay in ``schemas_agent.py``.
"""

from typing import Dict, List

from pydantic import BaseModel, Field

from type_defs.common import Metadata


class GoalPayload(BaseModel):
    """Goal payload — unified from bare and advanced variants (#10666 B1).

    The simple /goal endpoint reads only ``goal``/``use_phi2``/``user_role``.
    The /goal/orchestrated endpoint also reads the remaining optional fields.
    All added fields carry defaults, so existing callers that only send
    ``goal`` remain fully backward-compatible.
    """

    goal: str = Field(..., min_length=1, max_length=10000, description="Goal description")
    use_phi2: bool = False
    user_role: str = "user"
    # Fields from the former GoalPayload — all optional so /goal callers unaffected
    agents: List[str] | None = Field(None, description="Specific agents to use")
    coordination_mode: str = Field("intelligent", description="Coordination mode (parallel, sequential, intelligent)")
    priority: str = Field("normal", description="Task priority (low, normal, high, urgent)")
    context: str | None = Field(None, description="Additional context")
    use_knowledge_base: bool = Field(True, description="Use knowledge base for context")
    include_reasoning: bool = Field(False, description="Include reasoning steps")
    max_execution_time: int = Field(300, ge=30, le=1800, description="Max execution time in seconds")


class CommandApprovalPayload(BaseModel):
    task_id: str
    approved: bool
    user_role: str = "user"


# #15527: the route used to declare ``command_data: dict`` beside
# ``user_role: str = Form("user")``. A single ``Form`` field makes FastAPI read
# the whole body as ``application/x-www-form-urlencoded``, where every field
# arrives as a string, so ``command_data`` could never validate: the operation
# was published with a body no client could construct. Both fields live in one
# JSON model instead, which is the shape the Python and TypeScript SDKs send.
# The docstring below is deliberately one line -- it is the schema description
# the generated OpenAPI contract carries.
class CommandExecutePayload(BaseModel):
    """Body of POST /execute_command: the command to run and the caller's role."""

    command: str
    user_role: str = "user"


class MultiAgentTaskPayload(BaseModel):
    """Multi-agent task coordination payload."""

    task: str = Field(..., min_length=1, description="Task description")
    agents: List[str] = Field(..., min_length=1, description="Agents to coordinate")
    coordination_strategy: str = Field("adaptive", description="Coordination strategy")
    subtasks: List[Metadata] | None = Field(None, description="Predefined subtasks")
    dependencies: List[Dict[str, str]] | None = Field(None, description="Task dependencies")


class AgentAnalysisRequest(BaseModel):
    """Agent analysis request for development and optimization."""

    analysis_type: str = Field("comprehensive", description="Analysis type")
    target_path: str | None = Field(None, description="Specific path to analyze")
    include_performance: bool = Field(True, description="Include performance analysis")
    include_optimization: bool = Field(True, description="Include optimization suggestions")


class ResearchTaskRequest(BaseModel):
    """Research task request using multiple research agents."""

    research_query: str = Field(..., min_length=1, description="Research query")
    research_depth: str = Field("comprehensive", description="Research depth")
    include_web: bool = Field(True, description="Include web research")
    include_code_search: bool = Field(False, description="Include code search")
    sources: List[str] | None = Field(None, description="Specific sources")
