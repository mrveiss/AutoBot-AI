#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent model configuration checks.

``test_agent_models_resolve`` asserts the config layer resolves a concrete LLM
model for every agent type — a pure-config check with no external services.

Running this file as a script additionally probes a live Ollama instance and
reports which resolved models are actually pulled; that probe is operator
diagnostics, not an assertion, so it stays out of the test function.
"""

import subprocess  # nosec B404  # fixed argv, no shell, operator diagnostics only
import sys

from autobot_shared.ssot_config import config

# Agent identifiers whose model configuration must resolve.
AGENT_TYPES = (
    "orchestrator",
    "chat",
    "system_commands",
    "rag",
    "knowledge_retrieval",
    "research",
    "default",
)


def resolve_agent_models() -> dict[str, str]:
    """Return {agent_type: model_name} using the canonical config accessor.

    ``config.llm.get_model_for_agent`` reads AUTOBOT_{AGENT}_MODEL and falls back
    to the configured default model. It replaced the long-removed
    ``config.get_task_specific_model``.
    """
    return {agent_type: config.llm.get_model_for_agent(agent_type) for agent_type in AGENT_TYPES}


def test_agent_models_resolve():
    """Every agent type resolves to a non-empty model name."""
    models = resolve_agent_models()

    assert set(models) == set(AGENT_TYPES)
    for agent_type, model in models.items():
        assert isinstance(model, str) and model.strip(), f"{agent_type} resolved to an empty model name"


def _available_ollama_models() -> set[str]:
    """Return model names reported by a local Ollama install (empty when absent)."""
    try:
        result = subprocess.run(  # nosec B603  # fixed argv, shell=False
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    return {line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip()}


def main() -> int:
    """Report configured agent models and whether Ollama has them pulled."""
    print("AutoBot Multi-Agent Model Configuration Test")  # noqa: print
    print("=" * 50)  # noqa: print

    models = resolve_agent_models()
    available = _available_ollama_models()
    if not available:
        print("Could not read the Ollama model list — availability not checked.")  # noqa: print

    missing = []
    for agent_type, model in sorted(models.items()):
        status = "OK " if model in available else "-- "
        print(f"{status} {agent_type:18} -> {model}")  # noqa: print
        if model not in available:
            missing.append(model)

    print("=" * 50)  # noqa: print
    if available and not missing:
        print("All agent models are configured and pulled.")  # noqa: print
        return 0
    print("Models not pulled locally: " + ", ".join(sorted(set(missing))))  # noqa: print
    print("Pull them with: ollama pull <model>")  # noqa: print
    return 1


if __name__ == "__main__":
    sys.exit(main())
