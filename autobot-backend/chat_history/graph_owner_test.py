# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The memory-graph owner reads the shared owner keys, user_id first (#20928)."""

import pytest

from autobot_memory_graph.owner_scope import OwnerScope
from chat_history.graph_owner import session_owner_scope
from chat_history.owner_keys import strip_server_controlled
from security.session_ownership import build_owner_metadata


@pytest.mark.parametrize(
    "principal, expected",
    [
        ({"username": "alice", "user_id": "u-1", "org_id": "o-1"}, OwnerScope.for_user("u-1", "o-1")),
        ({"username": "alice"}, OwnerScope.for_user("alice")),
    ],
)
def test_server_built_session_resolves_to_the_entity_owner(principal, expected):
    """The create route writes the graph entity under ``user_id or username``; the scope matches it."""
    assert session_owner_scope(build_owner_metadata(principal)) == expected


def test_a_planted_client_user_id_does_not_set_the_graph_owner():
    client = {"user_id": "mallory-id", "org_id": "x", "color": "red"}
    metadata = {**strip_server_controlled(client), **build_owner_metadata({"username": "alice"})}
    assert session_owner_scope(metadata) == OwnerScope.for_user("alice")


def test_control_an_unstripped_planted_user_id_would_set_it():
    """Control: without the strip the planted key wins, so the test above measures the strip."""
    client = {"user_id": "mallory-id", "org_id": "x"}
    metadata = {**client, **build_owner_metadata({"username": "alice"})}
    assert session_owner_scope(metadata) == OwnerScope.for_user("mallory-id", "x")
