# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The multi-source routes: user A reads their private fact, B never does, an admin does (#16665).

Covers /search, /context and both /graph routes, each through the real router, plus the
research quarantine on every one (AC3). The KB is the shared read-path fake; ownership is real.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_search_aggregator as aggregator
from auth_middleware import get_current_user
from knowledge.read_path_fakes_16665 import PRIVATE_A, RESEARCH, SHARED, FakeKB, QuarantineGatedKB

ALICE = {"user_id": "alice", "role": "user"}
BOB = {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}

FACT_ROUTES = [
    ("post", "/multi-source/search", {"query": "q", "include_sources": ["facts"]}),
    ("post", "/multi-source/context", {"query": "q", "include_documentation": False}),
    ("post", "/multi-source/graph", {"max_facts": 10}),
    ("get", "/multi-source/graph", None),
]


class _DictKB(FakeKB):
    async def search(self, *args, **kwargs):
        return {"results": await super().search()}


def _call(user, method, path, body, kb):
    app = FastAPI()
    app.include_router(aggregator.router)
    app.dependency_overrides[get_current_user] = lambda: user
    with (
        patch.object(aggregator, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        client = TestClient(app)
        return client.get(path) if method == "get" else client.post(path, json=body)


@pytest.mark.parametrize("method,path,body", FACT_ROUTES)
def test_a_reads_their_private_fact_and_b_never_does(method, path, body):
    for_alice = _call(ALICE, method, path, body, _DictKB())
    for_bob = _call(BOB, method, path, body, _DictKB())

    assert for_alice.status_code == 200 and PRIVATE_A in for_alice.text
    assert for_bob.status_code == 200 and PRIVATE_A not in for_bob.text and SHARED in for_bob.text


@pytest.mark.parametrize("method,path,body", [r for r in FACT_ROUTES if r[1] != "/multi-source/context"])
def test_an_admin_reads_another_users_private_fact(method, path, body):
    response = _call(ADMIN, method, path, body, _DictKB())

    assert response.status_code == 200 and PRIVATE_A in response.text


def test_context_feeds_a_prompt_so_an_admin_gets_no_bypass():
    body = {"query": "q", "include_documentation": False}
    response = _call(ADMIN, "post", "/multi-source/context", body, _DictKB())

    assert response.status_code == 200 and PRIVATE_A not in response.text and SHARED in response.text


@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
@pytest.mark.parametrize("method,path,body", FACT_ROUTES)
def test_a_research_quarantined_fact_is_never_returned(user, method, path, body):
    response = _call(user, method, path, body, QuarantineGatedKB(dict_results=True))

    assert response.status_code == 200
    assert RESEARCH not in response.text and SHARED in response.text
