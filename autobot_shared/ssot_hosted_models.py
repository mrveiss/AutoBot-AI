# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hosted LLM providers' default models: one table, provider x tier (#15501, #18210).

Every hosted provider used to carry its own default-model literal, two of them stale for
years (OpenRouter ``gpt-3.5-turbo``, Bedrock ``claude-3-5-sonnet``), and five had no config
override at all. This table is now the only place a hosted default is written; the provider
modules ask ``hosted_default_model()``.

Tiers:
- ``default`` -- the model a provider uses when a request names none.
- ``light``   -- a cheap model of the same vendor for routing and classification, so a
  Full Provider run (#15494) need not spend its quality model on them.

Owner decision 2026-10-23 for the two stale defaults: mirror the direct providers -- OpenRouter
takes the OpenAI default in OpenRouter's ``vendor/model`` naming, and Bedrock takes Claude
Sonnet 4 (Bedrock ID ``anthropic.claude-sonnet-4-20250514-v1:0``, supplied by the owner).
The user can still switch to any model at any moment; these are out-of-the-box defaults only.

Lives here rather than in ``ssot_constants.py`` because that file is at its size ceiling; the
model names come from it.

Each provider's ``default`` tier can be overridden by its ``{PROVIDER}_DEFAULT_MODEL``
environment variable (``VERTEX_AI_DEFAULT_MODEL`` for Vertex AI); a blank value is no override.
The process environment wins; otherwise the project ``.env`` is read, as the pydantic fields
these replace did through ``env_file`` -- so a worker or script that never ran ``load_dotenv``
still sees a value set there (#15501 review).
"""

from __future__ import annotations

import os
from functools import lru_cache

from autobot_shared.env_utils import env_raw
from autobot_shared.ssot_constants import (
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_SONNET4_6,
    GOOGLE_GEMINI20_FLASH,
    GOOGLE_GEMINI25_FLASH,
    GROQ_LLAMA31_8B,
    MISTRAL_NEMO,
    MISTRAL_SMALL_LATEST,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT41_NANO,
)

#: OpenRouter names a model ``vendor/model``.
OPENROUTER_OPENAI_GPT4O_MINI = f"openai/{OPENAI_GPT4O_MINI}"
OPENROUTER_OPENAI_GPT41_NANO = f"openai/{OPENAI_GPT41_NANO}"
#: Bedrock's friendly name (a key of ``llm_shared.providers.bedrock.BEDROCK_MODELS``) and its ID.
BEDROCK_CLAUDE_SONNET4 = "claude-sonnet-4"
BEDROCK_CLAUDE_SONNET4_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
HUGGINGFACE_LLAMA32_3B_INSTRUCT = "meta-llama/Llama-3.2-3B-Instruct"
#: Nous's fallback when NOUS_DEFAULT_MODEL is unset (moved from bootstrap.py, #15501 review).
NOUS_HERMES2_MIXTRAL_DPO = "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO"
#: The chat models the HuggingFace provider lists (moved from its module, #15501).
HUGGINGFACE_KNOWN_CHAT_MODELS: tuple[str, ...] = (
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    HUGGINGFACE_LLAMA32_3B_INSTRUCT,
    "mistralai/Mistral-7B-Instruct-v0.3",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "microsoft/Phi-3-mini-4k-instruct",
    "HuggingFaceH4/zephyr-7b-beta",
    "google/gemma-2-9b-it",
)

TIERS: tuple[str, ...] = ("default", "light")

HOSTED_PROVIDER_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "openai": {"default": OPENAI_GPT4O_MINI, "light": OPENAI_GPT41_NANO},
    "anthropic": {"default": ANTHROPIC_CLAUDE_SONNET4_6, "light": ANTHROPIC_CLAUDE_HAIKU4_5},
    "groq": {"default": GROQ_LLAMA31_8B, "light": GROQ_LLAMA31_8B},
    "mistral": {"default": MISTRAL_SMALL_LATEST, "light": MISTRAL_NEMO},
    "vertexai": {"default": GOOGLE_GEMINI25_FLASH, "light": GOOGLE_GEMINI20_FLASH},
    "openrouter": {"default": OPENROUTER_OPENAI_GPT4O_MINI, "light": OPENROUTER_OPENAI_GPT41_NANO},
    # Light = default: Claude Haiku 4.5's Bedrock ID is not verified, and an older Haiku would
    # bring a stale model back by another door.
    "bedrock": {"default": BEDROCK_CLAUDE_SONNET4, "light": BEDROCK_CLAUDE_SONNET4},
    "huggingface": {"default": HUGGINGFACE_LLAMA32_3B_INSTRUCT, "light": HUGGINGFACE_LLAMA32_3B_INSTRUCT},
}

_ENV_OVERRIDE: dict[str, str] = {
    provider: ("VERTEX_AI_DEFAULT_MODEL" if provider == "vertexai" else f"{provider.upper()}_DEFAULT_MODEL")
    for provider in HOSTED_PROVIDER_DEFAULT_MODELS
}


@lru_cache(maxsize=4)
def _dotenv(path: str, mtime: float) -> dict[str, str]:
    """The project .env as a dict, re-read when its mtime changes."""
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def _from_dotenv(name: str) -> str | None:
    from autobot_shared.ssot_config import PROJECT_ROOT

    path = str(PROJECT_ROOT / ".env")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    return (_dotenv(path, mtime).get(name) or "").strip() or None


def hosted_default_model(provider: str, tier: str = "default") -> str:
    """The *tier* model for hosted *provider*; the ``default`` tier honours its env override.

    Raises KeyError for an unknown provider or tier -- a typo must not silently pick a model.
    """
    models = HOSTED_PROVIDER_DEFAULT_MODELS[provider]
    if tier not in TIERS:
        raise KeyError(f"unknown tier {tier!r}; expected one of {TIERS}")
    if tier == "default":
        override = (env_raw(_ENV_OVERRIDE[provider]) or "").strip() or _from_dotenv(_ENV_OVERRIDE[provider])
        if override:
            return override
    return models[tier]
