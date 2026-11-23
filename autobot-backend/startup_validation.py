#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Backend Startup Validation (MVA-1633)

Validates critical environment variables before uvicorn starts.
This prevents silent crashes when systemd restarts before .env is written.

Exit codes:
  0 = All critical env vars present
  1 = Missing required env var (logs error)
  1 = AUTOBOT_BACKEND_HOST is a bind-all address (#18810)
  2 = .env file not readable
"""

import os
import sys
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_reachable_host import is_unspecified_host

logger = get_logger(__name__)

# Required vars are declared in a manifest written by Ansible alongside .env.
# This keeps the validator in sync with the template without a parallel hardcoded list.
# Fallback list is used when the manifest is absent (dev/bare checkout).
_MANIFEST_PATH = Path(__file__).parent / ".validation_vars"


def _load_required_vars() -> list[str]:
    if _MANIFEST_PATH.exists():
        return [
            line.strip()
            for line in _MANIFEST_PATH.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    # Fallback: vars that Ansible always emits from backend.env.j2 (no | default() guard).
    # Keep this list in sync with backend.env.j2 and the Ansible manifest task.
    return [
        "AUTOBOT_REDIS_URL",  # redis://host:port — composed by Ansible from backend_redis_host/port
        "AUTOBOT_AI_STACK_HOST",  # required Ansible inventory var (backend_ai_stack_host)
        "AUTOBOT_CHROMADB_HOST",  # required Ansible inventory var (backend_chromadb_host)
        "AUTOBOT_DEFAULT_LLM_MODEL",  # required Ansible inventory var (backend_llm_model)
    ]


REQUIRED_ENV_VARS = _load_required_vars()


def validate_env_file(env_path: str) -> tuple[bool, str]:
    try:
        path = Path(env_path)
        if not path.exists():
            return False, f".env file not found: {env_path}"
        if not os.access(env_path, os.R_OK):
            return False, f".env file not readable: {env_path}"
        return True, ""
    except Exception as e:
        return False, f"Error checking .env: {e}"


def validate_env_vars() -> tuple[bool, list[str]]:
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing.append(var)
    return len(missing) == 0, missing


def validate_advertised_host() -> str | None:
    """The failure text when AUTOBOT_BACKEND_HOST is a bind-all address, else None (#18810).

    That variable is the address clients dial; a URL on the bind-all address is refused by the egress
    guard, so every outbound backend call (MCP bridges, VNC status) fails. The listen address
    belongs in AUTOBOT_BACKEND_BIND_HOST.
    """
    host = os.environ.get("AUTOBOT_BACKEND_HOST", "")
    if not is_unspecified_host(host):
        return None
    return (
        f"AUTOBOT_BACKEND_HOST={host} is a bind-all address, not a host clients can dial. "
        "Set it to the backend's reachable address and put the listen address in "
        "AUTOBOT_BACKEND_BIND_HOST (the builtin update re-renders the env from the backend role)."
    )


def main():
    env_path = os.environ.get("AUTOBOT_ENV_PATH", ".env")

    readable, err = validate_env_file(env_path)
    if not readable:
        logger.error("FATAL: %s", err)
        sys.exit(2)

    valid, missing = validate_env_vars()
    if not valid:
        logger.error("FATAL: Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    host_error = validate_advertised_host()
    if host_error:
        logger.error("FATAL: %s", host_error)
        sys.exit(1)

    logger.info("✓ Backend startup validation passed (%d vars)", len(REQUIRED_ENV_VARS))
    sys.exit(0)


if __name__ == "__main__":
    main()
