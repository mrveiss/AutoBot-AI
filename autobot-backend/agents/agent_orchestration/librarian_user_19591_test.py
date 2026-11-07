# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent orchestration reads the KB as the verified triggering user, else nothing (#19591, #16665)."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.agent_orchestration.agent_execution import AgentExecutor
from agents.agent_orchestration.reading_user import reading_user
from agents.agent_orchestration.types import AgentType
from agents.kb_librarian_agent import KBLibrarianAgent
from knowledge.read_path_fakes_16665 import PRIVATE_A, PRIVATE_B, SHARED, FakeKB

BACKEND = Path(__file__).resolve().parents[2]


def _librarian() -> KBLibrarianAgent:
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base, agent.enabled = FakeKB(), True
    agent.max_results, agent.similarity_threshold, agent.auto_summarize = 5, 0.0, False
    return agent


def _executor(rag=None) -> AgentExecutor:
    executor = object.__new__(AgentExecutor)
    librarian = _librarian()
    executor._get_kb_librarian = lambda: librarian
    executor._get_rag_agent = lambda: rag
    executor._specialized_getters = {}
    return executor


def _rag_recorder():
    rag = MagicMock()
    rag.process_document_query = AsyncMock(side_effect=lambda req, docs, ctx: {"docs": docs})
    return rag


async def _retrieve(user_id, context=None):
    return await _executor()._execute_single_agent(AgentType.KNOWLEDGE_RETRIEVAL, "q", context, None, user_id)


async def _rag(user_id, context=None):
    return await _executor(_rag_recorder())._execute_single_agent(AgentType.RAG, "q", context, None, user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("run", [_retrieve, _rag])
async def test_the_triggering_user_gets_their_facts_and_never_anothers(run):
    text = repr(await run("alice"))
    assert PRIVATE_A in text and SHARED in text
    assert PRIVATE_B not in text
    assert PRIVATE_A not in repr(await run("bob"))


@pytest.mark.asyncio
@pytest.mark.parametrize("run", [_retrieve, _rag])
async def test_with_no_user_the_librarian_still_denies(run):
    text = repr(await run(None))
    assert not any(fact in text for fact in (PRIVATE_A, PRIVATE_B, SHARED))


@pytest.mark.asyncio
async def test_a_user_named_in_context_is_never_trusted():
    text = repr(await _retrieve(None, context={"user_id": "alice", "metadata": {"user_id": "alice"}}))
    assert PRIVATE_A not in text


@pytest.mark.asyncio
async def test_the_multi_agent_secondary_step_reads_as_the_same_user():
    executor = _executor()
    routing = {"primary_agent": AgentType.KNOWLEDGE_RETRIEVAL, "secondary_agents": [AgentType.KNOWLEDGE_RETRIEVAL]}
    executor._synthesize_multi_agent_results = AsyncMock(side_effect=lambda p, s, r: {"p": p, "s": s})
    executor.router = MagicMock(adapt_request_for_secondary=lambda *a: "q2")

    text = repr(await executor._execute_multi_agent(routing, "q", None, None, "alice"))

    assert text.count(PRIVATE_A) >= 2 and PRIVATE_B not in text


@pytest.mark.parametrize("value", [None, "", "   ", 7, {"id": "a"}])
def test_reading_user_is_the_verified_string_or_nobody(value):
    assert reading_user(value) is None


def test_reading_user_keeps_a_real_user():
    assert reading_user("alice") == "alice"


@pytest.mark.asyncio
async def test_an_a2a_peer_is_not_a_local_user_so_the_librarian_gets_none():
    from a2a import task_executor

    coordinator = MagicMock(process_request=AsyncMock(return_value={"status": "refused"}))
    manager = MagicMock()
    hostile = {"user_id": "alice"}
    with (
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=coordinator),
        patch.object(task_executor, "_report_capability_refusal"),
        patch.object(task_executor, "_scrub_inbound", return_value="q"),
        patch.object(task_executor, "_abort_if_cancelled", AsyncMock(return_value=False)),
    ):
        await task_executor._execute_claimed("t1", "q", hostile, 0.6, "peer", manager)

    assert coordinator.process_request.await_args.kwargs.get("user_id") is None


KB_METHODS = {"process_query", "search_knowledge", "answer_question"}
#: ``_register_specialized_handlers`` calls the data-analysis, translation, ... agents as
#: ``g().process_query``: LLM-prompt agents with no KB read, so no user to name (checked in #19591).
NON_KB_FUNCTIONS = {"_register_specialized_handlers"}
#: ``api/ai_stack_integration.py`` calls the external AI-stack client's own ``search_knowledge``.
#: The seven modality agents define their own LLM-prompt ``process_query`` and never touch the KB.
NON_KB_FILES = {"api/ai_stack_integration.py"} | {
    f"agents/{name}_agent.py"
    for name in (
        "data_analysis",
        "translation",
        "sentiment_analysis",
        "code_generation",
        "audio_processing",
        "summarization",
        "image_analysis",
    )
}
EXPECTED_FILES = {
    "agents/agent_orchestration/reading_user.py",
    "agents/kb_librarian_agent.py",
    "api/kb_librarian.py",
    "api/workflow_librarian_step.py",
    "agents/knowledge_retrieval_agent.py",
}


def _parents(tree: ast.AST) -> dict:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _enclosing_function(node: ast.AST, parents: dict) -> str | None:
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return None


def _names_a_method(parent: ast.AST | None) -> bool:
    """True if a string constant is used to look a method up (``getattr``, ``partial``, an action table)."""
    if isinstance(parent, ast.keyword):
        return parent.arg in {"handler_method", "method_name"}
    if isinstance(parent, ast.Call):
        return ast.unparse(parent.func).split(".")[-1] in {"getattr", "hasattr", "partial", "methodcaller"}
    return False


def _scan(path: Path):
    """(calls, indirect) for *path*: KB-method calls as (line, has_user_id), and non-call references."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = _parents(tree)
    calls, indirect = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in KB_METHODS:
            parent = parents.get(node)
            if isinstance(parent, ast.Call) and parent.func is node:
                if _enclosing_function(node, parents) in NON_KB_FUNCTIONS:
                    continue
                calls.append((node.lineno, any(k.arg == "user_id" for k in parent.keywords)))
            elif not isinstance(parent, ast.FunctionDef):
                indirect.append(node.lineno)
        elif isinstance(node, ast.Constant) and node.value in KB_METHODS and _names_a_method(parents.get(node)):
            indirect.append(node.lineno)  # getattr(x, "process_query"), partial(...), handler_method="..."
    return calls, indirect


def _production_files(root: Path):
    return [
        p
        for p in root.rglob("*.py")
        if not p.name.endswith("_test.py") and not p.name.startswith(("test_", "conftest"))
    ]


def _def_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_every_librarian_call_in_the_backend_names_its_user_with_no_skips():
    files, bare, indirect = set(), [], []
    for path in _production_files(BACKEND):
        rel = path.relative_to(BACKEND).as_posix()
        if rel in NON_KB_FILES:
            continue
        calls, refs = _scan(path)
        if calls or refs:
            files.add(rel)
        bare += [f"{rel}:{line}" for line, ok in calls if not ok]
        indirect += [f"{rel}:{line}" for line in refs]
    assert not bare, f"KB librarian call without user_id=: {bare}"
    assert not indirect, f"KB librarian method reached indirectly (alias/getattr/partial): {indirect}"
    assert files == EXPECTED_FILES, f"call-site files changed: +{files - EXPECTED_FILES} -{EXPECTED_FILES - files}"


def test_agent_orchestration_reaches_the_librarian_only_through_the_one_helper():
    orchestration = Path(__file__).parent
    direct = [
        f"{p.name}:{line}"
        for p in _production_files(orchestration)
        if p.name != "reading_user.py"
        for line, _ in _scan(p)[0]
    ]
    assert not direct, f"call the librarian through reading_user.librarian_query: {direct}"
