# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LangGraph StateGraph for chat workflow orchestration.

Issue #1043: Replaces hand-rolled streaming architecture with LangGraph
StateGraph for native message identity, deduplication, and interrupt-based
command approval.

Issue #1373: Added RLM (Recursive Language Model) self-reflection node.
After generate_response, when no tool calls are present the graph routes
through reflect_on_response which scores the answer.  If quality is below
the threshold AND reflections haven't been exhausted, the graph loops
back to generate_response with a refinement hint injected into the prompt.

Architecture:
    - Graph state (ChatState) is the single source of truth for messages
    - Redis checkpointer provides thread-based persistence
    - LangGraph interrupts replace polling for command approval
    - Graph nodes delegate to existing ChatWorkflowManager business logic
    - RLM reflection evaluates response quality before persisting
"""

import hashlib
import json
from typing import Any, Dict, List, Tuple

from langchain_core.runnables import RunnableConfig

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

try:
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    _REDIS_CHECKPOINTER_AVAILABLE = True
except ImportError:
    AsyncRedisSaver = None  # type: ignore[assignment,misc]
    _REDIS_CHECKPOINTER_AVAILABLE = False
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool-call loop detection constants (#3254)
# ---------------------------------------------------------------------------

# Number of identical-fingerprint iterations required to declare a loop.
_LOOP_DETECTION_WINDOW: int = 3

# Maximum consecutive loop events before the graph halts tool execution.
_LOOP_ABORT_THRESHOLD: int = 2

# Warning injected into the prompt on first loop detection.
_LOOP_WARNING_MSG: str = (
    "You appear to be calling the same tool with identical or near-identical "
    "arguments repeatedly without making progress. Break the loop: either use "
    "the 'respond' tool to explain what you have found so far, or try a "
    "meaningfully different approach."
)

# Redis connection for checkpointer
_REDIS_URI = None  # Set lazily from SSOT config
_checkpointer = None
_compiled_graph = None


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

    # Agentic RAG search (#1718)
    agentic_context: str
    agentic_search_queries: List[str]

    # Command approval (interrupt-based)
    pending_approval: Dict[str, Any] | None
    approval_decision: Dict[str, Any] | None

    # Output messages streamed to frontend
    workflow_messages: List[Dict[str, Any]]

    # RLM self-reflection (#1373)
    reflection_count: int
    reflection_history: List[Dict[str, Any]]
    rlm_refinement_hint: str

    # Tool-call loop detection (#3254)
    # Each entry is a frozenset fingerprint of (tool_name, args_hash) for one iteration.
    tool_call_fingerprints: List[str]
    tool_loop_count: int
    tool_loop_warning: str

    # Error tracking
    error: str | None


# ---------------------------------------------------------------------------
# Tool-call loop detection helpers (#3254)
# ---------------------------------------------------------------------------


def _fingerprint_tool_call(tool_call: Dict[str, Any]) -> str:
    """Return a stable string fingerprint for one tool call.

    The fingerprint is built from the tool name plus a SHA-1 digest of the
    canonically sorted JSON-serialised params dict.  Using a digest (rather
    than the raw params string) keeps fingerprints constant-length and avoids
    false negatives caused by key-ordering differences.

    Issue #3254: content-aware detection — two calls are considered identical
    when *both* the tool name and the arguments are the same.

    Args:
        tool_call: A parsed tool-call dict with at least a "name" key and an
                   optional "params" key (dict or scalar).

    Returns:
        A short string of the form ``"<name>:<hex_digest>"``.
    """
    name = tool_call.get("name", "")
    params = tool_call.get("params", {})
    try:
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = str(params)
    digest = hashlib.sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{name}:{digest}"


def _detect_tool_call_loop(
    new_fingerprints: List[str],
    history: List[str],
    window: int = _LOOP_DETECTION_WINDOW,
) -> Tuple[bool, List[str]]:
    """Detect whether the current iteration is a repetition of recent ones.

    A loop is declared when the last ``window - 1`` entries in ``history``
    are all identical to the current set of fingerprints.  This requires at
    least ``window`` consecutive identical iterations before triggering.

    Issue #3254: content-aware (not just count-based) — two iterations are
    considered identical only when they produce *the same tool calls in the
    same order*.

    Args:
        new_fingerprints: Fingerprint strings for the current iteration's
                          tool calls (one entry per tool call).
        history:          Accumulated per-iteration fingerprint strings from
                          previous iterations (each entry is one iteration's
                          comma-joined fingerprints).
        window:           How many identical consecutive iterations trigger
                          the loop alarm (default: ``_LOOP_DETECTION_WINDOW``).

    Returns:
        ``(is_loop, updated_history)`` where ``updated_history`` has the new
        iteration's fingerprint appended.
    """
    current_key = ",".join(new_fingerprints)
    updated = (list(history) + [current_key])[-window:]

    if len(updated) < window:
        return False, updated

    recent = updated[-(window):]
    is_loop = len(set(recent)) == 1 and recent[0] != ""
    return is_loop, updated


# ---------------------------------------------------------------------------
# Graph node functions
# Each node delegates to ChatWorkflowManager methods via the manager
# instance stored in config["configurable"]["manager"].
# ---------------------------------------------------------------------------


async def initialize_session(state: ChatState, config: RunnableConfig) -> dict:
    """Initialize chat session, load history, detect exit intent."""
    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")

    try:
        (
            session,
            terminal_session_id,
            user_wants_exit,
        ) = await manager._initialize_chat_session(state["session_id"], state["user_message"])
        await manager._persist_user_message(state["session_id"], state["user_message"])

        # Issue #3278: fire ON_MESSAGE_RECEIVED hook so plugins can observe chat input.
        try:
            from autobot_shared.plugin_sdk import Hook, HookRegistry

            await HookRegistry().call_hook(
                Hook.ON_MESSAGE_RECEIVED.value,
                session_id=state["session_id"],
                message=state["user_message"],
            )
        except Exception as _hook_exc:  # noqa: BLE001
            logger.debug("Plugin hook ON_MESSAGE_RECEIVED failed (non-fatal): %s", _hook_exc)

        return {
            "terminal_session_id": terminal_session_id,
            "user_wants_exit": user_wants_exit,
            "iteration_count": 0,
            "all_llm_responses": [],
            "execution_history": [],
            "workflow_messages": [],
            "tool_calls": [],
            "should_continue": False,
            # RLM state (#1373)
            "reflection_count": 0,
            "reflection_history": [],
            "rlm_refinement_hint": "",
            # Tool-call loop detection (#3254)
            "tool_call_fingerprints": [],
            "tool_loop_count": 0,
            "tool_loop_warning": "",
        }
    except Exception as exc:
        logger.error("initialize_session failed: %s", exc, exc_info=True)
        error_msg = {
            "type": "error",
            "content": "Session initialization failed",
        }
        if stream_cb:
            stream_cb(error_msg)
        return {"error": "Session initialization failed", "workflow_messages": [error_msg]}


async def detect_intent(state: ChatState, config: RunnableConfig) -> dict:
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


async def prepare_llm(state: ChatState, config: RunnableConfig) -> dict:
    """Prepare LLM parameters and create iteration context."""
    if state.get("error"):
        return {}

    manager = config["configurable"]["manager"]

    session = await manager.get_or_create_session(state["session_id"])
    llm_params = await manager._prepare_llm_workflow_params(session, state["user_message"], state.get("context", {}))
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
        # Reset per-turn loop detection state (#3583). LangGraph persists
        # ChatState in Redis across turns; without this reset, loop counts
        # accumulate across different user turns and trigger false aborts.
        "tool_loop_count": 0,
        "tool_call_fingerprints": [],
        "tool_loop_warning": "",
    }


def _inject_mid_conversation_warning(hint: str, initial_prompt: str) -> str:
    """Append a corrective hint to the prompt string for mid-conversation injection.

    Issue #3260 — Anthropic provider constraint: the Anthropic API only permits
    a system message at the *start* of a conversation.  Any additional
    ``SystemMessage`` inserted after the first human turn raises a validation
    error from ``langchain_anthropic._format_messages()``.

    Rule: ALL mid-conversation corrective content (loop warnings, guardrail
    feedback, RLM refinement hints, etc.) MUST be injected by appending to
    ``initial_prompt`` (prompt-string injection) or wrapped in a
    ``HumanMessage``.  Never construct a standalone ``SystemMessage`` and
    insert it after the conversation has started.

    Args:
        hint: The corrective text to inject (e.g. a loop-detection warning or
              a self-reflection refinement note).
        initial_prompt: The current value of the initial prompt string that
                        will be forwarded to the LLM on the next iteration.

    Returns:
        A new prompt string with ``hint`` appended in a clearly labelled block.

    Example::

        >>> _inject_mid_conversation_warning("Avoid repeating tool calls.", "Answer the question.")
        'Answer the question.\\n\\n[Guidance: Avoid repeating tool calls.]'
    """
    return f"{initial_prompt}\n\n[Guidance: {hint}]"


def _build_llm_iteration_context(state: ChatState):
    """Helper for generate_response. Ref: #1088, #1373, #3254, #3260.

    Reconstructs an LLMIterationContext from the current graph state so that
    generate_response can delegate to the manager's continuation loop method.

    When an RLM refinement hint is present (set by reflect_on_response), it
    is appended to the initial prompt so the LLM focuses on the identified
    deficiency in the next pass.

    When a tool-call loop warning is present (#3254), it is similarly appended
    so the LLM is instructed to break out of the repetitive pattern.

    Note (Issue #3260): Corrective/warning content is always merged into
    ``initial_prompt`` via ``_inject_mid_conversation_warning``, never via a
    ``SystemMessage``.  See that helper's docstring for the full rationale.
    """
    from .models import LLMIterationContext

    initial_prompt = state["llm_params"].get("initial_prompt") or ""

    # Inject RLM refinement hint when looping back (#1373).
    # Must use _inject_mid_conversation_warning — not SystemMessage — to satisfy
    # Anthropic's requirement that SystemMessage only appear as the first message.
    hint = state.get("rlm_refinement_hint", "")
    if hint:
        initial_prompt = _inject_mid_conversation_warning(hint, initial_prompt)

    # Inject tool-call loop warning when a repetition loop is detected (#3254).
    # Same constraint applies: prompt-string injection only, never SystemMessage.
    loop_warning = state.get("tool_loop_warning", "")
    if loop_warning:
        initial_prompt = _inject_mid_conversation_warning(loop_warning, initial_prompt)

    return LLMIterationContext(
        ollama_endpoint=state["llm_params"]["ollama_endpoint"],
        selected_model=state["llm_params"]["selected_model"],
        session_id=state["session_id"],
        terminal_session_id=state["terminal_session_id"],
        used_knowledge=state.get("used_knowledge", False),
        rag_citations=state.get("rag_citations", []),
        workflow_messages=[],
        execution_history=list(state.get("execution_history", [])),
        system_prompt=state["llm_params"].get("system_prompt"),
        initial_prompt=initial_prompt,
        message=state["user_message"],
    )


async def _run_llm_iteration(manager, ctx, iteration, messages, stream_cb):
    """Helper for generate_response. Ref: #1088.

    Drives one pass through manager._run_continuation_loop_iteration, streaming
    non-terminal messages to the frontend and accumulating persisted ones.
    Returns (messages, llm_response, should_continue) on success.
    Raises aiohttp.ClientError on LLM transport failure.
    """

    from autobot_shared.http_client import get_http_client

    http_client = get_http_client()
    llm_response = None
    should_continue = False

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
            if stream_cb:
                stream_cb(msg_dict)
            is_streaming = msg_dict.get("metadata", {}).get("streaming", False)
            if not is_streaming:
                messages.append(msg_dict)

    return messages, llm_response, should_continue


async def generate_response(state: ChatState, config: RunnableConfig) -> dict:
    """Run one LLM iteration: call LLM, stream response, parse tool calls.

    Delegates to the manager's continuation loop logic for one iteration.
    Streams WorkflowMessage chunks to frontend via stream_callback.

    Issue #3232: emits agent.step.start / agent.step.complete CoT events.
    """
    if state.get("error"):
        return {}

    import aiohttp

    from chat_workflow.cot_events import emit_step_complete, emit_step_start

    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")
    messages = list(state.get("workflow_messages", []))
    iteration = state.get("iteration_count", 0) + 1
    ctx = _build_llm_iteration_context(state)
    session_id = state.get("session_id")

    # Issue #3232: emit step-level CoT event so frontend can track LLM reasoning.
    step_name = f"llm_iteration_{iteration}"
    _cot_start = emit_step_start(
        step_name,
        session_id=session_id,
        agent_type="chat_workflow",
        step_id=step_name,
    )

    # Issue #3278: notify plugins before LLM execution.
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_AGENT_EXECUTE.value,
            session_id=session_id,
            iteration=iteration,
            agent_type="chat_workflow",
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_AGENT_EXECUTE failed (non-fatal): %s", _hook_exc)

    try:
        messages, llm_response, should_continue = await _run_llm_iteration(manager, ctx, iteration, messages, stream_cb)
    except aiohttp.ClientError as exc:
        logger.error("LLM call failed: %s", exc)
        error_msg = {"type": "error", "content": "LLM error: Request failed"}
        messages.append(error_msg)
        if stream_cb:
            stream_cb(error_msg)
        emit_step_complete(
            step_name,
            _cot_start,
            output_summary="LLM error: Request failed",
            session_id=session_id,
        )
        # Issue #3278: notify plugins on agent error.
        try:
            from autobot_shared.plugin_sdk import Hook, HookRegistry

            await HookRegistry().call_hook(
                Hook.ON_AGENT_ERROR.value,
                session_id=session_id,
                iteration=iteration,
                error=str(exc),
            )
        except Exception as _hook_exc:  # noqa: BLE001
            logger.debug("Plugin hook ON_AGENT_ERROR failed (non-fatal): %s", _hook_exc)
        return {"error": str(exc), "workflow_messages": messages}

    # Issue #3278: notify plugins after successful LLM execution.
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_AGENT_COMPLETE.value,
            session_id=session_id,
            iteration=iteration,
            response=llm_response or "",
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_AGENT_COMPLETE failed (non-fatal): %s", _hook_exc)

    all_responses = list(state.get("all_llm_responses", []))
    if llm_response:
        all_responses.append(llm_response)
    parsed_tool_calls = list(ctx.execution_history) if ctx.execution_history else []

    # Issue #3232: emit plan event when the response contains a planning block.
    if parsed_tool_calls:
        from chat_workflow.cot_events import emit_plan

        emit_plan(parsed_tool_calls, session_id=session_id)

    emit_step_complete(
        step_name,
        _cot_start,
        output_summary=(
            f"{len(parsed_tool_calls)} tool call(s) queued" if parsed_tool_calls else "LLM response complete"
        ),
        session_id=session_id,
    )

    return {
        "llm_response": llm_response or "",
        "should_continue": should_continue,
        "iteration_count": iteration,
        "all_llm_responses": all_responses,
        "tool_calls": parsed_tool_calls,
        "workflow_messages": messages,
        # Reset loop warning so it is only active for one cycle (#3254).
        "tool_loop_warning": "",
    }


async def reflect_on_response(state: ChatState, config: RunnableConfig) -> dict:
    """RLM self-reflection: evaluate LLM response quality (#1373).

    Uses ResponseQualityEvaluator to score the latest LLM response.
    If the score is below the configured threshold and the reflection
    budget hasn't been exhausted, sets rlm_refinement_hint so the next
    generate_response pass can incorporate it.
    """
    from rlm import ResponseQualityEvaluator, RLMConfig

    rlm_cfg = config["configurable"].get("rlm_config") or RLMConfig()

    # Fast-path: RLM disabled or no response to evaluate
    if not rlm_cfg.enabled:
        return {}

    llm_response = state.get("llm_response", "")
    if not llm_response:
        return {}

    reflection_count = state.get("reflection_count", 0)
    history = list(state.get("reflection_history", []))

    evaluator = ResponseQualityEvaluator(config=rlm_cfg)
    result = await evaluator.evaluate(
        query=state["user_message"],
        response=llm_response,
        iteration=reflection_count + 1,
    )

    history.append(result.to_dict())

    logger.info(
        "RLM reflect: score=%.2f verdict=%s iter=%d/%d",
        result.quality_score,
        result.verdict.name,
        reflection_count + 1,
        rlm_cfg.max_reflections,
    )

    return {
        "reflection_count": reflection_count + 1,
        "reflection_history": history,
        "rlm_refinement_hint": result.refinement_hint,
    }


async def request_approval(state: ChatState, config: RunnableConfig) -> dict:
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


async def execute_tools(state: ChatState, config: RunnableConfig) -> dict:
    """Execute approved tool calls.

    Issue #3232: emits agent.step.start/complete around the tool execution
    block so the frontend reasoning trace shows the execution phase.
    """
    if state.get("error"):
        return {}

    from chat_workflow.cot_events import emit_step_complete, emit_step_start

    manager = config["configurable"]["manager"]
    stream_cb = config["configurable"].get("stream_callback")
    messages = list(state.get("workflow_messages", []))
    session_id = state.get("session_id")

    decision = state.get("approval_decision")
    tool_calls = state.get("tool_calls", [])

    if not tool_calls:
        return {"workflow_messages": messages}

    _cot_exec_start = emit_step_start(
        "execute_tools",
        session_id=session_id,
        agent_type="chat_workflow",
    )

    # If approval was needed and denied, skip execution
    if decision and not decision.get("approved", False):
        deny_msg = {
            "type": "response",
            "content": f"Command denied: {decision.get('reason', 'User denied')}",
        }
        messages.append(deny_msg)
        if stream_cb:
            stream_cb(deny_msg)
        emit_step_complete(
            "execute_tools",
            _cot_exec_start,
            output_summary="approval denied — tools skipped",
            session_id=session_id,
        )
        return {
            "should_continue": False,
            "workflow_messages": messages,
        }

    # Issue #3254: Fingerprint the tool calls about to run and detect loops
    # *before* execution.  This is the correct place because execute_tools
    # receives the parsed tool call list from generate_response via state.
    fingerprint_history = list(state.get("tool_call_fingerprints", []))
    tool_loop_count = state.get("tool_loop_count", 0)
    tool_loop_warning = ""

    new_fps = [_fingerprint_tool_call(tc) for tc in tool_calls]
    is_loop, fingerprint_history = _detect_tool_call_loop(new_fps, fingerprint_history)
    if is_loop:
        tool_loop_count += 1
        tool_loop_warning = _LOOP_WARNING_MSG
        logger.warning(
            "Tool-call loop detected (loop_count=%d, session=%s): %s",
            tool_loop_count,
            state.get("session_id", "unknown"),
            new_fps,
        )

    # Issue #3278: notify plugins before tool execution.
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_TOOL_CALL.value,
            session_id=state.get("session_id"),
            tool_calls=tool_calls,
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_TOOL_CALL failed (non-fatal): %s", _hook_exc)

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
            # Stream ALL messages for real-time display
            if stream_cb:
                stream_cb(msg_dict)
            # Only persist non-streaming chunks (#1064)
            is_streaming = msg_dict.get("metadata", {}).get("streaming", False)
            if not is_streaming:
                messages.append(msg_dict)
            # Track execution results
            if isinstance(item, dict) and item.get("type") == "execution_summary":
                exec_history.append(item)

    # Issue #3254: Emit a user-visible message when the loop abort threshold is
    # reached so the user understands why the assistant stopped making progress.
    if tool_loop_count >= _LOOP_ABORT_THRESHOLD:
        abort_msg = {
            "type": "response",
            "content": (
                "I noticed I was repeating the same action without making progress "
                "and stopped the loop. Please let me know if you would like me to "
                "try a different approach."
            ),
        }
        messages.append(abort_msg)
        if stream_cb:
            stream_cb(abort_msg)

    # Issue #3278: notify plugins after tool execution.
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_TOOL_COMPLETE.value,
            session_id=session_id,
            execution_history=exec_history,
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_TOOL_COMPLETE failed (non-fatal): %s", _hook_exc)

    # Issue #3232: emit step complete for the execute_tools block.
    emit_step_complete(
        "execute_tools",
        _cot_exec_start,
        output_summary=(f"tools executed; loop_aborted={tool_loop_count >= _LOOP_ABORT_THRESHOLD}"),
        session_id=session_id,
    )

    return {
        "should_continue": not break_loop,
        "execution_history": exec_history,
        "workflow_messages": messages,
        "tool_calls": [],  # Clear after execution
        # Tool-call loop state (#3254)
        "tool_call_fingerprints": fingerprint_history,
        "tool_loop_count": tool_loop_count,
        "tool_loop_warning": tool_loop_warning,
    }


async def perform_knowledge_search(state: ChatState, config: RunnableConfig) -> dict:
    """Agentic RAG pre-fetch: run knowledge_search_tool before LLM generation.

    Issue #1718: When agentic search is enabled (RAGConfig.enable_agentic_search),
    this node calls the AgenticSearchTool with the user's message, obtaining
    rewritten-query + iterative-retrieval context before the LLM sees the prompt.

    The assembled context string is stored in state["agentic_context"] and
    injected into the LLM prompt by prepare_llm (via the manager's context
    population path).  When the RAGService is unavailable the node degrades
    gracefully: agentic_context is set to "" and execution continues normally.

    Args:
        state:  Current ChatState.
        config: LangGraph RunnableConfig; must contain "configurable.manager".

    Returns:
        Partial state update with agentic_context and agentic_search_queries.
    """
    if state.get("error"):
        return {}

    manager = config["configurable"].get("manager")
    if manager is None:
        return {"agentic_context": "", "agentic_search_queries": []}

    # Respect the agentic search feature flag from RAGConfig
    try:
        from knowledge.search_components.agentic_search import (
            AgenticSearchConfig,
            knowledge_search_tool,
        )
        from services.rag_config import get_rag_config

        rag_cfg = get_rag_config()
        if not rag_cfg.enable_agentic_search:
            return {"agentic_context": "", "agentic_search_queries": []}

        agentic_cfg = AgenticSearchConfig(
            enable_agentic_search=rag_cfg.enable_agentic_search,
            rewrite_enabled=rag_cfg.rewrite_enabled,
            max_search_iterations=rag_cfg.max_search_iterations,
        )

        rag_service = getattr(manager, "rag_service", None)
        if rag_service is None:
            logger.debug("Manager has no rag_service; skipping agentic search")
            return {"agentic_context": "", "agentic_search_queries": []}

        # Issue #4263: Emit BEFORE_RAG_QUERY hook before executing RAG query
        from chat_workflow.session_handler import _emit_before_rag_query

        user_query = state["user_message"]
        try:
            # Allow extensions to inspect/modify the query
            user_query = await _emit_before_rag_query(
                user_query,
                state.get("session_id"),
                {},
            )
        except Exception as hook_exc:  # noqa: BLE001
            logger.debug("BEFORE_RAG_QUERY hook failed (non-fatal): %s", hook_exc)

        context_str = await knowledge_search_tool(
            query=user_query,
            rag_service=rag_service,
            context=None,
            config=agentic_cfg,
        )

        # Issue #4263: Emit AFTER_RAG_RESULTS hook after RAG returns results
        from chat_workflow.session_handler import _emit_after_rag_results

        try:
            # Convert context_str back to results format for extensions
            # Results format: list of dicts with content/metadata
            results = [{"content": context_str}] if context_str else []
            results = await _emit_after_rag_results(
                results,
                user_query,
                state.get("session_id"),
                {},
            )
            # Reconstruct context_str from filtered results
            context_str = "\n\n".join([r.get("content", "") for r in results if r.get("content")])
        except Exception as hook_exc:  # noqa: BLE001
            logger.debug("AFTER_RAG_RESULTS hook failed (non-fatal): %s", hook_exc)

        # Track the original query; refined queries are recorded inside the tool
        queries_used: List[str] = [state["user_message"]]

        logger.info(
            "Agentic search complete: context_len=%d",
            len(context_str),
        )

        # Issue #3278: notify plugins after knowledge base search.
        try:
            from autobot_shared.plugin_sdk import Hook, HookRegistry

            await HookRegistry().call_hook(
                Hook.ON_KB_SEARCH.value,
                session_id=state.get("session_id"),
                query=state["user_message"],
                context_length=len(context_str),
            )
        except Exception as _hook_exc:  # noqa: BLE001
            logger.debug("Plugin hook ON_KB_SEARCH failed (non-fatal): %s", _hook_exc)

        return {
            "agentic_context": context_str,
            "agentic_search_queries": queries_used,
            "used_knowledge": bool(context_str),
        }
    except Exception as exc:
        logger.warning("Agentic search failed (non-fatal): %s", exc)
        return {"agentic_context": "", "agentic_search_queries": []}


async def persist_conversation(state: ChatState, config: RunnableConfig) -> dict:
    """Persist conversation to Redis and file storage."""
    if state.get("error"):
        return {}

    from chat_workflow.llm_handler import _emit_loop_complete

    manager = config["configurable"]["manager"]
    session_id = state.get("session_id", "")
    total_iterations = state.get("iteration_count", 0)
    combined_response = "\n\n".join(state.get("all_llm_responses", []))

    # Emit LOOP_COMPLETE hook to notify extensions
    await _emit_loop_complete(total_iterations, combined_response, session_id)

    try:
        session = await manager.get_or_create_session(state["session_id"])

        # Issue #4263: Emit BEFORE_RESPONSE_SEND hook before sending response
        from chat_workflow.llm_handler import _emit_before_response_send

        try:
            # Allow extensions to inspect/modify response before sending
            combined_response = await _emit_before_response_send(
                combined_response,
                state.get("session_id"),
                {},
            )
        except Exception as hook_exc:  # noqa: BLE001
            logger.debug("BEFORE_RESPONSE_SEND hook failed (non-fatal): %s", hook_exc)

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

        # Issue #4263: Emit AFTER_RESPONSE_SEND hook after response is sent
        from chat_workflow.llm_handler import _emit_after_response_send

        try:
            await _emit_after_response_send(
                combined_response,
                state.get("session_id"),
                {},
            )
        except Exception as hook_exc:  # noqa: BLE001
            logger.debug("AFTER_RESPONSE_SEND hook failed (non-fatal): %s", hook_exc)

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
    """Route after LLM response generation.

    Issue #1373: When there are no tool calls, route through
    reflect_on_response before persisting so the RLM evaluator
    can decide whether to refine the answer.
    """
    if state.get("error"):
        return "persist_conversation"

    tool_calls = state.get("tool_calls", [])
    needs_approval = any(tc.get("needs_approval") for tc in tool_calls)

    if needs_approval:
        return "request_approval"
    if tool_calls:
        return "execute_tools"
    # No tool calls → run RLM self-reflection before persisting
    return "reflect_on_response"


def route_after_reflection(state: ChatState) -> str:
    """Route after RLM self-reflection (#1373).

    If the evaluator returned REFINE and the reflection budget isn't
    exhausted, loop back to generate_response.  Otherwise persist.
    """
    from rlm.types import RLMConfig

    history = state.get("reflection_history", [])
    if not history:
        return "persist_conversation"

    latest = history[-1]
    verdict = latest.get("verdict", "ACCEPT")
    reflection_count = state.get("reflection_count", 0)

    # Use default config ceiling — the actual config is in the node
    max_reflections = RLMConfig().max_reflections

    if verdict == "REFINE" and reflection_count < max_reflections:
        return "generate_response"
    return "persist_conversation"


def route_after_execution(state: ChatState) -> str:
    """Route after tool execution — may loop back for continuation.

    Issue #3254: Aborts to persist_conversation when the tool-call loop
    detector has fired ``_LOOP_ABORT_THRESHOLD`` or more consecutive times,
    preventing infinite repetition even when ``should_continue`` is True.
    """
    if state.get("error"):
        return "persist_conversation"

    # Issue #3254: Abort on persistent tool-call loop.
    if state.get("tool_loop_count", 0) >= _LOOP_ABORT_THRESHOLD:
        logger.warning(
            "Aborting tool-call loop after %d detections (session=%s)",
            state.get("tool_loop_count", 0),
            state.get("session_id", "unknown"),
        )
        return "persist_conversation"

    if state.get("should_continue") and state.get("iteration_count", 0) < 5:
        return "generate_response"
    return "persist_conversation"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_chat_graph() -> StateGraph:
    """Build the chat workflow StateGraph.

    Graph topology (#1718 — agentic search node; #1373 — RLM reflection loop;
    #3254 — content-aware tool-call loop detection):
        START -> initialize_session -> detect_intent
            -> [END if special intent]
            -> prepare_llm -> perform_knowledge_search -> generate_response
                -> [request_approval if needs approval] -> execute_tools
                -> [execute_tools if has tools]
                -> [reflect_on_response if no tools]
            reflect_on_response
                -> [generate_response if REFINE and budget remains]
                -> [persist_conversation if ACCEPT or budget exhausted]
            execute_tools
                -> [generate_response if should_continue AND loop_count < threshold]
                -> [persist_conversation if done or loop aborted (#3254)]
            persist_conversation -> END
    """
    builder = StateGraph(ChatState)

    # Add nodes
    builder.add_node("initialize_session", initialize_session)
    builder.add_node("detect_intent", detect_intent)
    builder.add_node("prepare_llm", prepare_llm)
    builder.add_node("perform_knowledge_search", perform_knowledge_search)  # Issue #1718
    builder.add_node("generate_response", generate_response)
    builder.add_node("reflect_on_response", reflect_on_response)
    builder.add_node("request_approval", request_approval)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("persist_conversation", persist_conversation)

    # Wire edges
    builder.add_edge(START, "initialize_session")
    builder.add_edge("initialize_session", "detect_intent")
    builder.add_conditional_edges("detect_intent", route_after_intent)
    builder.add_edge("prepare_llm", "perform_knowledge_search")  # Issue #1718
    builder.add_edge("perform_knowledge_search", "generate_response")  # Issue #1718
    builder.add_conditional_edges("generate_response", route_after_generation)
    builder.add_conditional_edges("reflect_on_response", route_after_reflection)
    builder.add_edge("request_approval", "execute_tools")
    builder.add_conditional_edges("execute_tools", route_after_execution)
    builder.add_edge("persist_conversation", END)

    return builder


async def get_redis_checkpointer() -> "AsyncRedisSaver":  # type: ignore[return]
    """Get or create the Redis checkpointer for graph persistence."""
    global _checkpointer, _REDIS_URI

    if not _REDIS_CHECKPOINTER_AVAILABLE:
        raise RuntimeError(
            "AsyncRedisSaver unavailable: langgraph-checkpoint-redis requires "
            "redisvl with a compatible redis-py version (issue #5623)."
        )

    if _checkpointer is not None:
        return _checkpointer

    # Get Redis URI and checkpoint TTL from SSOT config.
    # Issue #3231: default raised to 30 days (43200 min) to prevent silent
    # checkpoint expiry during human-in-the-loop pauses.
    ttl_minutes = 43200  # Default: 30 days
    try:
        from autobot_shared.ssot_config import config as ssot

        redis_host = ssot.vm.redis
        redis_port = ssot.port.redis
        _REDIS_URI = f"redis://{redis_host}:{redis_port}"
        ttl_minutes = ssot.redis.checkpoint_ttl_minutes
    except Exception:
        redis_host = config.redis_host
        redis_port = config.redis_port
        _REDIS_URI = f"redis://{redis_host}:{redis_port}"
        logger.warning(
            "SSOT config unavailable, using fallback Redis URI: %s",
            _REDIS_URI,
        )

    # Issue #1481: TTL config for checkpoint auto-expiration
    ttl_config = None
    if ttl_minutes > 0:
        ttl_config = {
            "default_ttl": ttl_minutes,
            "refresh_on_read": True,
        }

    # Issue #1433: from_conn_string() is an async generator, use direct init
    _checkpointer = AsyncRedisSaver(redis_url=_REDIS_URI, ttl=ttl_config)
    await _checkpointer.asetup()
    logger.info(
        "LangGraph Redis checkpointer initialized: %s (TTL: %s min)",
        _REDIS_URI,
        ttl_minutes if ttl_minutes > 0 else "disabled",
    )
    return _checkpointer


async def delete_thread_checkpoints(thread_id: str) -> None:
    """Delete all LangGraph checkpoints for a session thread.

    Issue #1475: Called after unrecoverable graph errors to prevent corrupted
    checkpoints from blocking future invocations on the same chat session.

    Args:
        thread_id: The session ID whose checkpoints should be deleted.
    """
    try:
        checkpointer = await get_redis_checkpointer()
        await checkpointer.adelete_thread(thread_id)
        logger.info("Cleared LangGraph checkpoints for thread: %s", thread_id)
    except Exception as exc:
        logger.warning("Failed to clear checkpoints for thread %s: %s", thread_id, exc)


async def get_compiled_graph(manager):
    """Get a compiled graph instance with Redis checkpointer.

    The compiled graph is cached as a module-level singleton since the graph
    structure is static — only per-invocation config (thread_id, manager,
    stream_callback) varies.

    Args:
        manager: ChatWorkflowManager instance (passed to nodes via config)

    Returns:
        Compiled StateGraph ready for invocation
    """
    global _compiled_graph

    if _compiled_graph is not None:
        return _compiled_graph

    checkpointer = await get_redis_checkpointer()
    builder = build_chat_graph()
    _compiled_graph = builder.compile(checkpointer=checkpointer)
    return _compiled_graph
