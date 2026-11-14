# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hypothesis helpers for the auto-research loop (pure functions, testable in isolation).

Split out of ``auto_research_agent.py`` (#17576) so that module stays within its file-size ceiling; the
agent imports all three functions, so ``from services.autoresearch.auto_research_agent import ...`` is
unchanged for callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from agent_loop.search.base import SearchResult

if TYPE_CHECKING:
    from .auto_research_agent import ImprovementMetrics

_THEME_KEYWORDS: Dict[str, List[str]] = {
    "attention": ["attention", "transformer", "self-attention", "multi-head"],
    "regularisation": ["dropout", "regularization", "weight decay", "l2"],
    "learning_rate": ["learning rate", "lr schedule", "warmup", "cosine annealing"],
    "architecture": ["layer", "depth", "width", "embedding", "hidden"],
    "data": ["data augmentation", "tokenization", "dataset", "preprocessing"],
    "batch": ["batch size", "gradient accumulation", "micro-batch"],
}

_THEME_TO_HP_ADJUSTMENTS: Dict[str, Dict[str, Any]] = {
    "attention": {"n_head": 8, "n_embd": 512},
    "regularisation": {"dropout": 0.1, "weight_decay": 0.05},
    "learning_rate": {"learning_rate": 1e-4, "warmup_steps": 200},
    "architecture": {"n_layer": 8, "block_size": 512},
    "data": {"batch_size": 128},
    "batch": {"batch_size": 32},
}


def _extract_themes(search_results: List[SearchResult]) -> List[str]:
    """Identify high-level research themes from a list of search results.

    Args:
        search_results: Web search results for the current iteration.

    Returns:
        Deduplicated list of theme names found in titles/summaries.
    """
    found: List[str] = []
    combined_text = " ".join(f"{r.title} {r.snippet}" for r in search_results).lower()
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(kw in combined_text for kw in keywords):
            found.append(theme)
    return found


def _themes_to_hyperparams(themes: List[str], iteration: int) -> Dict[str, Any]:
    """Map detected themes to concrete hyperparameter adjustments.

    Uses modular iteration cycling so successive iterations with the same themes
    still explore a varied parameter space.

    Args:
        themes: Theme names from _extract_themes().
        iteration: Current iteration index (1-based, used for cycling).

    Returns:
        Dict of hyperparameter overrides to apply for the next experiment.
    """
    if not themes:
        # Fallback: cycle through all theme adjustments based on iteration
        all_themes = list(_THEME_TO_HP_ADJUSTMENTS.keys())
        selected_theme = all_themes[(iteration - 1) % len(all_themes)]
        return dict(_THEME_TO_HP_ADJUSTMENTS[selected_theme])

    # Pick the theme that appears earliest (most prominent in search results)
    # and rotate through themes across iterations to avoid repetition
    selected_theme = themes[(iteration - 1) % len(themes)]
    return dict(_THEME_TO_HP_ADJUSTMENTS.get(selected_theme, {}))


def _summarise_prior_results(prior_results: List[ImprovementMetrics]) -> str:
    """Build a short text summary of prior iteration results.

    Args:
        prior_results: List of ImprovementMetrics from previous iterations.

    Returns:
        Human-readable summary string, empty if no prior results.
    """
    if not prior_results:
        return ""
    last = prior_results[-1]
    if last.improved and last.improvement_pct is not None:
        return f"Last iteration improved by {last.improvement_pct:.2f}%."
    return "Last iteration did not improve over baseline."
