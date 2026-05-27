# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for long_context tier routing (MVA-1372).

Covers all four routing cases mandated by the acceptance criteria:
  - short input, low complexity  → simple
  - short input, high complexity → complex
  - long input, low complexity   → long_context
  - long input, high complexity  → long_context
"""

from llm_shared.tiered_routing.complexity_router import ComplexityRouter
from llm_shared.tiered_routing.tier_config import TierConfig, TierModels

# ─── Message fixtures ─────────────────────────────────────────────────────────

# Short, low-complexity: ~1 token, no technical indicators
_SHORT_SIMPLE = [{"role": "user", "content": "hi"}]

# Short, high-complexity: technical multi-step content, well under 16k tokens
_SHORT_COMPLEX = [
    {
        "role": "user",
        "content": (
            "Write a multi-step algorithm in Python that implements "
            "a distributed consensus protocol with fault tolerance, "
            "including detailed code comments and error handling. " + "x" * 2000
        ),
    }
]

# Long content: 70_000 chars → ~17_500 tokens (char/4 estimate), safely above 16_000 threshold
_LONG_CONTENT = "x" * 70_000

# Long, low-complexity: large input but no complexity indicators
_LONG_SIMPLE = [{"role": "user", "content": _LONG_CONTENT}]

# Long, high-complexity: large input AND high-complexity indicators
_LONG_COMPLEX = [
    {
        "role": "user",
        "content": (
            "Write a multi-step algorithm in Python that implements "
            "a distributed consensus protocol with fault tolerance, "
            "including detailed code comments and error handling. " + _LONG_CONTENT
        ),
    }
]


def _make_router(long_context_threshold: int = 16_000) -> ComplexityRouter:
    cfg = TierConfig(
        enabled=True,
        complexity_threshold=3.0,
        long_context_threshold=long_context_threshold,
        models=TierModels(
            simple="cheap-model",
            complex="capable-model",
            long_context="long-model",
        ),
    )
    return ComplexityRouter(cfg)


# ─── Four required routing cases ──────────────────────────────────────────────


def test_short_low_routes_to_simple():
    """Short input + low complexity score → simple tier."""
    router = _make_router()
    model, result = router.route(_SHORT_SIMPLE)
    assert result.tier == "simple", f"expected simple, got {result.tier}"
    assert model == "cheap-model"


def test_short_high_routes_to_complex():
    """Short input + high complexity score → complex tier."""
    router = _make_router()
    model, result = router.route(_SHORT_COMPLEX)
    assert result.tier == "complex", f"expected complex, got {result.tier}"
    assert model == "capable-model"


def test_long_low_routes_to_long_context():
    """Long input + low complexity → long_context tier overrides complexity score."""
    router = _make_router()
    model, result = router.route(_LONG_SIMPLE)
    assert result.tier == "long_context", f"expected long_context, got {result.tier}"
    assert model == "long-model"


def test_long_high_routes_to_long_context():
    """Long input + high complexity → long_context tier still overrides."""
    router = _make_router()
    model, result = router.route(_LONG_COMPLEX)
    assert result.tier == "long_context", f"expected long_context, got {result.tier}"
    assert model == "long-model"


# ─── Supporting checks ────────────────────────────────────────────────────────


def test_long_context_threshold_is_configurable():
    """An extremely high threshold means long content still routes by complexity."""
    router = _make_router(long_context_threshold=999_999)
    _, result = router.route(_LONG_SIMPLE)
    assert result.tier != "long_context"


def test_input_tokens_exposed_on_result():
    """ComplexityResult.input_tokens must be populated for long_context detection."""
    router = _make_router()
    _, result = router.route(_LONG_SIMPLE)
    assert result.input_tokens > 16_000


def test_tier_models_has_long_context_field():
    """TierModels carries long_context str with a sensible default."""
    models = TierModels()
    assert hasattr(models, "long_context")
    assert isinstance(models.long_context, str)
    assert models.long_context  # non-empty default
