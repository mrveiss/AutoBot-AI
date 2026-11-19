#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Operator-command shim for documentation indexing (#18129).

This path was once a standalone indexer with its own chunking, tagging and
front-matter handling. Documentation indexing has ONE implementation,
``services.knowledge.doc_indexer.DocIndexerService``, reached through
``tools/index_documentation.py``; this shim keeps the documented command and all
of its flags and runs that entry point.
"""

import runpy
from pathlib import Path

_ENTRY_POINT = Path(__file__).resolve().parents[3] / "tools" / "index_documentation.py"

if __name__ == "__main__":
    runpy.run_path(str(_ENTRY_POINT), run_name="__main__")
