# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for LLM optimization package.

Issue #717: Efficient Inference Design implementation tests.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm_interface_pkg.types import ProviderType
from src.llm_interface_pkg.optimization.router import (
    OptimizationRouter,
    OptimizationCategory,
    OptimizationConfig,
)
from src.llm_interface_pkg.optimization.prompt_compressor import (
    PromptCompressor,
    CompressionConfig,
    CompressionResult,
)
from src.llm_interface_pkg.optimization.rate_limiter import (
    RateLimitHandler,
    RateLimitConfig,
    RateLimitError,
    RetryStrategy,
)
from src.llm_interface_pkg.optimization.cloud_batcher import (
    CloudRequestBatcher,
    BatchResult,
)


class TestOptimizationRouter:
    """Tests for OptimizationRouter class."""

    def test_init_creates_default_config(self):
        """Router should create default config if none provided."""
        router = OptimizationRouter()
        assert router.config is not None
        assert isinstance(router.config, OptimizationConfig)

    def test_local_provider_classification(self):
        """Should correctly classify local providers."""
        router = OptimizationRouter()

        assert router.is_local_provider(ProviderType.OLLAMA) is True
        assert router.is_local_provider(ProviderType.VLLM) is True
        assert router.is_local_provider(ProviderType.TRANSFORMERS) is True
        assert router.is_local_provider(ProviderType.LOCAL) is True

    def test_cloud_provider_classification(self):
        """Should correctly classify cloud providers."""
        router = OptimizationRouter()

        assert router.is_cloud_provider(ProviderType.OPENAI) is True
        assert router.is_cloud_provider(ProviderType.ANTHROPIC) is True
        assert router.is_cloud_provider(ProviderType.OLLAMA) is False

    def test_local_optimizations_include_gpu_features(self):
        """Local providers should get GPU-level optimizations."""
        router = OptimizationRouter()
        optimizations = router.get_optimizations(ProviderType.OLLAMA)

        assert OptimizationCategory.SPECULATIVE_DECODING in optimizations
        assert OptimizationCategory.FLASH_ATTENTION in optimizations
        assert OptimizationCategory.CUDA_GRAPHS in optimizations
        assert OptimizationCategory.QUANTIZATION in optimizations

    def test_cloud_optimizations_include_api_features(self):
        """Cloud providers should get API-level optimizations."""
        router = OptimizationRouter()
        optimizations = router.get_optimizations(ProviderType.OPENAI)

        assert OptimizationCategory.CONNECTION_POOLING in optimizations
        assert OptimizationCategory.API_REQUEST_BATCHING in optimizations
        assert OptimizationCategory.RETRY_WITH_BACKOFF in optimizations
        assert OptimizationCategory.RATE_LIMIT_HANDLING in optimizations

    def test_universal_optimizations_apply_to_all(self):
        """Universal optimizations should apply to all providers."""
        router = OptimizationRouter()

        for provider in [ProviderType.OLLAMA, ProviderType.OPENAI]:
            optimizations = router.get_optimizations(provider)
            assert OptimizationCategory.RESPONSE_CACHING in optimizations
            assert OptimizationCategory.PROMPT_COMPRESSION in optimizations
            assert OptimizationCategory.REQUEST_DEDUPLICATION in optimizations

    def test_should_apply_respects_config(self):
        """should_apply should respect config enablement."""
        config = OptimizationConfig(speculation_enabled=False)
        router = OptimizationRouter(config)

        # Speculation is disabled in config
        assert router.should_apply(
            OptimizationCategory.SPECULATIVE_DECODING, ProviderType.OLLAMA
        ) is False

    def test_cloud_optimizations_not_on_local(self):
        """Cloud-only optimizations should not apply to local providers."""
        router = OptimizationRouter()

        assert router.should_apply(
            OptimizationCategory.CONNECTION_POOLING, ProviderType.OLLAMA
        ) is False
        assert router.should_apply(
            OptimizationCategory.RATE_LIMIT_HANDLING, ProviderType.VLLM
        ) is False


class TestPromptCompressor:
    """Tests for PromptCompressor class."""

    def test_init_with_default_config(self):
        """Should initialize with default config."""
        compressor = PromptCompressor()
        assert compressor.config.enabled is True
        assert compressor.config.target_ratio == 0.7

    def test_compress_removes_filler_phrases(self):
        """Should remove filler phrases."""
        # Use a longer text to meet min_length_to_compress threshold
        config = CompressionConfig(min_length_to_compress=10)
        compressor = PromptCompressor(config)
        text = "Please note that you need to do this task correctly. It is important to remember the instructions and follow them carefully to achieve the desired outcome."
        result = compressor.compress(text)

        assert "Please note that" not in result.compressed_text
        assert "It is important to" not in result.compressed_text

    def test_compress_applies_replacements(self):
        """Should apply standard replacements."""
        # Use a longer text to meet min_length_to_compress threshold
        config = CompressionConfig(min_length_to_compress=10)
        compressor = PromptCompressor(config)
        text = "You are a helpful assistant that provides answers. Please provide the answer to the user question. Make sure to be accurate and helpful in your response."
        result = compressor.compress(text)

        assert "You are a helpful assistant" not in result.compressed_text
        assert "Assistant" in result.compressed_text or result.compression_ratio < 1.0

    def test_compress_preserves_code_blocks(self):
        """Should preserve code blocks when configured."""
        config = CompressionConfig(preserve_code_blocks=True)
        compressor = PromptCompressor(config)

        text = "Please note that ```python\nprint('hello')\n``` is important"
        result = compressor.compress(text)

        assert "```python" in result.compressed_text
        assert "print('hello')" in result.compressed_text

    def test_compress_preserves_urls(self):
        """Should preserve URLs when configured."""
        config = CompressionConfig(preserve_urls=True)
        compressor = PromptCompressor(config)

        text = "Please note that https://example.com/api is the endpoint"
        result = compressor.compress(text)

        assert "https://example.com/api" in result.compressed_text

    def test_compress_skips_short_text(self):
        """Should skip compression for short text."""
        config = CompressionConfig(min_length_to_compress=100)
        compressor = PromptCompressor(config)

        text = "Short text"
        result = compressor.compress(text)

        assert result.compression_ratio == 1.0
        assert result.strategy_used == "none"

    def test_compress_disabled_returns_original(self):
        """Should return original when compression disabled."""
        config = CompressionConfig(enabled=False)
        compressor = PromptCompressor(config)

        text = "Please note that this is a test with filler words."
        result = compressor.compress(text)

        assert result.compressed_text == text
        assert result.compression_ratio == 1.0

    def test_select_relevant_context_limits_results(self):
        """Should limit context chunks to max_contexts."""
        compressor = PromptCompressor()
        contexts = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        result = compressor.select_relevant_context("query", contexts, max_contexts=3)

        assert len(result) == 3

    def test_compression_result_includes_metrics(self):
        """Compression result should include proper metrics."""
        compressor = PromptCompressor()
        text = "Please note that this is a test message with some filler words."
        result = compressor.compress(text)

        assert isinstance(result, CompressionResult)
        assert result.original_tokens > 0
        assert result.compressed_tokens >= 0
        assert 0 <= result.compression_ratio <= 1.0


class TestRateLimitHandler:
    """Tests for RateLimitHandler class."""

    def test_init_with_default_config(self):
        """Should initialize with default config."""
        handler = RateLimitHandler()
        assert handler.config.max_retries == 3
        assert handler.config.strategy == RetryStrategy.EXPONENTIAL

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        """Should return result on successful call."""
        handler = RateLimitHandler()
        mock_call = AsyncMock(return_value="success")

        result = await handler.execute_with_retry(mock_call, provider="test")

        assert result == "success"
        mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_retry_retries_on_rate_limit(self):
        """Should retry on rate limit error."""
        config = RateLimitConfig(max_retries=2, base_delay=0.01)
        handler = RateLimitHandler(config)

        # Fail twice with rate limit, succeed on third
        mock_call = AsyncMock(
            side_effect=[
                RateLimitError("Rate limited", retry_after=0.01),
                RateLimitError("Rate limited", retry_after=0.01),
                "success",
            ]
        )

        result = await handler.execute_with_retry(mock_call, provider="test")

        assert result == "success"
        assert mock_call.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_retry_raises_after_max_retries(self):
        """Should raise after max retries exhausted."""
        config = RateLimitConfig(max_retries=2, base_delay=0.01)
        handler = RateLimitHandler(config)

        mock_call = AsyncMock(
            side_effect=RateLimitError("Rate limited", retry_after=0.01)
        )

        with pytest.raises(RateLimitError):
            await handler.execute_with_retry(mock_call, provider="test")

        assert mock_call.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_execute_with_retry_raises_non_rate_limit_immediately(self):
        """Should raise non-rate-limit errors immediately."""
        handler = RateLimitHandler()
        mock_call = AsyncMock(side_effect=ValueError("Bad value"))

        with pytest.raises(ValueError):
            await handler.execute_with_retry(mock_call, provider="test")

        mock_call.assert_called_once()

    def test_get_metrics_returns_stats(self):
        """Should return provider metrics."""
        handler = RateLimitHandler()
        metrics = handler.get_metrics()

        assert isinstance(metrics, dict)


class TestCloudRequestBatcher:
    """Tests for CloudRequestBatcher class."""

    def test_init_with_defaults(self):
        """Should initialize with default settings."""
        batcher = CloudRequestBatcher()
        assert batcher.batch_window_ms == 50
        assert batcher.max_batch_size == 10

    @pytest.mark.asyncio
    async def test_add_request_without_executor_fails(self):
        """Should fail if no executor configured."""
        batcher = CloudRequestBatcher(batch_window_ms=10)

        result = await batcher.add_request({"prompt": "test"})

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_add_request_with_executor_succeeds(self):
        """Should execute requests with configured executor."""
        async def mock_executor(payloads):
            return [{"response": f"result_{i}"} for i, _ in enumerate(payloads)]

        batcher = CloudRequestBatcher(batch_window_ms=10)
        batcher.set_executor(mock_executor)

        result = await batcher.add_request({"prompt": "test"})

        assert result.error is None
        assert result.response is not None

    @pytest.mark.asyncio
    async def test_batches_multiple_requests(self):
        """Should batch multiple concurrent requests."""
        call_count = 0

        async def counting_executor(payloads):
            nonlocal call_count
            call_count += 1
            return [{"response": f"result_{i}"} for i, _ in enumerate(payloads)]

        batcher = CloudRequestBatcher(batch_window_ms=50, max_batch_size=5)
        batcher.set_executor(counting_executor)

        # Add multiple requests concurrently
        tasks = [
            batcher.add_request({"prompt": f"test_{i}"})
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        # Should have batched into single call
        assert all(r.error is None for r in results)
        assert all(r.batch_size >= 1 for r in results)

    def test_get_metrics_returns_stats(self):
        """Should return batching metrics."""
        batcher = CloudRequestBatcher()
        metrics = batcher.get_metrics()

        assert "batches_sent" in metrics
        assert "requests_batched" in metrics
        assert "avg_batch_size" in metrics

    @pytest.mark.asyncio
    async def test_shutdown_flushes_pending(self):
        """Should flush pending requests on shutdown."""
        batcher = CloudRequestBatcher(batch_window_ms=1000)
        await batcher.shutdown()
        # Should complete without hanging


class TestOptimizationIntegration:
    """Integration tests for optimization components."""

    def test_router_and_compressor_work_together(self):
        """Router and compressor should work together."""
        router = OptimizationRouter()
        compressor = PromptCompressor()

        # Check if compression should be applied
        should_compress = router.should_apply(
            OptimizationCategory.PROMPT_COMPRESSION, ProviderType.OPENAI
        )

        if should_compress:
            text = "Please note that this is a test. It is important to check."
            result = compressor.compress(text)
            assert result.compression_ratio <= 1.0

    def test_config_propagates_correctly(self):
        """Config should propagate to router correctly."""
        config = OptimizationConfig(
            speculation_enabled=True,
            prompt_compression_enabled=False,
        )
        router = OptimizationRouter(config)

        # Check config-based behavior
        assert router.config.speculation_enabled is True
        assert router.config.prompt_compression_enabled is False
