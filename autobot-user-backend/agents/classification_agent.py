# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intelligent Classification Agent
Uses LLM reasoning to understand user intent and classify workflow complexity
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.agents.json_formatter_agent import CLASSIFICATION_SCHEMA, json_formatter
from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.autobot_types import TaskComplexity
from src.config.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from src.llm_interface import LLMInterface
from src.utils.redis_client import get_redis_client
from src.workflow_classifier import WorkflowClassifier

from .base_agent import AgentRequest
from .standardized_agent import StandardizedAgent

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of classification analysis."""

    complexity: TaskComplexity
    confidence: float
    reasoning: str
    suggested_agents: List[str]
    estimated_steps: int
    user_approval_needed: bool
    context_analysis: Dict[str, Any]


class ClassificationAgent(StandardizedAgent):
    """Intelligent agent that understands user intent for workflow classification."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "classification"

    def __init__(self, llm_interface: Optional[LLMInterface] = None):
        """Initialize classification agent with explicit LLM configuration."""
        super().__init__("classification")

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.llm = llm_interface or LLMInterface()
        self.redis_client = get_redis_client()
        self.keyword_classifier = WorkflowClassifier(self.redis_client)

        logger.info(
            "ClassificationAgent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )
        self.capabilities = [
            "intent_classification",
            "complexity_analysis",
            "workflow_routing",
            "request_classification",
            "agent_selection",
        ]

        # Initialize communication protocol for agent-to-agent messaging
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.initialize_communication(self.capabilities))
            else:
                loop.run_until_complete(
                    self.initialize_communication(self.capabilities)
                )
        except RuntimeError:
            # Event loop not available yet, will initialize later
            logger.debug(
                "Event loop not available, will initialize communication later"
            )

        # Initialize classification prompt
        self._initialize_classification_prompt()

    async def action_classify_request(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle classify_request action."""
        user_message = request.payload.get("message", "")
        result = await self.classify_request(user_message)

        # Convert ClassificationResult to dict for serialization
        return {
            "complexity": result.complexity.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "suggested_agents": result.suggested_agents,
            "estimated_steps": result.estimated_steps,
            "user_approval_needed": result.user_approval_needed,
            "context_analysis": result.context_analysis,
        }

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    def _get_complexity_levels_prompt(self) -> str:
        """
        Return the workflow complexity levels section of the classification prompt.

        Issue #620.
        """
        return """WORKFLOW COMPLEXITY LEVELS:

1. SIMPLE: Regular conversational requests that can be answered using
   Knowledge Base + LLM
   - Examples: "Hello", "What is Docker?", "Tell me about Python",
     "How does AutoBot work?", "Define machine learning"
   - Characteristics: Conversations, questions, definitions, greetings
   - Processing: Knowledge Base search + LLM response with source attribution
   - Note: ALL responses should include Knowledge Base context

2. COMPLEX: Requests requiring external tools, system actions, or research
   beyond Knowledge Base
   - Examples: "Install Docker", "Scan network", "Search the web",
     "Configure nginx", "Run diagnostics", "What's new on tvnet.lv"
   - Characteristics: Tool usage, system commands, external research,
     file operations, security scans, live information from websites
   - Processing: Knowledge Base + Tools + External Research +
     Multi-agent coordination
   - **IMPORTANT**: Requests for current/live information from specific
     websites requires COMPLEX classification for web browsing

IMPORTANT NOTES:
- Simple conversations can dynamically upgrade to Complex if user
  requests actions/tools
- ALWAYS use Knowledge Base first to ground responses and prevent
  hallucination
- Source attribution is required for all responses regardless of complexity"""

    def _get_context_analysis_prompt(self) -> str:
        """
        Return the context analysis and JSON format section of the classification prompt.

        Issue #620.
        """
        return """CONTEXT ANALYSIS:
- Intent: What does the user want to accomplish?
- Tools Needed: Does this require system commands, external APIs,
  or file operations?
- Scope: Conversational or actionable?
- Knowledge Base Relevance: Can this be answered from existing
  AutoBot knowledge?
- **Web Browsing**: Does this request need current/live information
  from a specific website? (If yes, classify as COMPLEX)
- **Temporal Context**: Is the user asking for "latest", "new",
  "current", or "what's happening" information?

Please provide your analysis in the following JSON format:
{{
    "complexity": "simple|complex",
    "confidence": 0.95,
    "reasoning": "Clear explanation of why you classified it this way",
    "domain": "Primary domain (conversation, security, networking, etc.)",
    "intent": "What the user wants to accomplish",
    "scope": "single|multi-step",
    "risk_level": "low|medium|high",
    "suggested_agents": ["list", "of", "relevant", "agents"],
    "estimated_steps": 1,
    "user_approval_needed": false,
    "knowledge_base_relevant": true,
    "tools_required": false,
    "source_attribution_needed": true
}}

Be thorough in your analysis and reasoning. Consider the implications
and requirements of the request."""

    def _initialize_classification_prompt(self):
        """Initialize the classification prompt template"""
        # noqa: E501 - Prompt content must remain human-readable
        intro = """You are an intelligent classification agent for AutoBot, a multi-agent
workflow orchestration system.

Your task is to analyze user requests and determine the appropriate
workflow complexity."""
        complexity_levels = self._get_complexity_levels_prompt()
        user_request = 'USER REQUEST: "{user_message}"'
        context_analysis = self._get_context_analysis_prompt()
        self.classification_prompt = f"""
{intro}

{complexity_levels}

{user_request}

{context_analysis}
"""

    async def classify_request(self, user_message: str) -> ClassificationResult:
        """
        Intelligently classify a user request using LLM reasoning.
        Falls back to keyword-based classification if LLM fails.
        """
        # Get keyword-based classification first as fallback
        keyword_result = self.keyword_classifier.classify_request(user_message)

        try:
            # Try to get LLM analysis
            llm_result = await self._llm_classify(user_message)

            # Combine results with LLM taking precedence but keyword as fallback
            final_result = self._combine_classifications(
                llm_result, keyword_result, user_message
            )

            # Log the classification for learning
            await self._log_classification(user_message, final_result)

            return final_result

        except Exception as e:
            logger.error("Classification error: %s", e)
            # Fallback to keyword classification
            return self._create_fallback_result(user_message, keyword_result)

    async def _llm_classify(self, user_message: str) -> Dict[str, Any]:
        """Use LLM to analyze and classify the request."""
        prompt = self.classification_prompt.format(user_message=user_message)

        try:
            failsafe_response = await self._get_llm_classification_response(
                prompt, user_message
            )
            self._log_llm_response_info(failsafe_response)
            return self._parse_classification_response(failsafe_response.content)

        except Exception as e:
            logger.error("LLM classification failed: %s", e)
            return {}

    async def _get_llm_classification_response(
        self, prompt: str, user_message: str
    ) -> Any:
        """Get robust LLM response for classification. Issue #620."""
        system_prompt = (
            "You are an expert classification agent. Respond only with valid JSON."
        )
        full_prompt = f"{system_prompt}\n\n{prompt}"

        return await get_robust_llm_response(
            full_prompt,
            context={"task": "classification", "user_message": user_message},
        )

    def _log_llm_response_info(self, failsafe_response: Any) -> None:
        """Log LLM response tier and any warnings. Issue #620."""
        logger.info(
            f"Classification LLM response using tier: {failsafe_response.tier_used.value}"
        )
        if failsafe_response.warnings:
            logger.warning(f"Classification LLM warnings: {failsafe_response.warnings}")

    def _parse_classification_response(self, response: Any) -> Dict[str, Any]:
        """Parse LLM response into classification dict. Issue #620."""
        if isinstance(response, str):
            return self._parse_string_response(response)
        elif isinstance(response, dict):
            return response
        else:
            logger.warning("Unexpected response type: %s", type(response))
            return {}

    def _parse_string_response(self, response: str) -> Dict[str, Any]:
        """Parse string LLM response using JSON formatter. Issue #620."""
        parse_result = json_formatter.parse_llm_response(
            response, CLASSIFICATION_SCHEMA
        )

        if parse_result.success:
            logger.info(
                f"JSON parsed using method: {parse_result.method_used} "
                f"(confidence: {parse_result.confidence:.2f})"
            )
            if parse_result.warnings:
                logger.warning(f"JSON parsing warnings: {parse_result.warnings}")
            return parse_result.data
        else:
            logger.warning("JSON parsing failed: %s", parse_result.warnings)
            return {}

    def _combine_classifications(
        self,
        llm_result: Dict[str, Any],
        keyword_result: TaskComplexity,
        user_message: str,
    ) -> ClassificationResult:
        """Combine LLM and keyword-based classifications intelligently."""
        if not llm_result:
            # LLM failed, use keyword result
            logger.info("LLM classification failed, using keyword-based fallback")
            return self._create_fallback_result(user_message, keyword_result)

        try:
            llm_complexity, confidence = self._resolve_complexity_with_keyword_check(
                llm_result, keyword_result
            )
            return self._build_classification_result(
                llm_result, llm_complexity, confidence, keyword_result
            )
        except Exception as e:
            logger.error("Error combining classifications: %s", e)
            return self._create_fallback_result(user_message, keyword_result)

    def _resolve_complexity_with_keyword_check(
        self, llm_result: Dict[str, Any], keyword_result: TaskComplexity
    ) -> tuple:
        """Resolve complexity using LLM result with keyword sanity check. Issue #620."""
        llm_complexity_str = llm_result.get("complexity", "simple").lower()
        llm_complexity = TaskComplexity(llm_complexity_str)
        confidence = float(llm_result.get("confidence", 0.7))

        # If LLM confidence is low and keyword differs significantly, blend results
        if confidence < 0.6:
            if (
                keyword_result == TaskComplexity.COMPLEX
                and llm_complexity == TaskComplexity.SIMPLE
            ):
                llm_complexity = TaskComplexity.COMPLEX
                confidence = 0.6

        return llm_complexity, confidence

    def _build_classification_result(
        self,
        llm_result: Dict[str, Any],
        complexity: TaskComplexity,
        confidence: float,
        keyword_result: TaskComplexity,
    ) -> ClassificationResult:
        """Build the ClassificationResult from LLM data. Issue #620."""
        return ClassificationResult(
            complexity=complexity,
            confidence=confidence,
            reasoning=llm_result.get("reasoning", "LLM-based analysis"),
            suggested_agents=self._extract_agents(llm_result),
            estimated_steps=int(llm_result.get("estimated_steps", 1)),
            user_approval_needed=llm_result.get("user_approval_needed", False),
            context_analysis=self._build_context_analysis(
                llm_result, keyword_result, confidence
            ),
        )

    def _build_context_analysis(
        self,
        llm_result: Dict[str, Any],
        keyword_result: TaskComplexity,
        confidence: float,
    ) -> Dict[str, Any]:
        """Build context analysis dictionary from LLM result. Issue #620."""
        return {
            "domain": llm_result.get("domain", "general"),
            "intent": llm_result.get("intent", "unknown"),
            "scope": llm_result.get("scope", "single"),
            "risk_level": llm_result.get("risk_level", "low"),
            "system_changes": llm_result.get("system_changes", False),
            "requires_research": llm_result.get("requires_research", False),
            "requires_installation": llm_result.get("requires_installation", False),
            "keyword_classification": keyword_result.value,
            "llm_confidence": confidence,
        }

    def _extract_agents(self, llm_result: Dict[str, Any]) -> List[str]:
        """Extract and map suggested agents from LLM result."""
        suggested = llm_result.get("suggested_agents", [])

        # Map LLM suggestions to actual agent names
        agent_mapping = {
            "research": "research_agent",
            "web_search": "research_agent",
            "knowledge": "kb_librarian",
            "librarian": "kb_librarian",
            "system": "system_commands",
            "install": "system_commands",
            "security": "security_scanner",
            "network": "network_tools",
            "orchestrator": "orchestrator",
        }

        agents = []
        for agent in suggested:
            mapped = agent_mapping.get(agent.lower(), agent)
            if mapped not in agents:
                agents.append(mapped)

        return agents or ["orchestrator"]  # Default to orchestrator

    def _create_fallback_result(
        self, user_message: str, keyword_result: TaskComplexity
    ) -> ClassificationResult:
        """Create a fallback result using keyword classification."""
        return ClassificationResult(
            complexity=keyword_result,
            confidence=0.5,  # Lower confidence for fallback
            reasoning=f"Keyword-based classification: {keyword_result.value}",
            suggested_agents=self._default_agents_for_complexity(keyword_result),
            estimated_steps=self._default_steps_for_complexity(keyword_result),
            user_approval_needed=keyword_result == TaskComplexity.COMPLEX,
            context_analysis={
                "domain": "general",
                "intent": "unknown",
                "scope": (
                    "single"
                    if keyword_result == TaskComplexity.SIMPLE
                    else "multi-step"
                ),
                "risk_level": (
                    "high" if keyword_result == TaskComplexity.COMPLEX else "medium"
                ),
                "classification_method": "keyword_fallback",
                "original_message": user_message,
            },
        )

    def _default_agents_for_complexity(self, complexity: TaskComplexity) -> List[str]:
        """Return default agents for each complexity level."""
        if complexity == TaskComplexity.SIMPLE:
            return ["chat_responder", "kb_librarian"]
        else:  # COMPLEX
            return ["kb_librarian", "research_agent", "system_commands", "orchestrator"]

    def _default_steps_for_complexity(self, complexity: TaskComplexity) -> int:
        """Return default step count for each complexity level."""
        return {
            TaskComplexity.SIMPLE: 1,
            TaskComplexity.COMPLEX: 5,
        }.get(complexity, 1)

    async def _log_classification(
        self, user_message: str, result: ClassificationResult
    ):
        """Log classification results for analysis and improvement."""
        try:
            log_data = {
                "timestamp": "2025-08-11",  # Will be replaced with actual timestamp
                "user_message": user_message,
                "classification": result.complexity.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "agents": result.suggested_agents,
                "steps": result.estimated_steps,
                "context": result.context_analysis,
            }

            # Store in Redis for analysis
            key = f"autobot:classification:log:{hash(user_message)}"
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                self.redis_client.setex, key, 86400, json.dumps(log_data)
            )  # 24h expiry

        except Exception as e:
            logger.error("Failed to log classification: %s", e)

    def get_classification_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent classification history for analysis."""
        try:
            pattern = "autobot:classification:log:*"
            keys = self.redis_client.keys(pattern)

            # Issue #397: Fix N+1 query pattern - use pipeline for batch retrieval
            history = []
            keys_to_fetch = keys[:limit]
            if keys_to_fetch:
                pipe = self.redis_client.pipeline()
                for key in keys_to_fetch:
                    pipe.get(key)
                results = pipe.execute()

                for data in results:
                    if data:
                        history.append(json.loads(data))

            return sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)

        except Exception as e:
            logger.error("Failed to get classification history: %s", e)
            return []


# CLI tool for testing the classification agent
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test the Classification Agent")
    parser.add_argument("message", nargs="?", help="Message to classify")
    parser.add_argument(
        "--history", action="store_true", help="Show classification history"
    )
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    def show_history(agent: ClassificationAgent) -> None:
        """Display recent classification history entries."""
        history = agent.get_classification_history()
        print("📊 Classification History:")
        for entry in history:
            print(f"   Message: {entry['user_message']}")
            classification = entry["classification"]
            confidence = entry["confidence"]
            print(f"   Classification: {classification} (confidence: {confidence})")
            print(f"   Reasoning: {entry['reasoning']}")
            print()

    async def run_interactive(agent: ClassificationAgent) -> None:
        """Run interactive classification mode with user input prompts."""
        print("🤖 Interactive Classification Agent")
        print("Enter messages to classify (Ctrl+C to exit)")

        while True:
            try:
                from src.utils.terminal_input_handler import safe_input

                message = safe_input("\n> ", timeout=10.0, default="exit").strip()
                if not message or message == "exit":
                    print("Exiting interactive mode...")
                    break

                result = await agent.classify_request(message)
                print(f"\nClassification: {result.complexity.value}")
                print(f"Confidence: {result.confidence:.2f}")
                print(f"Reasoning: {result.reasoning}")
                print(f"Suggested agents: {', '.join(result.suggested_agents)}")
                print(f"Estimated steps: {result.estimated_steps}")
                if result.context_analysis.get("domain"):
                    print(f"Domain: {result.context_analysis['domain']}")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break

    async def classify_single(agent: ClassificationAgent, message: str) -> None:
        """Classify a single message and print detailed results."""
        result = await agent.classify_request(message)
        print(f"Message: {message}")
        print(f"Classification: {result.complexity.value}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Suggested agents: {', '.join(result.suggested_agents)}")
        print(f"Context: {json.dumps(result.context_analysis, indent=2)}")

    async def main() -> None:
        """Main entry point for CLI classification agent testing."""
        agent = ClassificationAgent()

        if args.history:
            show_history(agent)
        elif args.interactive:
            await run_interactive(agent)
        elif args.message:
            await classify_single(agent, args.message)
        else:
            print("Usage: python3 classification_agent.py 'message' or --interactive")

    asyncio.run(main())
