# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The KB reset scripts only propose a wipe; an unapproved run deletes nothing (#21383, #17038).

Fakes only: the backend's ``services.kb_wipe_action`` is stubbed (an infra test never imports the backend,
#18288), and a Redis client that is touched at all fails the test.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

_SCRIPTS = pathlib.Path(__file__).parent
_PLAN = {
    "databases": [{"database": "knowledge", "keys": 3, "note": "kb", "indexes": [{"name": "i", "documents": 2}]}],
    "chroma_collections": [{"name": "autobot_memory", "vectors": 8}],
    "total_keys": 3,
    "total_vectors": 8,
}


def _load(name: str):
    """Import a script by path -- its directory is not a package."""
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kb_wipe_cli = _load("kb_wipe_cli")


@pytest.fixture
def proposals(monkeypatch):
    """Stub the wipe service; the list records every proposal raised."""
    raised = []

    async def plan_kb_wipe():
        return _PLAN

    stub = types.SimpleNamespace(plan_kb_wipe=plan_kb_wipe, CHANNEL_OPERATOR="operator")
    monkeypatch.setitem(sys.modules, "services.kb_wipe_action", stub)

    async def propose(plan):
        raised.append(plan)
        return "approval-1"

    monkeypatch.setattr(kb_wipe_cli, "propose_wipe", propose)
    return raised


@pytest.mark.asyncio
async def test_dry_run_lists_the_plan_and_raises_nothing(proposals, caplog):
    with caplog.at_level("INFO", logger=kb_wipe_cli.logger.name):
        assert await kb_wipe_cli.request_wipe(True) is True
    assert proposals == []
    assert "Database knowledge: 3 keys" in caplog.text and "Chroma collection autobot_memory: 8 vectors" in caplog.text


@pytest.mark.asyncio
async def test_a_request_raises_one_proposal_and_says_nothing_is_deleted(proposals, caplog):
    with caplog.at_level("INFO", logger=kb_wipe_cli.logger.name):
        assert await kb_wipe_cli.request_wipe(False) is True
    assert proposals == [_PLAN] and "Nothing is deleted until an admin approves it" in caplog.text


@pytest.mark.asyncio
async def test_reset_knowledge_base_only_proposes(proposals):
    script = _load("reset_knowledge_base")
    assert await script.reset_knowledge_base_index() is True
    assert proposals == [_PLAN]
    assert await script.reset_knowledge_base_index(dry_run=True) is True
    assert proposals == [_PLAN]  # the dry run raised nothing more


@pytest.mark.parametrize(
    "name", ["create_kb_index", "kb_dimension_utility", "reset_kb_dimensions", "reset_knowledge_base"]
)
def test_the_script_has_no_delete_calls_left(name):
    source = (_SCRIPTS / f"{name}.py").read_text(encoding="utf-8").lower()
    assert not any(word in source for word in ("dropindex", "flushdb", "flushall", ".delete(", ".keys("))
