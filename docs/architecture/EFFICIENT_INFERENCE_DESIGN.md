# LLM Inference Optimization Architecture

> **Issue:** [#717](https://github.com/mrveiss/AutoBot-AI/issues/717)
> **Status:** Research & Design
> **Author:** mrveiss
> **Last Updated:** 2026-01-13

---

## Executive Summary

This document describes a **latency-focused** inference optimization architecture for AutoBot. The goal is to achieve **faster inference AND lower memory usage** - not trade one for the other.

**Key insight:** The original AirLLM layer-sharding approach trades latency for memory (500ms → 2000ms). This is unacceptable for interactive use. Instead, we focus on techniques that **improve both metrics**.

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Technique Comparison](#2-technique-comparison)
3. [Recommended Optimizations](#3-recommended-optimizations)
4. [Speculative Decoding (Draft Models)](#4-speculative-decoding-draft-models)
5. [Quantization Integration](#5-quantization-integration)
6. [vLLM Optimization Tuning](#6-vllm-optimization-tuning)
7. [KV Cache Optimization](#7-kv-cache-optimization)
8. [FlashAttention & FlashInfer](#8-flashattention--flashinfer)
9. [Continuous Batching](#9-continuous-batching)
10. [Medusa Heads (Multi-Head Decoding)](#10-medusa-heads-multi-head-decoding)
11. [CUDA Graphs](#11-cuda-graphs)
12. [Prompt Compression & Token Reduction](#12-prompt-compression--token-reduction)
13. [Implementation Plan](#13-implementation-plan)
14. [Integration Points](#14-integration-points)
15. [References](#15-references)
16. [Cloud Model Integration](#16-cloud-model-integration)

---

## 1. Motivation

### Current State

AutoBot's LLM infrastructure:
- **Ollama** (primary) - Local inference at `127.0.0.1:11434`
- **vLLM** - High-performance inference with prefix caching
- **Default model:** `mistral:7b-instruct`
- **Current latency:** ~500ms first token

### Problem with AirLLM Approach

| Technique | Memory | Latency | Verdict |
|-----------|--------|---------|---------|
| AirLLM Layer Sharding | 4GB (great) | 2000ms (unacceptable) | **REJECTED** |

Layer-by-layer disk loading introduces unavoidable I/O latency that degrades user experience.

### Desired State

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| First token latency | 500ms | 250-350ms | **1.5-2x faster** |
| Memory usage | 12GB | 6-8GB | **40-50% reduction** |
| Model capability | 7B | 7B-13B | Enable larger models |

---

## 2. Technique Comparison

### Techniques That IMPROVE Latency

| Technique | Speedup | Memory Impact | Accuracy Loss | Complexity |
|-----------|---------|---------------|---------------|------------|
| **Speculative Decoding** | 1.5-2.8x faster | Slight increase | 0% (lossless) | Medium |
| **INT8 W+A Quantization** | 1.6x faster | 50% reduction | <0.5% | Low |
| **INT4 Weight-only** | 1.3x faster | 75% reduction | ~1% | Low |
| **vLLM Multi-Step** | 2.7x throughput | Same | 0% | Config only |
| **Prefix Caching** | 2-5x (repeat prompts) | Slight increase | 0% | Already in vLLM |
| **KV Cache Compression** | 1.3x faster | 30% reduction | <0.5% | Medium |

### Techniques That DEGRADE Latency (Avoid)

| Technique | Memory Benefit | Latency Cost | Use Case |
|-----------|----------------|--------------|----------|
| Layer Sharding (AirLLM) | 70% reduction | 4x slower | Batch only, not interactive |
| Disk Offloading | 80% reduction | 10x slower | Extreme memory constraints |

---

## 3. Recommended Optimizations

### Priority Order

```
Phase 1: Quick Wins (Config Changes)         ← Start here
    ├── Enable prefix caching in vLLM
    ├── Enable chunked prefill
    └── Tune multi-step scheduling

Phase 2: Speculative Decoding                ← High impact, medium effort
    ├── Add draft model support
    ├── Configure n-gram speculation
    └── Benchmark acceptance rates

Phase 3: Quantization                        ← Best memory/speed trade-off
    ├── INT8 weight+activation (recommended)
    ├── INT4 weight-only (aggressive)
    └── LLM Compressor integration

Phase 4: Advanced Optimizations              ← Future work
    ├── KV cache compression
    ├── Custom CUDA kernels
    └── Tensor parallelism
```

---

## 4. Speculative Decoding (Draft Models)

### How It Works

Speculative decoding uses a small, fast "draft" model to propose multiple tokens, then the main model verifies them in a single forward pass.

```
Traditional Autoregressive (slow):
┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐
│Token 1│ → │Token 2│ → │Token 3│ → │Token 4│
└───────┘   └───────┘   └───────┘   └───────┘
  Pass 1      Pass 2      Pass 3      Pass 4

  Total: 4 forward passes

Speculative Decoding (fast):
┌─────────────────────────────────────────────┐
│ Draft Model: Propose T1, T2, T3, T4, T5     │  (fast, parallel)
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│ Main Model: Verify all 5 tokens at once     │  (single pass)
└─────────────────────────────────────────────┘
                    │
                    ▼
         Accept: T1 ✓, T2 ✓, T3 ✓, T4 ✗
         Result: 3 tokens in 1 pass = 3x speedup
```

### Performance Results

| Method | Speedup | Best Use Case |
|--------|---------|---------------|
| Draft Model (Llama 68M → 7B) | 1.5x | General chat |
| N-gram Matching | 2.8x | Summarization, code completion |
| EAGLE-3 | 2.0x | Balanced workloads |
| Prompt Lookup | 2.8x | Tasks with prompt/output overlap |

### Implementation for AutoBot

**File:** `src/llm_interface_pkg/speculative/speculative_decoder.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Speculative Decoding for faster LLM inference.

Implements draft model speculation for 1.5-2.8x speedup with zero accuracy loss.
Reference: https://blog.vllm.ai/2024/10/17/spec-decode.html
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import torch

logger = logging.getLogger(__name__)


@dataclass
class SpeculativeConfig:
    """Configuration for speculative decoding."""

    # Draft model settings
    draft_model: Optional[str] = None  # e.g., "TinyLlama/TinyLlama-1.1B"
    num_speculative_tokens: int = 5    # Tokens to speculate per step

    # N-gram speculation (no draft model needed)
    use_ngram: bool = False
    ngram_prompt_lookup_max: int = 4

    # Acceptance settings
    min_acceptance_rate: float = 0.6   # Disable if acceptance too low

    # Performance tuning
    draft_tensor_parallel_size: int = 1


class SpeculativeDecoder:
    """
    Speculative decoding implementation for AutoBot.

    Supports two modes:
    1. Draft model: Small model proposes, large model verifies
    2. N-gram: Use prompt patterns for speculation (best for summarization)
    """

    def __init__(self, config: SpeculativeConfig):
        """
        Initialize speculative decoder.

        Args:
            config: Speculative decoding configuration
        """
        self.config = config
        self._draft_model = None
        self._acceptance_history: List[float] = []
        self._enabled = True

    async def initialize_draft_model(self, main_model_name: str) -> bool:
        """
        Initialize draft model compatible with main model.

        Args:
            main_model_name: Name of the main/target model

        Returns:
            True if draft model loaded successfully
        """
        if self.config.use_ngram:
            logger.info("Using n-gram speculation (no draft model)")
            return True

        if not self.config.draft_model:
            # Auto-select draft model based on main model
            self.config.draft_model = self._auto_select_draft(main_model_name)

        try:
            # Load draft model (implementation depends on backend)
            logger.info(f"Loading draft model: {self.config.draft_model}")
            # self._draft_model = await self._load_model(self.config.draft_model)
            return True
        except Exception as e:
            logger.warning(f"Failed to load draft model: {e}, falling back to standard decoding")
            self._enabled = False
            return False

    def _auto_select_draft(self, main_model: str) -> str:
        """Auto-select appropriate draft model for main model."""
        draft_mapping = {
            "llama": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "mistral": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "qwen": "Qwen/Qwen2-0.5B-Instruct",
            "phi": "microsoft/phi-1_5",
        }

        for key, draft in draft_mapping.items():
            if key in main_model.lower():
                return draft

        return "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Default

    async def speculate(
        self,
        input_ids: torch.Tensor,
        past_key_values: Optional[Tuple] = None,
    ) -> Tuple[torch.Tensor, int]:
        """
        Generate speculative tokens using draft model.

        Args:
            input_ids: Current input token IDs
            past_key_values: KV cache from previous generation

        Returns:
            Tuple of (speculative_tokens, num_tokens)
        """
        if not self._enabled:
            return torch.tensor([]), 0

        if self.config.use_ngram:
            return self._ngram_speculate(input_ids)
        else:
            return await self._draft_model_speculate(input_ids, past_key_values)

    def _ngram_speculate(self, input_ids: torch.Tensor) -> Tuple[torch.Tensor, int]:
        """N-gram based speculation using prompt patterns."""
        # Look for matching n-grams in the prompt
        prompt = input_ids.tolist()
        last_n = prompt[-self.config.ngram_prompt_lookup_max:]

        # Find matching patterns in prompt history
        for n in range(len(last_n), 0, -1):
            pattern = last_n[-n:]
            for i in range(len(prompt) - n - self.config.num_speculative_tokens):
                if prompt[i:i+n] == pattern:
                    # Found match, return following tokens
                    speculation = prompt[i+n:i+n+self.config.num_speculative_tokens]
                    return torch.tensor(speculation), len(speculation)

        return torch.tensor([]), 0

    async def _draft_model_speculate(
        self,
        input_ids: torch.Tensor,
        past_key_values: Optional[Tuple],
    ) -> Tuple[torch.Tensor, int]:
        """Draft model based speculation."""
        # Run draft model for num_speculative_tokens steps
        speculative_tokens = []
        current_ids = input_ids

        for _ in range(self.config.num_speculative_tokens):
            # Draft model forward pass (fast)
            # next_token = await self._draft_model.generate_one(current_ids)
            # speculative_tokens.append(next_token)
            # current_ids = torch.cat([current_ids, next_token.unsqueeze(0)], dim=-1)
            pass

        return torch.tensor(speculative_tokens), len(speculative_tokens)

    def record_acceptance(self, proposed: int, accepted: int) -> float:
        """
        Record acceptance rate and potentially disable if too low.

        Args:
            proposed: Number of tokens proposed
            accepted: Number of tokens accepted

        Returns:
            Current acceptance rate
        """
        rate = accepted / max(proposed, 1)
        self._acceptance_history.append(rate)

        # Keep last 100 measurements
        if len(self._acceptance_history) > 100:
            self._acceptance_history.pop(0)

        # Disable if sustained low acceptance
        avg_rate = sum(self._acceptance_history) / len(self._acceptance_history)
        if len(self._acceptance_history) >= 20 and avg_rate < self.config.min_acceptance_rate:
            logger.warning(
                f"Disabling speculation: acceptance rate {avg_rate:.2%} < "
                f"{self.config.min_acceptance_rate:.2%}"
            )
            self._enabled = False

        return rate

    def get_metrics(self) -> dict:
        """Get speculation performance metrics."""
        if not self._acceptance_history:
            return {"enabled": self._enabled, "acceptance_rate": 0.0}

        return {
            "enabled": self._enabled,
            "acceptance_rate": sum(self._acceptance_history) / len(self._acceptance_history),
            "measurements": len(self._acceptance_history),
            "mode": "ngram" if self.config.use_ngram else "draft_model",
            "draft_model": self.config.draft_model,
        }


# Recommended draft model pairings
DRAFT_MODEL_RECOMMENDATIONS = {
    # Main Model → Draft Model (with expected speedup)
    "meta-llama/Llama-2-7b": ("TinyLlama/TinyLlama-1.1B", "1.5x"),
    "meta-llama/Llama-2-13b": ("TinyLlama/TinyLlama-1.1B", "1.7x"),
    "meta-llama/Llama-2-70b": ("meta-llama/Llama-2-7b", "1.8x"),
    "mistralai/Mistral-7B": ("TinyLlama/TinyLlama-1.1B", "1.5x"),
    "Qwen/Qwen2-7B": ("Qwen/Qwen2-0.5B", "1.6x"),
}
```

### vLLM Configuration for Speculative Decoding

```python
# In src/llm_providers/vllm_provider.py

def _create_vllm_instance_with_speculation(self) -> LLM:
    """Create vLLM instance with speculative decoding enabled."""
    return LLM(
        model=self.model_name,
        # Speculative decoding config
        speculative_model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        num_speculative_tokens=5,
        speculative_draft_tensor_parallel_size=1,
        # OR use n-gram speculation (no draft model needed)
        # speculative_model="[ngram]",
        # ngram_prompt_lookup_max=4,

        # Standard config
        tensor_parallel_size=self.tensor_parallel_size,
        gpu_memory_utilization=self.gpu_memory_utilization,
        dtype=self.dtype,
    )
```

---

## 5. Quantization Integration

### Quantization Methods Comparison

| Method | Bits | Speedup | Memory | Accuracy | Best For |
|--------|------|---------|--------|----------|----------|
| **INT8 W+A** | 8 | 1.6x | 50% | 100.2% | Production (recommended) |
| **INT4 Weight** | 4 | 1.3x | 75% | 99.1% | Memory-constrained |
| **GPTQ** | 4 | 1.4x | 75% | 99.3% | GPU deployment |
| **AWQ** | 4 | 1.5x | 75% | 99.5% | Activation-aware |

### LLM Compressor Integration

**File:** `src/llm_interface_pkg/quantization/llm_compressor.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Compressor integration for quantized model inference.

Provides INT8/INT4 quantization with minimal accuracy loss and significant speedup.
Reference: https://developers.redhat.com/articles/2024/08/14/llm-compressor-here-faster-inference-vllm
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class QuantizationType(Enum):
    """Supported quantization types."""
    NONE = "none"
    INT8_WEIGHT_ACTIVATION = "w8a8"  # Recommended: 1.6x speedup
    INT4_WEIGHT_ONLY = "w4"          # Aggressive: 75% memory reduction
    GPTQ = "gptq"                    # GPU-optimized
    AWQ = "awq"                      # Activation-aware


@dataclass
class QuantizationConfig:
    """Configuration for model quantization."""

    quant_type: QuantizationType = QuantizationType.INT8_WEIGHT_ACTIVATION

    # INT8 specific
    smooth_quant_alpha: float = 0.5  # SmoothQuant migration strength

    # INT4 specific (GPTQ/AWQ)
    group_size: int = 128
    desc_act: bool = True  # Descending activation order

    # Calibration
    calibration_samples: int = 512
    calibration_sequence_length: int = 2048


class QuantizedModelLoader:
    """
    Loader for quantized models with automatic format detection.

    Supports loading pre-quantized models from HuggingFace Hub
    or quantizing on-the-fly using LLM Compressor.
    """

    def __init__(self, config: QuantizationConfig):
        """Initialize loader with quantization config."""
        self.config = config

    async def load_or_quantize(
        self,
        model_name: str,
        cache_dir: Optional[str] = None,
    ) -> str:
        """
        Load quantized model or quantize if not available.

        Args:
            model_name: HuggingFace model name
            cache_dir: Directory for cached quantized models

        Returns:
            Path to quantized model
        """
        # Check for pre-quantized version on HuggingFace
        quantized_name = self._find_quantized_variant(model_name)
        if quantized_name:
            logger.info(f"Found pre-quantized model: {quantized_name}")
            return quantized_name

        # Quantize locally
        logger.info(f"Quantizing {model_name} with {self.config.quant_type.value}")
        return await self._quantize_model(model_name, cache_dir)

    def _find_quantized_variant(self, model_name: str) -> Optional[str]:
        """Find pre-quantized variant on HuggingFace."""
        # Common quantized model naming patterns
        quant_suffix = {
            QuantizationType.INT8_WEIGHT_ACTIVATION: "-int8",
            QuantizationType.INT4_WEIGHT_ONLY: "-int4",
            QuantizationType.GPTQ: "-gptq",
            QuantizationType.AWQ: "-awq",
        }

        suffix = quant_suffix.get(self.config.quant_type, "")
        # Check if {model_name}{suffix} exists on HuggingFace
        # Implementation: use huggingface_hub.model_info()
        return None

    async def _quantize_model(
        self,
        model_name: str,
        cache_dir: Optional[str],
    ) -> str:
        """Quantize model using LLM Compressor."""
        # Implementation using llmcompressor library
        # from llmcompressor import compress
        # compressed_model = compress(model_name, ...)
        pass


# Pre-quantized model recommendations
QUANTIZED_MODEL_REGISTRY = {
    # Original → Recommended Quantized Version
    "mistralai/Mistral-7B-Instruct-v0.2": {
        "int8": "neuralmagic/Mistral-7B-Instruct-v0.2-INT8",
        "int4": "TheBloke/Mistral-7B-Instruct-v0.2-GPTQ",
    },
    "meta-llama/Llama-2-7b-chat-hf": {
        "int8": "neuralmagic/Llama-2-7b-chat-hf-INT8",
        "int4": "TheBloke/Llama-2-7B-Chat-GPTQ",
    },
    "meta-llama/Llama-2-13b-chat-hf": {
        "int8": "neuralmagic/Llama-2-13b-chat-hf-INT8",
        "int4": "TheBloke/Llama-2-13B-Chat-GPTQ",
    },
}
```

### Ollama Quantization (Already Supported)

Ollama models already support quantization via GGUF format:

```bash
# Current: mistral:7b-instruct (FP16, ~14GB)
# Optimized options:
ollama pull mistral:7b-instruct-q4_K_M   # 4-bit, ~4GB, slight quality loss
ollama pull mistral:7b-instruct-q8_0     # 8-bit, ~8GB, minimal quality loss
```

**Update `.env` for quantized Ollama models:**

```bash
# Use quantized model for better performance
AUTOBOT_DEFAULT_LLM_MODEL=mistral:7b-instruct-q8_0
```

---

## 6. vLLM Optimization Tuning

### Current vLLM Config Analysis

From `src/llm_providers/vllm_provider.py`:
- `enable_chunked_prefill: True` ✓
- `gpu_memory_utilization: 0.9` ✓

### Recommended Additional Optimizations

```python
# Enhanced vLLM configuration for maximum performance
OPTIMIZED_VLLM_CONFIG = {
    # Multi-step scheduling (2.7x throughput improvement)
    "num_scheduler_steps": 8,  # Run 8 steps before re-scheduling

    # Asynchronous output processing (8.7% latency improvement)
    "enable_async_output_proc": True,

    # Chunked prefill (already enabled)
    "enable_chunked_prefill": True,
    "max_num_batched_tokens": 8192,

    # Prefix caching (2-5x for repeated prompts)
    "enable_prefix_caching": True,

    # Memory optimization
    "gpu_memory_utilization": 0.9,
    "swap_space": 4,  # GB of CPU swap space

    # Speculative decoding
    "speculative_model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "num_speculative_tokens": 5,
}
```

### Updated vLLM Provider

```python
# In src/llm_providers/vllm_provider.py

def _create_vllm_instance(self) -> LLM:
    """Create optimized vLLM instance."""
    return LLM(
        model=self.model_name,
        tensor_parallel_size=self.tensor_parallel_size,
        gpu_memory_utilization=self.gpu_memory_utilization,
        max_model_len=self.max_model_len,
        trust_remote_code=self.trust_remote_code,
        dtype=self.dtype,

        # NEW: Performance optimizations
        enable_chunked_prefill=True,
        enable_prefix_caching=True,
        num_scheduler_steps=8,  # Multi-step scheduling

        # NEW: Speculative decoding (optional)
        # speculative_model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        # num_speculative_tokens=5,
    )
```

---

## 7. KV Cache Optimization

### Why KV Cache Matters

During autoregressive generation, the KV (key-value) cache stores attention states for all previous tokens. For long sequences, this becomes a memory bottleneck.

```
Sequence length: 4096 tokens
Model: 7B parameters, 32 layers, 32 heads
KV Cache size: 4096 × 32 × 32 × 2 × 128 × 2 bytes = ~2GB per request
```

### KV Cache Compression Techniques

| Technique | Memory Reduction | Speed Impact | Implementation |
|-----------|------------------|--------------|----------------|
| **Sliding Window** | 50-75% | Neutral | Config only |
| **H2O (Heavy Hitter)** | 50% | +10% faster | Medium |
| **Grouped Query Attention** | 75% | Neutral | Model-dependent |
| **Quantized KV Cache** | 50% | +5% faster | Low |

### Implementation

```python
# KV Cache optimization configuration
KV_CACHE_CONFIG = {
    # Sliding window attention (Mistral native support)
    "sliding_window": 4096,  # Only keep last 4096 tokens

    # Quantized KV cache (INT8)
    "kv_cache_dtype": "int8",  # vs "float16"

    # Block size for paged attention
    "block_size": 16,
}
```

---

## 8. FlashAttention & FlashInfer

### Why Attention is the Bottleneck

Standard attention has O(n²) memory complexity for sequence length n. For 4096 tokens, this becomes a significant bottleneck both for memory and computation.

### FlashAttention-3 (FA-3)

FlashAttention-3 is a re-engineered attention kernel that provides **1.5-2.0x speedup** over FA-2 on H100 GPUs.

**Key Innovations:**
- **Warp Specialization:** Overlaps compute and data movement
- **TMA (Tensor Memory Accelerator):** Hardware-accelerated memory operations
- **Interleaved matmul/softmax:** Better pipeline utilization
- **Native FP8 support:** Exploits Hopper architecture

| Version | Speedup vs Baseline | Long Context (128k+) | Hardware |
|---------|--------------------|-----------------------|----------|
| FlashAttention-2 | 2-4x | Degraded | Ampere+ |
| **FlashAttention-3** | **3-6x** | **Stable** | Hopper (H100) |

### FlashInfer: Customizable Attention Engine

FlashInfer is the **Best Paper Award winner at MLSys 2025** from UW/NVIDIA researchers. It's now integrated into vLLM and SGLang.

**Performance Improvements:**
- **29-69% inter-token latency reduction** vs compiler backends
- **28-30% latency reduction** for long-context inference
- **13-17% speedup** for parallel generation
- **1.6-3.7x bandwidth utilization** with fused RoPE kernels

**Key Features:**
- Block-sparse KV-cache format reduces memory fragmentation
- JIT compilation for customizable attention patterns
- CUDAGraph and torch.compile compatible
- Works with AMD GPUs via ROCm

### Implementation for AutoBot

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FlashInfer integration for optimized attention computation.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FlashAttentionConfig:
    """Configuration for FlashAttention/FlashInfer."""

    # Backend selection
    backend: str = "flashinfer"  # "flashinfer", "flash_attn", "xformers"

    # FlashInfer specific
    use_cuda_graph: bool = True
    enable_jit: bool = True

    # Memory optimization
    page_size: int = 16  # KV cache page size
    use_block_sparse: bool = True

    # FP8 (H100 only)
    use_fp8_attention: bool = False


def get_optimal_attention_backend() -> str:
    """
    Auto-detect best attention backend for current hardware.

    Returns:
        Backend name: "flashinfer", "flash_attn", or "xformers"
    """
    import torch

    if not torch.cuda.is_available():
        return "xformers"  # CPU fallback

    # Check for Hopper (H100) - supports FA-3
    capability = torch.cuda.get_device_capability()
    if capability >= (9, 0):
        return "flashinfer"  # Best for H100

    # Ampere (A100) - FA-2
    if capability >= (8, 0):
        return "flash_attn"

    return "xformers"  # Older GPUs
```

### vLLM Integration

```python
# In src/llm_providers/vllm_provider.py

def _create_vllm_instance_with_flashinfer(self) -> LLM:
    """Create vLLM instance with FlashInfer backend."""
    return LLM(
        model=self.model_name,
        # Use FlashInfer for attention
        attention_backend="FLASHINFER",

        # Enable CUDAGraph for lower latency
        enforce_eager=False,  # Allow CUDAGraph capture

        # Standard config
        tensor_parallel_size=self.tensor_parallel_size,
        gpu_memory_utilization=self.gpu_memory_utilization,
    )
```

---

## 9. Continuous Batching

### The Problem with Static Batching

Traditional static batching waits for all sequences in a batch to complete before processing new requests. This wastes GPU cycles when sequences have different lengths.

```text
Static Batching (inefficient):
┌─────────────────────────────────────────────────┐
│ Request A: ████████████                         │ (done at step 12)
│ Request B: ████████████████████████████████████ │ (done at step 36)
│ Request C: ████████████████                     │ (done at step 16)
│                          ↑                      │
│                    GPU idle waiting for B       │
└─────────────────────────────────────────────────┘

Continuous Batching (efficient):
┌─────────────────────────────────────────────────┐
│ Request A: ████████████                         │
│ Request D: ─────────────████████████            │ (fills A's slot)
│ Request B: ████████████████████████████████████ │
│ Request C: ████████████████                     │
│ Request E: ──────────────────██████████████████ │ (fills C's slot)
└─────────────────────────────────────────────────┘
```

### Performance Impact

| Metric | Static Batching | Continuous Batching | Improvement |
|--------|-----------------|---------------------|-------------|
| Throughput | 1x baseline | **23x** (vLLM) | 23x |
| Queue delay | 100-500ms | **5-50ms** | 50-70% reduction |
| GPU utilization | 30-50% | **85-95%** | 2x |

### How It Works

Continuous batching (iteration-level scheduling) allows:
1. New requests join immediately when capacity exists
2. Completed sequences release slots instantly
3. Prefill and decode phases scheduled separately

### vLLM Already Implements This

vLLM's scheduler uses continuous batching by default. Key configuration:

```python
# In src/llm_providers/vllm_provider.py

CONTINUOUS_BATCHING_CONFIG = {
    # Maximum batch size (limited by GPU memory)
    "max_num_seqs": 256,

    # Maximum tokens per iteration
    "max_num_batched_tokens": 8192,

    # Scheduling policy
    "scheduling_policy": "fcfs",  # First-come-first-served

    # Preemption mode for memory pressure
    "preemption_mode": "swap",  # or "recompute"
}
```

### Optimizing for AutoBot's Workload

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Continuous batching configuration for AutoBot workloads.
"""


def get_batching_config(workload_type: str) -> dict:
    """
    Get optimal batching config for workload type.

    Args:
        workload_type: "interactive", "batch", or "mixed"

    Returns:
        vLLM batching configuration
    """
    configs = {
        # Low latency for chat/interactive use
        "interactive": {
            "max_num_seqs": 64,
            "max_num_batched_tokens": 4096,
            "scheduling_policy": "fcfs",
            "max_waiting_time_ms": 10,  # Prioritize latency
        },
        # High throughput for batch processing
        "batch": {
            "max_num_seqs": 256,
            "max_num_batched_tokens": 16384,
            "scheduling_policy": "fcfs",
            "max_waiting_time_ms": 100,  # Allow batching
        },
        # Balanced for mixed workloads
        "mixed": {
            "max_num_seqs": 128,
            "max_num_batched_tokens": 8192,
            "scheduling_policy": "fcfs",
            "max_waiting_time_ms": 50,
        },
    }
    return configs.get(workload_type, configs["mixed"])
```

---

## 10. Medusa Heads (Multi-Head Decoding)

### Concept

Medusa adds **extra decoding heads** to predict multiple future tokens in parallel, achieving **2-3.6x speedup** without changing the base model.

```text
Standard Autoregressive:
┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐
│ Head  │ → │ Head  │ → │ Head  │ → │ Head  │
│  +1   │   │  +1   │   │  +1   │   │  +1   │
└───────┘   └───────┘   └───────┘   └───────┘
 Pass 1      Pass 2      Pass 3      Pass 4

Medusa Multi-Head:
┌─────────────────────────────────────────────┐
│              Single Forward Pass            │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐   │
│  │Head +1│ │Head +2│ │Head +3│ │Head +4│   │
│  └───────┘ └───────┘ └───────┘ └───────┘   │
│       ↓        ↓        ↓        ↓         │
│   Token 1  Token 2  Token 3  Token 4       │
│       (verify with tree attention)         │
└─────────────────────────────────────────────┘
```

### Performance

| Variant | Speedup | Training Required | Quality Impact |
|---------|---------|-------------------|----------------|
| Medusa-1 | 2.2x | Heads only (frozen base) | Lossless |
| Medusa-2 | 2.3-3.6x | Heads + base model | Minimal |

**Key stats:**
- Top-1 accuracy: ~60% for next token prediction
- Top-5 accuracy: >80%
- Training: Single A100-80G, few hours to 1 day
- A 33B model with Medusa performs like a 13B without it

### Architecture

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Medusa multi-head decoding implementation.

Reference: https://arxiv.org/abs/2401.10774
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


@dataclass
class MedusaConfig:
    """Configuration for Medusa heads."""

    num_heads: int = 5  # 5 heads recommended, 3-4 may suffice
    hidden_size: int = 4096  # Match base model
    vocab_size: int = 32000

    # Tree attention settings
    tree_candidates: int = 64  # Candidate sequences per step
    max_steps: int = 512

    # Acceptance threshold
    typical_acceptance_threshold: float = 0.3


class MedusaHead(nn.Module):
    """Single Medusa prediction head."""

    def __init__(self, hidden_size: int, vocab_size: int):
        """
        Initialize Medusa head.

        Args:
            hidden_size: Hidden dimension of base model
            vocab_size: Vocabulary size
        """
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.SiLU(),
            nn.Linear(hidden_size, vocab_size),
        )
        # Residual connection
        self.residual = nn.Linear(hidden_size, vocab_size, bias=False)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Forward pass with residual connection."""
        return self.head(hidden_states) + self.residual(hidden_states)


class MedusaDecoder:
    """
    Medusa multi-head decoder for accelerated generation.

    Adds lightweight heads to predict multiple tokens simultaneously,
    then verifies with tree attention.
    """

    def __init__(self, config: MedusaConfig):
        """Initialize Medusa decoder."""
        self.config = config
        self.heads: List[MedusaHead] = []
        self._initialized = False

    def load_heads(self, checkpoint_path: str) -> bool:
        """
        Load pre-trained Medusa heads.

        Args:
            checkpoint_path: Path to Medusa heads checkpoint

        Returns:
            True if loaded successfully
        """
        try:
            checkpoint = torch.load(checkpoint_path, weights_only=True)
            self.heads = []
            for i in range(self.config.num_heads):
                head = MedusaHead(
                    self.config.hidden_size,
                    self.config.vocab_size,
                )
                head.load_state_dict(checkpoint[f"head_{i}"])
                self.heads.append(head)

            self._initialized = True
            logger.info(f"Loaded {len(self.heads)} Medusa heads")
            return True

        except Exception as e:
            logger.warning(f"Failed to load Medusa heads: {e}")
            return False

    def generate_candidates(
        self,
        hidden_states: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Generate candidate token sequences using Medusa heads.

        Args:
            hidden_states: Last hidden state from base model

        Returns:
            Tuple of (candidate_tokens, candidate_probs)
        """
        if not self._initialized:
            raise RuntimeError("Medusa heads not initialized")

        # Get predictions from each head
        predictions = []
        for head in self.heads:
            logits = head(hidden_states)
            probs = torch.softmax(logits, dim=-1)
            # Get top-k candidates per head
            top_probs, top_tokens = probs.topk(10, dim=-1)
            predictions.append((top_tokens, top_probs))

        # Build candidate tree (simplified)
        # Full implementation uses tree attention mask
        return self._build_candidate_tree(predictions)

    def _build_candidate_tree(
        self,
        predictions: List[Tuple[torch.Tensor, torch.Tensor]],
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Build candidate sequences from head predictions."""
        # Simplified: return top predictions from each head
        all_tokens = torch.stack([p[0][:, 0] for p in predictions], dim=1)
        all_probs = torch.stack([p[1][:, 0] for p in predictions], dim=1)
        return all_tokens, all_probs

    def verify_and_accept(
        self,
        candidates: torch.Tensor,
        target_probs: torch.Tensor,
    ) -> Tuple[torch.Tensor, int]:
        """
        Verify candidates against target model and accept valid tokens.

        Uses typical acceptance scheme for quality guarantee.

        Args:
            candidates: Candidate token sequences
            target_probs: Probabilities from target model

        Returns:
            Tuple of (accepted_tokens, num_accepted)
        """
        # Typical acceptance: accept if prob > threshold
        threshold = self.config.typical_acceptance_threshold
        accepted_mask = target_probs > threshold

        # Find longest accepted prefix
        num_accepted = 0
        for i in range(candidates.shape[1]):
            if accepted_mask[0, i]:
                num_accepted = i + 1
            else:
                break

        return candidates[:, :num_accepted], num_accepted


# Pre-trained Medusa head checkpoints
MEDUSA_CHECKPOINTS = {
    "vicuna-7b": "FasterDecoding/medusa-vicuna-7b-v1.3",
    "vicuna-13b": "FasterDecoding/medusa-vicuna-13b-v1.3",
    "vicuna-33b": "FasterDecoding/medusa-vicuna-33b-v1.3",
    "llama-2-7b": "FasterDecoding/medusa-llama-2-7b",
}
```

### Medusa vs Speculative Decoding

| Aspect | Medusa | Speculative Decoding |
|--------|--------|---------------------|
| Extra model needed | No | Yes (draft model) |
| Training required | Yes (heads only) | No |
| Memory overhead | ~5% | +30-50% |
| Speedup | 2-3.6x | 1.5-2.8x |
| Best for | Known model distribution | Any model |

**Recommendation:** Use Medusa when fine-tuned heads are available; use speculative decoding for flexibility.

---

## 11. CUDA Graphs

### The Problem: Kernel Launch Overhead

Each CUDA kernel launch has ~5-10μs overhead. For a single token generation with hundreds of kernels, this adds up to significant latency.

```text
Without CUDA Graphs:
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│ K1 │→│ K2 │→│ K3 │→│ K4 │→│ K5 │  (5 launches = 50μs overhead)
└────┘ └────┘ └────┘ └────┘ └────┘

With CUDA Graphs:
┌─────────────────────────────────┐
│   Pre-recorded Graph            │  (1 launch = 10μs overhead)
│   K1 → K2 → K3 → K4 → K5        │
└─────────────────────────────────┘
```

### Performance Impact

| Metric | Without CUDA Graphs | With CUDA Graphs | Improvement |
|--------|--------------------|--------------------|-------------|
| Kernel overhead | 50-100μs/token | 5-10μs/token | **10x** |
| First token | No impact | +10-20ms warmup | Trade-off |
| Decode latency | Baseline | **-15-25%** | Significant |

### Implementation

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CUDA Graph optimization for LLM inference.
"""

import logging
from typing import Callable, Dict, Optional

import torch

logger = logging.getLogger(__name__)


class CUDAGraphManager:
    """
    Manager for CUDA graph capture and replay.

    Captures model forward pass as a graph for efficient replay
    during decode phase.
    """

    def __init__(self, warmup_steps: int = 3):
        """
        Initialize CUDA graph manager.

        Args:
            warmup_steps: Number of warmup iterations before capture
        """
        self.warmup_steps = warmup_steps
        self._graphs: Dict[str, torch.cuda.CUDAGraph] = {}
        self._static_inputs: Dict[str, torch.Tensor] = {}
        self._static_outputs: Dict[str, torch.Tensor] = {}

    def capture(
        self,
        key: str,
        forward_fn: Callable,
        input_tensor: torch.Tensor,
    ) -> torch.Tensor:
        """
        Capture forward pass as CUDA graph.

        Args:
            key: Unique identifier for this graph
            forward_fn: Function to capture
            input_tensor: Input tensor (shape must be static)

        Returns:
            Output tensor (from graph replay)
        """
        if key in self._graphs:
            # Replay existing graph
            self._static_inputs[key].copy_(input_tensor)
            self._graphs[key].replay()
            return self._static_outputs[key].clone()

        # Warmup phase
        for _ in range(self.warmup_steps):
            output = forward_fn(input_tensor)
        torch.cuda.synchronize()

        # Create static tensors
        self._static_inputs[key] = input_tensor.clone()
        self._static_outputs[key] = torch.empty_like(output)

        # Capture graph
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            self._static_outputs[key] = forward_fn(self._static_inputs[key])

        self._graphs[key] = graph
        logger.info(f"Captured CUDA graph: {key}")

        return self._static_outputs[key].clone()

    def clear(self, key: Optional[str] = None):
        """Clear captured graphs."""
        if key:
            self._graphs.pop(key, None)
            self._static_inputs.pop(key, None)
            self._static_outputs.pop(key, None)
        else:
            self._graphs.clear()
            self._static_inputs.clear()
            self._static_outputs.clear()


# vLLM CUDA Graph configuration
CUDA_GRAPH_CONFIG = {
    # Batch sizes to capture graphs for
    "cuda_graph_batch_sizes": [1, 2, 4, 8, 16, 32],

    # Maximum sequence length for graph capture
    "max_seq_len_to_capture": 8192,

    # Memory pool for graph allocation
    "cuda_graph_memory_pool": None,  # Auto-allocate
}
```

### vLLM Integration

vLLM supports CUDA graphs via `enforce_eager=False`:

```python
# In src/llm_providers/vllm_provider.py

def _create_vllm_instance_with_cuda_graph(self) -> LLM:
    """Create vLLM with CUDA graph optimization."""
    return LLM(
        model=self.model_name,
        # Enable CUDA graphs (default)
        enforce_eager=False,

        # Pre-capture graphs for common batch sizes
        # This adds ~10-20s startup time but improves decode latency
        max_seq_len_to_capture=8192,

        # Standard config
        tensor_parallel_size=self.tensor_parallel_size,
        gpu_memory_utilization=self.gpu_memory_utilization,
    )
```

---

## 12. Prompt Compression & Token Reduction

### Why Prompt Length Matters

Longer prompts = higher latency (O(n²) attention) and more memory. Reducing prompt tokens directly improves performance.

```text
Prompt: 2048 tokens → TTFT: 200ms, Memory: 1GB KV cache
Prompt: 512 tokens  → TTFT: 50ms,  Memory: 250MB KV cache
                       4x faster,  4x less memory
```

### Techniques

| Technique | Token Reduction | Quality Impact | Implementation |
|-----------|-----------------|----------------|----------------|
| **System prompt compression** | 30-50% | Minimal | Prompt engineering |
| **Dynamic context loading** | 50-70% | Depends on selection | RAG optimization |
| **Prefix caching** | 0% (reuse) | None | vLLM built-in |
| **LLMLingua compression** | 50-80% | ~2-5% | Model-based |

### Implementation

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt compression utilities for latency optimization.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """Result of prompt compression."""

    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    compressed_text: str


class PromptCompressor:
    """
    Compress prompts to reduce token count while preserving meaning.

    Implements multiple compression strategies:
    1. Rule-based: Remove filler words, redundancy
    2. Selective: Keep only most relevant context
    3. Model-based: Use compression model (LLMLingua)
    """

    def __init__(self, tokenizer=None):
        """Initialize compressor with tokenizer for token counting."""
        self._tokenizer = tokenizer

    def compress_system_prompt(self, prompt: str) -> CompressionResult:
        """
        Compress system prompt using rule-based techniques.

        Args:
            prompt: Original system prompt

        Returns:
            CompressionResult with compressed prompt
        """
        original_tokens = self._count_tokens(prompt)

        # Rule-based compression
        compressed = prompt

        # Remove excessive whitespace
        import re
        compressed = re.sub(r'\s+', ' ', compressed)

        # Remove filler phrases
        filler_phrases = [
            "Please note that",
            "It is important to",
            "Keep in mind that",
            "Remember that",
            "As you know,",
            "In other words,",
        ]
        for phrase in filler_phrases:
            compressed = compressed.replace(phrase, "")

        # Compress common instructions
        replacements = {
            "You are a helpful assistant": "Assistant",
            "Please provide": "Provide",
            "Make sure to": "Ensure",
            "In order to": "To",
        }
        for old, new in replacements.items():
            compressed = compressed.replace(old, new)

        compressed_tokens = self._count_tokens(compressed)

        return CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
            compressed_text=compressed.strip(),
        )

    def select_relevant_context(
        self,
        query: str,
        contexts: List[str],
        max_contexts: int = 3,
    ) -> List[str]:
        """
        Select most relevant context chunks for query.

        For RAG systems: Instead of including all retrieved documents,
        select only the most relevant ones.

        Args:
            query: User query
            contexts: Retrieved context chunks
            max_contexts: Maximum contexts to include

        Returns:
            List of most relevant contexts
        """
        if len(contexts) <= max_contexts:
            return contexts

        # Simple relevance scoring (word overlap)
        # Production: Use embedding similarity
        query_words = set(query.lower().split())

        scored_contexts = []
        for ctx in contexts:
            ctx_words = set(ctx.lower().split())
            overlap = len(query_words & ctx_words)
            scored_contexts.append((overlap, ctx))

        # Sort by relevance and take top N
        scored_contexts.sort(reverse=True, key=lambda x: x[0])
        return [ctx for _, ctx in scored_contexts[:max_contexts]]

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        # Rough estimate: ~4 chars per token
        return len(text) // 4


# Optimized system prompts for AutoBot
COMPRESSED_SYSTEM_PROMPTS = {
    "default": "Assistant for code analysis and automation. Be concise.",

    "code_review": "Code reviewer. Focus: bugs, security, performance. Be specific.",

    "documentation": "Doc writer. Style: clear, technical. Include examples.",

    "automation": "Automation assistant. Generate working code. Handle errors.",
}
```

### Prefix Caching Integration

AutoBot can leverage vLLM's prefix caching for repeated system prompts:

```python
# In src/llm_interface_pkg/cache.py

class PrefixCacheManager:
    """Manage prefix caching for common prompts."""

    # Common prefixes to cache
    CACHED_PREFIXES = [
        # System prompts
        "You are AutoBot, an AI assistant...",
        # RAG prefixes
        "Based on the following context:\n",
        # Code analysis prefixes
        "Analyze the following code:\n```",
    ]

    @staticmethod
    def get_prefix_cache_config() -> dict:
        """Get vLLM prefix caching configuration."""
        return {
            "enable_prefix_caching": True,
            # Prefix cache will automatically cache common prefixes
            # This provides 60-80% TTFT reduction for repeated prompts
        }
```

### Expected Impact

| Optimization | TTFT Reduction | Use Case |
|--------------|----------------|----------|
| System prompt compression | 10-30% | All requests |
| Dynamic context selection | 30-50% | RAG queries |
| Prefix caching | 60-80% | Repeated prompts |

---

## 13. Implementation Plan

### Phase 1: Quick Wins (1-2 days)

**No code changes required - configuration only**

- [ ] Update Ollama default model to quantized variant
- [ ] Enable prefix caching in vLLM config
- [ ] Add multi-step scheduling to vLLM
- [ ] Benchmark baseline vs optimized

**Expected improvement:** 20-30% latency reduction

### Phase 2: Speculative Decoding (1 week)

- [ ] Create `src/llm_interface_pkg/speculative/` package
- [ ] Implement `SpeculativeDecoder` class
- [ ] Add draft model configuration to SSOT
- [ ] Integrate with vLLM provider
- [ ] Add acceptance rate monitoring
- [ ] Benchmark with different draft models

**Expected improvement:** 1.5-2x latency reduction

### Phase 3: Quantization Integration (1 week)

- [ ] Create `src/llm_interface_pkg/quantization/` package
- [ ] Implement `QuantizedModelLoader`
- [ ] Add INT8 model registry
- [ ] Test accuracy vs baseline
- [ ] Update Ollama to use quantized models
- [ ] Document quantization options

**Expected improvement:** 1.6x speedup + 50% memory reduction

### Phase 4: Advanced Optimizations (2 weeks)

- [ ] Implement KV cache compression
- [ ] Add custom CUDA kernels for common operations
- [ ] Explore tensor parallelism for multi-GPU
- [ ] Profile and optimize hot paths
- [ ] Create performance dashboard

**Expected improvement:** Additional 10-20% gains

---

## 14. Integration Points

### 14.1 Configuration (SSOT)

Add to `.env`:

```bash
# LLM Inference Optimization Configuration

# Speculative Decoding
AUTOBOT_SPECULATION_ENABLED=true
AUTOBOT_SPECULATION_DRAFT_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
AUTOBOT_SPECULATION_NUM_TOKENS=5
AUTOBOT_SPECULATION_USE_NGRAM=false

# Quantization
AUTOBOT_QUANTIZATION_TYPE=int8  # none, int8, int4, gptq, awq
AUTOBOT_USE_QUANTIZED_MODELS=true

# vLLM Optimizations
AUTOBOT_VLLM_MULTI_STEP=8
AUTOBOT_VLLM_PREFIX_CACHING=true
AUTOBOT_VLLM_ASYNC_OUTPUT=true

# KV Cache
AUTOBOT_KV_CACHE_DTYPE=int8
AUTOBOT_KV_SLIDING_WINDOW=4096
```

### 14.2 Provider Registration

Update `src/llm_interface_pkg/interface.py`:

```python
# In LLMInterface.__init__()

# Load optimization configs
self._speculation_enabled = config.get("speculation.enabled", False)
self._quantization_type = config.get("quantization.type", "none")

# Initialize speculative decoder if enabled
if self._speculation_enabled:
    from .speculative.speculative_decoder import SpeculativeDecoder, SpeculativeConfig
    spec_config = SpeculativeConfig(
        draft_model=config.get("speculation.draft_model"),
        num_speculative_tokens=config.get("speculation.num_tokens", 5),
        use_ngram=config.get("speculation.use_ngram", False),
    )
    self._speculative_decoder = SpeculativeDecoder(spec_config)
```

### 14.3 Metrics Integration

Add Prometheus metrics for optimization monitoring:

```python
# New metrics for inference optimization
OPTIMIZATION_METRICS = {
    "autobot_speculation_acceptance_rate": Gauge,
    "autobot_speculation_tokens_proposed": Counter,
    "autobot_speculation_tokens_accepted": Counter,
    "autobot_quantization_speedup_ratio": Gauge,
    "autobot_kv_cache_memory_mb": Gauge,
    "autobot_prefix_cache_hit_rate": Gauge,
}
```

---

## 15. References

### Research Papers & Blogs

- [vLLM v0.6.0: 2.7x Throughput, 5x Latency Reduction](https://blog.vllm.ai/2024/09/05/perf-update.html)
- [Speculative Decoding in vLLM: Up to 2.8x Speedup](https://blog.vllm.ai/2024/10/17/spec-decode.html)
- [LLM Compressor: 1.6x Speedup with INT8](https://developers.redhat.com/articles/2024/08/14/llm-compressor-here-faster-inference-vllm)
- [3x Faster with Right Draft Model](https://www.bentoml.com/blog/3x-faster-llm-inference-with-speculative-decoding)
- [vLLM Speculative Decoding Docs](https://docs.vllm.ai/en/latest/features/spec_decode/)
- [NVIDIA Post-Training Quantization](https://developer.nvidia.com/blog/optimizing-llms-for-performance-and-accuracy-with-post-training-quantization/)
- [FlashInfer: Efficient Attention Engine (MLSys 2025 Best Paper)](https://arxiv.org/abs/2501.01005)
- [Continuous Batching: 23x LLM Throughput](https://www.anyscale.com/blog/continuous-batching-llm-inference)
- [Medusa: Multi-Head Decoding for 2-3.6x Speedup](https://arxiv.org/abs/2401.10774)
- [The New LLM Inference Stack 2025: FA-3, FP8 & FP4](https://www.stixor.com/blogs/new-inference-stack-2025)
- [NVIDIA FlashInfer Integration](https://developer.nvidia.com/blog/run-high-performance-llm-inference-kernels-from-nvidia-using-flashinfer/)
- [Latency Optimization Techniques for Real-Time LLM Inference](https://mljourney.com/latency-optimization-techniques-for-real-time-llm-inference/)

### AutoBot Integration Files

- LLM Interface: `src/llm_interface_pkg/interface.py`
- vLLM Provider: `src/llm_providers/vllm_provider.py`
- Ollama Provider: `src/llm_interface_pkg/providers/ollama.py`
- Response Cache: `src/llm_interface_pkg/cache.py`
- Performance Monitor: `src/utils/performance_monitoring/monitor.py`

---

## 16. Cloud Model Integration

### Provider-Based Optimization Routing

AutoBot supports both **local models** (Ollama, vLLM) and **cloud models** (Claude, OpenAI, etc.). Most optimizations in this document are **local-only** - they operate on GPU kernels and model weights that only exist locally.

### Optimization Applicability Matrix

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPTIMIZATION APPLICABILITY BY PROVIDER                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LOCAL MODELS ONLY (Ollama, vLLM)     │  BOTH LOCAL & CLOUD                │
│  ─────────────────────────────────────│──────────────────────────────────  │
│  ✓ Speculative Decoding               │  ✓ Response Caching (L1/L2)        │
│  ✓ FlashAttention / FlashInfer        │  ✓ Prompt Compression              │
│  ✓ CUDA Graphs                        │  ✓ Request Batching                │
│  ✓ Medusa Heads                       │  ✓ Connection Pooling              │
│  ✓ Quantization (INT8/INT4)           │  ✓ Retry Logic                     │
│  ✓ KV Cache Optimization              │  ✓ Rate Limit Handling             │
│  ✓ Continuous Batching (GPU-level)    │  ✓ Request Deduplication           │
│  ✓ Prefix Caching (KV cache)          │                                    │
│                                       │                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How AutoBot Routes Optimization

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider-aware optimization router.

Automatically applies appropriate optimizations based on provider type.
"""

from enum import Enum
from typing import Dict, Any


class ProviderType(Enum):
    """LLM provider categories."""
    LOCAL_VLLM = "vllm"           # GPU-based local inference
    LOCAL_OLLAMA = "ollama"       # Local inference via Ollama
    CLOUD_OPENAI = "openai"       # OpenAI API
    CLOUD_ANTHROPIC = "anthropic" # Claude API
    CLOUD_OTHER = "cloud"         # Generic cloud provider


class OptimizationRouter:
    """
    Route optimization strategies based on provider type.

    Local providers get GPU-level optimizations (speculative decoding,
    FlashInfer, quantization). Cloud providers get API-level optimizations
    (caching, batching, connection pooling).
    """

    LOCAL_OPTIMIZATIONS = {
        "speculative_decoding": True,
        "flash_attention": True,
        "cuda_graphs": True,
        "medusa_heads": True,
        "quantization": True,
        "kv_cache_optimization": True,
        "continuous_batching": True,
        "prefix_caching": True,
    }

    CLOUD_OPTIMIZATIONS = {
        "response_caching": True,      # L1/L2 cache
        "prompt_compression": True,    # Reduce token count = cost savings
        "request_batching": True,      # Batch API calls
        "connection_pooling": True,    # Reuse HTTP connections
        "retry_with_backoff": True,    # Handle rate limits
        "request_deduplication": True, # Avoid duplicate API calls
    }

    UNIVERSAL_OPTIMIZATIONS = {
        "response_caching": True,
        "prompt_compression": True,
        "request_deduplication": True,
    }

    @classmethod
    def get_optimizations(cls, provider_type: ProviderType) -> Dict[str, bool]:
        """
        Get applicable optimizations for provider type.

        Args:
            provider_type: The LLM provider being used

        Returns:
            Dict of optimization flags
        """
        if provider_type in (ProviderType.LOCAL_VLLM, ProviderType.LOCAL_OLLAMA):
            return {**cls.LOCAL_OPTIMIZATIONS, **cls.UNIVERSAL_OPTIMIZATIONS}
        else:
            return {**cls.CLOUD_OPTIMIZATIONS, **cls.UNIVERSAL_OPTIMIZATIONS}

    @classmethod
    def should_apply(cls, optimization: str, provider_type: ProviderType) -> bool:
        """Check if specific optimization applies to provider."""
        opts = cls.get_optimizations(provider_type)
        return opts.get(optimization, False)
```

### Cloud-Specific Optimizations

#### 1. Response Caching (Already Implemented)

The existing L1/L2 cache in `src/llm_interface_pkg/cache.py` works for **both** local and cloud models:

```text
Request → Cache Check → Hit? → Return cached response (skip API call)
              ↓
            Miss → Call API → Cache response → Return
```

**Cloud benefit:** Avoids expensive API calls for repeated queries.

#### 2. Prompt Compression (Token Cost Reduction)

For cloud models, prompt compression directly translates to **cost savings**:

```text
Cloud Pricing: $0.015 per 1K input tokens (Claude)

Original prompt: 2000 tokens → $0.03 per request
Compressed:      1000 tokens → $0.015 per request
                               50% cost reduction
```

#### 3. Request Batching (API-Level)

Unlike GPU continuous batching, cloud batching aggregates **multiple user requests** into optimized API calls:

```python
class CloudRequestBatcher:
    """
    Batch multiple requests to cloud providers for efficiency.

    Aggregates requests within a time window, then sends batch API calls
    where supported (OpenAI Batch API, etc.).
    """

    def __init__(
        self,
        batch_window_ms: int = 50,
        max_batch_size: int = 10,
    ):
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size
        self._pending_requests = []

    async def add_request(self, request: "LLMRequest") -> "LLMResponse":
        """Add request to batch queue."""
        # Implementation aggregates requests and sends when:
        # 1. batch_window_ms expires, OR
        # 2. max_batch_size reached
        pass
```

#### 4. Connection Pooling

Reduces HTTP connection overhead for cloud APIs:

```python
import httpx

# Shared connection pool for cloud providers
_http_client = httpx.AsyncClient(
    http2=True,                    # HTTP/2 multiplexing
    limits=httpx.Limits(
        max_connections=100,       # Connection pool size
        max_keepalive_connections=20,
    ),
    timeout=httpx.Timeout(30.0),
)
```

#### 5. Rate Limit Handling

Cloud APIs have rate limits that require intelligent handling:

```python
class RateLimitHandler:
    """Handle cloud API rate limits with exponential backoff."""

    async def execute_with_retry(
        self,
        api_call: Callable,
        max_retries: int = 3,
    ) -> Any:
        """Execute API call with automatic retry on rate limit."""
        for attempt in range(max_retries):
            try:
                return await api_call()
            except RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
```

### Integration with LLMInterface

The `LLMInterface` automatically applies provider-appropriate optimizations:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM REQUEST FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User Request                                                               │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────┐                                                            │
│  │ L1/L2 Cache │ ◄──── Universal (local + cloud)                            │
│  │   Check     │                                                            │
│  └─────────────┘                                                            │
│       │ miss                                                                │
│       ▼                                                                     │
│  ┌─────────────┐                                                            │
│  │   Prompt    │ ◄──── Universal (local saves compute, cloud saves cost)    │
│  │ Compression │                                                            │
│  └─────────────┘                                                            │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────┐     ┌───────────────────────────────────────────────────┐  │
│  │  Provider   │────►│ LOCAL (Ollama/vLLM)?                              │  │
│  │   Router    │     │   → Speculative Decoding                          │  │
│  └─────────────┘     │   → FlashInfer / CUDA Graphs                      │  │
│       │              │   → Quantization / KV Cache                       │  │
│       │              │   → Continuous Batching                           │  │
│       │              └───────────────────────────────────────────────────┘  │
│       │                                                                     │
│       │              ┌───────────────────────────────────────────────────┐  │
│       └─────────────►│ CLOUD (Claude/OpenAI)?                            │  │
│                      │   → Connection Pooling                            │  │
│                      │   → Request Batching (API-level)                  │  │
│                      │   → Rate Limit Handling                           │  │
│                      │   → Retry with Backoff                            │  │
│                      └───────────────────────────────────────────────────┘  │
│                                                                             │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────┐                                                            │
│  │   Response  │ ◄──── Universal (cache for future use)                     │
│  │   Caching   │                                                            │
│  └─────────────┘                                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Performance Impact by Provider Type

| Provider | Optimization Focus | Latency Improvement | Cost Impact |
|----------|-------------------|---------------------|-------------|
| **Ollama** | Quantization, Prefix Caching | 40-60% | N/A (local) |
| **vLLM** | FlashInfer, Speculative, CUDA Graphs | 60-80% | N/A (local) |
| **Claude API** | Caching, Prompt Compression | 0-95%* | 30-50% savings |
| **OpenAI API** | Caching, Batching, Compression | 0-95%* | 30-50% savings |

*Cache hit = 95%+ latency reduction (no API call needed)

### Configuration

```bash
# In .env - Cloud-specific settings

# Cloud Request Optimization
AUTOBOT_CLOUD_CONNECTION_POOL_SIZE=100
AUTOBOT_CLOUD_BATCH_WINDOW_MS=50
AUTOBOT_CLOUD_MAX_BATCH_SIZE=10
AUTOBOT_CLOUD_RETRY_MAX_ATTEMPTS=3

# Prompt Compression (applies to both local and cloud)
AUTOBOT_PROMPT_COMPRESSION_ENABLED=true
AUTOBOT_PROMPT_COMPRESSION_RATIO=0.7  # Target 70% of original length

# Response Caching (applies to both local and cloud)
AUTOBOT_CACHE_L1_SIZE=100
AUTOBOT_CACHE_L2_TTL=300  # 5 minutes for cloud responses
```

### Key Takeaways

1. **GPU optimizations (speculative, FlashInfer, quantization) are local-only** - they require access to model weights and GPU kernels

2. **Caching and compression work for everyone** - these reduce work regardless of where inference happens

3. **Cloud APIs have different bottlenecks** - network latency, rate limits, and per-token costs rather than GPU compute

4. **AutoBot automatically routes optimizations** - the optimization router applies appropriate strategies based on detected provider type

---

## Summary: Expected Outcomes

| Optimization | Latency Impact | Memory Impact | Complexity |
|--------------|----------------|---------------|------------|
| vLLM Config Tuning | -30% | Same | Low |
| FlashInfer/FA-3 | -30-69% ITL | Same | Low |
| Continuous Batching | -50-70% queue | Same | Built-in |
| Speculative Decoding | -50% (1.5-2x) | +10% | Medium |
| Medusa Heads | -60% (2-3.6x) | +5% | Medium |
| CUDA Graphs | -15-25% decode | Same | Low |
| INT8 Quantization | -40% (1.6x) | -50% | Low |
| Prompt Compression | -10-30% TTFT | Same | Low |
| **All Combined** | **-80% (3-5x)** | **-40%** | High |

**Updated target with new optimizations:**

- Current: 500ms first token, 12GB memory
- **New Target: 100-170ms first token, 6GB memory**

### Optimization Priority Matrix

| Priority | Technique | ROI | Implementation |
|----------|-----------|-----|----------------|
| 1 | vLLM config + FlashInfer | High | Config only |
| 2 | Quantization (INT8/Q8) | High | Model swap |
| 3 | Speculative Decoding | High | Medium effort |
| 4 | CUDA Graphs | Medium | Built-in |
| 5 | Medusa Heads | High | Training needed |
| 6 | Prompt Compression | Medium | Code changes |
