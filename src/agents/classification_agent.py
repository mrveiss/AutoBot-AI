"""
Intelligent Classification Agent
Uses LLM reasoning to understand user intent and classify workflow complexity
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.autobot_types import TaskComplexity
from src.llm_interface import LLMInterface
from src.utils.redis_client import get_redis_client
from src.workflow_classifier import WorkflowClassifier

from .base_agent import AgentRequest, AgentResponse, LocalAgent

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


class ClassificationAgent(LocalAgent):
    """Intelligent agent that understands user intent for workflow classification."""

    def __init__(self, llm_interface: Optional[LLMInterface] = None):
        super().__init__("classification")
        self.llm = llm_interface or LLMInterface()
        self.redis_client = get_redis_client()
        self.keyword_classifier = WorkflowClassifier(self.redis_client)
        self.capabilities = [
            "intent_classification",
            "complexity_analysis",
            "workflow_routing",
            "request_classification",
            "agent_selection",
        ]

        # Initialize classification prompt
        self._initialize_classification_prompt()

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """
        Process agent request using the standardized interface.
        """
        try:
            action = request.action
            payload = request.payload

            if action == "classify_request":
                user_message = payload.get("message", "")
                result = await self.classify_request(user_message)

                # Convert ClassificationResult to dict for serialization
                result_dict = {
                    "complexity": result.complexity.value,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "suggested_agents": result.suggested_agents,
                    "estimated_steps": result.estimated_steps,
                    "user_approval_needed": result.user_approval_needed,
                    "context_analysis": result.context_analysis,
                }

                return AgentResponse(
                    request_id=request.request_id,
                    agent_type=self.agent_type,
                    status="success",
                    result=result_dict,
                )

            else:
                return AgentResponse(
                    request_id=request.request_id,
                    agent_type=self.agent_type,
                    status="error",
                    result=None,
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            logger.error(f"Classification agent error: {e}")
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=str(e),
            )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    def _initialize_classification_prompt(self):
        """Initialize the classification prompt template"""
        self.classification_prompt = """
You are an intelligent classification agent for AutoBot, a multi-agent workflow orchestration system.

Your task is to analyze user requests and determine the appropriate workflow complexity and coordination strategy.

WORKFLOW COMPLEXITY LEVELS:

1. SIMPLE: Direct questions or requests that can be answered immediately
   - Examples: "What is 2+2?", "Define machine learning", "What time is it?"
   - Characteristics: Factual queries, definitions, simple calculations

2. RESEARCH: Requests requiring web research or knowledge base searches
   - Examples: "Latest Python frameworks", "Current trends in AI", "Best practices for Docker"
   - Characteristics: Need current information, comparisons, recommendations

3. INSTALL: Requests involving system configuration, software installation, or setup
   - Examples: "Install Docker", "Configure nginx", "Set up development environment"
   - Characteristics: System commands, configuration changes, software deployment

4. SECURITY_SCAN: Security scanning and network discovery tasks
   - Examples: "Scan network for open ports", "Perform vulnerability scan", "Network discovery", "Check SSL certificates"
   - Characteristics: Security focus, uses scanning tools, generates reports, may require target validation

5. COMPLEX: Multi-step tasks requiring coordination of multiple specialized agents
   - Examples: "What network scanning tools do we have available?", "Perform full security audit", "Deploy application with monitoring"
   - Characteristics: Multiple domains, requires approvals, system-level changes, security implications

USER REQUEST: "{user_message}"

CONTEXT ANALYSIS:
- Domain: Identify the primary domain(s) involved (security, networking, development, etc.)
- Intent: What does the user want to accomplish?
- Scope: Single task or multi-step process?
- Risk Level: Does this involve system changes, security implications, or require approvals?
- Dependencies: Does this require multiple tools or agents?

Please provide your analysis in the following JSON format:
{{
    "complexity": "simple|research|install|security_scan|complex",
    "confidence": 0.0-1.0,
    "reasoning": "Clear explanation of why you classified it this way",
    "domain": "Primary domain (security, networking, development, etc.)",
    "intent": "What the user wants to accomplish",
    "scope": "single|multi-step",
    "risk_level": "low|medium|high",
    "suggested_agents": ["list", "of", "relevant", "agents"],
    "estimated_steps": 1-10,
    "user_approval_needed": true/false,
    "system_changes": true/false,
    "requires_research": true/false,
    "requires_installation": true/false
}}

Be thorough in your analysis and reasoning. Consider the implications and requirements of the request.
"""

    async def classify_request(self, user_message: str) -> ClassificationResult:
        """
        Intelligently classify a user request using LLM reasoning.
        Falls back to keyword-based classification if LLM fails.
        """
        try:
            # First, get LLM analysis
            llm_result = await self._llm_classify(user_message)

            # Get keyword-based classification for comparison
            keyword_result = self.keyword_classifier.classify_request(user_message)

            # Combine results with LLM taking precedence but keyword as fallback
            final_result = self._combine_classifications(
                llm_result, keyword_result, user_message
            )

            # Log the classification for learning
            await self._log_classification(user_message, final_result)

            return final_result

        except Exception as e:
            logger.error(f"Classification error: {e}")
            # Fallback to keyword classification
            return self._create_fallback_result(user_message, keyword_result)

    async def _llm_classify(self, user_message: str) -> Dict[str, Any]:
        """Use LLM to analyze and classify the request."""
        prompt = self.classification_prompt.format(user_message=user_message)

        try:
            # Get LLM response
            response = await self.llm.chat_completion(
                [
                    {
                        "role": "system",
                        "content": "You are an expert classification agent. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            # Parse JSON response
            if (
                isinstance(response, dict)
                and "message" in response
                and "content" in response["message"]
            ):
                # Extract content from LLM response
                content = response["message"]["content"]
                if isinstance(content, str):
                    # Try to extract JSON from content
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    if start >= 0 and end > start:
                        json_str = content[start:end]
                        try:
                            parsed = json.loads(json_str)
                            # Check if parsed JSON has required fields
                            if not parsed.get("complexity"):
                                logger.warning(
                                    "LLM returned JSON without complexity field"
                                )
                                return {}
                            return parsed
                        except json.JSONDecodeError as je:
                            logger.warning(f"LLM returned malformed JSON: {je}")
                            # Try to fix the JSON by removing common malformed patterns
                            cleaned_json = json_str.replace('{"":"",', "{").replace(
                                '{"":""  }', "{}"
                            )
                            if cleaned_json != "{}":
                                try:
                                    parsed = json.loads(cleaned_json)
                                    if parsed.get("complexity"):
                                        return parsed
                                except Exception:
                                    pass
                            return {}
                return content if isinstance(content, dict) else {}
            elif isinstance(response, str):
                # Try to extract JSON from response string
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                    return json.loads(json_str)

            return response if isinstance(response, dict) else {}

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
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
            # Get LLM classification
            llm_complexity_str = llm_result.get("complexity", "simple").lower()
            llm_complexity = TaskComplexity(llm_complexity_str)

            # Compare with keyword classification
            confidence = float(llm_result.get("confidence", 0.7))

            # If LLM confidence is low and keyword differs significantly, blend results
            if confidence < 0.6:
                # Use keyword as a sanity check
                if (
                    keyword_result == TaskComplexity.COMPLEX
                    and llm_complexity == TaskComplexity.SIMPLE
                ):
                    llm_complexity = TaskComplexity.RESEARCH  # Compromise
                    confidence = 0.5

            # Create comprehensive result
            return ClassificationResult(
                complexity=llm_complexity,
                confidence=confidence,
                reasoning=llm_result.get("reasoning", "LLM-based analysis"),
                suggested_agents=self._extract_agents(llm_result),
                estimated_steps=int(llm_result.get("estimated_steps", 1)),
                user_approval_needed=llm_result.get("user_approval_needed", False),
                context_analysis={
                    "domain": llm_result.get("domain", "general"),
                    "intent": llm_result.get("intent", "unknown"),
                    "scope": llm_result.get("scope", "single"),
                    "risk_level": llm_result.get("risk_level", "low"),
                    "system_changes": llm_result.get("system_changes", False),
                    "requires_research": llm_result.get("requires_research", False),
                    "requires_installation": llm_result.get(
                        "requires_installation", False
                    ),
                    "keyword_classification": keyword_result.value,
                    "llm_confidence": confidence,
                },
            )

        except Exception as e:
            logger.error(f"Error combining classifications: {e}")
            return self._create_fallback_result(user_message, keyword_result)

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
            user_approval_needed=keyword_result
            in [TaskComplexity.INSTALL, TaskComplexity.COMPLEX],
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
            return ["chat_responder"]
        elif complexity == TaskComplexity.RESEARCH:
            return ["kb_librarian", "research_agent"]
        elif complexity == TaskComplexity.INSTALL:
            return ["system_commands", "orchestrator"]
        else:  # COMPLEX
            return ["kb_librarian", "research_agent", "system_commands", "orchestrator"]

    def _default_steps_for_complexity(self, complexity: TaskComplexity) -> int:
        """Return default step count for each complexity level."""
        return {
            TaskComplexity.SIMPLE: 1,
            TaskComplexity.RESEARCH: 3,
            TaskComplexity.INSTALL: 4,
            TaskComplexity.COMPLEX: 8,
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
            self.redis_client.setex(key, 86400, json.dumps(log_data))  # 24h expiry

        except Exception as e:
            logger.error(f"Failed to log classification: {e}")

    def get_classification_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent classification history for analysis."""
        try:
            pattern = "autobot:classification:log:*"
            keys = self.redis_client.keys(pattern)

            history = []
            for key in keys[:limit]:
                data = self.redis_client.get(key)
                if data:
                    history.append(json.loads(data))

            return sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)

        except Exception as e:
            logger.error(f"Failed to get classification history: {e}")
            return []


# CLI tool for testing the classification agent
if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test the Classification Agent")
    parser.add_argument("message", nargs="?", help="Message to classify")
    parser.add_argument(
        "--history", action="store_true", help="Show classification history"
    )
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    async def main():
        agent = ClassificationAgent()

        if args.history:
            history = agent.get_classification_history()
            print("📊 Classification History:")
            for entry in history:
                print(f"   Message: {entry['user_message']}")
                print(
                    f"   Classification: {entry['classification']} (confidence: {entry['confidence']})"
                )
                print(f"   Reasoning: {entry['reasoning']}")
                print()

        elif args.interactive:
            print("🤖 Interactive Classification Agent")
            print("Enter messages to classify (Ctrl+C to exit)")

            while True:
                try:
                    message = input("\n> ").strip()
                    if message:
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

        elif args.message:
            result = await agent.classify_request(args.message)
            print(f"Message: {args.message}")
            print(f"Classification: {result.complexity.value}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Reasoning: {result.reasoning}")
            print(f"Suggested agents: {', '.join(result.suggested_agents)}")
            print(f"Context: {json.dumps(result.context_analysis, indent=2)}")

        else:
            print("Usage: python3 classification_agent.py 'message' or --interactive")

    asyncio.run(main())
