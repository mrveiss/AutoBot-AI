# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AUTOBOT_* variables for the AI Stack client timeouts (#22141)."""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AI_STACK_REQUEST_TIMEOUT_SECONDS",
        type=int,
        default=60,
        description="Total timeout, in seconds, for one AI Stack request (services/ai_stack_client.py).",
        component="ai_stack",
        range=(1, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AI_STACK_RETRY_INTERVAL_SECONDS",
        type=int,
        default=60,
        description="Seconds between AI Stack reconnect probes while the stack is unreachable.",
        component="ai_stack",
        range=(1, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AI_STACK_OLLAMA_TAGS_TIMEOUT_SECONDS",
        type=int,
        default=10,
        description="Timeout, in seconds, for the Ollama model listing the AI Stack client uses to list agents.",
        component="ai_stack",
        range=(1, 3600),
    )
)
