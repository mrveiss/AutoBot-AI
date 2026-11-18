#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Fix knowledge base dimension mismatch by recreating with correct settings.

Entry point kept for existing invocations; the implementation lives in
``kb_dimension_utility.py`` (#18964), which reaches Redis through the centralized client.
"""

import sys
from pathlib import Path

# Loadable by file path from any working directory: put this script's own directory on
# the path for the sibling module, as the repo-root bootstrap does for `autobot_shared`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from kb_dimension_utility import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
