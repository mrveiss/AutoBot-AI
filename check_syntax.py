#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Check Python syntax of modified files."""

import py_compile
import sys

files_to_check = [
    "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot_shared/monitoring/metrics/mcp_worker.py",
    "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot_shared/monitoring/metrics/__init__.py",
    "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot_shared/monitoring/prometheus_metrics.py",
    "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot-backend/services/mcp_isolated_runtime.py",
]

all_ok = True
for filepath in files_to_check:
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"✓ {filepath}")
    except py_compile.PyCompileError as e:
        print(f"✗ {filepath}: {e}")
        all_ok = False

if all_ok:
    print("\nAll files have valid Python syntax!")
    sys.exit(0)
else:
    print("\nSome files have syntax errors!")
    sys.exit(1)
