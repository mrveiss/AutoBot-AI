# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reasoning effort mapping utility for provider-specific parameters.

Maps user-facing reasoning effort levels (low/medium/high/auto) to
provider-specific API parameters for different LLM providers.
"""

from typing import Dict, Any


def _map_effort_to_provider_params(effort: str, provider: str) -> Dict[str, Any]:
    """
    Map reasoning effort level to provider-specific parameters.

    Args:
        effort: Reasoning effort level ('low', 'medium', 'high', 'auto')
        provider: Provider name ('anthropic', 'openai', 'bedrock', etc.)

    Returns:
        Dict with provider-specific parameters to merge into the API request

    Examples:
        >>> _map_effort_to_provider_params('medium', 'anthropic')
        {'thinking_tokens': 5000}
        >>> _map_effort_to_provider_params('auto', 'openai')
        {}
    """
    if effort == "auto" or not effort:
        # Use provider defaults
        return {}

    provider_lower = provider.lower() if provider else ""

    # Anthropic Claude: thinking_tokens parameter
    if "anthropic" in provider_lower or "claude" in provider_lower:
        thinking_tokens_map = {
            "low": 2000,
            "medium": 5000,
            "high": 10000,
        }
        return {"thinking_tokens": thinking_tokens_map.get(effort, 5000)}

    # OpenAI: reasoning_effort parameter (for o1/o3 models)
    if "openai" in provider_lower:
        # OpenAI o1 models use 'low', 'medium', 'high' directly
        if effort in ("low", "medium", "high"):
            return {"reasoning_effort": effort}
        return {}

    # Bedrock (AWS): depends on underlying model
    if "bedrock" in provider_lower:
        # For Claude on Bedrock, use thinking_tokens
        thinking_tokens_map = {
            "low": 2000,
            "medium": 5000,
            "high": 10000,
        }
        return {"thinking_tokens": thinking_tokens_map.get(effort, 5000)}

    # Vertex AI: depends on underlying model (Gemini or Claude)
    if "vertex" in provider_lower or "gemini" in provider_lower:
        # Gemini doesn't have reasoning effort yet, return empty
        # (may be added in future)
        return {}

    # Other providers: no specific reasoning effort parameter
    # Return empty dict to use provider defaults
    return {}


__all__ = ["_map_effort_to_provider_params"]
