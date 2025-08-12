"""
LLM Providers for AutoBot
Supports multiple LLM backends for flexible model selection
"""

from .vllm_provider import VLLMProvider, VLLMModelManager, RECOMMENDED_MODELS

__all__ = ["VLLMProvider", "VLLMModelManager", "RECOMMENDED_MODELS"]