# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Regression Test: LEDGER vs EXECUTOR Rule Injection

Issue #7380: Verifies that the LEDGER_VS_EXECUTOR_RULE is properly injected
into agent system prompts and that agents understand the distinction between
coordination tools (which return records) and actual work execution.

Tests:
1. Rule constant is defined and contains key semantics
2. Rule is imported in StandardizedAgent and orchestrator (via grep)
3. Rule injection code is present and correct (via grep)
4. Token budget compliance (reasonable for clarity)
"""

import re
from pathlib import Path

from autobot_shared.prompt_rules import LEDGER_VS_EXECUTOR_RULE


class TestLedgerVsExecutorInjection:
    """Test suite for LEDGER_VS_EXECUTOR_RULE injection"""

    def test_rule_constant_exists(self):
        """Verify the LEDGER_VS_EXECUTOR_RULE constant is defined"""
        assert LEDGER_VS_EXECUTOR_RULE is not None
        assert isinstance(LEDGER_VS_EXECUTOR_RULE, str)
        assert "LEDGER" in LEDGER_VS_EXECUTOR_RULE
        assert "EXECUTOR" in LEDGER_VS_EXECUTOR_RULE
        assert "coordination" in LEDGER_VS_EXECUTOR_RULE.lower()
        assert "record" in LEDGER_VS_EXECUTOR_RULE.lower()

    def test_rule_content_clarity(self):
        """Verify the rule clearly explains the distinction"""
        assert "workflow_plan" in LEDGER_VS_EXECUTOR_RULE
        assert "agent_register" in LEDGER_VS_EXECUTOR_RULE
        assert "memory_store" in LEDGER_VS_EXECUTOR_RULE
        assert "swarm_init" in LEDGER_VS_EXECUTOR_RULE
        assert "IMMEDIATELY" in LEDGER_VS_EXECUTOR_RULE
        assert "do not wait" in LEDGER_VS_EXECUTOR_RULE.lower()

    def test_standardized_agent_imports_rule_via_source(self):
        """Verify StandardizedAgent source code imports the rule constant"""
        # Read the standardized_agent source directly
        sa_path = Path(__file__).parent.parent.parent / "agents" / "standardized_agent.py"
        source = sa_path.read_text()

        # Check that it imports LEDGER_VS_EXECUTOR_RULE
        assert "LEDGER_VS_EXECUTOR_RULE" in source
        assert "from autobot_shared.prompt_rules import" in source

    def test_standardized_agent_injects_rule_via_source(self):
        """Verify StandardizedAgent source code injects the rule in _get_localized_system_prompt"""
        # Read the standardized_agent source directly
        sa_path = Path(__file__).parent.parent.parent / "agents" / "standardized_agent.py"
        source = sa_path.read_text()

        # Find the _get_localized_system_prompt method
        # Extract the method body
        match = re.search(
            r"def _get_localized_system_prompt\(self.*?\):\s*.*?(?=\n    def |\n\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert match is not None, "_get_localized_system_prompt method not found"

        method_source = match.group(0)
        # Check that the method includes the rule
        assert "LEDGER_VS_EXECUTOR_RULE" in method_source

    def test_orchestrator_imports_rule_via_source(self):
        """Verify orchestrator source code imports the rule constant"""
        # Read the orchestrator source directly
        orch_path = Path(__file__).parent.parent.parent / "orchestrator.py"
        source = orch_path.read_text()

        # Check that it imports LEDGER_VS_EXECUTOR_RULE
        assert "LEDGER_VS_EXECUTOR_RULE" in source
        assert "from autobot_shared.prompt_rules import" in source

    def test_orchestrator_planning_prompt_includes_rule_via_source(self):
        """Verify orchestrator's planning prompt method references the rule"""
        # Read the orchestrator source directly
        orch_path = Path(__file__).parent.parent.parent / "orchestrator.py"
        source = orch_path.read_text()

        # Find the _build_planning_prompt method
        match = re.search(
            r"def _build_planning_prompt\(self.*?\):\s*.*?(?=\n    def |\n\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert match is not None, "_build_planning_prompt method not found"

        method_source = match.group(0)
        # Check that the method references LEDGER_VS_EXECUTOR_RULE
        assert "LEDGER_VS_EXECUTOR_RULE" in method_source

    def test_token_budget_reasonable(self):
        """Verify rule is reasonably sized (~130 tokens is acceptable for clarity)"""
        # LEDGER_VS_EXECUTOR_RULE is important for correctness
        # Estimate tokens (~4 chars per token on average)
        estimated_tokens = len(LEDGER_VS_EXECUTOR_RULE) // 4
        # Allow up to ~150 tokens for the rule since clarity is critical
        assert estimated_tokens < 150, f"Rule too large: ~{estimated_tokens} tokens"
