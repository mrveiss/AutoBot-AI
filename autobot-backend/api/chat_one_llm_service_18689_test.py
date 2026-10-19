# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One LLMService per process: chat shares the singleton (#18689).

``api.chat`` used to build a second ``LLMService`` on ``app.state`` beside the
module singleton, so a runtime ``switch_provider`` and the request/error
counters never reached the chat path.
"""

import ast
import importlib.util as _ilu
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

from initialization import background_workers as bw

_BACKEND = pathlib.Path(__file__).resolve().parents[1]  # autobot-backend/


def _load_real_llm_service():
    """Real ``services.llm_service`` under a private name (conftest stubs the public one)."""
    if "llm_shared.rate_limit_backoff" not in sys.modules:
        spec = _ilu.spec_from_file_location(
            "llm_shared.rate_limit_backoff", str(_BACKEND / "llm_shared/rate_limit_backoff.py")
        )
        mod = _ilu.module_from_spec(spec)
        sys.modules["llm_shared.rate_limit_backoff"] = mod
        spec.loader.exec_module(mod)
    spec = _ilu.spec_from_file_location("_real_llm_service_18689", str(_BACKEND / "services/llm_service.py"))
    mod = _ilu.module_from_spec(spec)
    sys.modules["_real_llm_service_18689"] = mod
    spec.loader.exec_module(mod)
    return mod


llm_mod = _load_real_llm_service()


class _NoProviderRegistry:
    """Registry with two known providers and none available to serve a request."""

    async def get_provider_for_request(self, provider_name=None, conversation_id=None):
        return None

    def get_provider_by_name(self, name):
        return None

    def list_providers(self):
        return [{"name": "ollama"}, {"name": "openai"}]


class _NoCache:
    async def get(self, key):
        return None

    async def set(self, key, response, skip_redis=False):
        return None

    def generate_cache_key(self, **kwargs):
        return "key"


def _load_chat_against_the_real_service():
    """``api/chat.py`` executed afresh while ``services.llm_service`` is the real module.

    conftest stubs the public module name, so the ``get_llm_service`` the shared
    ``api.chat`` bound at import is a stub attribute. Binding a private copy against
    the real module lets the test observe what chat's own accessor resolves to.
    """
    saved = sys.modules.get("services.llm_service")
    sys.modules["services.llm_service"] = llm_mod
    try:
        spec = _ilu.spec_from_file_location("_chat_18689", str(_BACKEND / "api/chat.py"))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if saved is None:
            sys.modules.pop("services.llm_service", None)
        else:
            sys.modules["services.llm_service"] = saved
    return mod


@pytest.fixture
def chat_module(monkeypatch):
    """Chat bound to the real module, with a fresh real singleton installed."""
    chat = _load_chat_against_the_real_service()
    service = llm_mod.LLMService(registry=_NoProviderRegistry())
    service._response_cache = _NoCache()
    monkeypatch.setitem(sys.modules, "services.llm_service", llm_mod)  # lifespan wiring imports it by public name
    monkeypatch.setattr(llm_mod, "_service_instance", service)
    return chat, service


def test_chat_defines_no_accessor_of_its_own_and_imports_the_canonical_one():
    tree = ast.parse((_BACKEND / "api/chat.py").read_text(encoding="utf-8"))
    defs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    imported = [
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "services.llm_service"
        for a in n.names
    ]
    assert "get_llm_service" not in defs
    assert "get_llm_service" in imported


@pytest.mark.asyncio
async def test_switch_provider_on_the_singleton_is_visible_to_chat(chat_module):
    chat, singleton = chat_module

    result = await singleton.switch_provider("openai")

    assert result["success"] is True
    assert chat.get_llm_service() is singleton
    assert chat.get_llm_service()._active_provider == "openai"


@pytest.mark.asyncio
async def test_chat_requests_increment_the_singletons_counters(chat_module):
    chat, singleton = chat_module

    await chat._generate_ai_response(
        llm_service=chat.get_llm_service(),
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert (singleton._request_count, singleton._error_count) == (1, 1)


def test_app_state_llm_service_is_the_singleton_after_startup_wiring(chat_module):
    chat, singleton = chat_module
    app = SimpleNamespace(state=SimpleNamespace())

    bw.wire_llm_service(app)

    assert app.state.llm_service is singleton
    assert app.state.llm_service is chat.get_llm_service()


@pytest.mark.asyncio
async def test_the_lifespan_entry_point_wires_it(chat_module, monkeypatch):
    _chat, singleton = chat_module

    async def _noop(_app):
        return None

    monkeypatch.setattr(bw, "start_doc_sync_queue_worker", _noop)
    monkeypatch.setattr(bw, "start_vector_reconciler", _noop)
    app = SimpleNamespace(state=SimpleNamespace())

    await bw.start_background_workers(app)

    assert app.state.llm_service is singleton


@pytest.mark.asyncio
async def test_a_failing_llm_service_does_not_skip_the_other_workers(monkeypatch):
    def _boom():
        raise RuntimeError("no provider config")

    started = []

    async def _record(app):
        started.append(app)

    monkeypatch.setitem(sys.modules, "services.llm_service", SimpleNamespace(get_llm_service=_boom))
    monkeypatch.setattr(bw, "start_doc_sync_queue_worker", _record)
    monkeypatch.setattr(bw, "start_vector_reconciler", _record)
    app = SimpleNamespace(state=SimpleNamespace())

    await bw.start_background_workers(app)

    assert len(started) == 2
    assert not hasattr(app.state, "llm_service")
    assert app.state.llm_service_error == "RuntimeError"


async def _health_llm_status(chat, **state) -> str:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(chat_history_manager=object(), **state)))
    response = await chat.chat_health_check(current_user={"username": "u"}, request=request)
    return json.loads(response.body)["components"]["llm_service"]


@pytest.mark.asyncio
async def test_health_reports_a_failed_startup_wiring_as_degraded(chat_module):
    chat, singleton = chat_module
    assert await _health_llm_status(chat, llm_service_error="RuntimeError") == "degraded"
    assert await _health_llm_status(chat, llm_service=singleton) == "healthy"
    assert await _health_llm_status(chat) == "available"


def test_a_failed_construction_is_not_cached_so_the_next_request_retries(monkeypatch):
    calls = []

    def _flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("provider config missing")
        return SimpleNamespace(name="ok")

    monkeypatch.setattr(llm_mod, "_service_instance", None)
    monkeypatch.setattr(llm_mod, "LLMService", _flaky)
    with pytest.raises(RuntimeError):
        llm_mod.get_llm_service()
    assert llm_mod.get_llm_service().name == "ok"


def _llm_service_constructions(tree: ast.AST) -> list[int]:
    """Lines that call ``LLMService(...)`` or hand the class itself to a factory."""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "LLMService":
            hits.append(node.lineno)
        hits.extend(a.lineno for a in node.args if isinstance(a, ast.Name) and a.id == "LLMService")
    return hits


@pytest.mark.parametrize("rel", ["api/chat_embed.py", "api/telegram_bot.py", "api/whatsapp.py"])
def test_app_state_fallbacks_build_the_singleton_not_a_second_service(rel):
    """The ``lazy_init_singleton`` fallbacks resolve to the process-wide service (#18689)."""
    source = (_BACKEND / rel).read_text(encoding="utf-8")
    assert "lazy_init_singleton" in source and "get_llm_service" in source, rel
    assert _llm_service_constructions(ast.parse(source)) == [], rel


def test_construction_detector_sees_both_shapes():
    """Control: the detector flags a direct call and a class-as-factory argument."""
    tree = ast.parse('LLMService()\nlazy_init_singleton(s, "llm_service", LLMService)\n')
    assert _llm_service_constructions(tree) == [1, 2]


def test_chat_streaming_groups_use_the_deduplication_timestamp_parser():
    """Chat's private timestamp parser was a byte-identical copy (#18731 G076)."""
    tree = ast.parse((_BACKEND / "api/chat.py").read_text(encoding="utf-8"))
    defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    imports = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "_parse_message_timestamp" not in defs
    assert ("chat_history.deduplication", "_parse_timestamp") in imports
