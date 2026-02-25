# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gemma-powered Lightweight Classification Agent
Uses Google's Gemma 2B/3 models for ultra-fast classification tasks
"""

import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from agents.classification_agent import ClassificationResult
from autobot_types import TaskComplexity
from workflow_classifier import WorkflowClassifier

from autobot_shared.http_client import get_http_client
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)

from .base_agent import AgentRequest
from .standardized_agent import StandardizedAgent

logger = logging.getLogger(__name__)


# Using ClassificationResult from classification_agent instead of custom result type


class GemmaClassificationAgent(StandardizedAgent):
    """Ultra-fast classification agent using Google's Gemma models."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "classification"

    def __init__(self, ollama_host: str = None):
        """Initialize Gemma classification agent with explicit LLM configuration."""
        super().__init__("gemma_classification")

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        # Allow override via constructor for testing
        self.ollama_host = ollama_host or self.llm_endpoint
        self.redis_client = get_redis_client()
        self.keyword_classifier = WorkflowClassifier(self.redis_client)

        # Use explicit model from SSOT config
        self.preferred_models = [self.model_name]

        logger.info(
            "GemmaClassificationAgent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

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
        self.classification_prompt = (
            (
                "You are an expert classification agent for AutoBot. "
                "Analyze the user request and respond with JSON ONLY."
            )
            + """

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
        )

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
            logger.error("Gemma classification error: %s", e)
            # Fallback to keyword classification
            final_result = self._create_fallback_result(user_message, keyword_result)
            final_result.context_analysis["response_time_ms"] = (
                time.time() - start_time
            ) * 1000
            return final_result

    async def _read_streaming_response(self, response) -> str:
        """Read streaming response from Ollama (Issue #334 - extracted helper)."""
        # Issue #383 - Use list and join instead of string concatenation
        response_parts = []
        async for line in response.content:
            if not line:
                continue
            try:
                chunk_data = json.loads(line.decode("utf-8"))
                if "response" in chunk_data:
                    response_parts.append(chunk_data["response"])
                if chunk_data.get("done", False):
                    break
            except json.JSONDecodeError:
                continue
        return "".join(response_parts).strip()

    async def _try_model_classify(
        self, model: str, prompt: str, available_models: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Try classification with single model (Issue #334 - extracted helper)."""
        if model not in available_models:
            return None

        http_client = get_http_client()
        timeout = aiohttp.ClientTimeout(total=10)

        async with await http_client.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 200,
                },
            },
            timeout=timeout,
        ) as response:
            if response.status != 200:
                logger.warning(
                    "Gemma model %s returned status %s", model, response.status
                )
                return None

            response_text = await self._read_streaming_response(response)
            parsed_result = self._parse_json_response(response_text)
            if parsed_result:
                parsed_result["_model_used"] = model
            return parsed_result

    async def _gemma_classify(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Use Gemma models for classification."""
        available_models = await self._get_available_models()
        prompt = self.classification_prompt.format(user_message=user_message)

        for model in self.preferred_models:
            try:
                result = await self._try_model_classify(model, prompt, available_models)
                if result:
                    return result
            except Exception as e:
                logger.warning("Failed to use Gemma model %s: %s", model, e)
                continue

        return None

    async def _get_available_models(self) -> List[str]:
        """Get list of available Ollama models."""
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=5)
            async with await http_client.get(
                f"{self.ollama_host}/api/tags", timeout=timeout
            ) as response:
                if response.status == 200:
                    models_data = await response.json()
                    return [model["name"] for model in models_data.get("models", [])]
        except Exception as e:
            logger.warning("Failed to get available models: %s", e)
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
            logger.warning("Failed to parse Gemma JSON response: %s", e)
            logger.debug("Response text: %s", response_text)
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
            logger.error("Error creating Gemma result: %s", e)
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
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test Gemma Classification Agent")
    parser.add_argument("message", nargs="?", help="Message to classify")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument(
        "--benchmark", action="store_true", help="Run performance benchmark"
    )

    args = parser.parse_args()

    async def run_benchmark(agent):
        """Run benchmark mode (Issue #334 - extracted helper)."""
        print("🚀 Running Gemma Classification Benchmark")  # noqa: print
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
            print(f"\n{i}. Testing: '{test_case}'")  # noqa: print
            result = await agent.classify_request(test_case)
            response_time = result.context_analysis.get("response_time_ms", 0)
            model_used = result.context_analysis.get("model_used", "unknown")
            total_time += response_time
            print(  # noqa: print
                f"   Result: {result.complexity.value} ({result.confidence:.2f}) - {response_time:.1f}ms"
            )
            print(f"   Model: {model_used}")  # noqa: print

        avg_time = total_time / len(test_cases)
        print(f"\n📊 Average response time: {avg_time:.1f}ms")  # noqa: print

    async def run_interactive(agent):
        """Run interactive mode (Issue #334 - extracted helper)."""
        print("🤖 Interactive Gemma Classification Agent")  # noqa: print
        print("Enter messages to classify (Ctrl+C to exit)")  # noqa: print

        while True:
            try:
                message = input("\n> ").strip()
                if not message:
                    continue
                result = await agent.classify_request(message)
                print(f"\nClassification: {result.complexity.value}")  # noqa: print
                print(f"Confidence: {result.confidence:.2f}")  # noqa: print
                model_used = result.context_analysis.get("model_used", "unknown")
                response_time = result.context_analysis.get("response_time_ms", 0)
                print(f"Model: {model_used}")  # noqa: print
                print(f"Response Time: {response_time:.1f}ms")  # noqa: print
                print(f"Reasoning: {result.reasoning}")  # noqa: print
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")  # noqa: print
                break

    async def run_single_message(agent, message):
        """Run single message mode (Issue #334 - extracted helper)."""
        result = await agent.classify_request(message)
        print(f"Message: {message}")  # noqa: print
        print(f"Classification: {result.complexity.value}")  # noqa: print
        print(f"Confidence: {result.confidence:.2f}")  # noqa: print
        model_used = result.context_analysis.get("model_used", "unknown")
        response_time = result.context_analysis.get("response_time_ms", 0)
        print(f"Model: {model_used}")  # noqa: print
        print(f"Response Time: {response_time:.1f}ms")  # noqa: print
        print(f"Reasoning: {result.reasoning}")  # noqa: print
        print(  # noqa: print
            f"Context: {json.dumps(result.context_analysis, indent=2)}"
        )  # noqa: print

    async def main():
        """Run Gemma classification agent in selected mode."""
        agent = GemmaClassificationAgent()

        if args.benchmark:
            await run_benchmark(agent)
        elif args.interactive:
            await run_interactive(agent)
        elif args.message:
            await run_single_message(agent, args.message)
        else:
            print(  # noqa: print
                "Usage: python gemma_classification_agent.py 'message' or --interactive or --benchmark"
            )

    asyncio.run(main())
