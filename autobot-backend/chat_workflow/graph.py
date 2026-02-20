# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LangGraph StateGraph for chat workflow orchestration.

Issue #1043: Replaces hand-rolled streaming architecture with LangGraph
StateGraph for native message identity, deduplication, and interrupt-based
command approval.

Architecture:
    - Graph state (ChatState) is the single source of truth for messages
    - Redis checkpointer provides thread-based persistence
    - LangGraph interrupts replace polling for command approval
    - Graph nodes delegate to existing ChatWorkflowManager business logic
"""

import logging
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

# Redis connection for checkpointer (fleet: 172.16.168.23)
_REDIS_URI = None  # Set lazily from SSOT config
_checkpointer = None


class ChatState(TypedDict, total=False):
    """State for the chat workflow graph.

    All fields except session_id and user_message are optional.
    The graph accumulates workflow_messages as it progresses through nodes.
    """

    # Input (set at invocation)
    session_id: str
    user_message: str
    context: Dict[str, Any]

    # Session (set by initialize node)
    terminal_session_id: str
    user_wants_exit: bool

    # Intent detection result
    special_intent_handled: bool
    intent_messages: List[Dict[str, Any]]

    # LLM workflow
    llm_params: Dict[str, Any]
    iteration_context: Dict[str, Any]
    llm_response: str
    tool_calls: List[Dict[str, Any]]
    should_continue: bool
    iteration_count: int
    execution_history: List[Dict[str, Any]]
    all_llm_responses: List[str]

    # Knowledge / RAG
    used_knowledge: bool
    rag_citations: List[Dict[str, Any]]

    # Command approval (interrupt-based)
    pending_approval: Optional[Dict[str, Any]]
    approval_decision: Optional[Dict[str, Any]]

    # Output messages streamed to frontend
    workflow_messages: List[Dict[str, Any]]

    # Error tracking
    error: Optional[str]


# ---------------------------------------------------------------------------
# Graph node functions
# Each node delegates to ChatWorkflowManager methods via the manager
# instance stored in config["configurable"]["manager"].
# ---------------------------------------------------------------------------


async def initialize_session(state: ChatState, config: dict) -> dict:
    """Initialize chat session, load history, detect exit intent."""
    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")

    try:
        (
            session,
            terminal_session_id,
            user_wants_exit,
        ) = await manager._initialize_chat_session(
            state["session_id"], state["user_message"]
        )
        await manager._persist_user_message(state["session_id"], state["user_message"])

        return {
            "terminal_session_id": terminal_session_id,
            "user_wants_exit": user_wants_exit,
            "iteration_count": 0,
            "all_llm_responses": [],
            "execution_history": [],
            "workflow_messages": [],
            "tool_calls": [],
            "should_continue": False,
        }
    except Exception as exc:
        logger.error("initialize_session failed: %s", exc, exc_info=True)
        error_msg = {
            "type": "error",
            "content": f"Session initialization failed: {exc}",
        }
        if stream_cb:
            stream_cb(error_msg)
        return {"error": str(exc), "workflow_messages": [error_msg]}


async def detect_intent(state: ChatState, config: dict) -> dict:
    """Check for exit intent and slash commands."""
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")
    messages = list(state.get("workflow_messages", []))

    from async_chat_workflow import WorkflowMessage

    wf_messages_collector: List[WorkflowMessage] = []
    handled = False

    async for item in manager._process_special_intents(
        state["session_id"],
        state["user_message"],
        state.get("user_wants_exit", False),
        wf_messages_collector,
    ):
        if isinstance(item, bool):
            handled = item
        else:
            msg_dict = item.to_dict() if hasattr(item, "to_dict") else item
            messages.append(msg_dict)
            if stream_cb:
                stream_cb(msg_dict)

    return {
        "special_intent_handled": handled,
        "intent_messages": messages,
        "workflow_messages": messages,
    }


async def prepare_llm(state: ChatState, config: dict) -> dict:
    """Prepare LLM parameters and create iteration context."""
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]

    session = await manager.get_or_create_session(state["session_id"])
    llm_params = await manager._prepare_llm_workflow_params(
        session, state["user_message"], state.get("context", {})
    )
    ctx = manager._create_llm_iteration_context(
        llm_params,
        state["session_id"],
        state["terminal_session_id"],
        state["user_message"],
        [],  # workflow_messages managed by graph state
    )

    return {
        "llm_params": {
            "ollama_endpoint": ctx.ollama_endpoint,
            "selected_model": ctx.selected_model,
            "system_prompt": ctx.system_prompt,
            "initial_prompt": ctx.initial_prompt,
        },
        "used_knowledge": ctx.used_knowledge,
        "rag_citations": [c for c in (ctx.rag_citations or [])],
    }


async def generate_response(state: ChatState, config: dict) -> dict:
    """Run one LLM iteration: call LLM, stream response, parse tool calls.

    Delegates to the manager's continuation loop logic for one iteration.
    Streams WorkflowMessage chunks to frontend via stream_callback.
    """
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")
    messages = list(state.get("workflow_messages", []))
    iteration = state.get("iteration_count", 0) + 1

    from .models import LLMIterationContext

    # Reconstruct the iteration context from state
    ctx = LLMIterationContext(
        ollama_endpoint=state["llm_params"]["ollama_endpoint"],
        selected_model=state["llm_params"]["selected_model"],
        session_id=state["session_id"],
        terminal_session_id=state["terminal_session_id"],
        used_knowledge=state.get("used_knowledge", False),
        rag_citations=state.get("rag_citations", []),
        workflow_messages=[],
        execution_history=list(state.get("execution_history", [])),
        system_prompt=state["llm_params"].get("system_prompt"),
        initial_prompt=state["llm_params"].get("initial_prompt"),
        message=state["user_message"],
    )

    import aiohttp

    from autobot_shared.http_client import get_http_client

    http_client = get_http_client()
    llm_response = None
    should_continue = False

    try:
        async for item in manager._run_continuation_loop_iteration(
            http_client,
            ctx.initial_prompt,
            iteration,
            ctx,
        ):
            if isinstance(item, tuple) and len(item) == 2:
                llm_response, should_continue = item
            else:
                msg_dict = item.to_dict() if hasattr(item, "to_dict") else item
                messages.append(msg_dict)
                if stream_cb:
                    stream_cb(msg_dict)

    except aiohttp.ClientError as exc:
        logger.error("LLM call failed: %s", exc)
        error_msg = {"type": "error", "content": f"LLM error: {exc}"}
        messages.append(error_msg)
        if stream_cb:
            stream_cb(error_msg)
        return {
            "error": str(exc),
            "workflow_messages": messages,
        }

    all_responses = list(state.get("all_llm_responses", []))
    if llm_response:
        all_responses.append(llm_response)

    # Extract tool calls from the iteration context
    parsed_tool_calls = list(ctx.execution_history) if ctx.execution_history else []

    return {
        "llm_response": llm_response or "",
        "should_continue": should_continue,
        "iteration_count": iteration,
        "all_llm_responses": all_responses,
        "tool_calls": parsed_tool_calls,
        "workflow_messages": messages,
    }


async def request_approval(state: ChatState, config: dict) -> dict:
    """Interrupt execution to request command approval from the user.

    Uses LangGraph's interrupt() to pause the graph. The frontend receives
    the interrupt payload via the SSE stream, shows an approval dialog,
    and resumes the graph with Command(resume=decision).
    """
    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return {"pending_approval": None}

    # Find the first tool call needing approval
    pending = None
    for tc in tool_calls:
        if tc.get("needs_approval"):
            pending = tc
            break

    if not pending:
        return {"pending_approval": None}

    stream_cb = config["configurable"].get("stream_callback")

    # Emit approval request to frontend before interrupting
    approval_request = {
        "type": "command_approval_request",
        "content": pending.get("description", ""),
        "metadata": {
            "command": pending.get("command", ""),
            "host": pending.get("host", ""),
            "risk_level": pending.get("risk_level", "medium"),
            "session_id": state["session_id"],
            "terminal_session_id": state["terminal_session_id"],
        },
    }
    if stream_cb:
        stream_cb(approval_request)

    # Interrupt — graph pauses here, resumes with Command(resume=decision)
    decision = interrupt(approval_request)

    return {
        "pending_approval": pending,
        "approval_decision": decision,
    }


async def execute_tools(state: ChatState, config: dict) -> dict:
    """Execute approved tool calls."""
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")
    messages = list(state.get("workflow_messages", []))

    decision = state.get("approval_decision")
    tool_calls = state.get("tool_calls", [])

    if not tool_calls:
        return {"workflow_messages": messages}

    # If approval was needed and denied, skip execution
    if decision and not decision.get("approved", False):
        deny_msg = {
            "type": "response",
            "content": f"Command denied: {decision.get('reason', 'User denied')}",
        }
        messages.append(deny_msg)
        if stream_cb:
            stream_cb(deny_msg)
        return {
            "should_continue": False,
            "workflow_messages": messages,
        }

    # Execute via existing manager method
    exec_history = list(state.get("execution_history", []))
    break_loop = False

    async for item in manager._process_tool_calls(
        tool_calls,
        state["session_id"],
        state["terminal_session_id"],
        state["llm_params"]["ollama_endpoint"],
        state["llm_params"]["selected_model"],
    ):
        if isinstance(item, tuple) and len(item) == 2:
            break_loop, _ = item
        else:
            msg_dict = item.to_dict() if hasattr(item, "to_dict") else item
            messages.append(msg_dict)
            if stream_cb:
                stream_cb(msg_dict)
            # Track execution results
            if isinstance(item, dict) and item.get("type") == "execution_summary":
                exec_history.append(item)

    return {
        "should_continue": not break_loop,
        "execution_history": exec_history,
        "workflow_messages": messages,
        "tool_calls": [],  # Clear after execution
    }


async def persist_conversation(state: ChatState, config: dict) -> dict:
    """Persist conversation to Redis and file storage."""
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]

    try:
        session = await manager.get_or_create_session(state["session_id"])
        combined_response = "\n\n".join(state.get("all_llm_responses", []))

        await manager._persist_conversation(
            state["session_id"],
            session,
            state["user_message"],
            combined_response,
        )

        # Persist workflow messages to chat history
        from async_chat_workflow import WorkflowMessage

        wf_messages = []
        for msg_dict in state.get("workflow_messages", []):
            wf_messages.append(
                WorkflowMessage(
                    type=msg_dict.get("type", "response"),
                    content=msg_dict.get("content", ""),
                    metadata=msg_dict.get("metadata", {}),
                )
            )

        await manager._persist_workflow_messages(
            state["session_id"],
            wf_messages,
            combined_response,
        )

        logger.info(
            "Persisted conversation for session=%s, messages=%d",
            state["session_id"],
            len(wf_messages),
        )
    except Exception as exc:
        logger.error("Failed to persist conversation: %s", exc, exc_info=True)

    return {}


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------


def route_after_intent(state: ChatState) -> str:
    """Route after intent detection."""
    if state.get("error"):
        return END
    if state.get("special_intent_handled"):
        return END
    return "prepare_llm"


def route_after_generation(state: ChatState) -> str:
    """Route after LLM response generation."""
    if state.get("error"):
        return "persist_conversation"

    tool_calls = state.get("tool_calls", [])
    needs_approval = any(tc.get("needs_approval") for tc in tool_calls)

    if needs_approval:
        return "request_approval"
    if tool_calls:
        return "execute_tools"
    return "persist_conversation"


def route_after_execution(state: ChatState) -> str:
    """Route after tool execution — may loop back for continuation."""
    if state.get("error"):
        return "persist_conversation"
    if state.get("should_continue") and state.get("iteration_count", 0) < 5:
        return "generate_response"
    return "persist_conversation"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_chat_graph() -> StateGraph:
    """Build the chat workflow StateGraph.

    Graph topology:
        START → initialize_session → detect_intent
            → [END if special intent]
            → prepare_llm → generate_response
                → [request_approval if needs approval] → execute_tools
                → [execute_tools if has tools]
                → [persist_conversation if no tools]
            execute_tools → [generate_response if should_continue]
                          → [persist_conversation if done]
            persist_conversation → END
    """
    builder = StateGraph(ChatState)

    # Add nodes
    builder.add_node("initialize_session", initialize_session)
    builder.add_node("detect_intent", detect_intent)
    builder.add_node("prepare_llm", prepare_llm)
    builder.add_node("generate_response", generate_response)
    builder.add_node("request_approval", request_approval)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("persist_conversation", persist_conversation)

    # Wire edges
    builder.add_edge(START, "initialize_session")
    builder.add_edge("initialize_session", "detect_intent")
    builder.add_conditional_edges("detect_intent", route_after_intent)
    builder.add_edge("prepare_llm", "generate_response")
    builder.add_conditional_edges("generate_response", route_after_generation)
    builder.add_edge("request_approval", "execute_tools")
    builder.add_conditional_edges("execute_tools", route_after_execution)
    builder.add_edge("persist_conversation", END)

    return builder


async def get_redis_checkpointer() -> AsyncRedisSaver:
    """Get or create the Redis checkpointer for graph persistence."""
    global _checkpointer, _REDIS_URI

    if _checkpointer is not None:
        return _checkpointer

    # Get Redis URI from SSOT config
    try:
        from autobot_shared.ssot_config import config as ssot

        redis_host = ssot.redis.host
        redis_port = ssot.redis.port
        _REDIS_URI = f"redis://{redis_host}:{redis_port}"
    except Exception:
        _REDIS_URI = "redis://172.16.168.23:6379"
        logger.warning(
            "SSOT config unavailable, using fallback Redis URI: %s",
            _REDIS_URI,
        )

    _checkpointer = AsyncRedisSaver.from_conn_string(_REDIS_URI)
    await _checkpointer.asetup()
    logger.info("LangGraph Redis checkpointer initialized: %s", _REDIS_URI)
    return _checkpointer


async def get_compiled_graph(manager):
    """Get a compiled graph instance with Redis checkpointer.

    Args:
        manager: ChatWorkflowManager instance (passed to nodes via config)

    Returns:
        Compiled StateGraph ready for invocation
    """
    checkpointer = await get_redis_checkpointer()
    builder = build_chat_graph()
    return builder.compile(checkpointer=checkpointer)
