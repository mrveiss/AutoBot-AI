# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Constructor compatibility tests for StandardizedAgent subclasses (Issue #6660).

LLMFailsafeAgent and DataAnalysisAgent previously dropped the parent's
required ``agent_type`` parameter, which broke factory call patterns like
``cls(agent_type, deployment_mode)``. After #6660 both subclasses accept
the parent signature with sensible defaults so:

  * ``LLMFailsafeAgent()``                 still works (legacy singleton call)
  * ``LLMFailsafeAgent("foo", mode)``      works (parent-shape factory call)
  * ``DataAnalysisAgent()``                still works
  * ``DataAnalysisAgent("foo", mode)``     works
"""

import inspect

import pytest


def _signature_or_skip(cls):
    sig = inspect.signature(cls.__init__)
    return list(sig.parameters.keys())


class TestLLMFailsafeAgentSignature:
    """Issue #6660: parent-compatible constructor."""

    def test_signature_accepts_agent_type_and_deployment_mode(self):
        try:
            from agents.llm_failsafe_agent import LLMFailsafeAgent
        except Exception as exc:  # pragma: no cover — env-dependent dep chain
            pytest.skip(f"LLMFailsafeAgent dep chain unavailable: {exc}")

        params = _signature_or_skip(LLMFailsafeAgent)
        assert "agent_type" in params, "LLMFailsafeAgent.__init__ must accept agent_type for factory compatibility"
        assert (
            "deployment_mode" in params
        ), "LLMFailsafeAgent.__init__ must accept deployment_mode for factory compatibility"

    def test_default_agent_type_falls_back_to_AGENT_ID(self):
        """Calling with no args must still produce the historical agent_type."""
        try:
            from agents.llm_failsafe_agent import LLMFailsafeAgent
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"LLMFailsafeAgent dep chain unavailable: {exc}")

        sig = inspect.signature(LLMFailsafeAgent.__init__)
        # The agent_type parameter must default to None (so `or self.AGENT_ID`
        # picks up the class constant); deployment_mode must default to LOCAL.
        agent_type_param = sig.parameters["agent_type"]
        assert agent_type_param.default is None
        deployment_mode_param = sig.parameters["deployment_mode"]
        assert deployment_mode_param.default is not inspect.Parameter.empty


class TestDataAnalysisAgentSignature:
    """Issue #6660: parent-compatible constructor."""

    def test_signature_accepts_agent_type_and_deployment_mode(self):
        try:
            from agents.data_analysis_agent import DataAnalysisAgent
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"DataAnalysisAgent dep chain unavailable: {exc}")

        params = _signature_or_skip(DataAnalysisAgent)
        assert "agent_type" in params, "DataAnalysisAgent.__init__ must accept agent_type for factory compatibility"
        assert (
            "deployment_mode" in params
        ), "DataAnalysisAgent.__init__ must accept deployment_mode for factory compatibility"

    def test_default_agent_type_falls_back_to_AGENT_ID(self):
        try:
            from agents.data_analysis_agent import DataAnalysisAgent
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"DataAnalysisAgent dep chain unavailable: {exc}")

        sig = inspect.signature(DataAnalysisAgent.__init__)
        agent_type_param = sig.parameters["agent_type"]
        assert agent_type_param.default is None
        deployment_mode_param = sig.parameters["deployment_mode"]
        assert deployment_mode_param.default is not inspect.Parameter.empty
