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

Maintainer decision (2026-10-23) for the two stale defaults: mirror the direct providers -- OpenRouter
takes the OpenAI default in OpenRouter's ``vendor/model`` naming, and Bedrock takes Claude
Sonnet 4 (Bedrock ID ``anthropic.claude-sonnet-4-20250514-v1:0``, supplied by the maintainer).
The user can still switch to any model at any moment; these are out-of-the-box defaults only.

Lives here rather than in ``ssot_constants.py`` because that file is at its size ceiling; the
model names come from it.

Each provider's ``default`` tier can be overridden by its ``{PROVIDER}_DEFAULT_MODEL``
environment variable (``VERTEX_AI_DEFAULT_MODEL`` for Vertex AI); a blank value is no override.
The overrides are read the canonical way, a ``RedactedSettings`` model with the project
``env_file``, like every other SSOT setting: the process environment wins, otherwise the project
``.env`` applies, so a worker or script that never ran ``load_dotenv`` still sees a value set
there (#15501 review).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from autobot_shared import ssot_config
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


def _override_field(env: str):
    return Field(default=None, alias=env)


class _HostedModelOverrides(ssot_config.RedactedSettings):
    """Each provider's ``{PROVIDER}_DEFAULT_MODEL``; ``None`` or blank is no override."""

    model_config = SettingsConfigDict(
        env_file=str(ssot_config.PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    openai: str | None = _override_field("OPENAI_DEFAULT_MODEL")
    anthropic: str | None = _override_field("ANTHROPIC_DEFAULT_MODEL")
    groq: str | None = _override_field("GROQ_DEFAULT_MODEL")
    mistral: str | None = _override_field("MISTRAL_DEFAULT_MODEL")
    vertexai: str | None = _override_field("VERTEX_AI_DEFAULT_MODEL")
    openrouter: str | None = _override_field("OPENROUTER_DEFAULT_MODEL")
    bedrock: str | None = _override_field("BEDROCK_DEFAULT_MODEL")
    huggingface: str | None = _override_field("HUGGINGFACE_DEFAULT_MODEL")


def _override(provider: str) -> str | None:
    """*provider*'s override, read now: the environment, then the project ``.env``."""
    return (getattr(_HostedModelOverrides(), provider) or "").strip() or None


def hosted_default_model(provider: str, tier: str = "default") -> str:
    """The *tier* model for hosted *provider*; the ``default`` tier honours its env override.

    Raises KeyError for an unknown provider or tier -- a typo must not silently pick a model.
    """
    models = HOSTED_PROVIDER_DEFAULT_MODELS[provider]
    if tier not in TIERS:
        raise KeyError(f"unknown tier {tier!r}; expected one of {TIERS}")
    if tier == "default":
        override = _override(provider)
        if override:
            return override
    return models[tier]
