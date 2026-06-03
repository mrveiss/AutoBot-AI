#!/usr/bin/env python3
"""
AutoBot Backend Startup Validation (MVA-1633)

Validates critical environment variables before uvicorn starts.
This prevents silent crashes when systemd restarts before .env is written.

Exit codes:
  0 = All critical env vars present
  1 = Missing required env var (logs error)
  2 = .env file not readable
"""

import os
import sys
from pathlib import Path

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


def main():
    env_path = os.environ.get("AUTOBOT_ENV_PATH", ".env")

    readable, err = validate_env_file(env_path)
    if not readable:
        print(f"FATAL: {err}", file=sys.stderr)
        sys.exit(2)

    valid, missing = validate_env_vars()
    if not valid:
        print(
            f"FATAL: Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"✓ Backend startup validation passed ({len(REQUIRED_ENV_VARS)} vars)", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
