# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env var for the chat model's GPU layer count (autobot_shared/chat_model_context.py, #22257)."""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_NUM_GPU",
        type=str,
        default=None,
        description=(
            "Ollama num_gpu (layers on the GPU) sent with every chat-model request. Unset: all layers when "
            "this host has an NVIDIA GPU (nvidia-smi answers), else the option is left out. An integer >= 0 "
            "is sent as is; 'off' or a negative number leaves the option out. Set it when Ollama runs on "
            "another host than the backend (#22257)."
        ),
        component="chat",
    )
)
