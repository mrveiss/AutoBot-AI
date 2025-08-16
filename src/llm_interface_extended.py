"""
Extended LLM Interface with vLLM Support
Extends the existing LLM interface to add vLLM and HuggingFace model support
"""

import logging
from typing import Any, Dict, List, Optional, Union

from .llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class ExtendedLLMInterface(LLMInterface):
    """
    Extended LLM interface that adds vLLM support for HuggingFace models.
    Maintains compatibility with existing Ollama and OpenAI providers.
    """

    def __init__(self):
        """Initialize the extended LLM interface"""
        super().__init__()

        # Initialize vLLM model manager
        self.vllm_manager = VLLMModelManager()
        self._initialize_vllm_models()

        # Provider routing map
        self.provider_routing = {
            "vllm": self._handle_vllm_request,
            "ollama": self._handle_ollama_request,
            "openai": self._handle_openai_request,
        }

        logger.info("Extended LLM interface initialized with vLLM support")

    def _initialize_vllm_models(self):
        """Register recommended vLLM models"""
        for model_id, config in RECOMMENDED_MODELS.items():
            self.vllm_manager.register_model(model_id, config)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        llm_type: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Enhanced chat completion with multi-provider support.

        Args:
            messages: List of message dicts
            llm_type: Type of LLM (orchestrator, task, chat, rag, etc.)
            model_name: Specific model name
            provider: Provider to use (vllm, ollama, openai)
            **kwargs: Additional parameters

        Returns:
            Dict with completion response
        """
        try:
            # Determine provider and model
            selected_provider, selected_model = self._select_provider_and_model(
                llm_type, model_name, provider
            )

            logger.debug(
                f"Using provider: {selected_provider}, model: {selected_model}"
            )

            # Route to appropriate provider
            if selected_provider in self.provider_routing:
                return await self.provider_routing[selected_provider](
                    messages, selected_model, **kwargs
                )
            else:
                # Fallback to parent implementation
                return await super().chat_completion(
                    messages, llm_type=llm_type, **kwargs
                )

        except Exception as e:
            logger.error(f"Extended chat completion error: {e}")
            # Fallback to parent implementation
            return await super().chat_completion(messages, llm_type=llm_type, **kwargs)

    def _select_provider_and_model(
        self,
        llm_type: Optional[str],
        model_name: Optional[str],
        provider: Optional[str],
    ) -> tuple[str, str]:
        """
        Select the best provider and model for the request.

        Returns:
            Tuple of (provider, model_name)
        """
        # If provider explicitly specified
        if provider:
            if provider == "vllm":
                # Use model_name if provided, otherwise default for llm_type
                model = model_name or self._get_default_vllm_model(llm_type)
                return "vllm", model
            else:
                return provider, model_name or ""

        # If model_name suggests a provider
        if model_name:
            if model_name in RECOMMENDED_MODELS:
                return "vllm", model_name
            elif "ollama_" in model_name or model_name in self.ollama_models:
                return "ollama", model_name
            elif "gpt-" in model_name or "claude-" in model_name:
                return "openai", model_name

        # Default routing based on llm_type
        return self._get_default_provider_for_type(llm_type)

    def _get_default_provider_for_type(
        self, llm_type: Optional[str]
    ) -> tuple[str, str]:
        """Get default provider and model for LLM type"""
        type_mapping = {
            "chat": ("vllm", "phi-3-mini"),  # Fast for chat
            "rag": ("vllm", "llama-3.2-3b"),  # Good for synthesis
            "classification": ("vllm", "phi-3-mini"),  # Fast classification
            "system_commands": ("vllm", "codellama-7b"),  # Code generation
            "orchestrator": ("vllm", "llama-3.1-8b"),  # Complex reasoning
            "research": ("ollama", "llama3.2:3b"),  # Use existing Ollama
        }

        return type_mapping.get(llm_type, ("ollama", "llama3.2:1b"))

    def _get_default_vllm_model(self, llm_type: Optional[str]) -> str:
        """Get default vLLM model for LLM type"""
        type_mapping = {
            "chat": "phi-3-mini",
            "rag": "llama-3.2-3b",
            "classification": "phi-3-mini",
            "system_commands": "codellama-7b",
            "orchestrator": "llama-3.1-8b",
        }

        return type_mapping.get(llm_type, "phi-3-mini")

    async def _handle_vllm_request(
        self, messages: List[Dict[str, str]], model_name: str, **kwargs
    ) -> Dict[str, Any]:
        """Handle request using vLLM provider"""
        try:
            # Get or load the model
            provider = await self.vllm_manager.get_model(model_name)

            # Generate completion
            response = await provider.chat_completion(messages, **kwargs)

            # Add metadata
            response["provider"] = "vllm"
            response["model_id"] = model_name

            return response

        except Exception as e:
            logger.error(f"vLLM request failed for model {model_name}: {e}")
            raise

    async def _handle_ollama_request(
        self, messages: List[Dict[str, str]], model_name: str, **kwargs
    ) -> Dict[str, Any]:
        """Handle request using Ollama (parent implementation)"""
        # Use parent implementation for Ollama
        return await super().chat_completion(messages, **kwargs)

    async def _handle_openai_request(
        self, messages: List[Dict[str, str]], model_name: str, **kwargs
    ) -> Dict[str, Any]:
        """Handle request using OpenAI (parent implementation)"""
        # Use parent implementation for OpenAI
        return await super().chat_completion(messages, **kwargs)

    async def get_available_models(self) -> Dict[str, Any]:
        """Get information about all available models"""
        models_info = {
            "vllm_models": self.vllm_manager.list_models(),
            "ollama_models": list(self.ollama_models.keys()),
            "provider_routing": {
                llm_type: {"default_provider": provider, "default_model": model}
                for llm_type, (provider, model) in {
                    "chat": self._get_default_provider_for_type("chat"),
                    "rag": self._get_default_provider_for_type("rag"),
                    "classification": self._get_default_provider_for_type(
                        "classification"
                    ),
                    "system_commands": self._get_default_provider_for_type(
                        "system_commands"
                    ),
                    "orchestrator": self._get_default_provider_for_type("orchestrator"),
                }.items()
            },
        }

        return models_info

    async def preload_models(self, model_ids: List[str]):
        """Preload vLLM models for better performance"""
        for model_id in model_ids:
            if model_id in RECOMMENDED_MODELS:
                try:
                    await self.vllm_manager.load_model(model_id)
                    logger.info(f"Preloaded vLLM model: {model_id}")
                except Exception as e:
                    logger.error(f"Failed to preload model {model_id}: {e}")

    async def unload_models(self, model_ids: List[str]):
        """Unload vLLM models to free memory"""
        for model_id in model_ids:
            try:
                await self.vllm_manager.unload_model(model_id)
                logger.info(f"Unloaded vLLM model: {model_id}")
            except Exception as e:
                logger.error(f"Failed to unload model {model_id}: {e}")

    async def get_model_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for all providers"""
        stats = {
            "vllm": self.vllm_manager.list_models(),
            "memory_usage": await self._get_memory_usage(),
            "active_models": len(
                [m for m in self.vllm_manager.list_models().values() if m["loaded"]]
            ),
        }

        return stats

    async def _get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage information"""
        try:
            import psutil
            import torch

            memory_info = {
                "system_memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                }
            }

            # Add GPU memory if available
            if torch.cuda.is_available():
                memory_info["gpu_memory"] = {
                    "total": torch.cuda.get_device_properties(0).total_memory,
                    "allocated": torch.cuda.memory_allocated(0),
                    "cached": torch.cuda.memory_reserved(0),
                }

            return memory_info

        except Exception as e:
            logger.warning(f"Could not get memory usage: {e}")
            return {"error": str(e)}

    async def cleanup(self):
        """Cleanup all providers"""
        try:
            await self.vllm_manager.cleanup_all()
            logger.info("Extended LLM interface cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Convenience function to get the extended interface
def get_extended_llm_interface() -> ExtendedLLMInterface:
    """Get a singleton instance of the extended LLM interface"""
    global _extended_llm_instance

    if "_extended_llm_instance" not in globals():
        _extended_llm_instance = ExtendedLLMInterface()

    return _extended_llm_instance
