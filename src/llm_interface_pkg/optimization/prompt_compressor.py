# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt Compressor - Reduce token count while preserving meaning.

Compresses prompts to reduce latency (local) and costs (cloud). Implements
multiple compression strategies from rule-based to model-based.

Issue #717: Efficient Inference Design implementation.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """Result of prompt compression."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    strategy_used: str


@dataclass
class CompressionConfig:
    """Configuration for prompt compression."""

    enabled: bool = True
    target_ratio: float = 0.7          # Target 70% of original length
    min_length_to_compress: int = 100  # Only compress prompts > 100 chars
    preserve_code_blocks: bool = True
    preserve_urls: bool = True
    aggressive_mode: bool = False      # Enable aggressive compression


class PromptCompressor:
    """
    Compress prompts to reduce token count while preserving meaning.

    Implements multiple compression strategies:
    1. Rule-based: Remove filler words, redundancy, whitespace
    2. Selective: Keep only most relevant context
    3. Template: Use pre-compressed templates for common patterns

    Typical usage:
        compressor = PromptCompressor()
        result = compressor.compress(prompt_text)
        logger.info("Compressed by %.0f%%", (1 - result.compression_ratio) * 100)
    """

    # Common filler phrases that can be removed
    FILLER_PHRASES = [
        "Please note that",
        "It is important to",
        "Keep in mind that",
        "Remember that",
        "As you know,",
        "In other words,",
        "To be more specific,",
        "As mentioned earlier,",
        "It should be noted that",
        "It goes without saying that",
        "Needless to say,",
        "For your information,",
        "Just to clarify,",
        "To put it simply,",
        "In essence,",
        "Basically,",
        "Essentially,",
        "Actually,",
        "Obviously,",
        "Clearly,",
    ]

    # Phrases that can be shortened
    REPLACEMENTS = {
        "You are a helpful assistant": "Assistant",
        "You are an AI assistant": "AI assistant",
        "Please provide": "Provide",
        "Please help me": "Help me",
        "Could you please": "Please",
        "Would you please": "Please",
        "Make sure to": "Ensure",
        "In order to": "To",
        "Due to the fact that": "Because",
        "In the event that": "If",
        "At this point in time": "Now",
        "In the near future": "Soon",
        "On a regular basis": "Regularly",
        "For the purpose of": "To",
        "With regard to": "About",
        "In reference to": "About",
        "In terms of": "For",
        "As a result of": "Because of",
        "In spite of the fact that": "Although",
        "The fact that": "That",
    }

    # Aggressive replacements (may affect clarity)
    AGGRESSIVE_REPLACEMENTS = {
        "however": "but",
        "therefore": "so",
        "additionally": "also",
        "furthermore": "also",
        "consequently": "so",
        "nevertheless": "but",
        "subsequently": "then",
        "accordingly": "so",
        "utilize": "use",
        "implement": "do",
        "facilitate": "help",
        "demonstrate": "show",
        "accomplish": "do",
        "regarding": "about",
        "concerning": "about",
    }

    def __init__(
        self,
        config: CompressionConfig = None,
        tokenizer: Callable[[str], int] = None,
    ):
        """
        Initialize prompt compressor.

        Args:
            config: Compression configuration
            tokenizer: Function to count tokens (defaults to char/4 estimate)
        """
        self.config = config or CompressionConfig()
        self._tokenizer = tokenizer

        logger.info(
            "PromptCompressor initialized: target_ratio=%.2f, aggressive=%s",
            self.config.target_ratio,
            self.config.aggressive_mode,
        )

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._tokenizer:
            return self._tokenizer(text)
        # Rough estimate: ~4 chars per token for English
        return len(text) // 4

    def compress(
        self,
        text: str,
        strategy: str = "auto",
    ) -> CompressionResult:
        """
        Compress prompt text.

        Args:
            text: Original prompt text
            strategy: Compression strategy ("auto", "rule", "selective")

        Returns:
            CompressionResult with compressed text and metrics
        """
        if not self.config.enabled:
            return self._no_compression_result(text)

        if len(text) < self.config.min_length_to_compress:
            return self._no_compression_result(text)

        original_tokens = self._count_tokens(text)

        # Apply compression
        if strategy == "auto" or strategy == "rule":
            compressed = self._rule_based_compression(text)
        elif strategy == "selective":
            compressed = self._selective_compression(text)
        else:
            compressed = self._rule_based_compression(text)

        compressed_tokens = self._count_tokens(compressed)
        ratio = compressed_tokens / max(original_tokens, 1)

        return CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=ratio,
            strategy_used=strategy,
        )

    def _no_compression_result(self, text: str) -> CompressionResult:
        """Return result for uncompressed text."""
        tokens = self._count_tokens(text)
        return CompressionResult(
            original_text=text,
            compressed_text=text,
            original_tokens=tokens,
            compressed_tokens=tokens,
            compression_ratio=1.0,
            strategy_used="none",
        )

    def _rule_based_compression(self, text: str) -> str:
        """Apply rule-based compression techniques."""
        compressed = text

        # Preserve code blocks if configured
        code_blocks = []
        if self.config.preserve_code_blocks:
            # Extract code blocks
            code_pattern = r"```[\s\S]*?```"
            matches = list(re.finditer(code_pattern, compressed))
            for i, match in enumerate(reversed(matches)):
                placeholder = f"__CODE_BLOCK_{len(matches) - 1 - i}__"
                code_blocks.insert(0, match.group())
                compressed = (
                    compressed[: match.start()]
                    + placeholder
                    + compressed[match.end() :]
                )

        # Preserve URLs if configured
        urls = []
        if self.config.preserve_urls:
            url_pattern = r"https?://\S+"
            matches = list(re.finditer(url_pattern, compressed))
            for i, match in enumerate(reversed(matches)):
                placeholder = f"__URL_{len(matches) - 1 - i}__"
                urls.insert(0, match.group())
                compressed = (
                    compressed[: match.start()]
                    + placeholder
                    + compressed[match.end() :]
                )

        # Remove excessive whitespace
        compressed = re.sub(r"\s+", " ", compressed)
        compressed = re.sub(r"\n\s*\n", "\n", compressed)

        # Remove filler phrases
        for phrase in self.FILLER_PHRASES:
            compressed = compressed.replace(phrase, "")

        # Apply standard replacements
        for old, new in self.REPLACEMENTS.items():
            compressed = compressed.replace(old, new)

        # Apply aggressive replacements if enabled
        if self.config.aggressive_mode:
            for old, new in self.AGGRESSIVE_REPLACEMENTS.items():
                # Case-insensitive word replacement
                pattern = rf"\b{re.escape(old)}\b"
                compressed = re.sub(pattern, new, compressed, flags=re.IGNORECASE)

        # Clean up extra spaces
        compressed = re.sub(r" +", " ", compressed)
        compressed = compressed.strip()

        # Restore code blocks
        for i, code in enumerate(code_blocks):
            compressed = compressed.replace(f"__CODE_BLOCK_{i}__", code)

        # Restore URLs
        for i, url in enumerate(urls):
            compressed = compressed.replace(f"__URL_{i}__", url)

        return compressed

    def _selective_compression(self, text: str) -> str:
        """Apply selective compression - keep most relevant parts."""
        # For now, use rule-based as base
        return self._rule_based_compression(text)

    def compress_system_prompt(self, prompt: str) -> CompressionResult:
        """
        Compress a system prompt specifically.

        System prompts often have more room for compression as they're
        typically verbose by design.

        Args:
            prompt: System prompt text

        Returns:
            CompressionResult with compressed system prompt
        """
        return self.compress(prompt, strategy="rule")

    def select_relevant_context(
        self,
        query: str,
        contexts: List[str],
        max_contexts: int = 3,
    ) -> List[str]:
        """
        Select most relevant context chunks for a query.

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
        query_words = set(query.lower().split())

        scored_contexts = []
        for ctx in contexts:
            ctx_words = set(ctx.lower().split())
            overlap = len(query_words & ctx_words)
            scored_contexts.append((overlap, ctx))

        # Sort by relevance and take top N
        scored_contexts.sort(reverse=True, key=lambda x: x[0])
        return [ctx for _, ctx in scored_contexts[:max_contexts]]

    def get_compression_stats(
        self, results: List[CompressionResult]
    ) -> Dict[str, Any]:
        """
        Get aggregate compression statistics.

        Args:
            results: List of compression results

        Returns:
            Dict with aggregate statistics
        """
        if not results:
            return {}

        total_original = sum(r.original_tokens for r in results)
        total_compressed = sum(r.compressed_tokens for r in results)
        avg_ratio = sum(r.compression_ratio for r in results) / len(results)

        return {
            "total_prompts": len(results),
            "total_original_tokens": total_original,
            "total_compressed_tokens": total_compressed,
            "tokens_saved": total_original - total_compressed,
            "average_compression_ratio": round(avg_ratio, 3),
            "overall_compression_ratio": round(
                total_compressed / max(total_original, 1), 3
            ),
        }


# Optimized system prompts for AutoBot
COMPRESSED_SYSTEM_PROMPTS = {
    "default": "Assistant for code analysis and automation. Be concise.",
    "code_review": "Code reviewer. Focus: bugs, security, performance. Be specific.",
    "documentation": "Doc writer. Style: clear, technical. Include examples.",
    "automation": "Automation assistant. Generate working code. Handle errors.",
    "analysis": "Analyst. Extract key information. Provide structured output.",
    "chat": "Conversational assistant. Be helpful and direct.",
}


def get_compressed_system_prompt(prompt_type: str) -> Optional[str]:
    """
    Get a pre-compressed system prompt.

    Args:
        prompt_type: Type of system prompt

    Returns:
        Compressed prompt or None if not found
    """
    return COMPRESSED_SYSTEM_PROMPTS.get(prompt_type)


__all__ = [
    "PromptCompressor",
    "CompressionConfig",
    "CompressionResult",
    "COMPRESSED_SYSTEM_PROMPTS",
    "get_compressed_system_prompt",
]
