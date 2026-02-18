# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Explanation Service

LLM-powered service that generates explanations for:
- Part 1: What a command does and what each flag/argument means
- Part 2: What the command output shows and key findings

Uses caching to reduce LLM calls for common commands.
"""

import hashlib
import json
import logging
from typing import Dict, Optional

from backend.dependencies import global_config_manager

from autobot_shared.http_client import get_http_client

from .types import CommandBreakdownPart, CommandExplanation, OutputExplanation

logger = logging.getLogger(__name__)


class CommandExplanationService:
    """
    LLM-powered command and output explanation service.

    Provides two-part explanations:
    - Part 1: Command explanation (what it does, flag breakdown)
    - Part 2: Output explanation (what results show, key findings)
    """

    # L1 cache for common commands (in-memory)
    _command_cache: Dict[str, CommandExplanation] = {}
    # Cache for output explanations (keyed by command+output hash)
    _output_cache: Dict[str, OutputExplanation] = {}

    def __init__(self):
        """Initialize the command explanation service."""
        self._http_client = None

    def _get_http_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = get_http_client()
        return self._http_client

    def _get_ollama_endpoint(self) -> str:
        """Get Ollama endpoint from config."""
        try:
            endpoint = global_config_manager.get_ollama_url()
            if not endpoint.endswith("/api/generate"):
                endpoint = endpoint.rstrip("/") + "/api/generate"
            return endpoint
        except Exception as e:
            logger.error("Failed to get Ollama endpoint: %s", e)
            from config import UnifiedConfigManager

            config = UnifiedConfigManager()
            return f"http://{config.get_host('ollama')}:{config.get_port('ollama')}/api/generate"

    def _get_model(self) -> str:
        """Get LLM model from config."""
        try:
            return global_config_manager.get_selected_model()
        except Exception:
            return "qwen3:14b"

    def _get_cache_key(self, command: str) -> str:
        """Generate cache key for a command."""
        # Normalize command by removing extra whitespace
        normalized = " ".join(command.split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _get_output_cache_key(self, command: str, output: str) -> str:
        """Generate cache key for command+output combination."""
        # Truncate output for caching (only first 2000 chars matter for explanation)
        truncated_output = output[:2000] if len(output) > 2000 else output
        combined = f"{command}::{truncated_output}"
        return hashlib.md5(combined.encode()).hexdigest()

    async def explain_command(self, command: str) -> CommandExplanation:
        """
        Generate Part 1 explanation: What the command does.

        Args:
            command: The shell command to explain

        Returns:
            CommandExplanation with summary and breakdown
        """
        # Check L1 cache first
        cache_key = self._get_cache_key(command)
        if cache_key in self._command_cache:
            logger.debug("Command explanation cache hit: %s", command[:50])
            return self._command_cache[cache_key]

        # Generate explanation via LLM
        prompt = self._build_command_explanation_prompt(command)

        try:
            response = await self._call_llm(prompt)
            explanation = self._parse_command_explanation(response, command)

            # Cache the result
            self._command_cache[cache_key] = explanation
            logger.info("Generated command explanation for: %s", command[:50])

            return explanation

        except Exception as e:
            logger.error("Failed to explain command: %s", e)
            # Return a basic fallback explanation
            return CommandExplanation(
                summary=f"Executes: {command}",
                breakdown=[
                    CommandBreakdownPart(
                        part=command.split()[0] if command else "unknown",
                        explanation="Command to be executed",
                    )
                ],
            )

    async def explain_output(
        self, command: str, output: str, return_code: int = 0
    ) -> OutputExplanation:
        """
        Generate Part 2 explanation: What the output shows.

        Args:
            command: The command that was executed
            output: The command output (stdout/stderr combined)
            return_code: The command's return code

        Returns:
            OutputExplanation with summary and key findings
        """
        # Check cache
        cache_key = self._get_output_cache_key(command, output)
        if cache_key in self._output_cache:
            logger.debug("Output explanation cache hit")
            return self._output_cache[cache_key]

        # Generate explanation via LLM
        prompt = self._build_output_explanation_prompt(command, output, return_code)

        try:
            response = await self._call_llm(prompt)
            explanation = self._parse_output_explanation(response)

            # Cache the result
            self._output_cache[cache_key] = explanation
            logger.info("Generated output explanation for: %s", command[:50])

            return explanation

        except Exception as e:
            logger.error("Failed to explain output: %s", e)
            # Return a basic fallback explanation
            return OutputExplanation(
                summary="Command execution completed."
                if return_code == 0
                else f"Command failed with return code {return_code}.",
                key_findings=["See output above for details."],
            )

    def _build_command_explanation_prompt(self, command: str) -> str:
        """Build prompt for command explanation."""
        return f"""Analyze this shell command and explain what it does.

Command: {command}

Provide your response in this exact JSON format:
{{
  "summary": "Brief 1-2 sentence description of what this command does overall",
  "breakdown": [
    {{"part": "command_part", "explanation": "what this part does"}},
    {{"part": "flag_or_argument", "explanation": "what this means"}}
  ],
  "security_notes": "Any security implications (null if none)"
}}

Rules:
- Keep explanations concise but informative
- Explain each significant part (command, flags, arguments)
- Skip trivial parts like common paths if obvious
- Note any potentially dangerous operations in security_notes
- Response must be valid JSON only, no other text"""

    def _build_output_explanation_prompt(
        self, command: str, output: str, return_code: int
    ) -> str:
        """Build prompt for output explanation."""
        # Truncate very long outputs
        max_output_len = 4000
        truncated = output[:max_output_len] if len(output) > max_output_len else output
        truncation_note = (
            f"\n[Output truncated, showing first {max_output_len} chars of {len(output)} total]"
            if len(output) > max_output_len
            else ""
        )

        return f"""Analyze the output of this command and explain what we're looking at.

Command: {command}
Return Code: {return_code}

Output:
```
{truncated}{truncation_note}
```

Provide your response in this exact JSON format:
{{
  "summary": "Brief description of what this output shows",
  "key_findings": [
    "Important finding 1",
    "Important finding 2",
    "Important finding 3"
  ],
  "details": "More detailed explanation if needed (null if not needed)",
  "next_steps": ["Suggested action 1", "Suggested action 2"] or null
}}

Rules:
- Focus on what the user would want to know
- Highlight important discoveries or issues
- Keep key_findings to 3-5 most important points
- Only suggest next_steps if there's a clear follow-up action
- Response must be valid JSON only, no other text"""

    async def _call_llm(self, prompt: str) -> str:
        """Make LLM API call and return response text."""
        endpoint = self._get_ollama_endpoint()
        model = self._get_model()

        http_client = self._get_http_client()
        response = await http_client.post_json(
            endpoint,
            json_data={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower for more consistent explanations
                    "top_p": 0.9,
                    "num_ctx": 4096,
                },
            },
        )

        return response.get("response", "")

    def _parse_command_explanation(
        self, response: str, command: str
    ) -> CommandExplanation:
        """Parse LLM response into CommandExplanation."""
        try:
            # Try to extract JSON from response
            data = self._extract_json(response)

            breakdown = [
                CommandBreakdownPart(part=item["part"], explanation=item["explanation"])
                for item in data.get("breakdown", [])
            ]

            return CommandExplanation(
                summary=data.get("summary", f"Executes {command.split()[0]}"),
                breakdown=breakdown
                or [
                    CommandBreakdownPart(
                        part=command.split()[0], explanation="Main command"
                    )
                ],
                security_notes=data.get("security_notes"),
            )

        except Exception as e:
            logger.warning("Failed to parse command explanation: %s", e)
            # Fallback: create basic explanation
            parts = command.split()
            return CommandExplanation(
                summary=f"Executes the {parts[0]} command",
                breakdown=[
                    CommandBreakdownPart(part=parts[0], explanation="Command name")
                ]
                + [
                    CommandBreakdownPart(part=p, explanation="Argument/flag")
                    for p in parts[1:3]
                ],
            )

    def _parse_output_explanation(self, response: str) -> OutputExplanation:
        """Parse LLM response into OutputExplanation."""
        try:
            data = self._extract_json(response)

            return OutputExplanation(
                summary=data.get("summary", "Command output displayed above."),
                key_findings=data.get("key_findings", ["See output for details."]),
                details=data.get("details"),
                next_steps=data.get("next_steps"),
            )

        except Exception as e:
            logger.warning("Failed to parse output explanation: %s", e)
            return OutputExplanation(
                summary="Command executed. See output above.",
                key_findings=["Output displayed above"],
            )

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response text."""
        # Try direct parse first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON in the response
        import re

        # Look for JSON object pattern
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError("Could not extract JSON from response")

    def clear_cache(self) -> None:
        """Clear all cached explanations."""
        self._command_cache.clear()
        self._output_cache.clear()
        logger.info("Cleared command explanation cache")


# Singleton instance
_service_instance: Optional[CommandExplanationService] = None


def get_command_explanation_service() -> CommandExplanationService:
    """Get or create the command explanation service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CommandExplanationService()
    return _service_instance
