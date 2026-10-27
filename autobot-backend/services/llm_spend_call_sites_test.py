# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every reference to a provider method records its spend or says why not (#16924).

Three live call sites once streamed from a provider and recorded nothing; they
were found by reading. This scan finds the next one on arrival. It walks every
git-tracked Python file and counts each reference to ``stream_completion``,
``chat_completion`` or ``stream_chat``: an attribute (called, stored in a
variable or passed as a callback) or a ``getattr(obj, "<name>")`` constant.

Each reference must be accounted for by function, with an exact count, in
``_RECORDED`` (where it records) or ``_KNOWN_UNRECORDED`` (its tracking issue),
so a new reference inside an already-listed function fails too.

**Exempt by structure, not by path:** a reference inside a class that itself
defines a provider method. That is a provider implementation delegating to
another, and recording belongs to whoever called the outermost provider.
``docs/`` is not scanned; its example scripts are documentation, not product.
Tests are not scanned.

Behavioural tests for the recorder live in ``llm_usage_recording_stream_test.py``.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PROVIDER_METHODS = frozenset({"stream_completion", "chat_completion", "stream_chat"})
_NOT_SCANNED = ("docs",)

# Sites that record, or reference a method without invoking it: path::function -> (count, where).
# A DECLARATION, not proof: the count check verifies only that each site still holds exactly
# this many references. That the site records is asserted by the "where" text and by the
# behavioural tests, not by this scan.
_RECORDED = {
    "autobot-backend/services/llm_usage_recording.py::recorded_stream": (1, "the recorder itself"),
    "autobot-backend/services/llm_service.py::LLMService._attempt_chat_once": (1, "awaits _track_usage (#16845)"),
    "autobot-backend/services/llm_service.py::LLMService.chat_optimized": (1, "awaits _track_usage (#16845)"),
    "autobot-backend/api/openai_compat.py::_stream_generator": (1, "record_token_usage at stream end (#16845)"),
    "autobot-backend/api/openai_compat.py::_complete_chat": (1, "inspect.isasyncgenfunction check; no call"),
    "autobot-backend/api/anthropic_compat.py::_stream_generator_anthropic": (1, "record_token_usage at stream end"),
    "autobot-backend/api/anthropic_compat.py::_handle_messages": (1, "inspect.isasyncgenfunction check; no call"),
    "autobot-backend/llm_shared/model_fallback_coordinator.py::ModelFallbackCoordinator._dispatch": (
        1,
        "only the compat gateways' non-stream paths call it; both record_response_usage the result (#16845)",
    ),
}

# Known unrecorded, tracked rather than fixed here: path::function -> (count, issue).
_KNOWN_UNRECORDED = {
    # In llm_shared / autobot_shared, below services/, so they cannot import the recorder: #19650.
    "autobot-backend/llm_shared/tiered_routing/complexity_router.py::ComplexityRouter.route_with_escalation": (
        1,
        "#19650",
    ),
    "autobot_shared/pre_action_verifier_guard.py::_call_verifier_once": (1, "#19650"),
    "autobot-backend/llm_shared/adapters/anthropic_adapter.py::AnthropicAdapter.execute": (1, "#19650"),
    "autobot-backend/llm_shared/adapters/groq_adapter.py::GroqAdapter.execute": (1, "#19650"),
    "autobot-backend/llm_shared/adapters/ollama_adapter.py::OllamaAdapter.execute": (1, "#19650"),
    "autobot-backend/llm_shared/adapters/openai_adapter.py::OpenAIAdapter.execute": (1, "#19650"),
    # chat_completion on an LLMService, which has no such method since #3185: #19649.
    "autobot-backend/agents/agent_orchestration/routing.py::AgentRouter._determine_routing_base": (1, "#19649"),
    "autobot-backend/async_chat_workflow.py::AsyncChatWorkflow._generate_llm_response": (1, "#19649"),
    "autobot-backend/modern_ai_integration.py::LocalModelProvider.generate_text": (1, "#19649"),
    "autobot-backend/task_handlers/llm_handlers.py::LLMChatCompletionHandler.execute": (1, "#19649"),
}

# Ratchet (see docs/developer/RATCHET_BASELINES.md): the known-unrecorded population
# measured when this guard landed. It ONLY goes down -- lower it in the same change
# that fixes an entry. Never raise it to admit a new site; record that site instead.
_KNOWN_UNRECORDED_CEILING = 10

# Raw-HTTP inference no method-name scan can see, exempt by a stated condition.
_OLLAMA_DIRECT = _REPO / "autobot-backend" / "chat_workflow" / "manager.py"
_OLLAMA_EXEMPTION = "Spend exemption (#16924)"


class _SiteCollector(ast.NodeVisitor):
    """Count provider-method references per ``path::Qualified.function`` in one module."""

    def __init__(self, rel: str) -> None:
        self.rel, self.scope, self.in_provider, self.sites = rel, [], [], Counter()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        defined = {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.in_provider.append(bool(defined & _PROVIDER_METHODS))
        self._enter(node)
        self.in_provider.pop()

    def _enter(self, node) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def _hit(self) -> None:
        if not any(self.in_provider):
            self.sites[f"{self.rel}::{'.'.join(self.scope) or '<module>'}"] += 1

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _PROVIDER_METHODS:
            self._hit()
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        is_getattr = isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2
        if is_getattr and isinstance(node.args[1], ast.Constant) and node.args[1].value in _PROVIDER_METHODS:
            self._hit()
        self.generic_visit(node)


def _sites_in(source: str, rel: str) -> Counter:
    collector = _SiteCollector(rel)
    collector.visit(ast.parse(source))
    return collector.sites


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    """Every tracked ``*.py``, via the repo's one git enumeration helper (#15926).

    Loaded by path: ``autobot-backend/tools`` shadows the top-level ``tools`` package.
    """
    spec = importlib.util.spec_from_file_location("_scan_helpers_16924", _REPO / "tools" / "lint" / "_scan_helpers.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return tuple(helpers.tracked_paths(_REPO, "*.py", exclude=_NOT_SCANNED))


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or "/tests/" in f"/{rel}"


@functools.lru_cache(maxsize=1)
def _production_sites() -> Counter:
    """Scanned once per session; callers must not mutate the result."""
    sites: Counter = Counter()
    for rel in _tracked_python_files():
        if not _is_test(rel):
            sites += _sites_in((_REPO / rel).read_text(encoding="utf-8"), rel)
    return sites


def _listed() -> Counter:
    return Counter({site: count for site, (count, _why) in {**_RECORDED, **_KNOWN_UNRECORDED}.items()})


def test_the_collector_sees_every_reference_shape_and_exempts_only_provider_classes() -> None:
    """Control: an empty result below must mean "nothing unaccounted", not "the parser saw nothing"."""
    source = (
        "class Svc:\n"
        "    async def run(self, provider, req):\n"
        "        fn = provider.stream_completion\n"
        "        getattr(provider, 'chat_completion')\n"
        "        return await provider.chat_completion(req)\n"
        "class Prov:\n"
        "    async def chat_completion(self, req):\n"
        "        return await self.inner.chat_completion(req)\n"
    )
    assert _sites_in(source, "pkg/mod.py") == Counter({"pkg/mod.py::Svc.run": 3})


def test_the_scan_reads_every_python_root() -> None:
    roots = {rel.split("/", 1)[0] for rel in _tracked_python_files()}
    assert {"autobot-backend", "autobot_shared", "autobot-slm-backend", "tools"} <= roots


def test_every_provider_reference_is_accounted_for_with_its_exact_count() -> None:
    found, listed = _production_sites(), _listed()
    unaccounted = {site: count for site, count in found.items() if count != listed.get(site)}
    assert not unaccounted, (
        f"Provider-method references not matching the lists (site: found count): {unaccounted}. Stream "
        "through services.llm_usage_recording.recorded_stream or LLMService, or record the response with "
        "record_response_usage, then list the site in _RECORDED (#16924)."
    )


def test_no_listed_site_has_gone_stale() -> None:
    """A listed site that no longer references a provider method is removed, so the lists cannot rot."""
    stale = set(_listed()) - set(_production_sites())
    assert not stale, f"Listed but no longer a provider reference; delete the entry: {sorted(stale)}"


def test_known_unrecorded_only_shrinks() -> None:
    total = sum(count for count, _issue in _KNOWN_UNRECORDED.values())
    assert total <= _KNOWN_UNRECORDED_CEILING, (
        f"{total} known-unrecorded references against a ceiling of {_KNOWN_UNRECORDED_CEILING}. "
        "Record the new site; never list it here."
    )
    assert total == _KNOWN_UNRECORDED_CEILING, f"Fixed one: lower _KNOWN_UNRECORDED_CEILING to {total}."


def test_the_ollama_direct_workflow_states_its_spend_exemption() -> None:
    assert _OLLAMA_EXEMPTION in _OLLAMA_DIRECT.read_text(encoding="utf-8")
