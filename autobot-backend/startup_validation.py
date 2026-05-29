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

REQUIRED_ENV_VARS = [
    "AUTOBOT_REDIS_URL",
    "AUTOBOT_KNOWLEDGE_BASE_URL",
    "AUTOBOT_EMBEDDING_MODEL",
]

def validate_env_file(env_path: str) -> tuple[bool, str]:
    """Check if .env file is readable."""
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
    """Check if all required env vars are set."""
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing.append(var)
    return len(missing) == 0, missing

def main():
    env_path = os.environ.get("AUTOBOT_ENV_PATH", ".env")

    # Check .env file
    readable, err = validate_env_file(env_path)
    if not readable:
        print(f"FATAL: {err}", file=sys.stderr)
        sys.exit(2)

    # Check required vars
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
