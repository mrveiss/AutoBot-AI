# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Centralized context window management for LLM interactions.

Issue #7351: architecture_family-aware compression bypass.  Non-transformer
models (state_space, linear_attention, hybrid) carry constant inference memory
and do not face the quadratic attention cost that justifies the 4K/8K
compression trigger.  For those families the model's declared
``context_window_tokens`` is used directly as the compression threshold
instead of hard-capping at 8192.

Issue #13640: multi-section allocation.  Sizing the window is not the same as
dividing it.  ``allocate_sections`` allocates one budget across named,
prioritised sections so an overflowing prompt sheds its least valuable content
first — and reports what it shed — instead of dropping whatever the calling
code happened to cut last.
"""

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List

_CONTEXT_HEADROOM: float = 0.85
_CONTEXT_HARD_MAX: int = 200_000

import yaml

from autobot_shared.logging_manager import get_logger
from constants.model_constants import ModelConfig, ModelConstants

logger = get_logger(__name__)

# Architecture families whose cost curve does not require transformer caps.
# "ssm" matches llm_shared.ArchitectureFamily.SSM; "state_space" is kept for
# backward-compatible YAML entries written before MVA-1379 standardised the
# enum.  Both string values bypass the 4K/8K compression trigger.
_NON_TRANSFORMER_FAMILIES: frozenset[str] = frozenset({"ssm", "state_space", "linear_attention", "hybrid"})

# Lazy singleton — imported on first call to avoid circular imports.
_compression_service = None


def _get_compression_service():
    """Return the shared ContextCompressionService instance (lazy init)."""
    global _compression_service
    if _compression_service is None:
        from services.memory.compression import ContextCompressionService

        _compression_service = ContextCompressionService()
    return _compression_service


def _head_trim(content: str, max_chars: int) -> str:
    """Default section shrink: keep the head, drop the tail.

    Deliberately dumb. Sections with a better strategy pass their own ``trim``
    — e.g. ``prompt_manager._truncate_large_file``, which keeps head+tail and
    snaps to JSON/XML boundaries. #13640 decides *how much* a section gets; it
    does not decide *how* a section shrinks.
    """
    return content[:max_chars]


@dataclass
class ContextSection:
    """One named, prioritised piece of a prompt competing for the budget.

    Attributes:
        name: Stable identifier reported back when the section is trimmed.
        content: The section text.
        priority: Higher is pruned last. Ties break on ``name`` for determinism.
        max_share: Ceiling as a fraction of the budget, applied *before*
                   priority. A high-priority section still cannot crowd out
                   the rest of the prompt.
        trim: Optional shrink strategy ``(content, max_chars) -> str``.
    """

    name: str
    content: str
    priority: int = 0
    max_share: float = 1.0
    trim: Callable[[str, int], str] = _head_trim


@dataclass
class ContextAllocation:
    """Outcome of an allocation, including what was lost.

    ``trimmed`` and ``dropped`` are what make prompt degradation traceable:
    without them an overflowing prompt ships silently degraded and neither a
    quality regression nor a cost spike can be attributed to a cause.
    """

    sections: List[ContextSection]
    tokens_before: int
    tokens_after: int
    budget: int
    trimmed: List[str] = field(default_factory=list)
    dropped: List[str] = field(default_factory=list)

    @property
    def fits(self) -> bool:
        """True when the allocated sections are within budget."""
        return self.tokens_after <= self.budget

    def render(self, separator: str = "\n\n") -> str:
        """Join the allocated sections, skipping any reduced to empty."""
        return separator.join(s.content for s in self.sections if s.content)


class ContextWindowManager:
    """Manages context window budgeting for LLM models."""

    def __init__(self, config_path: str = "config/context_windows.yaml"):
        """Initialize context window manager with model configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config = self._load_config(config_path)
        self.current_model = self.config["models"]["default"]["name"]

    def _load_config(self, config_path: str) -> Dict:
        """Load model configuration from YAML.

        Args:
            config_path: Path to YAML file

        Returns:
            Configuration dictionary
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning("Config not found: %s, using defaults", config_path)
            return self._get_default_config()

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # If models is a list it's the LLM provider registry (PR #3257 schema),
            # not the context-window config dict this class expects.
            if not isinstance(config.get("models"), dict):
                logger.warning(
                    "Config %s uses list-format model registry; using context-window defaults",
                    config_path,
                )
                return self._get_default_config()

            logger.info("✅ Loaded config for %s models", len(config["models"]))
            return config
        except Exception as e:
            logger.error("Failed to load config: %s, using defaults", e)
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Fallback config if YAML not found.

        Returns:
            Default configuration dictionary
        """
        return {
            "models": {
                "default": {
                    "name": ModelConstants.DEFAULT_OLLAMA_MODEL,
                    "context_window_tokens": 4096,
                    "max_output_tokens": 2048,
                    "message_budget": {
                        "system_prompt": 500,
                        "recent_messages": 20,
                        "max_history_tokens": ModelConfig.MAX_HISTORY_TOKENS,
                    },
                },
                ModelConstants.DEFAULT_OLLAMA_MODEL: {
                    "context_window_tokens": 4096,
                    "max_output_tokens": 2048,
                    "message_budget": {
                        "system_prompt": 500,
                        "recent_messages": 20,
                        "max_history_tokens": ModelConfig.MAX_HISTORY_TOKENS,
                    },
                },
            },
            "token_estimation": {
                # Config dict; 'token_estimation' refers to LLM token counting, not a credential.
                "chars_per_token": 4,  # nosec B105
                "safety_margin": 0.9,
            },
        }

    def set_model(self, model_name: str):
        """Set active model for context management.

        Args:
            model_name: Name of the LLM model to use
        """
        if model_name not in self.config["models"]:
            logger.warning("Unknown model %s, using default", model_name)
            self.current_model = self.config["models"]["default"]["name"]
        else:
            self.current_model = model_name

        logger.info("Active model: %s", self.current_model)

    def get_message_limit(self, model_name: str | None = None) -> int:
        """Get recommended message limit for model.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Number of recent messages to use for context
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]["message_budget"]["recent_messages"]

    def get_max_history_tokens(self, model_name: str | None = None) -> int:
        """Get max tokens to allocate for conversation history.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Maximum tokens for conversation history
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]["message_budget"]["max_history_tokens"]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text.

        NOT repointed onto autobot_shared.doc_chunking.estimate_tokens
        (#12764/#12645): chars_per_token here is a genuine runtime config
        knob (config/context_windows.yaml `token_estimation.chars_per_token`,
        default 4) rather than a hardcoded constant. The canonical estimator
        hardcodes //4, so delegating would silently ignore any deployment
        that configures a different ratio and change truncation behavior.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // self._chars_per_token()

    def _chars_per_token(self) -> int:
        """Runtime chars-per-token ratio backing :meth:`estimate_tokens`."""
        return max(1, int(self.config["token_estimation"]["chars_per_token"]))

    def _shrink(self, section: ContextSection, max_tokens: int) -> ContextSection:
        """Return a copy of *section* reduced to at most *max_tokens*.

        A section's own ``trim`` is free to overshoot — ``_truncate_large_file``
        adds a marker, so at small allocations head+tail+marker exceeds the
        limit. The allocation is a ceiling, not a suggestion, so the result is
        re-clamped. Without this a single overshooting strategy silently puts
        the whole prompt back over budget.
        """
        if max_tokens <= 0:
            return replace(section, content="")
        max_chars = max_tokens * self._chars_per_token()
        shrunk = section.trim(section.content, max_chars)
        if not isinstance(shrunk, str):
            shrunk = _head_trim(section.content, max_chars)
        return replace(section, content=shrunk[:max_chars])

    def allocate_sections(
        self,
        sections: List[ContextSection],
        budget_tokens: int,
    ) -> ContextAllocation:
        """Allocate one token budget across competing sections by priority.

        Pure function — no I/O, no config reload, no mutation of the inputs.

        Two phases, in this order:

        1. **Cap.** Each section is limited to ``budget_tokens * max_share``.
           This runs before priority so a single oversized section cannot
           crowd out everything else merely by being important.
        2. **Trim.** If the total still exceeds the budget, sections are
           reduced lowest-priority-first until it fits.

        Args:
            sections: Competing sections. Input order is preserved in the result.
            budget_tokens: Total token budget for all sections combined.

        Returns:
            ContextAllocation with before/after totals and the names of
            sections that were trimmed or reduced to nothing.
        """
        allocated = list(sections)
        tokens = [self.estimate_tokens(s.content) for s in allocated]
        tokens_before = sum(tokens)

        # Pass-through when the total already fits. ``max_share`` is a
        # *contention* ceiling — with headroom to spare there is nothing to
        # crowd out, and enforcing it would throw away content while the window
        # sits idle, which is strictly worse than the concatenation this
        # replaces.
        if tokens_before <= budget_tokens:
            return ContextAllocation(
                sections=allocated,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                budget=budget_tokens,
            )

        trimmed_idx: set = set()
        allocated, tokens = self._apply_share_caps(allocated, tokens, budget_tokens, trimmed_idx)
        allocated, tokens = self._trim_by_priority(allocated, tokens, budget_tokens, trimmed_idx)

        # Indices, not names: duplicate section names would otherwise double-count
        # in `trimmed` and cross-attribute in `dropped`.
        trimmed = [allocated[i].name for i in sorted(trimmed_idx)]
        dropped = [allocated[i].name for i in sorted(trimmed_idx) if tokens[i] <= 0]
        return ContextAllocation(
            sections=allocated,
            tokens_before=tokens_before,
            tokens_after=sum(tokens),
            budget=budget_tokens,
            trimmed=trimmed,
            dropped=dropped,
        )

    def _apply_share_caps(
        self, allocated: List[ContextSection], tokens: List[int], budget: int, trimmed: set
    ) -> "tuple[List[ContextSection], List[int]]":
        """Phase 1: cap each section at ``budget * max_share``."""
        for i, section in enumerate(allocated):
            cap = int(budget * section.max_share)
            if tokens[i] <= cap:
                continue
            allocated[i] = self._shrink(section, cap)
            tokens[i] = self.estimate_tokens(allocated[i].content)
            trimmed.add(i)
        return allocated, tokens

    @staticmethod
    def _tier_keeps(sizes: "dict[int, int]", tier_keep: int) -> "dict[int, int]":
        """Split *tier_keep* tokens across peers in proportion to their sizes (#13717).

        Peers must share, not queue. Draining a tier in name order makes the
        trim total, so the last section by name keeps everything and the rest
        are zeroed — deterministic, and wrong for sections that genuinely rank
        equally (N retrieved chunks, N file contents, N tool results).

        Rounding is the interesting part: proportional shares rarely land on
        integers, so each keep is floored and the remainder handed out one token
        at a time by largest fractional part, ties broken by index. That is
        deterministic for any input order and never exceeds *tier_keep*.
        """
        total = sum(sizes.values())
        if tier_keep <= 0 or total <= 0:
            return {i: 0 for i in sizes}

        exact = {i: size * tier_keep / total for i, size in sizes.items()}
        keeps = {i: int(value) for i, value in exact.items()}
        # A section never keeps more than it had, whatever the arithmetic says.
        keeps = {i: min(keeps[i], sizes[i]) for i in sizes}

        remainder = tier_keep - sum(keeps.values())
        if remainder > 0:
            # Largest fractional part first; index breaks ties so the result is
            # independent of dict iteration order.
            candidates = sorted(sizes, key=lambda i: (-(exact[i] - int(exact[i])), i))
            for i in candidates:
                if remainder <= 0:
                    break
                if keeps[i] < sizes[i]:
                    keeps[i] += 1
                    remainder -= 1
        return keeps

    def _trim_by_priority(
        self, allocated: List[ContextSection], tokens: List[int], budget: int, trimmed: set
    ) -> "tuple[List[ContextSection], List[int]]":
        """Phase 2: reduce lowest-priority sections until the total fits.

        Tiers are still pruned strictly lowest-priority-first — a section that
        genuinely outranks another must not lose tokens to it. Within a tier the
        share is proportional (#13717) rather than name-ordered.
        """
        tiers: "dict[object, list[int]]" = {}
        for i in range(len(allocated)):
            tiers.setdefault(allocated[i].priority, []).append(i)

        for priority in sorted(tiers):
            overflow = sum(tokens) - budget
            if overflow <= 0:
                break
            indices = [i for i in tiers[priority] if tokens[i] > 0]
            if not indices:
                continue

            sizes = {i: tokens[i] for i in indices}
            tier_total = sum(sizes.values())
            # This tier absorbs as much of the overflow as it can hold; whatever
            # is left falls through to the next tier up.
            tier_keep = max(0, tier_total - overflow)
            keeps = self._tier_keeps(sizes, tier_keep)

            for i in indices:
                if keeps[i] >= tokens[i]:
                    continue
                allocated[i] = self._shrink(allocated[i], keeps[i])
                tokens[i] = self.estimate_tokens(allocated[i].content)
                trimmed.add(i)
        return allocated, tokens

    def get_prompt_budget(self, model_name: str | None = None) -> int:
        """Tokens available to the *prompt*, after reserving room to answer (#13640).

        ``get_adaptive_context_length`` returns the whole declared window. A
        prompt that fills it leaves the model nowhere to generate, and the
        system prompt is sent separately (Ollama ``system`` field) so it
        consumes window while being invisible to the allocator. Both are
        subtracted here.
        """
        window = self.get_adaptive_context_length(model_name)
        info = self.get_model_info(model_name)
        reserved = int(info.get("max_output_tokens", 0) or 0)
        reserved += int((info.get("message_budget") or {}).get("system_prompt", 0) or 0)
        # Never reserve the window away entirely: a pathological config must
        # still leave a usable prompt budget rather than zero.
        return max(window // 4, window - reserved)

    def calculate_retrieval_limit(self, model_name: str | None = None) -> int:
        """Calculate how many messages to retrieve from Redis.

        More efficient than fetching 500 when we only use 200.
        Fetches 2x what we plan to use as a buffer for filtering.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Number of messages to retrieve from storage
        """
        message_limit = self.get_message_limit(model_name)
        # Fetch 2x what we plan to use (buffer for filtering)
        return message_limit * 2

    def should_truncate_history(self, messages: List[Dict], model_name: str | None = None) -> bool:
        """Check if message history needs truncation.

        Args:
            messages: List of message dictionaries
            model_name: Optional model name, uses current if not specified

        Returns:
            True if history should be truncated
        """
        # Calculate total characters from all message contents
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        # Estimate tokens based on character count
        estimated_tokens = total_chars // self.config["token_estimation"]["chars_per_token"]

        max_tokens = self.get_max_history_tokens(model_name)
        return estimated_tokens > max_tokens

    @staticmethod
    def _registry_family(model: str) -> str:
        """Look up architecture_family from llm_shared registry (lazy import)."""
        try:
            from llm_shared.model_param_registry import get_architecture_family as _get

            return _get(model)
        except Exception:
            return "transformer"

    def get_architecture_family(self, model_name: str | None = None) -> str:
        """Return the architecture_family for a model (defaults to 'transformer').

        Issue #7351: resolution order:
        1. ``architecture_family`` key from ``context_windows.yaml`` (normalized).
        2. ``llm_shared.get_architecture_family()`` — reads ``llm_models.yaml``
           and, optionally, HuggingFace ``config.json`` (MVA-1379).
        3. ``'transformer'`` safe default.

        Args:
            model_name: Optional model name, uses current if not specified.

        Returns:
            Architecture family string (e.g. ``'transformer'``, ``'ssm'``).
        """
        model = model_name or self.current_model
        # Issue #8360: unknown models must not inherit default model's family.
        if model not in self.config["models"]:
            return self._registry_family(model)
        raw = self.config["models"][model].get("architecture_family")
        if raw is None:
            # Entry exists but omits architecture_family — delegate to registry.
            return self._registry_family(model)
        # Issue #8361: normalize whitespace and case before frozenset check.
        return raw.strip().lower()

    def get_compression_threshold(self, model_name: str | None = None) -> int:
        """Get the compression threshold for a model.

        Issue #3770: transformer models whose context_window_tokens <= 8192
        trigger compression when retrieved content exceeds this value.

        Issue #7351: non-transformer families (state_space, linear_attention,
        hybrid) return the model's declared ``context_window_tokens`` instead of
        the 8192 default so that large-context models are not falsely capped.
        When ``context_window_tokens`` is also absent the fallback is 8192
        (same safe default as before, still transformer-conservative).

        Args:
            model_name: Optional model name, uses current if not specified.

        Returns:
            Token threshold above which compression should be applied.
        """
        model = model_name or self.current_model
        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        entry = self.config["models"][model]
        # Use the method so the llm_shared registry fallback is applied.
        family = self.get_architecture_family(model_name)

        # Issue #8359: explicit compression_threshold always wins, regardless of
        # architecture family.  Only fall back to family-specific defaults when
        # the field is absent.
        if "compression_threshold" in entry:
            return entry["compression_threshold"]

        if family in _NON_TRANSFORMER_FAMILIES:
            # Use the model's declared context window as the threshold —
            # no artificial cap for non-attention architectures.
            threshold = entry.get("context_window_tokens", 8192)
            logger.debug(
                "get_compression_threshold: %s (family=%s) → %d (no cap)",
                model,
                family,
                threshold,
            )
            return threshold

        return 8192

    def _query_known_context_length(self, model_name: str) -> int:
        """Try to get context window from llm_shared model registry. Returns 0 when unknown."""
        try:
            from llm_shared.model_param_registry import get_model_kwargs

            kwargs = get_model_kwargs(model_name)
            return int(kwargs.get("context_window_tokens", 0))
        except Exception:
            return 0

    def get_adaptive_context_length(self, model_name: str | None = None) -> int:
        """Return the effective context length for token budget calculations.

        Resolution order:
        1. Model in YAML config → return declared context_window_tokens exactly.
        2. Not in YAML → query llm_shared registry; scale by _CONTEXT_HEADROOM,
           cap at _CONTEXT_HARD_MAX.
        3. Registry also misses → YAML fallback (4096).
        """
        model = model_name or self.current_model
        if model in self.config["models"]:
            return int(self.config["models"][model].get("context_window_tokens", 4096))

        discovered = self._query_known_context_length(model)
        if discovered > 0:
            return min(int(discovered * _CONTEXT_HEADROOM), _CONTEXT_HARD_MAX)

        default_name = self.config["models"]["default"]["name"]
        return int(self.config["models"].get(default_name, {}).get("context_window_tokens", 4096))

    async def async_should_compress(self, content_tokens: int, model_name: str | None = None) -> bool:
        """Return True when content_tokens exceed the model compression threshold.

        Issue #3770: Delegates to ContextCompressionService which applies the
        large-model guard (threshold > 8192 -> always False).

        Issue #7351: non-transformer families bypass compression entirely —
        their cost curve does not justify the 4K/8K trigger.

        Args:
            content_tokens: Estimated token count of content to evaluate.
            model_name: Optional model name, uses current if not specified.

        Returns:
            True when compression should be applied.
        """
        model = model_name or self.current_model
        family = self.get_architecture_family(model)
        if family in _NON_TRANSFORMER_FAMILIES:
            logger.debug(
                "async_should_compress: %s (family=%s) → False (bypass)",
                model,
                family,
            )
            return False
        svc = _get_compression_service()
        return await svc.should_compress(model, content_tokens)

    def get_model_info(self, model_name: str | None = None) -> Dict:
        """Get full model configuration.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Model configuration dictionary
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]


@lru_cache(maxsize=4)
def get_context_window_manager(config_path: str = "config/context_windows.yaml") -> ContextWindowManager:
    """Return a shared ContextWindowManager (#13640).

    ``__init__`` reads and parses a 13 KB YAML file. Constructing one per chat
    turn put ~45 ms of synchronous parsing on the event loop, blocking every
    concurrent request, and logged a config line per turn. The config is static
    for the process lifetime, so it is parsed once.
    """
    return ContextWindowManager(config_path=config_path)
