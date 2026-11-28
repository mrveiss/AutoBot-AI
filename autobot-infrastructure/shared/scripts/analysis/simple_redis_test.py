#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple Redis hash test
"""

import sys
from pathlib import Path

# Runs from any directory with no PYTHONPATH: the repository root provides `autobot_shared` (#18289).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# #19232: the knowledge database's host, port, credentials and number come from the one
# endpoint resolver and the one name -> number table, not a private chain with literals.
from autobot_shared.redis_client import require_redis_client  # noqa: E402


def simple_redis_test():
    client = require_redis_client(database="knowledge")

    # Get first key directly from FT.SEARCH
    result = client.execute_command("FT.SEARCH", "llama_index", "*", "LIMIT", "0", "1")

    if len(result) > 1:
        key = result[1]  # First document key
        print(f"Testing key: {key}")

        # Get hash data
        hash_data = client.hgetall(key)
        print(f"Hash fields: {list(hash_data.keys())}")

        for field, value in hash_data.items():
            print(f"{field}: {str(value)[:100]}...")


if __name__ == "__main__":
    simple_redis_test()
