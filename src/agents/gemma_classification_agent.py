"""
Gemma-powered Lightweight Classification Agent
Uses Google's Gemma 2B/3 models for ultra-fast classification tasks
"""

import json
import logging
import requests
from typing import Any, Dict, List, Optional

from src.autobot_types import TaskComplexity
from src.utils.redis_client import get_redis_client
from src.workflow_classifier import WorkflowClassifier
from src.agents.classification_agent import ClassificationResult

from .base_agent import AgentRequest
from .standardized_agent import StandardizedAgent

logger = logging.getLogger(__name__)


# Using ClassificationResult from classification_agent instead of custom result type


class GemmaClassificationAgent(StandardizedAgent):
    """Ultra-fast classification agent using Google's Gemma models."""

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        super().__init__("gemma_classification")
        self.ollama_host = ollama_host
        self.redis_client = get_redis_client()
        self.keyword_classifier = WorkflowClassifier(self.redis_client)

        # Preferred models in order of preference (smallest/fastest first)
        self.preferred_models = [
            "gemma2:2b",  # 2B parameters - ultra fast
            "gemma3:latest",  # Latest Gemma 3 model
            "llama3.2:1b",  # Fallback to existing small model
        ]

        self.capabilities = [
            "ultra_fast_classification",
            "intent_classification",
            "complexity_analysis",
            "workflow_routing",
            "lightweight_llm_inference",
        ]

        self._initialize_classification_prompt()

    async def action_classify_request(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle classify_request action using Gemma models."""
        user_message = request.payload.get("message", "")
        result = await self.classify_request(user_message)

        return {
            "complexity": result.complexity.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "suggested_agents": result.suggested_agents,
            "estimated_steps": result.estimated_steps,
            "user_approval_needed": result.user_approval_needed,
            "context_analysis": result.context_analysis,
            "model_used": result.context_analysis.get("model_used", "unknown"),
            "response_time_ms": result.context_analysis.get("response_time_ms", 0),
        }

    def _initialize_classification_prompt(self):
        """Initialize the optimized classification prompt for Gemma."""
        self.classification_prompt = """You are an expert classification agent for AutoBot. Analyze the user request and respond with JSON ONLY.

COMPLEXITY LEVELS:
- SIMPLE: Basic questions, definitions, greetings, explanations from knowledge base
- COMPLEX: External research, website data, system actions, installations, current/live information

USER REQUEST: "{user_message}"

ANALYSIS GUIDELINES:
- Requests for "what's new", "latest", "current" info from websites = COMPLEX
- Requests with URLs (.com, .lv, .net, etc.) = COMPLEX
- General questions/definitions = SIMPLE
- Installation/system commands = COMPLEX

Respond with valid JSON:
{{
    "complexity": "simple|complex",
    "confidence": 0.9,
    "reasoning": "Brief explanation",
    "domain": "conversation|research|system|web",
    "intent": "Brief intent description",
    "scope": "single|multi-step",
    "risk_level": "low|medium|high",
    "suggested_agents": ["agent1", "agent2"],
    "estimated_steps": 1,
    "user_approval_needed": false,
    "tools_required": false,
    "web_browsing_needed": false
}}"""

    async def classify_request(self, user_message: str) -> ClassificationResult:
        """Classify user request using Gemma models with fallback."""
        import time

        start_time = time.time()

        # Get keyword-based classification as fallback
        keyword_result = self.keyword_classifier.classify_request(user_message)

        try:
            # Try Gemma classification
            gemma_result = await self._gemma_classify(user_message)

            if gemma_result:
                # Use Gemma result
                final_result = self._create_gemma_result(
                    gemma_result, keyword_result, user_message
                )
            else:
                # Fallback to keyword classification
                final_result = self._create_fallback_result(
                    user_message, keyword_result
                )

            # Calculate response time
            response_time = (time.time() - start_time) * 1000
            final_result.context_analysis["response_time_ms"] = response_time

            # Log performance
            model_used = final_result.context_analysis.get("model_used", "unknown")
            logger.info(
                f"Gemma classification completed in {response_time:.1f}ms using {model_used}"
            )

            return final_result

        except Exception as e:
            logger.error(f"Gemma classification error: {e}")
            # Fallback to keyword classification
            final_result = self._create_fallback_result(user_message, keyword_result)
            final_result.context_analysis["response_time_ms"] = (
                time.time() - start_time
            ) * 1000
            return final_result

    async def _gemma_classify(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Use Gemma models for classification."""

        for model in self.preferred_models:
            try:
                # Check if model is available
                available_models = await self._get_available_models()
                if model not in available_models:
                    continue

                # Format prompt
                prompt = self.classification_prompt.format(user_message=user_message)

                # Call Ollama API
                response = requests.post(
                    f"{self.ollama_host}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,  # Low temperature for consistent classification
                            "top_p": 0.9,
                            "num_predict": 200,  # Limit response length
                        },
                    },
                    timeout=10,  # Fast timeout for lightweight models
                )

                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get("response", "").strip()

                    # Parse JSON response
                    parsed_result = self._parse_json_response(response_text)
                    if parsed_result:
                        parsed_result["_model_used"] = model
                        return parsed_result

                else:
                    logger.warning(
                        f"Gemma model {model} returned status {response.status_code}"
                    )

            except Exception as e:
                logger.warning(f"Failed to use Gemma model {model}: {e}")
                continue

        return None

    async def _get_available_models(self) -> List[str]:
        """Get list of available Ollama models."""
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                return [model["name"] for model in models_data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to get available models: {e}")
        return []

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from Gemma model."""
        try:
            # Try to find JSON in response
            import re

            # Look for JSON block
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response_text)
            if json_match:
                json_text = json_match.group(0)
                return json.loads(json_text)

            # Try parsing entire response as JSON
            return json.loads(response_text)

        except Exception as e:
            logger.warning(f"Failed to parse Gemma JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            return None

    def _create_gemma_result(
        self,
        gemma_result: Dict[str, Any],
        keyword_result: TaskComplexity,
        user_message: str,
    ) -> ClassificationResult:
        """Create result from successful Gemma classification."""

        try:
            # Parse complexity
            complexity_str = gemma_result.get("complexity", "simple").lower()
            gemma_complexity = TaskComplexity(complexity_str)

            # Sanity check with keyword classifier
            confidence = float(gemma_result.get("confidence", 0.8))

            # If keyword and Gemma disagree and confidence is low, favor keyword
            if (
                confidence < 0.7
                and keyword_result == TaskComplexity.COMPLEX
                and gemma_complexity == TaskComplexity.SIMPLE
            ):
                gemma_complexity = TaskComplexity.COMPLEX
                confidence = 0.6

            return ClassificationResult(
                complexity=gemma_complexity,
                confidence=confidence,
                reasoning=gemma_result.get("reasoning", "Gemma model analysis"),
                suggested_agents=self._extract_agents(gemma_result),
                estimated_steps=int(gemma_result.get("estimated_steps", 1)),
                user_approval_needed=gemma_result.get("user_approval_needed", False),
                context_analysis={
                    "domain": gemma_result.get("domain", "general"),
                    "intent": gemma_result.get("intent", "unknown"),
                    "scope": gemma_result.get("scope", "single"),
                    "risk_level": gemma_result.get("risk_level", "low"),
                    "tools_required": gemma_result.get("tools_required", False),
                    "web_browsing_needed": gemma_result.get(
                        "web_browsing_needed", False
                    ),
                    "keyword_classification": keyword_result.value,
                    "classification_method": "gemma_llm",
                    "model_used": gemma_result.get("_model_used", "gemma"),
                    "response_time_ms": 0.0,  # Will be set later
                },
            )

        except Exception as e:
            logger.error(f"Error creating Gemma result: {e}")
            return self._create_fallback_result(user_message, keyword_result)

    def _create_fallback_result(
        self, user_message: str, keyword_result: TaskComplexity
    ) -> ClassificationResult:
        """Create fallback result using keyword classification."""

        return ClassificationResult(
            complexity=keyword_result,
            confidence=0.5,
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
                    "medium" if keyword_result == TaskComplexity.COMPLEX else "low"
                ),
                "classification_method": "keyword_fallback",
                "original_message": user_message,
                "model_used": "keyword_classifier",
                "response_time_ms": 0.0,  # Will be set later
            },
        )

    def _extract_agents(self, gemma_result: Dict[str, Any]) -> List[str]:
        """Extract and validate suggested agents."""
        suggested = gemma_result.get("suggested_agents", [])

        # Map common suggestions to actual agents
        agent_mapping = {
            "research": "research_agent",
            "web_search": "research_agent",
            "browser": "research_agent",
            "knowledge": "kb_librarian",
            "librarian": "kb_librarian",
            "system": "system_commands",
            "install": "system_commands",
            "security": "security_scanner",
            "network": "network_tools",
            "orchestrator": "orchestrator",
        }

        agents = []
        for agent in suggested[:3]:  # Limit to 3 agents
            if isinstance(agent, str):
                mapped = agent_mapping.get(agent.lower(), agent)
                if mapped not in agents:
                    agents.append(mapped)

        return agents or ["orchestrator"]

    def _default_agents_for_complexity(self, complexity: TaskComplexity) -> List[str]:
        """Return default agents for complexity level."""
        if complexity == TaskComplexity.SIMPLE:
            return ["chat_responder", "kb_librarian"]
        else:
            return ["kb_librarian", "research_agent", "system_commands", "orchestrator"]

    def _default_steps_for_complexity(self, complexity: TaskComplexity) -> int:
        """Return default step count for complexity level."""
        return 1 if complexity == TaskComplexity.SIMPLE else 3

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities."""
        return self.capabilities.copy()


# CLI test tool
if __name__ == "__main__":
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(description="Test Gemma Classification Agent")
    parser.add_argument("message", nargs="?", help="Message to classify")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument(
        "--benchmark", action="store_true", help="Run performance benchmark"
    )

    args = parser.parse_args()

    async def main():
        agent = GemmaClassificationAgent()

        if args.benchmark:
            print("🚀 Running Gemma Classification Benchmark")
            test_cases = [
                "whats new on tvnet.lv",
                "what is docker",
                "install nginx on ubuntu",
                "hello there",
                "current updates on github.com",
                "define machine learning",
            ]

            total_time = 0
            for i, test_case in enumerate(test_cases, 1):
                print(f"\n{i}. Testing: '{test_case}'")
                result = await agent.classify_request(test_case)
                response_time = result.context_analysis.get("response_time_ms", 0)
                model_used = result.context_analysis.get("model_used", "unknown")
                total_time += response_time
                print(
                    f"   Result: {result.complexity.value} ({result.confidence:.2f}) - {response_time:.1f}ms"
                )
                print(f"   Model: {model_used}")

            avg_time = total_time / len(test_cases)
            print(f"\n📊 Average response time: {avg_time:.1f}ms")

        elif args.interactive:
            print("🤖 Interactive Gemma Classification Agent")
            print("Enter messages to classify (Ctrl+C to exit)")

            while True:
                try:
                    message = input("\n> ").strip()
                    if message:
                        result = await agent.classify_request(message)
                        print(f"\nClassification: {result.complexity.value}")
                        print(f"Confidence: {result.confidence:.2f}")
                        model_used = result.context_analysis.get(
                            "model_used", "unknown"
                        )
                        response_time = result.context_analysis.get(
                            "response_time_ms", 0
                        )
                        print(f"Model: {model_used}")
                        print(f"Response Time: {response_time:.1f}ms")
                        print(f"Reasoning: {result.reasoning}")
                except KeyboardInterrupt:
                    print("\n👋 Goodbye!")
                    break

        elif args.message:
            result = await agent.classify_request(args.message)
            print(f"Message: {args.message}")
            print(f"Classification: {result.complexity.value}")
            print(f"Confidence: {result.confidence:.2f}")
            model_used = result.context_analysis.get("model_used", "unknown")
            response_time = result.context_analysis.get("response_time_ms", 0)
            print(f"Model: {model_used}")
            print(f"Response Time: {response_time:.1f}ms")
            print(f"Reasoning: {result.reasoning}")
            print(f"Context: {json.dumps(result.context_analysis, indent=2)}")

        else:
            print(
                "Usage: python gemma_classification_agent.py 'message' or --interactive or --benchmark"
            )

    asyncio.run(main())
