# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared schema classification rules."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402
from schema_rules import DOMAIN_RULES, classify_class  # noqa: E402


@pytest.mark.parametrize(
    "cls,domain",
    [
        ("TerminalSession", "terminal"),
        ("KnowledgeFact", "knowledge"),
        ("LLMConfig", "agent"),
        ("WorkflowRun", "workflows"),
        ("SuccessResponse", "common"),
    ],
)
def test_classify_known_prefixes(cls, domain):
    assert classify_class(cls) == domain


def test_unmatched_falls_back_to_common():
    assert classify_class("ZzzUnknownThing") == "common"


def test_first_match_wins_over_shorter_prefix():
    # AgentTerminal* matches rule 1 (terminal) before AgentConfig/agent rules.
    assert classify_class("AgentTerminalSession") == "terminal"
    assert classify_class("AgentConfigUpdate") == "agent"


def test_rules_are_ordered_tuples():
    assert len(DOMAIN_RULES) == 10
