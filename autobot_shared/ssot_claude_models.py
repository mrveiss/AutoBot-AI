# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The current Claude model IDs: the one place a pinned Claude ID is written (#20884).

Pinned IDs had spread through runtime code, config, templates, the frontend and the docs, all a
generation stale. Code reads them from here; the YAML/JSON homes that cannot import
(``llm_models.yaml``, ``context_windows.yaml``) carry the same IDs and are held to this module by
``repo_tests/claude_model_id_ssot_20884_test.py``.

The short aliases (``opus`` / ``sonnet`` / ``haiku`` / ``fable``) are what templates, the hire
form and docs name; ``resolve_claude_model`` turns one into the pinned ID at the edge.

Lives beside ``ssot_constants`` rather than in it because that file is at its size ceiling. The
older ``ANTHROPIC_CLAUDE_*`` constants stay there for the models they name (pricing, history).
"""

from __future__ import annotations

import re
from typing import Any

CLAUDE_OPUS = "claude-opus-5-5"
CLAUDE_SONNET = "claude-sonnet-5-5"
CLAUDE_HAIKU = "claude-haiku-5-5"
CLAUDE_FABLE = "claude-fable-5-1"

#: Tier alias -> pinned ID. Order is capability order, highest first.
CLAUDE_TIER_MODELS: dict[str, str] = {
    "fable": CLAUDE_FABLE,
    "opus": CLAUDE_OPUS,
    "sonnet": CLAUDE_SONNET,
    "haiku": CLAUDE_HAIKU,
}

CLAUDE_MODEL_IDS: tuple[str, ...] = tuple(CLAUDE_TIER_MODELS.values())

#: Short chain names that earlier releases keyed fallback chains on (``AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4``
#: and friends) -> the pinned ID that replaces each. An update must not drop an operator's configured chain,
#: so the env loader maps these through ``legacy_claude_model`` and warns. One table, here, and nowhere else.
LEGACY_CLAUDE_KEYS: dict[str, str] = {
    "claude-opus-4": CLAUDE_OPUS,
    "claude-sonnet-4": CLAUDE_SONNET,
    "claude-haiku-4": CLAUDE_HAIKU,
    "claude-opus-4-cross": f"{CLAUDE_OPUS}-cross",
}

#: Every current model has a 1M-token context window.
CLAUDE_CONTEXT_WINDOW = 1_000_000


def resolve_claude_model(value: str | None) -> str | None:
    """The pinned ID for a tier alias; any other value (an ID, ``None``) passes through unchanged."""
    if value is None:
        return None
    return CLAUDE_TIER_MODELS.get(value.strip().lower(), value)


def resolve_claude_models(node: Any) -> Any:
    """*node* (parsed JSON) with every ``model`` tier alias replaced by its pinned ID, recursively.

    Built-in templates name a tier, never a pinned ID, so a model bump is one edit in this module.
    Any other value passes through unchanged.
    """
    if isinstance(node, dict):
        return {
            key: (
                resolve_claude_model(value)
                if key == "model" and isinstance(value, str)
                else resolve_claude_models(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [resolve_claude_models(item) for item in node]
    return node


def legacy_claude_model(value: str) -> str | None:
    """The current ID replacing a legacy short chain name (case-insensitive), or ``None`` if it is not one."""
    return LEGACY_CLAUDE_KEYS.get(value.strip().lower())


#: Families that still take ``budget_tokens``: Claude 3.x and the 4 / 4.0 / 4.1 / 4.5 generations. ``budget_tokens``
#: is rejected with HTTP 400 on every current 5.x model and on Opus 4.7 / 4.8, and deprecated on Opus 4.6 /
#: Sonnet 4.6, so the default is inverted: any other Claude ID (future, dated, cloud-hosted spelling) is adaptive.
_PRE_ADAPTIVE_RE = re.compile(r"^claude-(?:3(?:-\d+)?-(?:opus|sonnet|haiku)|(?:opus|sonnet|haiku)-4(?:-[015])?)$")
_DATE_SUFFIX_RE = re.compile(r"-(?:\d{8}|latest)$")
_BEDROCK_SUFFIX_RE = re.compile(r"-v\d+(?::\d+)?$")


def _normalise_claude_id(model: str) -> str:
    """*model* as a bare family ID: alias resolved; vendor prefix, ``@`` / version and date suffixes dropped."""
    value = (resolve_claude_model(model) or "").strip().lower()
    value = value.split("@", 1)[0]
    value = value.rsplit("/", 1)[-1]  # Vertex / gateway path spellings
    if value.startswith(("anthropic.", "us.anthropic.", "eu.anthropic.", "global.anthropic.")):
        value = value.split("anthropic.", 1)[1]
    value = _BEDROCK_SUFFIX_RE.sub("", value)
    return _DATE_SUFFIX_RE.sub("", value)


def requires_adaptive_thinking(model: str) -> bool:
    """True when *model* must use adaptive thinking instead of a ``budget_tokens`` budget.

    False only for an explicit pre-4.6 family (and its dated or cloud-hosted forms) or a non-Claude ID.
    """
    value = _normalise_claude_id(model)
    if not value.startswith("claude-"):
        return False
    return _PRE_ADAPTIVE_RE.match(value) is None


_LEGACY_ID_RE = re.compile(
    r"^claude-(?:(?P<tier_a>opus|sonnet|haiku)-4(?:-\d)?|3(?:-\d+)?-(?P<tier_b>opus|sonnet|haiku))$"
)


def current_claude_model(value: str | None) -> str | None:
    """The current ID for *value*: a tier alias, a legacy short name, or a pre-5 pinned ID (dated forms too).

    Any other value (a current ID, a non-Claude ID, ``None``) passes through unchanged. Used at the edges that
    validate or compare a stored model ID, so a row written under an earlier generation still means its tier.
    """
    if value is None:
        return None
    resolved = resolve_claude_model(value) or value
    legacy = legacy_claude_model(resolved)
    if legacy is not None:
        return legacy
    match = _LEGACY_ID_RE.match(_normalise_claude_id(resolved))
    if match:
        return CLAUDE_TIER_MODELS[match.group("tier_a") or match.group("tier_b")]
    return resolved
