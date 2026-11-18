# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat turn reads the KB as the session's user, or as SYSTEM_SCOPE when it has none (#16664)."""

from autobot_shared.scoping import Principal
from chat_workflow.models import WorkflowSession
from knowledge.search_filters import SYSTEM_SCOPE


def _session(**metadata) -> WorkflowSession:
    return WorkflowSession(session_id="s1", workflow=None, metadata=metadata)


def test_a_turn_with_a_stamped_user_reads_as_that_user_and_org():
    principal = _session(user_id="A", org_id="o1").kb_principal()

    assert principal == Principal("A", "o1", frozenset(), True)


def test_a_turn_with_no_user_reads_as_system_scope_not_as_anyone():
    assert _session().kb_principal() is SYSTEM_SCOPE
    assert _session(user_id="").kb_principal() is SYSTEM_SCOPE


def test_an_org_stamp_without_a_user_does_not_become_a_user_principal():
    assert _session(org_id="o1").kb_principal() is SYSTEM_SCOPE
