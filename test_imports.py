#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Quick import test for MCP metrics implementation."""

import sys

sys.path.insert(0, "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot-backend")
sys.path.insert(0, "/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4109/autobot_shared")

try:
    from monitoring.metrics.mcp_worker import MCPWorkerMetricsRecorder

    print("✓ MCPWorkerMetricsRecorder imported successfully")
except Exception as e:
    print(f"✗ Failed to import MCPWorkerMetricsRecorder: {e}")
    sys.exit(1)

try:
    from monitoring.prometheus_metrics import get_metrics_manager

    print("✓ get_metrics_manager imported successfully")
except Exception as e:
    print(f"✗ Failed to import get_metrics_manager: {e}")
    sys.exit(1)

try:
    from services.mcp_isolated_runtime import IsolatedBridgeClient

    print("✓ IsolatedBridgeClient imported successfully")
except Exception as e:
    print(f"✗ Failed to import IsolatedBridgeClient: {e}")
    sys.exit(1)

print("\nAll imports successful!")
