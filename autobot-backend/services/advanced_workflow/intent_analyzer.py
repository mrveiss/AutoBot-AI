# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intent Analyzer

AI-driven user intent analysis for workflow generation.
"""

import json
import logging
from typing import List

from backend.type_defs.common import Metadata
from llm_interface import LLMInterface

from .models import WorkflowComplexity, WorkflowIntent

logger = logging.getLogger(__name__)

# Issue #380: Module-level constants for intent keyword detection
# Moved from _fallback_intent_analysis to avoid repeated dict creation
_INTENT_KEYWORDS = {
    WorkflowIntent.INSTALLATION: ("install", "setup", "add", "get"),
    WorkflowIntent.CONFIGURATION: ("configure", "config", "set up", "adjust"),
    WorkflowIntent.DEPLOYMENT: ("deploy", "release", "publish", "launch"),
    WorkflowIntent.SECURITY: ("secure", "harden", "protect", "firewall"),
    WorkflowIntent.DEVELOPMENT: ("develop", "code", "build", "compile"),
    WorkflowIntent.MAINTENANCE: ("update", "upgrade", "maintain", "clean"),
}


class IntentAnalyzer:
    """Analyzes user intent using AI and fallback heuristics"""

    def __init__(self, llm_interface: LLMInterface = None):
        """Initialize intent analyzer with optional LLM interface."""
        self.llm_interface = llm_interface or LLMInterface()

    async def analyze_user_intent(self, user_request: str) -> Metadata:
        """Analyze user intent using AI"""
        try:
            analysis_prompt = """
            Analyze this user request and determine the workflow intent, \
complexity, and requirements:

            Request: "{user_request}"

            Please provide analysis in JSON format with:
            1. Primary intent (installation, configuration, deployment, etc.)
            2. Complexity level (simple, moderate, complex, enterprise)
            3. Key components/technologies mentioned
            4. Risk factors
            5. Estimated steps needed
            6. Prerequisites
            7. Success criteria
            """

            response = await self.llm_interface.chat_completion(
                model="default", messages=[{"role": "user", "content": analysis_prompt}]
            )

            if response and response.get("content"):
                try:
                    analysis = json.loads(response["content"])
                    return analysis
                except json.JSONDecodeError:
                    return self._fallback_intent_analysis(user_request)

            return self._fallback_intent_analysis(user_request)

        except Exception as e:
            logger.error("Intent analysis failed: %s", e)
            return self._fallback_intent_analysis(user_request)

    def _fallback_intent_analysis(self, user_request: str) -> Metadata:
        """Fallback intent analysis using keywords"""
        request_lower = user_request.lower()

        # Intent detection (Issue #380: use module-level constant)
        detected_intent = WorkflowIntent.CONFIGURATION
        for intent, keywords in _INTENT_KEYWORDS.items():
            if any(keyword in request_lower for keyword in keywords):
                detected_intent = intent
                break

        # Complexity estimation - cache split result (#624)
        request_words = request_lower.split()
        word_count = len(request_words)

        complexity_indicators = {
            "simple": word_count < 10,
            "moderate": 10 <= word_count < 20,
            "complex": word_count >= 20 or "enterprise" in request_lower,
        }

        complexity = WorkflowComplexity.SIMPLE
        for level, condition in complexity_indicators.items():
            if condition:
                complexity = WorkflowComplexity(level)
                break

        return {
            "primary_intent": detected_intent.value,
            "complexity": complexity.value,
            "components": self._extract_components(request_lower),
            "risk_factors": self._assess_basic_risks(request_lower),
            "estimated_steps": min(3 + word_count // 5, 15),
            "prerequisites": [],
            "success_criteria": ["Command execution successful", "No errors reported"],
        }

    def _extract_components(self, request: str) -> List[str]:
        """Extract technology components from request"""
        components = []
        tech_keywords = [
            "nginx",
            "apache",
            "docker",
            "kubernetes",
            "python",
            "node",
            "nodejs",
            "git",
            "mysql",
            "postgresql",
            "redis",
            "mongodb",
            "ssl",
            "https",
            "firewall",
            "ssh",
            "ftp",
            "api",
            "rest",
            "graphql",
            "react",
            "vue",
        ]

        for keyword in tech_keywords:
            if keyword in request:
                components.append(keyword)

        return components

    def _assess_basic_risks(self, request: str) -> List[str]:
        """Assess basic risk factors"""
        risks = []
        risk_indicators = {
            "sudo": "Requires elevated privileges",
            "rm": "File deletion operations",
            "install": "System modification",
            "firewall": "Network security changes",
            "ssl": "Certificate management",
            "database": "Data storage modifications",
        }

        for indicator, risk in risk_indicators.items():
            if indicator in request:
                risks.append(risk)

        return risks
