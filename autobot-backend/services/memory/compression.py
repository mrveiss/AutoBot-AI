# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Context compression service for small-context LLM models. Issue #3770.

Compresses conversation history and KB results to fit within model-specific
token budgets when the model's context window is too small to hold the full
retrieved memory.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Default threshold: only compress for models with context_window_tokens <= 8192.
_DEFAULT_COMPRESSION_THRESHOLD = 8192

# Token estimation: words * 1.3 approximates BPE token count without an
# external tokenizer dependency (GPT-style subword tokenisation averages
# ~1.3 tokens per whitespace-delimited word for English prose).
_WORDS_TO_TOKENS = 1.3

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "context_windows.yaml"


def _estimate_tokens(text: str) -> int:
    """Estimate token count using word-count heuristic.

    Approximation: len(text.split()) * 1.3.  Avoids any external tokenizer
    dependency while staying within ~10 % of real BPE counts for English prose.
    """
    return int(len(text.split()) * _WORDS_TO_TOKENS)


def _message_tokens(msg: Dict[str, Any]) -> int:
    """Estimate tokens for a single role/content message dict."""
    return _estimate_tokens(str(msg.get("content", "")))


class ContextCompressionService:
    """Compresses retrieved memory to fit within model token budgets.

    Usage::

        svc = ContextCompressionService()
        if await svc.should_compress(model_name, content_tokens):
            history = await svc.compress_history(history, target_tokens)
            kb_results = await svc.compress_kb_results(kb_results, max_tokens)
    """

    def __init__(
        self,
        config_path: Path | None = None,
        model_thresholds: Dict[str, int] | None = None,
    ) -> None:
        if model_thresholds is not None:
            self._model_thresholds: Dict[str, int] = model_thresholds
        else:
            self._config_path = config_path or _CONFIG_PATH
            self._model_thresholds = {}
            self._load_thresholds()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_thresholds(self) -> None:
        """Load per-model compression thresholds from context_windows.yaml."""
        try:
            with open(self._config_path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh)
            models = cfg.get("models", {})
            if not isinstance(models, dict):
                logger.warning("[#3770] context_windows.yaml has unexpected format")
                return
            for name, spec in models.items():
                if not isinstance(spec, dict):
                    continue
                threshold = spec.get("compression_threshold", _DEFAULT_COMPRESSION_THRESHOLD)
                context_window = spec.get("context_window_tokens")
                if context_window is not None and threshold > context_window:
                    raise ValueError(
                        f"[#3811] context_windows.yaml: model '{name}' has "
                        f"compression_threshold={threshold} > "
                        f"context_window_tokens={context_window}. "
                        "compression_threshold must not exceed context_window_tokens."
                    )
                self._model_thresholds[name] = threshold
            logger.debug("[#3770] Loaded thresholds for %d models", len(self._model_thresholds))
        except ValueError:
            # Configuration error — re-raise immediately so startup fails fast
            # rather than silently running with an invalid threshold.
            raise
        except Exception as exc:
            logger.warning("[#3770] Could not load thresholds, using default: %s", exc)

    def _get_threshold(self, model_name: str) -> int:
        """Return the compression threshold for a model."""
        return self._model_thresholds.get(model_name, _DEFAULT_COMPRESSION_THRESHOLD)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def should_compress(self, model_name: str, content_tokens: int) -> bool:
        """Return True if content_tokens exceeds the model's compression_threshold.

        The threshold in context_windows.yaml encodes the correct per-model value:
        small models (e.g. phi3 = 4096) compress aggressively; large models
        (e.g. gpt-4o = 32768) compress only when content is genuinely oversized.

        Args:
            model_name: The active LLM model name.
            content_tokens: Estimated token count of the content to evaluate.

        Returns:
            True when compression should be applied.
        """
        threshold = self._get_threshold(model_name)
        return content_tokens > threshold

    async def compress_history(self, messages: List[Dict[str, Any]], target_tokens: int) -> List[Dict[str, Any]]:
        """Trim conversation history to fit within target_tokens.

        Strategy: keep the most recent messages that fit; prefix the result
        with a one-line summary of any dropped messages so the model retains
        awareness of earlier context.

        Args:
            messages: List of role/content message dicts (oldest first).
            target_tokens: Maximum token budget for the returned history.

        Returns:
            Trimmed list of messages, possibly prefixed with a summary message.
            Returns original messages unchanged on any error.
        """
        try:
            return self._trim_with_summary(messages, target_tokens)
        except Exception as exc:
            logger.warning("[#3770] compress_history failed, returning original: %s", exc)
            return messages

    def _trim_with_summary(self, messages: List[Dict[str, Any]], target_tokens: int) -> List[Dict[str, Any]]:
        """Keep trailing messages that fit, prepend summary of dropped ones."""
        kept: List[Dict[str, Any]] = []
        used = 0
        for msg in reversed(messages):
            cost = _message_tokens(msg)
            if used + cost > target_tokens:
                break
            kept.insert(0, msg)
            used += cost

        dropped_count = len(messages) - len(kept)
        if dropped_count == 0:
            return messages

        summary = {
            "role": "assistant",
            "content": (
                f"[Summary: {dropped_count} earlier message(s) were omitted to fit"
                f" the {target_tokens}-token history budget.]"
            ),
        }
        return [summary] + kept

    async def compress_kb_results(self, results: List[Any], max_tokens: int) -> List[Any]:
        """Re-rank KB results by score and trim to fit max_tokens.

        Args:
            results: List of KB result objects/dicts.  Each item may have a
                     ``score`` attribute or key for ranking.
            max_tokens: Maximum token budget for the returned results.

        Returns:
            Highest-scoring results that fit within max_tokens.
            Returns original results unchanged on any error.
        """
        try:
            return self._rank_and_trim(results, max_tokens)
        except Exception as exc:
            logger.warning("[#3770] compress_kb_results failed, returning original: %s", exc)
            return results

    def _get_score(self, item: Any) -> float:
        """Extract score from a KB result (dict key or attribute)."""
        if isinstance(item, dict):
            return float(item.get("score", 0.0))
        return float(getattr(item, "score", 0.0))

    def _get_text(self, item: Any) -> str:
        """Extract text content from a KB result for token estimation."""
        if isinstance(item, dict):
            return str(item.get("content", item.get("text", item)))
        return str(getattr(item, "content", getattr(item, "text", item)))

    def _rank_and_trim(self, results: List[Any], max_tokens: int) -> List[Any]:
        """Sort by score descending and keep top items within budget."""
        ranked = sorted(results, key=self._get_score, reverse=True)
        kept: List[Any] = []
        used = 0
        for item in ranked:
            cost = _estimate_tokens(self._get_text(item))
            if used + cost > max_tokens:
                break
            kept.append(item)
            used += cost
        logger.debug(
            "[#3770] KB compression: kept %d/%d results (%d tokens)",
            len(kept),
            len(results),
            used,
        )
        return kept
