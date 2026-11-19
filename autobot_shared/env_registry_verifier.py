# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars of the pre-action verifier (#21844, #17306).

``VERIFIER_MAX_TOKENS`` and ``VERIFIER_TIMEOUT_S`` keep their original, un-prefixed names: renaming them would
silently drop an operator's existing setting. They are registered under those names so the registry, the generated
docs and the guard see them. Every variable added since carries the ``AUTOBOT_`` prefix.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

_COMPONENT = "verifier"

for _spec in (
    EnvVarSpec(
        name="AUTOBOT_VERIFIER_MODEL",
        type=str,
        default="",  # empty: the light-processing model, resolved by verifier_model.configured_verifier_model
        description=(
            "Ollama tag the pre-action verifier asks (#21844); empty means the light-processing model. "
            "Must be pulled on the Ollama host, else the provider "
            "default answers and a startup warning plus a verifier_model health degradation say so. It loads next to "
            "the chat model, so OLLAMA_MAX_LOADED_MODELS must be at least 2 or each pass pays a model load."
        ),
        component=_COMPONENT,
    ),
    EnvVarSpec(
        name="VERIFIER_MAX_TOKENS",
        type=int,
        default=512,
        description="Token budget of the verifier LLM call (un-prefixed legacy name, kept for existing configs).",
        component=_COMPONENT,
        range=(1, 8192),
    ),
    EnvVarSpec(
        name="VERIFIER_TIMEOUT_S",
        type=float,
        default=10.0,
        description=(
            "Seconds the verifier LLM call may take (un-prefixed legacy name, kept for existing configs); past it "
            "the pass is a 'timeout' degradation (#21844)."
        ),
        component=_COMPONENT,
        range=(0.1, 600.0),
    ),
    EnvVarSpec(
        name="AUTOBOT_VERIFIER_ARG_MAX_CHARS",
        type=int,
        default=2000,
        description="Characters of one tool argument (and of the stated reason) shown to the verifier (#21844).",
        component=_COMPONENT,
        range=(1, 1_000_000),
    ),
    EnvVarSpec(
        name="AUTOBOT_VERIFIER_PROMPT_MAX_CHARS",
        type=int,
        default=8000,
        description=(
            "Characters of the whole user prompt sent to the verifier; arguments are cut to fit (#21844). "
            "A value below the prompt template's own size is raised to it."
        ),
        component=_COMPONENT,
        range=(1024, 1_000_000),
    ),
    EnvVarSpec(
        name="AUTOBOT_VERIFIER_MODEL_CHECK_TTL_SECONDS",
        type=int,
        default=300,
        description="Seconds a verifier-model availability reading is reused before the provider is asked again.",
        component=_COMPONENT,
        range=(10, 86400),
    ),
):
    register_env_var(_spec)
