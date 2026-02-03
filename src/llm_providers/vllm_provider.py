# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
vLLM Provider for AutoBot
High-performance inference for HuggingFace models using vLLM
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional


try:
    from vllm import LLM, SamplingParams
    from vllm.model_executor.parallel_utils.parallel_state import destroy_model_parallel

    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    LLM = None
    SamplingParams = None

logger = logging.getLogger(__name__)


class VLLMProvider:
    """
    vLLM provider for serving HuggingFace models with high performance.
    Supports local inference with GPU/CPU acceleration.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize vLLM provider.

        Args:
            config: Provider configuration dict
                - model: HuggingFace model name/path
                - tensor_parallel_size: Number of GPUs to use
                - gpu_memory_utilization: GPU memory fraction (0.0-1.0)
                - max_model_len: Maximum model length
                - trust_remote_code: Whether to trust remote code
                - dtype: Model data type (auto, half, float16, bfloat16)
        """
        if not VLLM_AVAILABLE:
            raise ImportError("vLLM not available. Install with: pip install vllm")

        self.config = config
        self.model_name = config["model"]
        self.llm: Optional[LLM] = None
        self.is_initialized = False

        # vLLM configuration
        self.tensor_parallel_size = config.get("tensor_parallel_size", 1)
        self.gpu_memory_utilization = config.get("gpu_memory_utilization", 0.9)
        self.max_model_len = config.get("max_model_len", None)
        self.trust_remote_code = config.get("trust_remote_code", False)
        self.dtype = config.get("dtype", "auto")
        self.enable_chunked_prefill = config.get("enable_chunked_prefill", True)

        logger.info("vLLM provider configured for model: %s", self.model_name)

    async def initialize(self):
        """Initialize the vLLM model"""
        if self.is_initialized:
            return

        try:
            logger.info("Initializing vLLM with model: %s", self.model_name)

            # Initialize vLLM in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            self.llm = await loop.run_in_executor(None, self._create_vllm_instance)

            self.is_initialized = True
            logger.info("vLLM model %s initialized successfully", self.model_name)

        except Exception as e:
            logger.error("Failed to initialize vLLM model: %s", e)
            raise

    def _create_vllm_instance(self) -> LLM:
        """Create vLLM instance (runs in thread)"""
        return LLM(
            model=self.model_name,
            tensor_parallel_size=self.tensor_parallel_size,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_model_len=self.max_model_len,
            trust_remote_code=self.trust_remote_code,
            dtype=self.dtype,
            enable_chunked_prefill=self.enable_chunked_prefill,
        )

    async def chat_completion(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> Dict[str, Any]:
        """
        Generate chat completion using vLLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Dict with completion response
        """
        if not self.is_initialized:
            await self.initialize()

        try:
            # Convert messages to prompt
            prompt = self._messages_to_prompt(messages)

            # Create sampling parameters
            sampling_params = self._create_sampling_params(**kwargs)

            # Generate completion
            start_time = time.time()

            # Run generation in thread to avoid blocking
            loop = asyncio.get_event_loop()
            outputs = await loop.run_in_executor(
                None, self._generate_completion, prompt, sampling_params
            )

            generation_time = time.time() - start_time

            # Format response
            if outputs:
                output = outputs[0]
                generated_text = output.outputs[0].text

                return {
                    "message": {"role": "assistant", "content": generated_text.strip()},
                    "usage": {
                        "prompt_tokens": len(output.prompt_token_ids),
                        "completion_tokens": len(output.outputs[0].token_ids),
                        "total_tokens": (
                            len(output.prompt_token_ids)
                            + len(output.outputs[0].token_ids)
                        ),
                    },
                    "model": self.model_name,
                    "provider": "vllm",
                    "generation_time": generation_time,
                    "finish_reason": output.outputs[0].finish_reason,
                }
            else:
                raise RuntimeError("No output generated")

        except Exception as e:
            logger.error("vLLM completion error: %s", e)
            raise

    def _generate_completion(self, prompt: str, sampling_params: SamplingParams):
        """Generate completion (runs in thread)"""
        return self.llm.generate([prompt], sampling_params)

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to a single prompt string"""
        # Basic chat template - can be customized per model
        prompt_parts = []

        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        # Add final assistant prompt
        prompt_parts.append("Assistant:")

        return "\n".join(prompt_parts)

    def _create_sampling_params(self, **kwargs) -> SamplingParams:
        """Create vLLM sampling parameters"""
        # Extract parameters with defaults
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 512)
        top_p = kwargs.get("top_p", 0.95)
        top_k = kwargs.get("top_k", -1)  # -1 means disabled
        frequency_penalty = kwargs.get("frequency_penalty", 0.0)
        presence_penalty = kwargs.get("presence_penalty", 0.0)
        stop = kwargs.get("stop", None)

        return SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
        )

    async def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        if not self.is_initialized:
            await self.initialize()

        return {
            "model_name": self.model_name,
            "provider": "vllm",
            "tensor_parallel_size": self.tensor_parallel_size,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "max_model_len": self.max_model_len,
            "dtype": self.dtype,
            "is_initialized": self.is_initialized,
        }

    async def cleanup(self):
        """Cleanup vLLM resources"""
        if self.llm:
            try:
                # Clean up model parallel state
                destroy_model_parallel()
                self.llm = None
                self.is_initialized = False
                logger.info("vLLM model %s cleaned up", self.model_name)
            except Exception as e:
                logger.warning("Error during vLLM cleanup: %s", e)


class VLLMModelManager:
    """
    Manages multiple vLLM models for different tasks.
    Allows loading/unloading models on demand.
    """

    def __init__(self):
        """Initialize vLLM model manager with empty model registry."""
        self.models: Dict[str, VLLMProvider] = {}
        self.model_configs: Dict[str, Dict[str, Any]] = {}

    def register_model(self, model_id: str, config: Dict[str, Any]):
        """Register a model configuration"""
        self.model_configs[model_id] = config
        logger.info("Registered vLLM model config: %s", model_id)

    async def load_model(self, model_id: str) -> VLLMProvider:
        """Load a model if not already loaded"""
        if model_id in self.models:
            return self.models[model_id]

        if model_id not in self.model_configs:
            raise ValueError(f"Model {model_id} not registered")

        config = self.model_configs[model_id]
        provider = VLLMProvider(config)
        await provider.initialize()

        self.models[model_id] = provider
        logger.info("Loaded vLLM model: %s", model_id)

        return provider

    async def unload_model(self, model_id: str):
        """Unload a model to free memory"""
        if model_id in self.models:
            await self.models[model_id].cleanup()
            del self.models[model_id]
            logger.info("Unloaded vLLM model: %s", model_id)

    async def get_model(self, model_id: str) -> VLLMProvider:
        """Get a model, loading it if necessary"""
        return await self.load_model(model_id)

    def list_models(self) -> Dict[str, Dict[str, Any]]:
        """List all registered models and their status"""
        return {
            model_id: {
                "config": config,
                "loaded": model_id in self.models,
                "initialized": (
                    self.models[model_id].is_initialized
                    if model_id in self.models
                    else False
                ),
            }
            for model_id, config in self.model_configs.items()
        }

    async def cleanup_all(self):
        """Cleanup all loaded models"""
        for model_id in list(self.models.keys()):
            await self.unload_model(model_id)


# Recommended model configurations
RECOMMENDED_MODELS = {
    # Small models for fast inference
    "phi-3-mini": {
        "model": "microsoft/Phi-3-mini-4k-instruct",
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "trust_remote_code": True,
        "dtype": "hal",
    },
    # Medium models for balanced performance
    "llama-3.2-3b": {
        "model": "meta-llama/Llama-3.2-3B-Instruct",
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.9,
        "max_model_len": 8192,
        "trust_remote_code": False,
        "dtype": "hal",
    },
    # Code-focused models
    "codellama-7b": {
        "model": "codellama/CodeLlama-7b-Instruct-h",
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.9,
        "max_model_len": 4096,
        "trust_remote_code": False,
        "dtype": "hal",
    },
    # Large models for complex tasks (requires more GPU memory)
    "llama-3.1-8b": {
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.9,
        "max_model_len": 8192,
        "trust_remote_code": False,
        "dtype": "half",
    },
}
