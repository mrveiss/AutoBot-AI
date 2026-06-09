# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tiered L0-L4 context wake-up stack (#5066, GH#6469).

Replaces unconditional prompt injection (#4811) with a 5-tier context
pipeline that is budget-aware and selectively loaded:

  L0 Identity     (~100 tok, always) — agent role + owner
  L1 EssentialStory (~500-800 tok, always) — compact memory summary
  L2 OnDemand     (~200-500 tok, conditional) — entity/topic lookup
  L3 DeepSearch   (unlimited, conditional) — hybrid KB search + rerank
  L4 GoalAncestry (~150-300 tok, conditional) — goal→project→tenant chain

Feature flag: ``TIERED_CONTEXT_ENABLED=true`` (env var, default false).

Usage::

    from chat_history.layers import TieredContextBuilder
from autobot_shared.logging_manager import get_logger

    ctx = await TieredContextBuilder().build(
        user_message=message,
        model_name=selected_model,
        session_id=session_id,
        memory_graph=self.memory_graph,           # Optional
        knowledge_service=self.knowledge_service, # Optional
        goal_ancestry=self.goal_ancestry,         # Optional list[dict]
    )
"""

import asyncio
import re
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot_config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

TIERED_CONTEXT_ENABLED: bool = bool(_ssot_config.tiered_context_enabled)

# ---------------------------------------------------------------------------
# Retrieval-trigger keywords for L3
# ---------------------------------------------------------------------------

_RETRIEVAL_KEYWORDS = frozenset(
    {
        "find",
        "search",
        "lookup",
        "look up",
        "retrieve",
        "show me",
        "what does the kb say",
        "what does the knowledge base say",
        "what do you know about",
        "tell me about",
        "do you have info on",
        "do you have information on",
    }
)

# Uppercase token pattern for L2 entity candidate extraction
_UPPER_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z]{1,}\b")


# ---------------------------------------------------------------------------
# Layer 0 — Identity (~100 tokens, always loaded)
# ---------------------------------------------------------------------------


class Layer0Identity:
    """Agent role + owner block. Always loaded. Estimated ~100 tokens."""

    async def render(self, context: dict) -> str:  # noqa: ARG002
        """Return a short identity block from config or safe defaults."""
        try:
            from autobot_shared.ssot_config import config as _cfg

            owner = getattr(getattr(_cfg, "owner", None), "name", None) or "mrveiss"
            role = getattr(getattr(_cfg, "agent", None), "role", None) or "AutoBot AI assistant"
        except Exception:
            owner = "mrveiss"
            role = "AutoBot AI assistant"
        return f"## Identity\nRole: {role}\nOwner: {owner}"

    async def token_estimate(self, context: dict) -> int:  # noqa: ARG002
        return 100


# ---------------------------------------------------------------------------
# Layer 1 — Essential Story (~500-800 tokens, always loaded)
# ---------------------------------------------------------------------------


class Layer1EssentialStory:
    """Compact memory summary from EssentialStoryGenerator. Always loaded."""

    async def render(self, context: dict) -> str:
        try:
            from memory.essential_story import EssentialStoryGenerator

            model_name: str | None = context.get("model_name")
            return await EssentialStoryGenerator().generate(model_name)
        except Exception:
            logger.warning("Layer1EssentialStory.render failed", exc_info=True)
            return ""

    async def token_estimate(self, context: dict) -> int:
        """Read budget from context_windows.yaml; fall back to 600."""
        try:
            from pathlib import Path

            import yaml

            yaml_path = Path(__file__).parent.parent / "config" / "context_windows.yaml"
            # #7467: was sync `yaml_path.read_text` blocking the event loop.
            content = await asyncio.to_thread(yaml_path.read_text, encoding="utf-8")
            data = yaml.safe_load(content)
            model_name = context.get("model_name", "default")
            entry = (data.get("models") or {}).get(model_name) or {}
            if "essential_story_tokens" in entry:
                return int(entry["essential_story_tokens"])
        except Exception:
            pass
        return 600


# ---------------------------------------------------------------------------
# Layer 2 — On-Demand entity context (~200-500 tokens, conditional)
# ---------------------------------------------------------------------------


class Layer2OnDemand:
    """Entity/topic context. Loaded when the user message mentions named entities."""

    async def should_load(self, user_message: str) -> bool:
        """Return True when uppercase tokens are present in the message."""
        candidates = _UPPER_TOKEN_RE.findall(user_message)
        return bool(candidates)

    async def render(self, context: dict) -> str:
        """Look up candidate entities in the memory graph and render facts."""
        try:
            user_message: str = context.get("user_message", "")
            memory_graph: Any = context.get("memory_graph")
            if not memory_graph:
                return ""

            candidates = _UPPER_TOKEN_RE.findall(user_message)
            if not candidates:
                return ""

            # De-duplicate while preserving order
            seen: set = set()
            unique: list = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    unique.append(c)

            parts: list[str] = []
            for candidate in unique[:5]:  # cap at 5 lookups
                entities = await memory_graph.search_entities(query=candidate, limit=3)
                for ent in entities:
                    name = ent.get("name", "")
                    description = ent.get("description", "") or ent.get("content", "")
                    if name and description:
                        parts.append(f"- **{name}**: {description}")

            if not parts:
                return ""

            return "## Related Context\n" + "\n".join(parts)
        except Exception:
            logger.warning("Layer2OnDemand.render failed", exc_info=True)
            return ""

    async def token_estimate(self, context: dict) -> int:  # noqa: ARG002
        return 350


# ---------------------------------------------------------------------------
# Layer 3 — Deep Search (unlimited, conditional)
# ---------------------------------------------------------------------------


class Layer3DeepSearch:
    """Hybrid KB search + rerank. Invoked only for explicit retrieval queries."""

    async def should_load(self, user_message: str) -> bool:
        """Return True when message contains retrieval-trigger keywords."""
        lower = user_message.lower()
        return any(kw in lower for kw in _RETRIEVAL_KEYWORDS)

    async def render(self, context: dict) -> str:
        """Delegate to knowledge_service for hybrid retrieval."""
        try:
            knowledge_service: Any = context.get("knowledge_service")
            user_message: str = context.get("user_message", "")
            if not knowledge_service or not user_message:
                return ""

            knowledge_context, citations, _, _ = await knowledge_service.conversation_aware_retrieve(
                query=user_message,
                conversation_history=[],
                top_k=5,
                score_threshold=0.3,
                force_retrieval=True,
            )
            if not knowledge_context:
                return ""

            logger.info("Layer3DeepSearch: retrieved %d citations", len(citations))
            return knowledge_context
        except Exception:
            logger.warning("Layer3DeepSearch.render failed", exc_info=True)
            return ""

    async def token_estimate(self, context: dict) -> int:  # noqa: ARG002
        return 0  # unbounded — tracked by ContextWindowManager


# ---------------------------------------------------------------------------
# Layer 4 — Goal Ancestry (~150-300 tokens, conditional) GH#6469
# ---------------------------------------------------------------------------


class Layer4GoalAncestry:
    """Goal→project→tenant ancestry chain injected as system context (GH#6469).

    Loaded when ``goal_ancestry`` is present in the build context — a list of
    dicts with at minimum ``title`` and ``level`` keys (mirrors LLCGoal fields).
    Callers are responsible for fetching the chain via GoalService.get_goal_ancestry_for_work_item().
    """

    async def should_load(self, goal_ancestry: list | None) -> bool:
        """Return True when a non-empty ancestry chain is available."""
        return bool(goal_ancestry)

    async def render(self, context: dict) -> str:
        """Render a compact ancestry breadcrumb for prompt injection."""
        try:
            goal_ancestry: list | None = context.get("goal_ancestry")
            if not goal_ancestry:
                return ""

            crumbs: list[str] = []
            for node in goal_ancestry:
                level = node.get("level", "goal")
                title = node.get("title", "?")
                crumbs.append(f"{level.capitalize()}: {title}")

            if not crumbs:
                return ""

            chain = " → ".join(crumbs)
            return f"## Goal Ancestry\n{chain}"
        except Exception:
            logger.warning("Layer4GoalAncestry.render failed", exc_info=True)
            return ""

    async def token_estimate(self, context: dict) -> int:  # noqa: ARG002
        return 200  # conservative estimate per ancestry chain


# ---------------------------------------------------------------------------
# Tiered Context Builder
# ---------------------------------------------------------------------------


class TieredContextBuilder:
    """Compose all layers respecting the feature flag and token budget.

    When ``TIERED_CONTEXT_ENABLED`` is False (default) an empty string is
    returned so the caller falls through to the existing unconditional path.
    """

    _L0_L1_MAX_TOKENS: int = 900  # acceptance-criterion guard

    async def build(
        self,
        user_message: str,
        model_name: str,
        session_id: str,  # noqa: ARG002  (reserved for future per-session state)
        memory_graph: Any | None = None,
        knowledge_service: Any | None = None,
        goal_ancestry: list | None = None,
    ) -> str:
        """Build the tiered context string.

        Returns empty string when the feature flag is off so callers can
        fall through to the legacy unconditional injection path.

        Args:
            goal_ancestry: Optional root-first list of goal-like dicts
                           (``title``, ``level``) from GoalService.get_ancestors().
                           When present, L4 GoalAncestry is appended. GH#6469.
        """
        if not TIERED_CONTEXT_ENABLED:
            return ""

        base_ctx: dict = {"model_name": model_name}

        # ------------------------------------------------------------------
        # Always: L0 + L1
        # ------------------------------------------------------------------
        l0 = Layer0Identity()
        l1 = Layer1EssentialStory()

        l0_est = await l0.token_estimate(base_ctx)
        l1_est = await l1.token_estimate(base_ctx)
        total_l0_l1 = l0_est + l1_est
        if total_l0_l1 > self._L0_L1_MAX_TOKENS:
            logger.warning(
                "L0+L1 estimated tokens (%d) exceed budget (%d)",
                total_l0_l1,
                self._L0_L1_MAX_TOKENS,
            )

        l0_text = await l0.render(base_ctx)
        l1_text = await l1.render(base_ctx)

        parts: list[str] = [t for t in [l0_text, l1_text] if t]

        # ------------------------------------------------------------------
        # Conditional: L2 — entity detection
        # ------------------------------------------------------------------
        l2 = Layer2OnDemand()
        if await l2.should_load(user_message):
            l2_ctx: dict = {
                **base_ctx,
                "user_message": user_message,
                "memory_graph": memory_graph,
            }
            l2_text = await l2.render(l2_ctx)
            if l2_text:
                parts.append(l2_text)

        # ------------------------------------------------------------------
        # Conditional: L3 — retrieval-heavy queries
        # ------------------------------------------------------------------
        l3 = Layer3DeepSearch()
        if await l3.should_load(user_message):
            l3_ctx: dict = {
                **base_ctx,
                "user_message": user_message,
                "knowledge_service": knowledge_service,
            }
            l3_text = await l3.render(l3_ctx)
            if l3_text:
                parts.append(l3_text)

        # ------------------------------------------------------------------
        # Conditional: L4 — goal ancestry (GH#6469)
        # ------------------------------------------------------------------
        l4 = Layer4GoalAncestry()
        if await l4.should_load(goal_ancestry):
            l4_ctx: dict = {**base_ctx, "goal_ancestry": goal_ancestry}
            l4_text = await l4.render(l4_ctx)
            if l4_text:
                parts.append(l4_text)

        return "\n\n".join(parts)


__all__ = [
    "TIERED_CONTEXT_ENABLED",
    "Layer0Identity",
    "Layer1EssentialStory",
    "Layer2OnDemand",
    "Layer3DeepSearch",
    "Layer4GoalAncestry",
    "TieredContextBuilder",
]
